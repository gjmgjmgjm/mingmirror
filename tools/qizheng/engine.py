"""Qi Zheng Si Yu analysis engine.

Provides a DeepSeek-compatible LLM wrapper plus a deterministic mock fallback
when no API key is available. The output schema mirrors the bazi engine so that
the multi-system destiny layer can consume it uniformly.

Environment:
    DEEPSEEK_API_KEY      - required for real inference
    DEEPSEEK_BASE_URL     - defaults to https://api.deepseek.com/v1
    DEEPSEEK_MODEL        - defaults to deepseek-chat
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiofiles

from tools.qizheng import calendar as qz_calendar
from tools.qizheng.prompts import (
    build_system_prompt,
    build_user_prompt,
    build_yearly_system_prompt,
    build_yearly_user_prompt,
)
from utils.logger import setup_logger

logger = setup_logger("QiZhengAnalyzer")

# Four pillars: e.g. "甲子 丙寅 戊辰 庚午"
_CHART_RE = re.compile(
    r"^[\u4e00-\u9fa5]{2}\s+[\u4e00-\u9fa5]{2}\s+[\u4e00-\u9fa5]{2}\s+[\u4e00-\u9fa5]{2}$"
)

_DOMAIN_KEYS = ("career", "wealth", "marriage", "health")


def _normalize_chart(chart: str) -> Optional[str]:
    """Normalize and validate a four-pillar chart string."""
    if not isinstance(chart, str):
        return None
    chart = chart.strip()
    if not chart:
        return None
    # Normalize multiple spaces to single space.
    chart = re.sub(r"\s+", " ", chart)
    if _CHART_RE.match(chart):
        return chart
    return None


async def _load_cases(cases_path: Optional[Path]) -> List[Dict[str, Any]]:
    if cases_path is None or not cases_path.exists():
        return []
    cases: List[Dict[str, Any]] = []
    try:
        async with aiofiles.open(cases_path, "r", encoding="utf-8") as handle:
            async for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        logger.warning("Failed to load qizheng cases from %s: %s", cases_path, exc)
    return cases


def _score_case_relevance(case: Dict[str, Any], chart: str, question: str) -> int:
    score = 0
    if case.get("chart") == chart:
        score += 100
    text = " ".join(
        [
            case.get("chart", ""),
            case.get("analysis", ""),
            " ".join(str(v) for v in (case.get("domains") or {}).values()),
        ]
    )
    if question:
        for kw in re.split(r"[，。！？、\s]", question):
            kw = kw.strip()
            if len(kw) >= 2 and kw in text:
                score += 10
    return score


async def _retrieve_similar_cases(
    chart: str,
    question: str,
    cases_path: Optional[Path],
    top_k: int,
) -> List[Dict[str, Any]]:
    cases = await _load_cases(cases_path)
    if not cases:
        return []
    scored = [(_score_case_relevance(c, chart, question), c) for c in cases]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _build_mock_result(chart: str, question: str, similar_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    refs = [c.get("chart") for c in similar_cases[:2] if c.get("chart")]
    # Take day master from the third pillar's first character.
    pillars = chart.split()
    day_master = pillars[2][0] if len(pillars) == 4 and pillars[2] else ""

    domain_texts = {
        "career": "七政得时，适合稳健型职业，中年后渐入佳境。",
        "wealth": "财星有根，正财为主，不宜高风险投机。",
        "marriage": "夫妻宫平和，配偶得力，宜晚婚。",
        "health": "注意脾胃消化与肝胆调养。",
    }

    if question:
        # When a domain-specific question is asked, leave unrelated domains
        # with a placeholder so the caller can see the focus.
        domain_analysis = {
            k: (v if any(kw in question for kw in _domain_keywords(k)) else "待详细排盘后补充")
            for k, v in domain_texts.items()
        }
    else:
        domain_analysis = dict(domain_texts)

    return {
        "basic_info": {
            "chart": chart,
            "day_master": day_master,
            "life_palace": "待模型分析",
            "body_palace": "待模型分析",
            "dominant_stars": [],
        },
        "reasoning": (
            "当前未配置 DEEPSEEK_API_KEY，仅返回七政四余基础结构与 RAG 检索信息。"
            "设置环境变量后可获得完整模型分析。"
        ),
        "domain_analysis": domain_analysis,
        "summary": [f"参考相似案例：{', '.join(refs)}" if refs else "未找到相似案例"],
        "confidence": "low",
        "caveats": ["未调用真实模型", "请配置 DEEPSEEK_API_KEY"],
        "_mock": True,
    }


def _domain_keywords(domain: str) -> List[str]:
    mapping = {
        "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁"],
        "wealth": ["财", "钱", "富", "收入", "资产", "赚钱"],
        "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚"],
        "health": ["健康", "病", "身体", "手术", "肾", "肝胆", "脾胃"],
    }
    return mapping.get(domain, [])


def _parse_json(content: str, chart: str) -> Dict[str, Any]:
    content = content.strip()
    if not content:
        return {"basic_info": {"chart": chart}, "parse_error": True, "raw_content": ""}

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            pass

    return {"basic_info": {"chart": chart}, "parse_error": True, "raw_content": content}


def _merge_structural_profile(result: Dict[str, Any], profile: Optional[Dict[str, Any]]) -> None:
    """Inject computed structural facts into the result's basic_info."""
    if not profile:
        return
    basic = result.setdefault("basic_info", {})
    for key in (
        "day_master",
        "life_palace",
        "body_palace",
        "body_lord",
        "nayin",
        "five_element_pattern",
        "twelve_palaces",
    ):
        if key not in basic or not basic[key]:
            basic[key] = profile.get(key)


