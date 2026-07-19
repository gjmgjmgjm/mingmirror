#!/usr/bin/env python3
"""BaziQA benchmark evaluator for MingMirror.

Loads the BaziQA dataset (https://github.com/ChenJiangxi/BaziQA), converts each
person's birth datetime into a bazi chart, asks the configured LLM each
multiple-choice question, and reports accuracy.

The evaluator supports two modes:
- ``baseline``: only the bazi string and the question are provided to the LLM.
- ``enhanced``: the prompt is enriched with structural facts, liuqin facts,
  knowledge-base snippets, and similar cases, mirroring the production engine.

Run::

    python tools/bazi_ai/baziqa_eval.py --data benchmarks/baziqa/data --limit 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# When executed as ``python tools/bazi_ai/baziqa_eval.py``, sys.path[0] is
# ``tools/bazi_ai`` which shadows the stdlib ``calendar`` module with
# ``tools.bazi_ai.calendar``. Fix path before any third-party imports.
_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] in ("", _SCRIPT_DIR):
    sys.path[0] = str(_ROOT)
elif str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
# Drop any lingering local package shadow of stdlib calendar.
if "calendar" in sys.modules and not getattr(
    sys.modules["calendar"], "__file__", ""
).endswith(f"{os.sep}calendar.py"):
    pass
elif "calendar" in sys.modules:
    _cal_file = str(getattr(sys.modules["calendar"], "__file__", "") or "")
    if "bazi_ai" in _cal_file or "qizheng" in _cal_file:
        del sys.modules["calendar"]

import yaml

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from control import RateLimiter
from tools.bazi_ai import bazi_structural
from tools.bazi_ai import calendar as bazi_calendar
from tools.bazi_ai.bazi_validator import normalize_bazi
from tools.bazi_ai.engine import retrieve_similar_cases
from tools.bazi_ai.knowledge_retriever import retrieve_knowledge_snippets
from tools.bazi_ai.rule_reasoner import (
    Candidate,
    apply_rule_reasoner,
    arbitrate_shortlist,
    format_domain_hint_block,
    format_shortlist_block,
    prefer_shortlist_after_llm,
    rank_year_candidates,
)

# Alias used throughout this module (was ``calendar``).
calendar = bazi_calendar

_BAZIQA_DATA_URL = "https://github.com/ChenJiangxi/BaziQA/archive/refs/heads/main.zip"

# Track whether we have already warned about Kimi temperature so logs stay clean.
_kimi_temperature_warned: bool = False


def _load_config_extra_cases(config_path: Optional[Path] = None) -> List[Path]:
    """Load ``bazi_ai.extra_cases_paths`` from config.yml (or another YAML path)."""
    config_path = config_path or Path("config.yml")
    if not config_path.exists():
        return []
    try:
        with config_path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        return []
    paths = config.get("bazi_ai", {}).get("extra_cases_paths", [])
    return [Path(p) for p in paths if isinstance(p, str)]


def _ensure_dataset(data_dir: Path) -> None:
    """Download BaziQA dataset if the directory is missing."""
    if data_dir.exists() and any(data_dir.iterdir()):
        return

    import tempfile
    import urllib.request
    import zipfile

    data_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        urllib.request.urlretrieve(_BAZIQA_DATA_URL, tmp.name)
        with zipfile.ZipFile(tmp.name, "r") as zf:
            zf.extractall(data_dir.parent)
        extracted = data_dir.parent / "BaziQA-main"
        if extracted.exists():
            extracted.replace(data_dir)
        os.unlink(tmp.name)


def load_baziqa(data_dir: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load Contest8 and Celebrity50 records from *data_dir*."""
    _ensure_dataset(data_dir)
    contest_records: List[Dict[str, Any]] = []
    celebrity_records: List[Dict[str, Any]] = []

    for path in sorted(data_dir.glob("contest8_*.json")):
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # First element is contest metadata; remaining are persons.
        contest_records.extend(data[1:])

    celeb_path = data_dir / "celebrity50_zh.json"
    if celeb_path.exists():
        with celeb_path.open("r", encoding="utf-8") as f:
            celebrity_records = json.load(f)

    return contest_records, celebrity_records


def person_to_bazi(person: Dict[str, Any]) -> Optional[str]:
    """Convert a BaziQA person profile into a normalized bazi string."""
    birth = person.get("profile", {}).get("birth", {})
    year = birth.get("year")
    month = birth.get("month")
    day = birth.get("day")
    hour = birth.get("hour", 0)
    minute = birth.get("minute", 0)
    if not all(isinstance(v, int) for v in (year, month, day)):
        return None
    dt = datetime(year, month, day, hour, minute)
    pillars = calendar.pillars_for_datetime(dt)
    bazi = f"{pillars['year']} {pillars['month']} {pillars['day']} {pillars['hour']}"
    normalized = normalize_bazi(bazi)
    return normalized if normalized else bazi


def _format_options(options: List[str]) -> str:
    labels = [chr(ord("A") + i) for i in range(len(options))]
    return "\n".join(f"{labels[i]}. {opt}" for i, opt in enumerate(options))


def _strip_model_thinking(text: str) -> str:
    """Remove MiniMax/M-series ``<think>…</think>`` blocks; keep final answer text."""
    if not text:
        return ""
    # Prefer content *after* the last closed think block.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    # Unclosed think dump: drop everything from the open tag.
    text = re.sub(r"<think>[\s\S]*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _extract_answer(text: str, max_label: str = "E") -> Optional[str]:
    """Extract the answer letter from *text*.

    The prompt asks models to end with ``答案：X``; try that first. If the model
    does not follow the format, fall back to the first isolated option letter.
    """
    if not text:
        return None
    cleaned = _strip_model_thinking(text)
    # Search cleaned first, then full text (some models put 答案 inside think).
    for blob in (cleaned, text):
        if not blob:
            continue
        text_upper = blob.upper()
        label_range = f"[A-{max_label}]"
        explicit = re.search(rf"(?:答案|ANSWER)[:：]\s*({label_range})", text_upper)
        if explicit:
            return explicit.group(1)
        # Prefer last explicit 答案 if multiple
        all_ans = re.findall(rf"(?:答案|ANSWER)[:：]\s*({label_range})", text_upper)
        if all_ans:
            return all_ans[-1]
    text_upper = (cleaned or text).upper()
    label_range = f"[A-{max_label}]"
    match = re.search(rf"\b({label_range})\b", text_upper)
    if match:
        return match.group(1)
    return None


def _ensemble_vote(raw_answers: List[str], max_label: str = "E") -> Tuple[str, Dict[str, int]]:
    """Return the most common answer raw text and per-letter vote counts."""
    if not raw_answers:
        return "", {}
    if len(raw_answers) == 1:
        return raw_answers[0], {}
    answers: List[Tuple[str, str]] = []
    for raw in raw_answers:
        letter = _extract_answer(raw, max_label=max_label) or ""
        answers.append((raw, letter))
    counts = Counter(letter for _, letter in answers if letter)
    if not counts:
        return raw_answers[0], {}
    best_count = counts.most_common(1)[0][1]
    tied = {letter for letter, c in counts.items() if c == best_count}
    winner = counts.most_common(1)[0][0]
    # Tie-break by first run whose letter is among the tied leaders.
    for raw, letter in answers:
        if letter in tied:
            winner = letter
            for r, ans_letter in answers:
                if ans_letter == winner:
                    return r, dict(counts)
    return raw_answers[0], dict(counts)


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 3000,
    timeout_seconds: float = 60.0,
) -> str:
    """Lightweight LLM call returning raw text."""
    key = (
        api_key
        or os.environ.get("MINIMAX_API_KEY")
        or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )
    if not key:
        raise RuntimeError("No API key configured for BaziQA evaluation")
    if aiohttp is None:  # pragma: no cover
        raise ImportError("aiohttp is required for LLM calls")

    base = (
        base_url
        or os.environ.get("MINIMAX_BASE_URL")
        or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")
    mdl = (
        model
        or os.environ.get("MINIMAX_MODEL")
        or os.environ.get("DOUYIN_BAZI_AI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "deepseek-chat"
    )

    # Kimi API only accepts temperature=1 for some models.
    effective_temperature = temperature
    global _kimi_temperature_warned
    if "kimi" in mdl.lower() and temperature != 1.0:
        effective_temperature = 1.0
        if not _kimi_temperature_warned:
            _kimi_temperature_warned = True
            print(
                f"Warning: Kimi model '{mdl}' requires temperature=1.0; overriding {temperature} -> 1.0",
                file=sys.stderr,
            )

    # MiniMax M-series spends many tokens on internal thinking; budget extra.
    mdl_l = mdl.lower()
    effective_max_tokens = max_tokens
    if any(x in mdl_l for x in ("minimax-m", "m2.", "m3")) and max_tokens < 2500:
        effective_max_tokens = 3000

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": effective_temperature,
        "max_tokens": effective_max_tokens,
    }

    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            f"{base}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            # Prefer final content; append reasoning only if content empty.
            if content.strip():
                return content
            return reasoning or content


_DOMAIN_KEYWORDS = {
    "career": ["职业", "工作", "事业", "升职", "创业", "公司", "职位", "跳槽", "从事", "行业"],
    "wealth": ["财", "富", "穷", "钱", "收入", "资产", "投资", "买房", "置业", "贫富"],
    "health": ["病", "疾", "健康", "手术", "医院", "身体", "受伤", "骨折", "困扰"],
    "marriage": ["结婚", "离婚", "婚姻", "配偶", "妻子", "丈夫", "感情", "桃花", "恋爱"],
    "kinship": ["父", "母", "子", "女", "兄弟", "姐妹", "六亲", "家庭"],
    "education": ["学历", "读书", "学业", "毕业", "学校", "大学", "文凭"],
}


_DOMAIN_LABELS = {
    "career": "事业/职业",
    "wealth": "财运",
    "health": "健康",
    "marriage": "婚姻/感情",
    "kinship": "六亲/家庭",
    "education": "学业/学历",
    "general": "综合",
}


_DOMAIN_FOCUS = {
    "career": (
        "本题问事业/职业。严格按十神组合映射选项，勿空猜："
        "①官杀+印→公职/机构/稳定岗；②食伤+财→技艺/创业/商贸；"
        "③食伤泄秀且官弱/无→技术/自由/文艺（禁止硬套公职）；"
        "④比劫夺财→合伙/销售奔波；⑤有官无印→压力管理岗非清闲编制。"
        "若上方有「选项措辞」升降权提示，优先对照，再结合大运是否引动官杀或食伤。"
    ),
    "wealth": (
        "本题问财运。身旺有财→能任财（小康至富）；身弱财重→难稳任、易起伏；"
        "财库被冲开看横财/破财节点。结合大运对财星的生克。"
    ),
    "health": (
        "本题问健康。先看五行偏枯（最旺/最弱对应脏腑），再看冲克刑害是否落在该宫，"
        "大运流年是否加重失衡。忌神对应系统优先。"
    ),
    "marriage": (
        "本题问婚姻/感情。按序取象："
        "①夫妻宫（日支）逢冲刑害→波折/离异/多段关系权重大；"
        "②配偶星（男正财/女正官杀）弱或不现→晚婚、助力弱、勿选「美满一世」；"
        "③星有力且宫位稳→才支持稳定婚配；"
        "④女命伤官见官、男命比劫夺财→感情是非加重。"
        "把选项措辞（未婚/离异/再婚/稳定）映射到上述结构，勿空猜。"
    ),
    "kinship": (
        "本题问六亲/家庭。按星宫取象："
        "①偏财看父、正印/偏印看母、官杀(男)/食伤(女)看子女；"
        "②星透干有根→该亲缘有力可依；虚浮/坏根/不现→疏离、辛苦或助力薄；"
        "③父母宫在月支、子女宫在时支，逢冲克则关系波折。"
        "对照选项中「和睦/疏离/早年辛苦/经济支持」等措辞。"
    ),
    "education": (
        "本题问学业/学历。印星主文星：印透有根且身不太弱→学历偏高；"
        "印被合坏/食伤过旺无印→偏技艺或中等学历。结合早年大运是否助印。"
    ),
    "general": "本题是综合问题，请结合命局整体信息判断。",
}


def _detect_domain(question_text: str) -> str:
    """Map a question to one of the benchmark domains."""
    scores = {domain: 0 for domain in _DOMAIN_KEYWORDS}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in question_text:
                scores[domain] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _person_key_from_qid(qid: str) -> str:
    """Strip trailing ``-Q\\d+`` so P026-Q6 and P026-Q7 share person key ``P026``."""
    if not qid:
        return ""
    return re.sub(r"-Q\d+$", "", qid)


def _structural_case_match(query_bazi: str, case_bazi: str) -> bool:
    """True if cases share day-master or month-branch (transfer-worthy peers)."""
    qp = (query_bazi or "").split()
    cp = (case_bazi or "").split()
    if len(qp) != 4 or len(cp) != 4:
        return False
    try:
        return qp[2][0] == cp[2][0] or qp[1][1] == cp[1][1]
    except IndexError:
        return False


def _extract_years(text: str) -> List[int]:
    """Return 4-digit years mentioned in *text*.

    Uses digit lookarounds (not ``\\b``) so Chinese suffixes like ``2010年``
    still match — CJK characters are word chars under Python 3 Unicode ``\\b``.
    """
    years = [int(y) for y in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text)]
    return sorted(set(years))