def _ensure_domain_analysis(result: Dict[str, Any]) -> Dict[str, Any]:
    """Make sure the result contains the canonical domain keys."""
    domains = result.get("domain_analysis") or {}
    if not isinstance(domains, dict):
        domains = {}
    for key in _DOMAIN_KEYS:
        if key not in domains or not domains[key]:
            domains[key] = "待详细分析"
    result["domain_analysis"] = domains
    return result


class QiZhengAnalyzer:
    """Analyze a Qi Zheng Si Yu chart via LLM or mock fallback."""

    def __init__(
        self,
        *,
        rule_primer_path: Optional[Path] = None,
        cases_path: Optional[Path] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        top_k: int = 3,
    ):
        self.rule_primer_path = rule_primer_path
        self.cases_path = cases_path
        package_dir = Path(__file__).resolve().parent
        self.examples_path = package_dir / "examples.jsonl"
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.top_k = max(0, min(top_k, 10))

    async def analyze(
        self,
        chart_info: Dict[str, Any],
        question: str = "",
    ) -> Dict[str, Any]:
        """Analyze a Qi Zheng Si Yu chart.

        Args:
            chart_info: dict with at least a "bazi" / "chart" key containing
                the four pillars, e.g. "甲子 丙寅 戊辰 庚午".
            question: optional user question.

        Returns:
            Structured analysis result matching the bazi engine schema.
        """
        chart = str(chart_info.get("chart") or chart_info.get("bazi") or "").strip()
        normalized = _normalize_chart(chart)
        if normalized is None:
            return {
                "basic_info": {"chart": chart},
                "error": "无效的命盘格式，需要四柱六十甲子（如：甲子 丙寅 戊辰 庚午）",
                "reasoning": "",
                "domain_analysis": {},
                "summary": [],
                "confidence": "low",
                "caveats": ["输入命盘无法解析为四柱"],
            }

        chart = normalized
        similar_cases = await _retrieve_similar_cases(
            chart, question, self.cases_path, self.top_k
        )
        system_prompt = await build_system_prompt(self.rule_primer_path)
        from tools.qizheng.prompts import _load_few_shot_examples

        profile = qz_calendar.structural_profile(chart)
        few_shot_examples = _load_few_shot_examples(self.examples_path)
        user_prompt = build_user_prompt(
            chart, question, similar_cases,
            profile=profile,
            few_shot_examples=few_shot_examples,
        )

        key = (
            self.api_key
            or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
        )
        if not key:
            return _ensure_domain_analysis(_build_mock_result(chart, question, similar_cases))

        base = (
            self.base_url
            or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
            or os.environ.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        mdl = (
            self.model
            or os.environ.get("DOUYIN_BAZI_AI_MODEL")
            or os.environ.get("DEEPSEEK_MODEL")
            or "deepseek-chat"
        )

        try:
            import aiohttp
        except ImportError as exc:  # pragma: no cover
            raise ImportError("需要 aiohttp 来调用 DeepSeek API") from exc

        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 2500,
            "response_format": {"type": "json_object"},
        }

        async with aiohttp.ClientSession() as session:
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
                content = data["choices"][0]["message"]["content"]
                parsed = _parse_json(content, chart)
                parsed.setdefault("basic_info", {}).setdefault("chart", chart)
                _merge_structural_profile(parsed, profile)
                return _ensure_domain_analysis(parsed)