def _relevant_dayun(dayun_list: List[Dict], ages: List[int]) -> List[Dict]:
    """Return the dayun step covering each age plus one step before/after."""
    if not ages:
        return dayun_list[:3]
    selected = []
    seen = set()
    for age in ages:
        for idx, d in enumerate(dayun_list):
            if d.get("start_age", 0) <= age < d.get("end_age", 0):
                for offset in (-1, 0, 1):
                    j = idx + offset
                    if 0 <= j < len(dayun_list) and j not in seen:
                        seen.add(j)
                        selected.append(dayun_list[j])
                break
    selected.sort(key=lambda d: d.get("start_age", 0))
    return selected if selected else dayun_list[:3]


def _format_dayun(dayun_list: List[Dict]) -> str:
    if not dayun_list:
        return "（无大运信息）"
    lines = []
    for d in dayun_list:
        start = int(d.get("start_age", 0))
        end = int(d.get("end_age", 0))
        lines.append(f"{start}-{end}岁：{d.get('pillar', '')}")
    return "\n".join(lines)


def _format_liunian(liunian_list: List[Dict]) -> str:
    if not liunian_list:
        return "（无流年信息）"
    return "、".join(f"{d['year']}年{d['pillar']}" for d in liunian_list)


def _build_baseline_prompt(bazi: str, question: str, options: List[str]) -> str:
    labels = [chr(ord("A") + i) for i in range(len(options))]
    label_list = "/".join(labels)
    return f"""请根据以下八字命局回答选择题。

八字：{bazi}

问题：{question}

{_format_options(options)}

请先结合八字命局简要说明推理依据（50字以内），然后给出答案。
要求：
1. 所有内容必须用中文输出，禁止出现英文。
2. 严格按以下格式输出，不要添加任何额外解释、标题或思考过程。
3. 不要输出 "thinking process"、"Analyze User Input"、"Task" 等英文分析框架。

输出格式：
推理：<依据>
答案：<{label_list}>

示例：
推理：日主身弱喜印比，财星旺而难担，故以正财工资为主。
答案：A"""


# When non-empty, this full text REPLACES the 2K-char RAG knowledge snippet —
# for long-context models (DeepSeek/Qwen) we want the entire 盲派 rulebook in
# context instead of a truncated embedding-retrieved slice. Set via the
# ``--inject-knowledge`` CLI flag (see main()).
_FULL_KNOWLEDGE_TEXT: str = ""


def set_full_knowledge(paths: List[str], max_chars: int = 60000) -> None:
    """Load *paths* in full (concatenated, truncated to *max_chars*) for injection."""
    global _FULL_KNOWLEDGE_TEXT
    parts = []
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            print(f"warning: inject-knowledge path missing: {p}", file=sys.stderr)
            continue
        parts.append(p.read_text(encoding="utf-8"))
    text = "\n\n".join(parts)
    _FULL_KNOWLEDGE_TEXT = text[:max_chars]
    print(
        f"inject-knowledge: {len(paths)} file(s), {len(_FULL_KNOWLEDGE_TEXT)} chars "
        f"(~{len(_FULL_KNOWLEDGE_TEXT)//1500}K tokens) will replace RAG snippet",
        file=sys.stderr,
    )


async def _build_enhanced_context(
    bazi: str,
    question: str,
    *,
    gender: str,
    birth_date: str,
    birth_time: str,
    cases_path: Optional[Path] = None,
    knowledge_base_path: Optional[Path] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    extra_cases_paths: Optional[List[Path]] = None,
    exclude_case_matcher: Optional[Callable[[Dict], bool]] = None,
    domain: str = "general",
    top_k: int = 2,
) -> str:
    """Build the same enrichment used by the production engine."""
    domain_boost: Optional[List[str]] = None
    if domain and domain != "general":
        domain_boost = [domain]
        # Keep top_k=2 — n30 showed top_k=3 celebrity MCQ cases added noise.

    similar_cases = await retrieve_similar_cases(
        bazi,
        question,
        cases_path or Path("./bazi_knowledge/cases.jsonl"),
        top_k=max(top_k * 3, 6),  # over-fetch then filter by structure
        embedding_cache_path=embedding_cache_path,
        extra_cases_paths=extra_cases_paths,
        exclude_case_matcher=exclude_case_matcher,
        domain_boost=domain_boost,
    )
    # Keep only structurally related cases (same day-master or month-branch).
    # Unrelated celebrity career stories hurt more than they help (n50 LOO:
    # unfiltered RAG 32% vs shortlist-only 38%).
    similar_cases = [
        c
        for c in similar_cases
        if _structural_case_match(bazi, c.get("bazi") or "")
    ][:top_k]

    # Long-context path: inject the full knowledge corpus if configured;
    # otherwise fall back to embedding-RAG over a short snippet.
    if _FULL_KNOWLEDGE_TEXT:
        knowledge_context = _FULL_KNOWLEDGE_TEXT
    else:
        knowledge_paths = [Path("./bazi_knowledge/rule_primer.md")]
        if knowledge_base_path is not None and knowledge_base_path.exists():
            knowledge_paths.append(knowledge_base_path)
        knowledge_context = await retrieve_knowledge_snippets(
            query=f"{bazi}\n{question}".strip(),
            knowledge_paths=knowledge_paths,
            cache_path=knowledge_embedding_cache_path,
            top_k=3,
            max_chars=2000,
        )

    structural_facts = bazi_structural.structural_profile(bazi) or {}
    liuqin_facts = bazi_structural.liuqin_profile(bazi, gender=gender) or {}

    # Show transferable structure, NOT gold option letters — reverse-engineered
    # BaziQA cases that print "正确答案：C" caused the model to copy irrelevant
    # celebrity answers (n30 LOO 50%→40% regression).
    def _format_case(i: int, c: Dict) -> str:
        domains = list((c.get("domains") or {}).keys())
        conclusions = c.get("conclusions") or []
        # Prefer reasoning skeleton (usually 2nd conclusion) over "答案：C. ..."
        reason_bits = [
            str(x)
            for x in conclusions
            if "答案：" not in str(x) and "正确答案" not in str(x)
        ]
        concl = "；".join(reason_bits[:2]) if reason_bits else ""
        if not concl and conclusions:
            # Fall back: strip answer-letter patterns from first conclusion.
            raw = str(conclusions[0])
            raw = re.sub(r"答案[:：]\s*[A-E]\.?\s*", "要点：", raw)
            raw = re.sub(r"正确答案[:：]\s*[A-E]\.?\s*", "", raw)
            concl = raw[:120]
        analysis = c.get("analysis_corrected") or ""
        # Keep structural blurb / 推理要点 lines only.
        keep_lines = []
        for line in analysis.splitlines():
            if any(
                k in line
                for k in ("结构：", "推理要点", "领域：", "八字：", "旺衰", "用神")
            ):
                keep_lines.append(line)
            if "推理要点" in line:
                break
        analysis_short = "\n".join(keep_lines)[:280] if keep_lines else analysis[:160]
        analysis_short = re.sub(r"正确答案[:：].*", "", analysis_short)
        parts = [
            f"案例 {i+1}：",
            f"八字：{c.get('bazi')}",
            f"领域：{domains}",
        ]
        if concl:
            parts.append(f"可迁移要点：{concl[:140]}")
        if analysis_short.strip():
            parts.append(analysis_short.strip())
        return "\n".join(parts)

    cases_text = "\n\n".join(_format_case(i, c) for i, c in enumerate(similar_cases))
    if not similar_cases:
        cases_text = "（无高度相似案例）"
    else:
        cases_text += (
            "\n\n（注意：参考案例仅供结构与取象类比，其具体选项字母与命主人生细节不可照搬。）"
        )

    # Compute DaYun / Liunian to ground time-sensitive questions.
    dayun_text = "（无大运信息）"
    liunian_text = "（无流年信息）"
    birth_year = 0
    years: List[int] = []
    if birth_date:
        try:
            birth_year = int(str(birth_date).split("-")[0])
        except ValueError:
            birth_year = 0

    if question:
        years = _extract_years(question)

    if birth_year and bazi:
        try:
            dayun_list = calendar.dayun_list(
                bazi,
                gender,
                birth_date,
                birth_time,
                calendar_type="solar",
                until_age=80,
            )
            ages = [y - birth_year for y in years]
            relevant_dayun = _relevant_dayun(dayun_list, ages)
            dayun_text = _format_dayun(relevant_dayun)
        except Exception:
            dayun_text = "（大运计算失败）"

        if years:
            try:
                start = min(years) - 1
                end = max(years) + 1
                liunian_data = calendar.liunian_list(start, end)
                liunian_text = _format_liunian(liunian_data)
            except Exception:
                liunian_text = "（流年计算失败）"

    yongshen_block = structural_facts.get("yongshen_block") or ""
    if not yongshen_block:
        # Fallback one-liner if structural profile is older/partial.
        yongshen_block = (
            f"【用神/忌神】旺衰：{structural_facts.get('strength', '')}；"
            f"用神：{structural_facts.get('useful_gods', '')}；"
            f"忌神：{structural_facts.get('taboo_gods', '')}"
        )

    return f"""【命局结构事实】
- 日主：{structural_facts.get('day_master', '')}
- 月令：{structural_facts.get('month_branch', '')}
- 天干十神：{structural_facts.get('stem_shishen', {})}
- 地支十神（本气）：{structural_facts.get('branch_shishen', {})}
- 参考旺衰：{structural_facts.get('strength', '')}
- 参考用神：{structural_facts.get('useful_gods', '')}
- 参考忌神：{structural_facts.get('taboo_gods', '')}
- 用神主法：{structural_facts.get('yongshen_primary', '')}
- 地支综合关系：{structural_facts.get('di_zhi_comprehensive_text', '无')}

{yongshen_block}

【六亲星宫事实】
{json.dumps(liuqin_facts, ensure_ascii=False, indent=2)}

【大运走势】
{dayun_text}

【相关流年】
{liunian_text}

【相关知识片段】
{knowledge_context}

【参考案例】
{cases_text}
"""