# ── Yearly luck analysis (dayun + liunian) ──

_STEM_ELEMENT = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

_BRANCH_ELEMENT = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

_GENERATING = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_RESTRAINING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

_PALACE_DOMAIN = {
    "命宫": ("自身根基", "心态与整体气运"),
    "财帛": ("正财偏财", "收入与理财"),
    "兄弟": ("同辈竞争", "合作与分夺"),
    "田宅": ("家庭房产", "居住环境"),
    "男女": ("子女晚辈", "下属关系"),
    "奴仆": ("人际同事", "朋友助力"),
    "夫妻": ("感情婚姻", "配偶关系"),
    "疾厄": ("健康隐患", "身体调养"),
    "迁移": ("外出变动", "远方机遇"),
    "官禄": ("事业地位", "职场发展"),
    "福德": ("精神状态", "福报贵人"),
    "相貌": ("外在形象", "人际第一印象"),
}


async def analyze_yearly(
    chart: str,
    *,
    gender: str = "",
    birth_year: Optional[int] = None,
    mode: str = "10y",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    rule_primer_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Analyze yearly luck for a Qi Zheng Si Yu chart.

    *mode* can be ``"10y"`` for the next 10 years, or ``"lifetime"`` for a
    full reading until age 80.
    """
    normalized = _normalize_chart(chart)
    if normalized is None:
        return {
            "error": "无效的命盘格式",
            "dayun_summary": [],
            "yearly_analysis": [],
            "overall_guidance": "",
        }
    chart = normalized

    current_year = datetime.now().year
    birth_year = birth_year or current_year

    dayun = qz_calendar.dayun_list(chart, gender, until_age=80)

    if mode == "10y":
        start_year = current_year
        end_year = current_year + 9
    else:
        start_year = birth_year
        end_year = birth_year + 79

    liunian = qz_calendar.liunian_list(start_year, end_year)

    # Populate start/end years for dayun when birth year is known.
    for d in dayun:
        d["start_year"] = birth_year + int(d["start_age"])
        d["end_year"] = birth_year + int(d["end_age"]) - 1

    # Filter dayun to those overlapping the analyzed years.
    dayun_active = [
        d
        for d in dayun
        if d["end_age"] >= (start_year - birth_year)
        and d["start_age"] <= (end_year - birth_year)
    ]

    primer = ""
    if rule_primer_path is not None and rule_primer_path.exists():
        async with aiofiles.open(rule_primer_path, "r", encoding="utf-8") as handle:
            primer = (await handle.read())[:12000]

    profile = qz_calendar.structural_profile(chart) or {}
    yearly_rels = []
    for y in liunian:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun_active if d["start_age"] <= age < d["end_age"]),
            dayun_active[-1] if dayun_active else None,
        )
        if active is None:
            continue
        rel = qz_calendar.yearly_relations(chart, active["pillar"], y["pillar"])
        if rel is not None:
            rel["year"] = y["year"]
            rel["age"] = age
            rel["palace"] = active.get("palace", "")
            yearly_rels.append(rel)

    system_prompt = build_yearly_system_prompt(primer)
    user_prompt = build_yearly_user_prompt(
        chart, gender, dayun_active, liunian, mode, profile, yearly_rels, birth_year
    )

    key = (
        api_key
        or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )
    if not key:
        return _rule_based_yearly(chart, dayun_active, liunian, birth_year)

    base = (
        base_url
        or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com/v1"
    ).rstrip("/")
    mdl = (
        model
        or os.environ.get("DOUYIN_BAZI_AI_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or "deepseek-chat"
    )

    try:
        import aiohttp
    except ImportError as exc:  # pragma: no cover
        raise ImportError("需要 aiohttp 来调用 DeepSeek API") from exc

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 5000,
        "response_format": {"type": "json_object"},
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, 3):
        try:
            timeout = aiohttp.ClientTimeout(total=90)
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
                    content = data["choices"][0]["message"]["content"]
                    parsed = _parse_json_yearly(content)
                    if parsed.get("parse_error"):
                        raw_snippet = (parsed.get("raw_content") or "")[:500]
                        logger.warning(
                            "七政流年分析 JSON 解析失败，使用兜底分析。原始输出片段：%s",
                            raw_snippet,
                        )
                        return _rule_based_yearly(
                            chart,
                            dayun_active,
                            liunian,
                            birth_year,
                            Exception(f"AI 输出无法解析，已切换兜底。片段：{raw_snippet}"),
                        )
                    parsed.setdefault("dayun_summary", [])
                    parsed.setdefault("yearly_analysis", [])
                    parsed.setdefault("overall_guidance", "")
                    parsed.setdefault("confidence", "low")
                    parsed["caveats"] = list(parsed.get("caveats", []))
                    parsed["caveats"].append("算法排盘，结果仅供参考")

                    if mode == "lifetime":
                        rule_fallback = _rule_based_yearly(
                            chart, dayun_active, liunian, birth_year
                        )
                        parsed["yearly_analysis"] = rule_fallback.get("yearly_analysis", [])
                        if not parsed.get("overall_guidance"):
                            parsed["overall_guidance"] = rule_fallback.get("overall_guidance", "")
                        existing = set(parsed["caveats"])
                        for c in rule_fallback.get("caveats", []):
                            if "当前为本地规则分析" in c:
                                continue
                            if c not in existing:
                                parsed["caveats"].append(c)
                                existing.add(c)
                        return parsed

                    return _validate_yearly_output(parsed, chart, dayun_active, liunian, birth_year)
        except Exception as exc:
            last_error = exc
            logger.warning("七政流年分析请求失败 (attempt %d/2): %s", attempt, exc)
            if attempt < 2:
                await asyncio.sleep(2.0)

    return _rule_based_yearly(
        chart, dayun_active, liunian, birth_year,
        Exception(f"AI 服务暂时不可用：{last_error}")
    )


def _parse_json_yearly(content: str) -> Dict[str, Any]:
    """Parse model output as JSON for yearly analysis, with fallback."""
    content = content.strip()
    if not content:
        return {"parse_error": True, "raw_content": ""}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            pass
    return {"parse_error": True, "raw_content": content}


def _validate_yearly_output(
    result: Dict[str, Any],
    chart: str,
    dayun: List[Dict[str, Any]],
    liunian: List[Dict[str, Any]],
    birth_year: int,
) -> Dict[str, Any]:
    """Sanity-check yearly output; fall back to rule-based if too generic."""
    yearly = result.get("yearly_analysis", [])
    required = ("year", "pillar", "overview", "career", "wealth", "marriage", "health", "caution")
    if not yearly or len(yearly) < len(liunian) * 0.8 or not all(all(k in y for k in required) for y in yearly):
        logger.warning("七政流年分析字段缺失或年份不足，使用兜底分析")
        return _rule_based_yearly(
            chart, dayun, liunian, birth_year,
            Exception("AI 返回字段缺失或年份不足，已切换兜底")
        )
    return result


def _rule_based_yearly(
    chart: str,
    dayun: List[Dict[str, Any]],
    liunian: List[Dict[str, Any]],
    birth_year: int,
    last_error: Optional[Exception] = None,
) -> Dict[str, Any]:
    """Return a structured fallback combining dayun and liunian."""
    profile = qz_calendar.structural_profile(chart) or {}
    day_master_stem = profile.get("day_master", "")
    dm_element = _STEM_ELEMENT.get(day_master_stem, "")

    def _element_relation(target_element: str) -> str:
        if not dm_element or not target_element:
            return "平"
        if target_element == dm_element:
            return "比劫"
        if _GENERATING.get(dm_element) == target_element:
            return "泄耗"
        if _GENERATING.get(target_element) == dm_element:
            return "生助"
        if _RESTRAINING.get(dm_element) == target_element:
            return "克制"
        if _RESTRAINING.get(target_element) == dm_element:
            return "受克"
        return "平"

    def _branch_interaction(b1: str, b2: str) -> Optional[str]:
        pair = (b1, b2)
        chong = {
            ("子", "午"), ("丑", "未"), ("寅", "申"),
            ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
        }
        he = {
            ("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
            ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土",
        }
        if pair in chong or pair[::-1] in chong:
            return "冲"
        for h, el in he.items():
            if pair == h or pair[::-1] == h:
                return f"合({el})"
        return None

    def _dayun_theme(palace: str, branch: str) -> Tuple[str, str]:
        domain = _PALACE_DOMAIN.get(palace, ("运势", "综合"))
        element = _BRANCH_ELEMENT.get(branch, "")
        return domain[0], f"{palace}（{branch}，{element}）主{domain[1]}"

    dayun_summary = []
    for d in dayun:
        theme, focus = _dayun_theme(d["palace"], d["pillar"])
        dayun_summary.append(
            {
                "pillar": d["pillar"],
                "palace": d["palace"],
                "start_age": d["start_age"],
                "end_age": d["end_age"],
                "theme": f"{d['palace']}大限，{theme}当令",
                "focus": focus,
            }
        )

    yearly_analysis = []
    for y in liunian:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun if d["start_age"] <= age < d["end_age"]),
            dayun[-1] if dayun else None,
        )
        if active is None:
            continue

        ly_stem = y["pillar"][0]
        ly_branch = y["pillar"][1]
        ly_stem_rel = _element_relation(_STEM_ELEMENT.get(ly_stem, ""))
        ly_branch_rel = _element_relation(_BRANCH_ELEMENT.get(ly_branch, ""))
        interaction = _branch_interaction(active["pillar"], ly_branch)

        overview_parts = [f"流年{y['pillar']}（{active['palace']}大限）"]
        if interaction:
            overview_parts.append(f"大限宫支与流年支{interaction}")
        else:
            overview_parts.append(f"天干{ly_stem_rel}、地支{ly_branch_rel}")
        overview = "，".join(overview_parts)

        domains = _yearly_domain_text(
            active["palace"], ly_stem_rel, ly_branch_rel, interaction, age
        )

        if interaction and interaction.startswith("冲"):
            caution = f"{active['palace']}宫逢冲，变动明显"
        elif ly_stem_rel == "受克" or ly_branch_rel == "受克":
            caution = "流年克耗日主，宜稳守"
        elif ly_stem_rel == "生助" or ly_branch_rel == "生助":
            caution = "得助之年，可适度进取"
        else:
            caution = "平运，按部就班"

        yearly_analysis.append(
            {
                "year": y["year"],
                "pillar": y["pillar"],
                "overview": overview,
                "career": domains["career"],
                "wealth": domains["wealth"],
                "marriage": domains["marriage"],
                "health": domains["health"],
                "caution": caution,
            }
        )

    caveats = ["当前为本地规则分析，建议配置稳定 AI 服务以获取更深度流年解读。"]
    if last_error:
        caveats.append(str(last_error))

    return {
        "dayun_summary": dayun_summary,
        "yearly_analysis": yearly_analysis,
        "overall_guidance": "当前为本地规则兜底分析，已将大限宫位与流年干支结合推断；建议配置稳定 AI 服务以获取更深度解读。",
        "confidence": "low",
        "caveats": caveats,
        "_rule_based": True,
    }


def _yearly_domain_text(
    palace: str,
    stem_rel: str,
    branch_rel: str,
    interaction: Optional[str],
    age: int,
) -> Dict[str, str]:
    """Generate domain texts for the rule-based yearly fallback."""
    good = stem_rel in ("生助", "比劫") or branch_rel in ("生助", "比劫")
    bad = stem_rel == "受克" or branch_rel == "受克"
    chong = interaction and interaction.startswith("冲")

    if chong:
        level = "chong"
    elif bad:
        level = "bad"
    elif good:
        level = "good"
    else:
        level = "flat"

    palace_focus = {
        "命宫": ("自身", "心态"),
        "财帛": ("收入", "理财"),
        "兄弟": ("同事", "合作"),
        "田宅": ("家庭", "房产"),
        "男女": ("子女", "下属"),
        "奴仆": ("人际", "朋友"),
        "夫妻": ("感情", "配偶"),
        "疾厄": ("健康", "身体"),
        "迁移": ("外出", "变动"),
        "官禄": ("事业", "职场"),
        "福德": ("精神", "贵人"),
        "相貌": ("形象", "人际"),
    }
    focus_a, focus_b = palace_focus.get(palace, ("综合", "运势"))

    templates = {
        "chong": {
            "career": f"{focus_a}宫位逢冲，职场易有变动，重大决策宜缓",
            "wealth": "财务波动，预留备用金，忌高风险投资",
            "marriage": "感情易有口角或距离变化，多沟通",
            "health": "注意突发急症与出行安全",
        },
        "bad": {
            "career": f"流年克耗，{focus_a}方面压力增加，以稳为主",
            "wealth": "支出可能增加，控制预算",
            "marriage": "是非稍多，少争执",
            "health": "关注对应脏腑，规律作息",
        },
        "good": {
            "career": f"流年得助，{focus_a}方面可主动争取",
            "wealth": "小有进益，量入为出",
            "marriage": "人际和谐，感情宜积极推进",
            "health": "精力充沛，保持运动习惯",
        },
        "flat": {
            "career": f"{focus_a}方面按节奏推进",
            "wealth": "量入为出",
            "marriage": "顺其自然",
            "health": "规律作息",
        },
    }
    return templates[level]