async def _build_enhanced_prompt(
    bazi: str,
    question: str,
    options: List[str],
    context: str,
    domain: str = "general",
    shortlist_block: str = "",
) -> str:
    domain_focus = _DOMAIN_FOCUS.get(domain, _DOMAIN_FOCUS["general"])
    domain_label = _DOMAIN_LABELS.get(domain, "综合")
    labels = [chr(ord("A") + i) for i in range(len(options))]
    label_list = "/".join(labels)
    label_text = "、".join(labels)
    shortlist_section = f"\n{shortlist_block}\n" if shortlist_block else ""
    return f"""你是一位资深命理师。请根据以下命局信息回答选择题。

八字：{bazi}

{context}

问题：{question}

{_format_options(options)}
{shortlist_section}
【领域判断要求】
{domain_label}题：{domain_focus}

如果题目涉及具体年份或大运，请结合上面列出的大运、流年干支与十神作用进行判断，
不要只凭原局旺衰直接猜。若上方给出了 shortlist：
- 应期 shortlist：对照十神/宫位信号与大运流年；近并列时必须逐项对比，勿默认第一名。
- 结构取象 shortlist：先按命局十神组合（官印/食伤财等）对选项归类，再选最贴者。

请先结合命局、大运、流年信息给出简要推理（100字以内），然后从选项中选择最可能的一个。
要求：
1. 所有分析、推理和结论必须用中文输出，禁止出现英文。
2. 严格按以下格式输出，不要添加任何额外解释、标题或思考过程。
3. 答案只能是 {label_text} 中的一个字母。

输出格式：
推理：<你的推理>
答案：<{label_list}>

示例：
推理：日主庚金身弱，财星卯木当令且三合火局，官杀过旺。早运火土助官杀，感情多波折；中年后辰运土金渐旺，方能稳定。故为晚婚且育有双胞胎之象。
答案：B"""


async def evaluate_question(
    bazi: str,
    question: Dict[str, Any],
    *,
    mode: str = "enhanced",
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    cases_path: Optional[Path] = None,
    knowledge_base_path: Optional[Path] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    mock_answer: Optional[str] = None,
    timeout_seconds: float = 60.0,
    extra_cases_paths: Optional[List[Path]] = None,
    leave_one_out: bool = False,
    exclude_case_matcher: Optional[Callable[[Dict], bool]] = None,
    temperature: float = 0.0,
    max_tokens: int = 3000,
    ensemble_runs: int = 1,
    rate_limiter: Optional[RateLimiter] = None,
    use_rule_reasoner: bool = True,
    rule_min_confidence: str = "low",
    use_rule_shortlist: bool = True,
    rule_shortlist_k: int = 2,
    shortlist_mode: str = "soft",
    use_domain_hints: bool = False,
) -> Dict[str, Any]:
    """Evaluate a single BaziQA question and return prediction + metadata.

    If *use_rule_reasoner* is True and the symbolic reasoner returns a candidate
    with at least *rule_min_confidence* confidence, that answer is used directly
    and the LLM call is skipped.

    When confidence is below the threshold (or no hard hit), *use_rule_shortlist*
    injects the engine's top-*k* year candidates into the enhanced prompt so the
    LLM chooses among a narrowed set — Phase 4 shortlist path.

    *shortlist_mode*:
    - ``soft``: single LLM call with shortlist in the prompt (default, 1x cost).
    - ``arbiter``: free pass + guided pass, then ``arbitrate_shortlist`` (2x cost
      when shortlist fires; recovers cases where soft shortlist pulls the model
      off a correct free answer).
    - ``off``: never inject shortlist (same as ``use_rule_shortlist=False``).

    *use_domain_hints*: inject non-year structural 取象 hints.  Default **False**
    after n30 LOO showed domain hints regressed 50%→43% vs year-shortlist-only.
    Domain *focus* text in the prompt is always on; this flag only adds the
    extra ``format_domain_hint_block`` section.
    """
    qid = question.get("question_id", "")
    qtext = question.get("question", "")
    options = question.get("options", [])
    answer = question.get("answer", "")

    # Compose an exclusion matcher for leave-one-out / cross-domain benchmarks.
    matchers: List[Callable[[Dict], bool]] = []
    if exclude_case_matcher:
        matchers.append(exclude_case_matcher)
    if leave_one_out and qid:
        # Person-level LOO: exclude ALL questions from the same person, not just
        # the current qid.  Same-bazi siblings (P026-Q7 marriage when asking
        # P026-Q6 career) previously dominated retrieval via bazi-exact +100.
        person_key = _person_key_from_qid(qid)

        def _loo_exclude(case: Dict, person_key: str = person_key, qid: str = qid) -> bool:
            src = case.get("source_video") or ""
            if src == qid:
                return True
            if person_key and _person_key_from_qid(src) == person_key:
                return True
            return False

        matchers.append(_loo_exclude)

    def _exclude_matcher(case: Dict) -> bool:
        return any(m(case) for m in matchers)

    final_exclude_matcher: Optional[Callable[[Dict], bool]] = _exclude_matcher if matchers else None

    domain = _detect_domain(qtext)

    if shortlist_mode == "off":
        use_rule_shortlist = False

    # Soft shortlist for year events; domain questions get structural hints only
    # (no option-letter ranking — offline domain top-2 ~55% is too weak).
    shortlist_block = ""
    shortlist_meta: List[Dict[str, Any]] = []
    shortlist_objs: List[Candidate] = []
    domain_hint_block = ""
    if use_rule_reasoner and use_rule_shortlist and mode == "enhanced":
        shortlist_objs = rank_year_candidates(
            bazi,
            qtext,
            options,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time,
            top_k=rule_shortlist_k,
        )
        if shortlist_objs:
            shortlist_block = format_shortlist_block(
                shortlist_objs, top_k=rule_shortlist_k, kind="year"
            )
            shortlist_meta = [
                {
                    "option": c.option,
                    "text": c.text,
                    "score": c.score,
                    "confidence": c.confidence,
                    "reasons": c.reasons,
                    "kind": "year",
                }
                for c in shortlist_objs
            ]
        else:
            # Always-on: marriage/kinship + career/education structural hints.
            # Wealth/health still gated by --domain-hints (noisier slice).
            domain_hint_block = format_domain_hint_block(
                bazi,
                qtext,
                gender=gender,
                include_career_wealth=use_domain_hints,
                options=options,
            )
            if domain_hint_block:
                shortlist_block = domain_hint_block

    async def _single_run(*, with_shortlist: bool = True) -> str:
        system_prompt = (
            "你是一位精通中国传统八字命理的命理师。"
            "所有回答必须使用中文，严禁出现英文。"
            "不要输出思考过程、分析步骤或任何元评论，只输出最终要求的格式。"
        )
        if mode == "baseline":
            user_prompt = _build_baseline_prompt(bazi, qtext, options)
            return await _call_llm(
                system_prompt,
                user_prompt,
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )
        context = await _build_enhanced_context(
            bazi,
            qtext,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time,
            cases_path=cases_path,
            knowledge_base_path=knowledge_base_path,
            embedding_cache_path=embedding_cache_path,
            knowledge_embedding_cache_path=knowledge_embedding_cache_path,
            extra_cases_paths=extra_cases_paths,
            exclude_case_matcher=final_exclude_matcher,
            domain=domain,
        )
        block = shortlist_block if with_shortlist else ""
        user_prompt = await _build_enhanced_prompt(
            bazi,
            qtext,
            options,
            context,
            domain=domain,
            shortlist_block=block,
        )
        return await _call_llm(
            system_prompt,
            user_prompt,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )

    raw = ""
    error = None
    ensemble_raws: List[str] = []
    vote_counts: Dict[str, int] = {}
    rule_based = False
    arbiter_meta: Optional[Dict[str, Any]] = None
    try:
        if mock_answer is not None:
            raw = mock_answer
        else:
            # Try fast symbolic rules first (hard override only at high confidence).
            if use_rule_reasoner:
                rule_answer = apply_rule_reasoner(
                    bazi,
                    qtext,
                    options,
                    gender=gender,
                    birth_date=birth_date,
                    birth_time=birth_time,
                    min_confidence=rule_min_confidence,
                )
                if rule_answer:
                    raw = f"推理：规则引擎命中{rule_answer}选项。\n答案：{rule_answer}"
                    rule_based = True
            if not rule_based:
                max_label = chr(ord("A") + len(options) - 1) if options else "E"
                # Two-pass arbiter: free + guided, only when shortlist fires.
                if (
                    shortlist_mode == "arbiter"
                    and shortlist_objs
                    and mode == "enhanced"
                ):
                    if rate_limiter is not None:
                        await rate_limiter.acquire()
                    free_raw = await _single_run(with_shortlist=False)
                    if rate_limiter is not None:
                        await rate_limiter.acquire()
                    guided_raw = await _single_run(with_shortlist=True)
                    free_pred = _extract_answer(free_raw, max_label=max_label) or ""
                    guided_pred = _extract_answer(guided_raw, max_label=max_label) or ""
                    chosen, reason = arbitrate_shortlist(
                        free_pred, guided_pred, shortlist_objs
                    )
                    raw = guided_raw if reason.startswith("guided") else free_raw
                    # Ensure predicted letter is the arbitrated one even if raw differs.
                    if chosen and _extract_answer(raw, max_label=max_label) != chosen:
                        raw = f"推理：仲裁选择{chosen}（{reason}）。\n答案：{chosen}"
                    arbiter_meta = {
                        "free_pred": free_pred,
                        "guided_pred": guided_pred,
                        "chosen": chosen,
                        "reason": reason,
                    }
                    ensemble_raws = [free_raw, guided_raw]
                else:
                    runs = max(1, ensemble_runs)
                    for _ in range(runs):
                        if rate_limiter is not None:
                            await rate_limiter.acquire()
                        ensemble_raws.append(
                            await _single_run(with_shortlist=bool(shortlist_block))
                        )
                    raw, vote_counts = _ensemble_vote(ensemble_raws, max_label=max_label)
                    # One empty-answer retry (model sometimes returns prose without 答案：X).
                    max_label_try = chr(ord("A") + len(options) - 1) if options else "E"
                    if not _extract_answer(raw, max_label=max_label_try) and runs == 1:
                        if rate_limiter is not None:
                            await rate_limiter.acquire()
                        retry_raw = await _single_run(with_shortlist=bool(shortlist_block))
                        ensemble_raws.append(retry_raw)
                        if _extract_answer(retry_raw, max_label=max_label_try):
                            raw = retry_raw
    except Exception as exc:  # pragma: no cover - safety net for live API
        error = f"{type(exc).__name__}: {exc}"

    max_label = chr(ord("A") + len(options) - 1) if options else "E"
    predicted = _extract_answer(raw, max_label=max_label) or ""
    if arbiter_meta and arbiter_meta.get("chosen"):
        predicted = arbiter_meta["chosen"]
    # Soft shortlist post-process: when symbolic top-1 is strong and the model
    # wandered, prefer the shortlist (zero extra API cost).
    shortlist_override_meta: Optional[Dict[str, Any]] = None
    if shortlist_objs and not rule_based and shortlist_mode != "off":
        override, ov_reason = prefer_shortlist_after_llm(predicted, shortlist_objs)
        if override and override != predicted:
            shortlist_override_meta = {
                "from": predicted,
                "to": override,
                "reason": ov_reason,
            }
            predicted = override
            raw = (
                f"推理：shortlist后处理覆盖（{ov_reason}，原模型{shortlist_override_meta['from']}）。\n"
                f"答案：{override}"
            )
    result: Dict[str, Any] = {
        "question_id": qid,
        "question": qtext,
        "bazi": bazi,
        "answer": answer,
        "predicted": predicted,
        "correct": predicted == answer,
        "raw": raw,
        "mode": mode,
    }
    if error:
        result["error"] = error
    if rule_based:
        result["rule_based"] = True
    if shortlist_meta:
        result["rule_shortlist"] = shortlist_meta
    if shortlist_override_meta:
        result["shortlist_override"] = shortlist_override_meta
    if arbiter_meta:
        result["shortlist_arbiter"] = arbiter_meta
    if ensemble_raws:
        result["ensemble_raws"] = ensemble_raws
        result["ensemble_vote_counts"] = vote_counts
    return result


def _birth_date_time(person: Dict[str, Any]) -> Tuple[str, str]:
    birth = person.get("profile", {}).get("birth", {})
    date_parts = [
        str(birth.get("year", "")),
        str(birth.get("month", "")).zfill(2),
        str(birth.get("day", "")).zfill(2),
    ]
    birth_date = "-".join(date_parts) if all(p for p in date_parts) else ""
    hour = str(birth.get("hour", 0)).zfill(2)
    minute = str(birth.get("minute", 0)).zfill(2)
    birth_time = f"{hour}:{minute}"
    return birth_date, birth_time


async def run_evaluation(
    data_dir: Path,
    *,
    mode: str = "enhanced",
    limit: Optional[int] = None,
    offset: int = 0,
    datasets: Optional[List[str]] = None,
    output: Optional[Path] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    cases_path: Optional[Path] = None,
    knowledge_base_path: Optional[Path] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    mock_answer: Optional[str] = None,
    timeout_seconds: float = 60.0,
    extra_cases_paths: Optional[List[Path]] = None,
    leave_one_out: bool = False,
    exclude_datasets: Optional[List[str]] = None,
    max_concurrency: int = 1,
    rate_limit: Optional[float] = None,
    temperature: float = 0.0,
    max_tokens: int = 3000,
    ensemble_runs: int = 1,
    use_rule_reasoner: bool = True,
    rule_min_confidence: str = "low",
    use_rule_shortlist: bool = True,
    rule_shortlist_k: int = 2,
    shortlist_mode: str = "soft",
    use_domain_hints: bool = False,
) -> Dict[str, Any]:
    """Run BaziQA evaluation across selected datasets.

    Args:
        data_dir: directory containing contest8_*.json and celebrity50_zh.json.
        mode: "baseline" or "enhanced".
        limit: optional max number of questions to evaluate.
        offset: number of questions to skip from the start.
        datasets: list of dataset names to include (e.g. ["contest8", "celebrity50"]).
        output: optional path to write JSONL predictions.
        mock_answer: if set, bypass LLM and use this letter for every question.
        timeout_seconds: per-question LLM timeout.
        extra_cases_paths: additional case files for RAG enrichment.
        leave_one_out: if True, exclude the current question's own case from RAG.
        exclude_datasets: datasets whose questions should be excluded from RAG
            (useful for cross-domain validation, e.g. train on contest8 and test
            on celebrity50 by excluding celebrity50 cases from retrieval).
        max_concurrency: number of questions to evaluate concurrently. The default
            of 1 keeps the original sequential behavior; raise it to speed up live
            API experiments while staying within rate limits.
        rate_limit: optional maximum requests per second. Use this to avoid 429
            errors from providers that throttle inbound calls.
        temperature: sampling temperature for the LLM (some endpoints, e.g. Kimi,
            only accept 1.0).
        max_tokens: max tokens per LLM response. Raise this for reasoning models
            that emit long chains of thought.
        ensemble_runs: number of independent LLM calls per question; the most
            common answer letter wins.
        use_rule_reasoner: if True, try the symbolic rule reasoner before LLM.
        rule_min_confidence: minimum confidence (low/medium/high) for rule
            answers to bypass the LLM.
        use_rule_shortlist: if True, inject top-k year candidates into the
            enhanced prompt when hard override does not fire.
        rule_shortlist_k: number of year candidates to inject (default 2).
        shortlist_mode: ``soft`` | ``arbiter`` | ``off`` (see evaluate_question).
        use_domain_hints: inject non-year structural hints (default off; regressed in n30).
    """
    contest_records, celebrity_records = load_baziqa(data_dir)
    datasets = datasets or ["contest8", "celebrity50"]

    records: List[Dict[str, Any]] = []
    if "contest8" in datasets:
        records.extend(contest_records)
    if "celebrity50" in datasets:
        records.extend(celebrity_records)

    questions: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for person in records:
        for q in person.get("questions", []):
            questions.append((person, q))

    if offset > 0:
        questions = questions[offset:]
    if limit is not None and limit > 0:
        questions = questions[:limit]

    # Build an exclusion matcher for cross-domain benchmarks.
    exclude_qids: set[str] = set()
    if exclude_datasets:
        if "contest8" in exclude_datasets:
            for person in contest_records:
                for q in person.get("questions", []):
                    exclude_qids.add(q.get("question_id", ""))
        if "celebrity50" in exclude_datasets:
            for person in celebrity_records:
                for q in person.get("questions", []):
                    exclude_qids.add(q.get("question_id", ""))

    def _cross_domain_matcher(case: Dict) -> bool:
        return case.get("source_video") in exclude_qids

    cross_domain_matcher: Optional[Callable[[Dict], bool]] = None
    if exclude_qids:
        cross_domain_matcher = _cross_domain_matcher

    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    rate_limiter = RateLimiter(max_per_second=rate_limit) if rate_limit else None

    async def _evaluate_one(
        person: Dict[str, Any], q: Dict[str, Any]
    ) -> Dict[str, Any]:
        async with semaphore:
            bazi = person_to_bazi(person)
            if not bazi:
                return {
                    "question_id": q.get("question_id"),
                    "error": "无法从 profile 生成八字",
                    "correct": False,
                }

            birth_date, birth_time = _birth_date_time(person)
            gender = person.get("profile", {}).get("gender", "male")
            return await evaluate_question(
                bazi,
                q,
                mode=mode,
                gender=gender,
                birth_date=birth_date,
                birth_time=birth_time,
                api_key=api_key,
                base_url=base_url,
                model=model,
                cases_path=cases_path,
                knowledge_base_path=knowledge_base_path,
                embedding_cache_path=embedding_cache_path,
                knowledge_embedding_cache_path=knowledge_embedding_cache_path,
                mock_answer=mock_answer,
                timeout_seconds=timeout_seconds,
                extra_cases_paths=extra_cases_paths,
                leave_one_out=leave_one_out,
                exclude_case_matcher=cross_domain_matcher,
                temperature=temperature,
                max_tokens=max_tokens,
                ensemble_runs=ensemble_runs,
                rate_limiter=rate_limiter,
                use_rule_reasoner=use_rule_reasoner,
                rule_min_confidence=rule_min_confidence,
                use_rule_shortlist=use_rule_shortlist,
                rule_shortlist_k=rule_shortlist_k,
                shortlist_mode=shortlist_mode,
                use_domain_hints=use_domain_hints,
            )

    tasks = [asyncio.create_task(_evaluate_one(person, q)) for person, q in questions]
    results: List[Dict[str, Any]] = []
    correct = 0
    for i, task in enumerate(asyncio.as_completed(tasks), start=1):
        result = await task
        results.append(result)
        if result.get("correct"):
            correct += 1
        if i % 10 == 0 or i == len(tasks):
            print(
                f"Progress: {i}/{len(tasks)} answered, {correct} correct",
                file=sys.stderr,
                flush=True,
            )

    accuracy = correct / len(results) if results else 0.0
    summary = {
        "mode": mode,
        "datasets": datasets,
        "total": len(results),
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "ensemble_runs": ensemble_runs,
        "results": results,
    }

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        summary["output_path"] = str(output)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MingMirror bazi AI on BaziQA")
    parser.add_argument("--data", default="benchmarks/baziqa/data", help="BaziQA data directory")
    parser.add_argument("--mode", choices=["baseline", "enhanced"], default="enhanced")
    parser.add_argument("--datasets", nargs="+", choices=["contest8", "celebrity50"], default=None)
    parser.add_argument("--limit", type=int, default=None, help="Max questions to evaluate")
    parser.add_argument("--offset", type=int, default=0, help="Questions to skip")
    parser.add_argument("--output", default=None, help="Output JSONL path for predictions")
    parser.add_argument("--api-key", default=None, help="LLM API key")
    parser.add_argument("--base-url", default=None, help="LLM API base URL")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--mock-answer", default=None, help="Use fixed letter for every question (for testing)")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-question LLM timeout in seconds")
    parser.add_argument("--extra-cases", nargs="+", default=None, help="Additional case files for RAG")
    parser.add_argument("--leave-one-out", action="store_true", help="Exclude the current question's case from RAG")
    parser.add_argument("--exclude-datasets", nargs="+", choices=["contest8", "celebrity50"], default=None, help="Exclude a whole dataset from RAG (cross-domain validation)")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent API calls (default 1)")
    parser.add_argument("--rate-limit", type=float, default=None, help="Max API requests per second (e.g. 0.5)")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM sampling temperature (0=greedy, lower variance)")
    parser.add_argument("--max-tokens", type=int, default=3000, help="Max tokens per LLM response")
    parser.add_argument("--ensemble-runs", type=int, default=1, help="Independent LLM calls per question for voting")
    parser.add_argument("--no-rule-reasoner", action="store_true", help="Disable symbolic rule reasoner")
    parser.add_argument("--rule-min-confidence", choices=["low", "medium", "high"], default="high", help="Minimum confidence for rule answers (high = only override LLM when margin >=0.5, ~75% reliable)")
    parser.add_argument("--no-rule-shortlist", action="store_true", help="Disable top-k year shortlist injection into the LLM prompt")
    parser.add_argument("--rule-shortlist-k", type=int, default=2, help="How many year candidates to inject as soft shortlist (default 2)")
    parser.add_argument(
        "--shortlist-mode",
        choices=["soft", "arbiter", "off"],
        default="soft",
        help="soft=inject shortlist (1x); arbiter=free+guided arbitration (2x when shortlist fires); off=no shortlist",
    )
    parser.add_argument(
        "--domain-hints",
        action="store_true",
        help="Inject non-year structural 取象 hints (experimental; regressed n30 LOO 50%%→43%%, default off)",
    )
    parser.add_argument("--config", default="config.yml", help="YAML config to load extra_cases_paths from")
    parser.add_argument("--inject-knowledge", nargs="+", default=None, help="Inject these files IN FULL (replacing 2K RAG snippet) for long-context models, e.g. the 盲派 rulebook + mnemonics")
    parser.add_argument("--inject-knowledge-max-chars", type=int, default=60000, help="Max total chars for --inject-knowledge")
    args = parser.parse_args()
    if args.inject_knowledge:
        set_full_knowledge(args.inject_knowledge, max_chars=args.inject_knowledge_max_chars)

    extra_cases_paths: Optional[List[Path]] = None
    if args.extra_cases:
        extra_cases_paths = [Path(p) for p in args.extra_cases]
    else:
        extra_cases_paths = _load_config_extra_cases(Path(args.config))

    # Fall back to config.yml for API credentials when CLI flags/env vars are absent.
    config_api_key: Optional[str] = None
    config_base_url: Optional[str] = None
    config_model: Optional[str] = None
    try:
        with Path(args.config).open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        bazi_ai_cfg = cfg.get("bazi_ai", {})
        config_api_key = bazi_ai_cfg.get("api_key") or None
        config_base_url = bazi_ai_cfg.get("base_url") or None
        config_model = bazi_ai_cfg.get("model") or None
    except Exception:
        pass

    # CLI flag > env > config file, so a one-off experiment key can override
    # the production config without editing config.yml.
    api_key = (
        args.api_key
        or os.environ.get("MINIMAX_API_KEY")
        or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or config_api_key
    )
    base_url = (
        args.base_url
        or os.environ.get("MINIMAX_BASE_URL")
        or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or config_base_url
    )
    model = (
        args.model
        or os.environ.get("MINIMAX_MODEL")
        or os.environ.get("DOUYIN_BAZI_AI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or config_model
    )

    summary = asyncio.run(
        run_evaluation(
            Path(args.data),
            mode=args.mode,
            limit=args.limit,
            offset=args.offset,
            datasets=args.datasets,
            output=Path(args.output) if args.output else None,
            api_key=api_key,
            base_url=base_url,
            model=model,
            mock_answer=args.mock_answer,
            timeout_seconds=args.timeout,
            extra_cases_paths=extra_cases_paths,
            leave_one_out=args.leave_one_out,
            exclude_datasets=args.exclude_datasets,
            max_concurrency=args.concurrency,
            rate_limit=args.rate_limit,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            ensemble_runs=args.ensemble_runs,
            use_rule_reasoner=not args.no_rule_reasoner,
            rule_min_confidence=args.rule_min_confidence,
            use_rule_shortlist=not args.no_rule_shortlist and args.shortlist_mode != "off",
            rule_shortlist_k=args.rule_shortlist_k,
            shortlist_mode=args.shortlist_mode,
            use_domain_hints=args.domain_hints,
        )
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
