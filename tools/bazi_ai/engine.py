#!/usr/bin/env python3
"""
engine.py — DeepSeek-powered bazi analysis engine.

Design:
    1. Validate the input bazi and reject garbage early.
    2. Retrieve similar cases from the structured case database (RAG).
    3. Inject a compact rule primer from the PDF knowledge base.
    4. Ask DeepSeek to reason step-by-step and return structured JSON.

Environment:
    DEEPSEEK_API_KEY      - required for real inference
    DEEPSEEK_BASE_URL     - defaults to https://api.deepseek.com/v1
    DEEPSEEK_MODEL        - defaults to deepseek-chat
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiofiles

from tools.bazi_ai import bazi_structural, calendar

try:
    import aiohttp
    from aiohttp import ClientResponseError
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]
    ClientResponseError = Exception  # type: ignore[assignment,misc]

from tools.bazi_ai.bazi_validator import (
    day_master,
    extract_pillars,
    month_branch,
    normalize_bazi,
)
from tools.bazi_ai.embeddings import EmbeddingStore
from tools.bazi_ai.rule_checker import check_analysis

logger = logging.getLogger(__name__)

# Branch six-clash pairs for palace checks.
_SIX_CHONG = {
    ("子", "午"), ("丑", "未"), ("寅", "申"),
    ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
}

# Domain keywords used to boost retrieval when the user asks a domain question.
_DOMAIN_KEYWORDS = {
    "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁", "贵人"],
    "wealth": ["财", "钱", "富", "收入", "资产", "赚钱", "百万", "千万", "小康"],
    "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚", "离婚"],
    "health": ["健康", "病", "身体", "手术", "肾", "妇科", "心脏", "血液", "子宫"],
    "family": ["父母", "父亲", "母亲", "子女", "孩子", "兄弟", "姐妹"],
}


async def _load_cases(cases_path: Path) -> List[Dict]:
    if not cases_path.exists():
        return []
    cases = []
    async with aiofiles.open(cases_path, "r", encoding="utf-8") as f:
        async for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


def _detect_question_domains(question: str) -> List[str]:
    """Return the life domains mentioned in *question*."""
    if not question:
        return []
    domains = []
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in question for kw in keywords):
            domains.append(domain)
    return domains


def _case_relevance(case: Dict, bazi: str, question: str) -> int:
    """Keyword relevance score for RAG, with domain-aware boosts."""
    score = 0
    text = " ".join(
        [
            case.get("bazi", ""),
            case.get("analysis_corrected", ""),
            " ".join(case.get("key_terms", [])),
            " ".join(case.get("conclusions", [])),
        ]
    )
    case_domains = case.get("domains", {})

    # Exact bazi match is the strongest signal.
    if case.get("bazi") == bazi:
        score += 100

    # Structural similarity.
    query_pillars = bazi.split()
    case_pillars = case.get("bazi", "").split()
    if len(query_pillars) == 4 and len(case_pillars) == 4:
        if query_pillars[2][0] == case_pillars[2][0]:  # day master
            score += 20
        if query_pillars[1][1] == case_pillars[1][1]:  # month branch
            score += 15
        if query_pillars[0][0] == case_pillars[0][0]:  # year stem
            score += 5
        if query_pillars[3][1] == case_pillars[3][1]:  # hour branch
            score += 5

    # Domain-aware boost: if the user asks about career, prefer career cases.
    for domain in _detect_question_domains(question):
        if case_domains.get(domain):
            score += 12
        domain_text = " ".join(case_domains.get(domain, []))
        for kw in _DOMAIN_KEYWORDS.get(domain, []):
            if kw in domain_text or kw in text:
                score += 3

    # Question keyword overlap.
    if question:
        for kw in re.split(r"[，。！？、\s]", question):
            kw = kw.strip()
            if len(kw) >= 2 and kw in text:
                score += 10
    return score


async def retrieve_similar_cases(
    bazi: str,
    question: str,
    cases_path: Path,
    top_k: int = 3,
    embedding_cache_path: Optional[Path] = None,
    extra_cases_paths: Optional[List[Path]] = None,
) -> List[Dict]:
    """Return the top-k most relevant cases.

    If *embedding_cache_path* exists and sentence-transformers is installed,
    semantic similarity is combined with the keyword heuristic for ranking.

    *extra_cases_paths* allows users to load additional private/local case
    databases without mixing them into the default public case file.
    """
    cases = await _load_cases(cases_path)
    for path in extra_cases_paths or []:
        cases.extend(await _load_cases(path))
    if not cases:
        return []

    embedding_bonus: Dict[int, float] = {}

    if embedding_cache_path is not None and embedding_cache_path.exists():
        store = EmbeddingStore()
        if store.load_cache(embedding_cache_path):
            query = f"{bazi}\n{question}".strip()
            for rank, (case, score) in enumerate(store.search(query, top_k=min(len(cases), top_k * 3))):
                for idx, c in enumerate(cases):
                    if c is case:
                        # Normalize score to a 0-30 bonus and decay by rank.
                        embedding_bonus[idx] = max(0.0, score * 30 - rank * 3)
                        break

    scored = []
    for idx, case in enumerate(cases):
        keyword_score = _case_relevance(case, bazi, question)
        bonus = embedding_bonus.get(idx, 0.0)
        scored.append((keyword_score + bonus, case))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


async def _build_rule_primer(
    knowledge_base_paths: List[Path], max_chars: int = 10000
) -> str:
    """Load a short rule primer from one or more knowledge base files."""
    if isinstance(knowledge_base_paths, Path):
        knowledge_base_paths = [knowledge_base_paths]
    parts = []
    for path in knowledge_base_paths:
        if not path.exists():
            continue
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            parts.append(await f.read())
    if not parts:
        return ""
    text = "\n\n".join(parts)
    # Truncate to avoid blowing up the prompt.
    return text[:max_chars]


def _build_system_prompt(rule_primer: str) -> str:
    return f"""你是一位坐在茶桌对面、说话直接又有温度的命理师。你不是在写报告，而是在跟一个具体的人聊他的命。你会先看他八字，然后像真人一样说出你的判断，有依据、有场景、有情绪，但绝不编造。

表达风格（必须严格执行）：
1. 用第二人称"你"和第一人称"我"，像面对面交谈。例如："我看你这个八字……""我直说，你这几年……""你要注意的是……"
2. 禁止公文式、教科书式结构。不要出现"首先……其次……综上……""需要注意以下几点""综上所述"等套话。
3. 禁止把结论写成干巴巴的一句话标签。每个领域结论都要像一段话：先说命局依据，再讲会呈现成什么生活场景，最后给一句具体建议。
4. 少用"适合""注意""宜""不宜""建议"这类模板词。换成更自然的说法，比如"你更适合……""这块要当心……""你可以往……方向走"。
5. `reasoning` 要像你口述推理过程，可以有一句"我看""这里关键是"，不要写成 1、2、3 的步骤清单。
6. `summary` 要像你临走前对命主说的三句叮嘱，有先后、有轻重，不是标签罗列。
7. `liuqin_analysis` 要像你一边看四柱一边讲家里六亲关系，自然带过，不要像填空。
8. 允许有口语化的衔接词和轻微重复，允许有"说实话""说白了""关键是"这样的口头语，但要克制。
9. 结论必须有命局依据，禁止为了讨好用户而编造不存在的吉凶事件。
10. 输出必须是 JSON，不要有任何额外解释文字。

分析原则：
1. 以子平格局和旺衰喜用为主，必要时参考盲派做功思路。
2. 推理过程要连贯自然，像你在解释给命主听，不必分点罗列。关键判断要在 reasoning 中体现。
3. 结论要具体，但必须有命局依据，禁止为了迎合用户而编造不存在的吉凶事件。
4. 财富等级直断标准（严格按此执行，不能随意）：
   - 贫/温饱：日主极弱，财星全无或财星被坏，无用神救助。
   - 小康：财星有根但身弱难担，靠正财工资收入，无大财。
   - 中产：身财两停，或食伤生财有情，能稳定积累。
   - 小富：身旺能担财，财星旺且有库，或食伤生财有力。
   - 中富/大富/巨富：从财格、从杀格等特殊格局，或财官印俱全且用神得力，配合大运。
5. 婚姻状况直断标准（严格按此执行）：
   - 早婚：配偶星早现且得力，夫妻宫稳定，无严重冲克。
   - 晚婚：配偶星弱、迟现，或夫妻宫有冲克需大运解。
   - 一婚稳定：夫妻宫为喜用，配偶星清纯，无严重刑冲。
   - 二婚/多婚：夫妻宫被冲穿严重，配偶星混杂，或日支反复受伤。
   - 孤独：配偶星全无，夫妻宫被坏，又走忌神运。
6. milestones 只允许列高置信度节点，必须满足以下条件之一：
   - 婚动/结婚：流年或大运与夫妻宫（日支）六合、三合、红鸾天喜，或配偶星透干合身。
   - 离婚/感情危机：夫妻宫被冲、刑、穿，且配偶星受制。
   - 财富转折：财星、财库、食伤被大运/流年强烈引动（如冲开财库、食伤生财）。
   - 事业转折：官杀、印星、食伤发生重大变化，如杀印相生、伤官见官。
   - 重大疾病：五行严重失衡，对应脏腑被冲克。
   - 搬迁：驿马被冲，或流年冲命局日支/时支。
   证据不足时宁可不写，也不要硬凑。禁止连续两年列出剧烈人生转折，除非命局确实如此。
7. 必须输出 `liuqin_analysis`，按四柱逐柱写明六亲定位：
   - 格式："年柱XX：天干X为十神，代表母亲/父亲；地支X为十神，藏干XXX，代表祖上/兄弟/子女……"
   - 男命：正财为妻，偏财为父/妾，正印为母，偏印为继母/长辈，食神为女婿/儿子，伤官为女儿/祖母，正官为女儿，七杀为儿子，比肩为兄弟，劫财为姐妹。
   - 女命：正官为夫，七杀为情人，食神为女儿，伤官为儿子，正印为母，偏印为继母，比肩为姐妹，劫财为兄弟。
   - 必须结合天干和地支藏干分别说明，不能只说一柱论某六亲。
8. 如果八字有争议或时辰不准，必须给出置信度和 caveat。置信度只能在顶层 `confidence` 字段出现，禁止在 domain_analysis、summary、events、wealth_level、marriage_status、liuqin_analysis 等任何字符串里追加“（置信度：...）”。
9. 输出必须是 JSON，不要有任何额外解释文字。
10. 在给出最终结论前，先用基础知识交叉验证：日主、月令、格局、用神忌神的组合是否合理。

示例输出格式（仅供参考，不要直接照搬内容；重点看语气，不是结论）：
{{
  "basic_info": {{
    "bazi": "甲子 丙寅 戊辰 庚午",
    "day_master": "戊",
    "month_branch": "寅",
    "pattern": "七杀格",
    "useful_gods": ["火", "土"],
    "taboo_gods": ["木", "水"]
  }},
  "reasoning": "我看你这个八字，戊土日主生在寅月，木旺土虚，日主偏弱。年支子水、月干丙火生土，时支午火为根，所以身弱喜印比。月令寅木七杀当令，格局取七杀格。用神是火土，忌神是木水。事业上你更适合稳定、技术或管理类岗位，高风险投机不太适合你。",
  "domain_analysis": {{
    "career": "你这个人做事踏实，技术或管理类岗位比较对你胃口。30岁之后印星渐旺，贵人运会起来，事业上会慢慢有起色，但前半段别太急着换跑道。",
    "wealth": "财星不旺，正财为主，说白了就是靠工资和稳定收入积累，小康水平是有的。大额借贷和投资要慎重，尤其别碰高杠杆。",
    "marriage": "配偶宫坐午火为喜用，夫妻关系底子不错，但早年运势不稳，晚一点结婚反而更稳。",
    "health": "土虚木旺，脾胃和肝胆是你天生的薄弱点，少熬夜、少喝酒，规律吃饭比吃补药管用。"
  }},
  "wealth_level": "小康",
  "wealth_evidence": "财星不透干，正财坐日支，收入靠正业积累，不是暴发格局。",
  "marriage_status": "晚婚一婚稳定",
  "marriage_evidence": "配偶宫为喜用神，婚姻质量不差，但早年事业和感情都还没定，晚婚更稳。",
  "liuqin_analysis": "年柱甲子：天干甲木为比肩（兄弟），地支子水为正印（母亲），藏干癸水偏印亦为母亲长辈；月柱丙寅：天干丙火为偏印（继母/长辈），地支寅木为比肩（兄弟），藏干丙火偏印、戊土偏财、甲木比肩；日柱戊辰：天干戊土为日主自身，地支辰土为比肩（兄弟/自身根基），藏干戊土比肩、乙木正官、癸水正财（妻）；时柱庚午：天干庚金为食神（女婿/儿子），地支午火为正印（母亲），藏干丁火正印、己土劫财。",
  "milestones": [
    {{"year": 2028, "age": 28, "type": "事业转折", "description": "流年助身，升职或跳槽成功"}},
    {{"year": 2031, "age": 31, "type": "婚动", "description": "财星合入妻宫，有结婚机会"}}
  ],
  "summary": ["你身弱杀旺，平时多靠印比扶身，做事别单打独斗。", "事业上前半段求稳，技术或管理路线更适合你。", "婚姻宫为喜，感情底子不错，晚婚更稳。", "中年后运势渐顺，不必太焦虑。"],
  "confidence": "medium",
  "caveats": ["时辰若不准，日柱变化会显著影响结论"]
}}

基础知识参考：
{rule_primer}
"""


def _build_user_prompt(bazi: str, question: str, similar_cases: List[Dict]) -> str:
    cases_text = "\n\n".join(
        f"案例 {i+1}：\n八字：{c.get('bazi')}\n命理师分析：{c.get('analysis_corrected', '')[:500]}"
        for i, c in enumerate(similar_cases)
    )
    if not cases_text:
        cases_text = "（暂无相似案例）"

    domains = _detect_question_domains(question)
    if domains:
        focus = "、".join(
            {"career": "事业", "wealth": "财运", "marriage": "婚姻/感情", "health": "健康", "family": "家庭"}.get(d, d)
            for d in domains
        )
        focus_instruction = f"请重点分析：{focus}。其他领域可简要说明。"
    else:
        focus_instruction = "请全面分析事业、财运、婚姻、健康四个领域。"

    return f"""请为以下八字做详细分析，像一位真人命理师面对面跟命主交谈那样回答。

八字：{bazi}
命主提问：{question or "全面分析事业、财运、婚姻、健康"}

{focus_instruction}

参考案例（仅作风格与论证参考，不要直接照搬结论）：
{cases_text}

表达要求：
- 用自然、口语化的中文，像真人说话。
- 避免"根据子平法……""从八字来看……""综上所述……"等学术腔和公文腔开头。
- 每个结论都要像一段话，有依据、有场景、有具体建议。

请按以下 JSON 格式输出（不要输出 markdown 代码块，只输出 JSON）：
{{
  "basic_info": {{
    "bazi": "{bazi}",
    "day_master": "日主天干",
    "month_branch": "月令地支",
    "pattern": "格局",
    "useful_gods": ["用神1", "用神2"],
    "taboo_gods": ["忌神1", "忌神2"]
  }},
  "reasoning": "完整的逐步推理过程，300-800字。必须包含：日主旺衰判断、格局取法、用神忌神选择、各领域推断依据。",
  "domain_analysis": {{
    "career": "事业分析（只写结论，禁止写置信度）",
    "wealth": "财运分析（只写结论，禁止写置信度）",
    "marriage": "婚姻/感情分析（只写结论，禁止写置信度）",
    "health": "健康分析（只写结论，禁止写置信度）"
  }},
  "wealth_level": "从「贫、温饱、小康、中产、小富、中富、大富、巨富」中选择一级",
  "wealth_evidence": "给出财富等级的简要依据",
  "marriage_status": "从「未婚、早婚、晚婚、一婚稳定、二婚、多婚、孤独」中选择一项",
  "marriage_evidence": "给出婚姻状况的简要依据",
  "liuqin_analysis": "按年柱、月柱、日柱、时柱逐柱说明：天干十神代表什么六亲，地支及藏干又代表什么六亲。男命正财为妻、偏财为父、正印为母、食神为子、伤官为女、七杀为子、正官为女；女命正官为夫、七杀为情人、食神为女、伤官为子、正印为母。",
  "milestones": [
    {{"year": 年份, "age": 年龄, "type": "婚动/子女/事业转折/财富转折/重大疾病/搬迁/学业/其他", "description": "必须有命局依据，证据不足时宁可留空数组"}}
  ],
  "personality": "根据日主、十神、五行喜忌，描述命主的性格、行为模式与气质特点，200字以内。",
  "events": ["直断1：具体事件或趋势", "直断2：具体事件或趋势", "直断3：具体事件或趋势"],
  "summary": ["3-5条核心断语"],
  "confidence": "high|medium|low",
  "caveats": ["可能的误差来源"]
}}
"""


async def analyze_bazi(
    bazi: str,
    *,
    question: str = "",
    cases_path: Optional[Path] = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Optional[Path] = None,
    extra_cases_paths: Optional[List[Path]] = None,
    extra_knowledge_base_paths: Optional[List[Path]] = None,
    embedding_cache_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    top_k: int = 3,
) -> Dict:
    """Analyze a bazi using DeepSeek (or mock mode if no API key).

    *extra_cases_paths* and *extra_knowledge_base_paths* are for local/private
    research material. They are never loaded by default and must be configured
    explicitly by the user.
    """
    normalized = normalize_bazi(bazi)
    if normalized is None:
        return {
            "basic_info": {"bazi": bazi},
            "error": "无效的八字格式",
            "reasoning": "",
            "domain_analysis": {},
            "summary": [],
            "confidence": "low",
            "caveats": ["输入八字无法解析为四柱六十甲子"],
        }

    bazi = normalized
    top_k = max(0, min(top_k, 10))
    if cases_path is not None:
        similar_cases = await retrieve_similar_cases(
            bazi,
            question,
            cases_path,
            top_k=top_k,
            embedding_cache_path=embedding_cache_path,
            extra_cases_paths=extra_cases_paths,
        )
    else:
        similar_cases = []

    # Base rule primer + any explicitly configured knowledge bases.
    rule_primer_paths = [Path("./bazi_knowledge/rule_primer.md")]
    if knowledge_base_path is not None and knowledge_base_path.exists():
        rule_primer_paths.append(knowledge_base_path)
    for path in extra_knowledge_base_paths or []:
        if path.exists():
            rule_primer_paths.append(path)

    rule_primer = await _build_rule_primer(rule_primer_paths, max_chars=12000)
    system_prompt = _build_system_prompt(rule_primer)
    user_prompt = _build_user_prompt(bazi, question, similar_cases)

    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return _mock_analyze(bazi, question, similar_cases)

    base = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    mdl = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

    if aiohttp is None:  # pragma: no cover
        raise ImportError("需要 aiohttp 来调用 DeepSeek API")

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

    last_error: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            timeout = aiohttp.ClientTimeout(total=60)
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
                    parsed = _parse_json(content, bazi, similar_cases)
                    return _validate_output(parsed, bazi)
        except (ClientResponseError, asyncio.TimeoutError, Exception) as exc:
            last_error = exc
            logger.warning("AI 分析请求失败 (attempt %d/3): %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(attempt * 1.5)

    logger.error("AI 分析全部重试失败，返回兜底分析: %s", last_error)
    fallback = _mock_analyze(bazi, question, similar_cases)
    fallback["caveats"].insert(
        0,
        f"AI 服务暂时不可用（{last_error}），已切换为规则兜底分析，结果仅供参考。",
    )
    return fallback


def _bazi_profile(bazi: str) -> Dict[str, str]:
    """Return a concise structural profile of the chart for prompts."""
    from tools.bazi_ai.bazi_validator import extract_pillars

    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return {"day_master": "", "month_branch": "", "strength": "", "useful_gods": "", "taboo_gods": ""}

    day_master_stem = pillars[2][0]
    month_branch_char = pillars[1][1]
    dm_element = calendar.STEM_ELEMENTS.get(day_master_stem, "")
    mb_element = calendar.BRANCH_ELEMENTS.get(month_branch_char, "")

    generating = {"wood": "fire", "fire": "earth", "earth": "metal", "metal": "water", "water": "wood"}
    restraining = {"wood": "earth", "earth": "water", "water": "fire", "fire": "metal", "metal": "wood"}

    # Count element occurrences: stems count as 0.5, branches as 1.0.
    counts: Dict[str, int] = {"wood": 0, "fire": 0, "earth": 0, "metal": 0, "water": 0}
    for p in pillars:
        counts[calendar.STEM_ELEMENTS.get(p[0], "")] += 1
        counts[calendar.BRANCH_ELEMENTS.get(p[1], "")] += 1
    weighted: Dict[str, float] = {"wood": 0.0, "fire": 0.0, "earth": 0.0, "metal": 0.0, "water": 0.0}
    for p in pillars:
        weighted[calendar.STEM_ELEMENTS.get(p[0], "")] += 0.5
        weighted[calendar.BRANCH_ELEMENTS.get(p[1], "")] += 1.0

    # Determine if day master is supported by month branch.
    month_supports = mb_element == dm_element or generating.get(mb_element) == dm_element
    month_opposes = restraining.get(mb_element) == dm_element or generating.get(dm_element) == mb_element
    dm_score = weighted.get(dm_element, 0.0)

    if month_supports and dm_score >= 2.0:
        strength = "偏旺"
    elif month_opposes and dm_score <= 1.5:
        strength = "偏弱"
    elif dm_score >= 2.5:
        strength = "偏旺"
    elif dm_score <= 1.0:
        strength = "偏弱"
    else:
        strength = "中和"

    # Simplified useful/taboo gods based on strength.
    def _element_label(el: str) -> str:
        return {"wood": "木", "fire": "火", "earth": "土", "metal": "金", "water": "水"}.get(el, "")

    def _find_key(mapping: Dict[str, str], value: str) -> str:
        for k, v in mapping.items():
            if v == value:
                return k
        return ""

    # 十神对应五行
    guan_sha = _find_key(restraining, dm_element)   # 克我者
    shi_shang = generating.get(dm_element, "")       # 我生者
    cai = restraining.get(dm_element, "")            # 我克者
    yin = _find_key(generating, dm_element)           # 生我者
    bi_jie = dm_element                               # 同我者

    if strength == "偏旺":
        useful = [_element_label(guan_sha), _element_label(shi_shang), _element_label(cai)]
        taboo = [_element_label(bi_jie), _element_label(yin)]
    elif strength == "偏弱":
        useful = [_element_label(yin), _element_label(bi_jie)]
        taboo = [_element_label(guan_sha), _element_label(cai)]
    else:
        useful = []
        taboo = []

    # Deduplicate while preserving order.
    useful = list(dict.fromkeys([x for x in useful if x]))
    taboo = list(dict.fromkeys([x for x in taboo if x]))

    element_labels = {"wood": "木", "fire": "火", "earth": "土", "metal": "金", "water": "水"}
    element_counts_text = ",".join(
        f"{element_labels[k]}{counts[k]}" for k in ["wood", "fire", "earth", "metal", "water"]
    )

    return {
        "day_master": day_master_stem,
        "month_branch": month_branch_char,
        "element_counts": element_counts_text,
        "strength": strength,
        "useful_gods": ",".join(useful) or "需细断",
        "taboo_gods": ",".join(taboo) or "需细断",
    }


def _build_yearly_system_prompt(rule_primer: str) -> str:
    return f"""你是一位坐在对面、擅长大运流年推演的命理师。你不是在写年运报告，而是在逐年告诉命主他接下来会经历什么。语气像真人聊天：直接、有温度、有画面感。

表达风格（必须严格执行）：
1. 用第二人称"你"和第一人称"我"，像逐年讲给命主听。例如："我看你这一年……""你这一运要注意的是……""说白了，这几年你……"
2. 禁止公文式、条目式结构。不要把每一年写成"事业、财运、感情、健康"四栏空话。
3. 每一年 overview 要像一句话把这一年的"大运背景 + 流年触发 + 会出什么事"串起来，有叙事感。
4. 四个领域结论要像小段对话，不是标签。例如不要写"事业：有晋升机会"，要写"这一年事业上会有变动，如果主动争取，上半年有机会往上走一步"。
5. 少用"适合""注意""宜""不宜""建议"等模板词，换成"你可以……""你要当心……""对你来说……"
6. `overall_guidance` 要像你最后给命主的几句交代，有先后、有轻重，不要写成分点总结。
7. 允许有口语化衔接词和轻微重复，让命主感觉是在听人说话。
8. 输出必须是合法 JSON，不要有任何额外解释文字。

分析原则：
1. 必须以命局为体、大运为纲、流年为应。每一年都要说清楚：它落在哪一步大运、该步大运对命局的作用、流年干支如何引发这一年的吉凶。
2. 每步大运先点明：天干十神、地支与命局的关系、该运主题（例如：财官旺地、印比扶身、食伤生财等）。
3. 逐年分析时，必须结合流年天干十神、地支与命局/大运的刑冲合害，给出具体判断。例如：
   - “丙午年七杀透干，与原局午午自刑，你这一年工作压力会明显变大，容易跟上头起冲突，跳槽不是好时机。”
   - “戊申年偏印坐禄，有贵人愿意拉你一把，考证、进修或者争取晋升都对你有利。”
4. 事业、财运、感情、健康四个领域禁止写空话。要给出命主能听懂、能操作的判断，比如"上半年有机会跳槽，但薪资涨幅有限""偏财不稳，别追热点""有桃花，但多半是烂桃花""肠胃和睡眠要注意"。
5. 若某年与大运、命局形成明显冲克（子午冲、寅申冲、卯酉冲、辰戌冲、巳亥冲、丑未冲），必须在 overview 或 caution 中明确指出。
6. 每一年 overview 控制在 80 字以内，必须包含：本年所在大运、流年十神作用、关键触发（十神/合冲刑害）、具体事件预测。
7. 四个领域每栏控制在 60 字以内，caution 控制在 40 字以内。整体要凝练、有断语。
8. 如果某一年没有明显吉凶事件，允许写“这一年没什么大动静，平顺过渡”，禁止硬凑四栏套话。
9. 六亲断语要像你随口讲起命主家里关系，按年柱、月柱、日柱、时柱逐柱带过。
10. 每一年输出 `key_event`：有明显事件时直接点明（结婚、离婚、升职、跳槽、破财、发财、生子、手术、搬迁、创业失败、官司、桃花、学业、长辈灾等）；无明显事件时写“平稳过渡，无重大事件”。禁止为凑数而编造事件。
11. 全局 `milestones` 只汇总真正高置信度的人生节点：
    - 婚动/结婚：流年或大运冲合夫妻宫，或配偶星透干合身。
    - 离婚/感情危机：夫妻宫被冲刑穿，且配偶星受制。
    - 生子：子女宫或子女星被引动。
    - 事业转折：官杀/印星/食伤发生重大变化。
    - 财富转折：财星、财库、食伤被强烈引动。
    - 重大疾病：对应脏腑被严重冲克。
    - 搬迁：驿马被冲。
    证据不足时宁可留空数组，禁止每年硬凑一个节点。

输出格式：
{{
  "dayun_summary": [
    {{"pillar": "大运干支", "start_age": 数字, "end_age": 数字, "theme": "该运主题（含十神与命局关系）", "focus": "重点关注（必须具体）"}}
  ],
  "yearly_analysis": [
    {{
      "year": 2024,
      "pillar": "流年干支",
      "overview": "整体运势，必须点明所在大运、流年十神作用、关键触发与具体事件",
      "key_event": "有明显事件直接断；无明显事件写'平稳过渡，无重大事件'",
      "career": "事业具体建议",
      "wealth": "财运具体建议",
      "marriage": "感情具体建议",
      "health": "健康具体建议",
      "caution": "注意事项，突出刑冲合害或重大决策提示"
    }}
  ],
  "liuqin_analysis": "六亲断语，按年柱、月柱、日柱、时柱逐柱说明：天干十神主何六亲，地支及藏干主何六亲",
  "milestones": [
    {{"year": 2026, "age": 33, "type": "婚动", "description": "夫妻宫被冲，感情关系剧变，可能结婚或分手"}}
  ],
  "overall_guidance": "综合建议，300字以内，分阶段总结",
  "confidence": "high|medium|low",
  "caveats": ["至少2条具体注意事项"]
}}

禁用词汇清单（绝对禁止出现，同义词也禁止）：顺其自然、按部就班、按年度节奏推进、量入为出、规律作息、平稳、平顺、逐步、稳步前进、保持现状、整体平顺、心态平和、多沟通、多包容、低调行事、宜守不宜攻、守成、观望、谨慎、注意即可、无大碍、总体尚可、一般、普通、平淡。

基础知识参考：
{rule_primer}
"""


def _build_yearly_user_prompt(
    bazi: str,
    gender: str,
    dayun: List[Dict],
    liunian: List[Dict],
    mode: str,
    profile: Dict,
    yearly_rels: List[Dict],
    birth_year: int,
) -> str:
    dayun_text = "\n".join(
        f"{d['start_age']}-{d['end_age']}岁: {d['pillar']} "
        f"({birth_year + int(d['start_age'])}-{birth_year + int(d['end_age']) - 1})"
        for d in dayun
    )

    def _dayun_for_year(year: int) -> str:
        age = year - birth_year
        for d in dayun:
            if d["start_age"] <= age < d["end_age"]:
                return d["pillar"]
        return dayun[-1]["pillar"] if dayun else "未知"

    # Build structural facts string
    stem_shishen_text = "、".join(
        f"{k}：{v}" for k, v in profile.get("stem_shishen", {}).items()
    )
    branch_shishen_text = "、".join(
        f"{k}：{v}" for k, v in profile.get("branch_shishen", {}).items()
    )
    palace_text = profile.get("palace_text", "")
    structural_facts = f"""【命局结构事实】（由程序严格计算，你必须以此为依据，禁止自行发明不存在的合化、冲克）
- 日主：{profile.get("day_master", "")}
- 月令：{profile.get("month_branch", "")}
- 天干十神：{stem_shishen_text}
- 地支十神（本气）：{branch_shishen_text}
- 五行统计（天干0.5+地支1.0）：{profile.get("element_weighted_text", "")}
- 参考旺衰：{profile.get("strength", "")}
- 参考用神：{profile.get("useful_gods", "")}
- 参考忌神：{profile.get("taboo_gods", "")}
- 天干合化：{profile.get("tian_gan_he_text", "无")}
- 地支合冲刑害：{profile.get("di_zhi_relations_text", "无")}
- 空亡：{profile.get("kong_wang", "")}
- 宫位：{palace_text}
- 六亲：{profile.get("liuqin_text", "")}"""

    liunian_text = "\n".join(
        f"{y['year']}年: {y['pillar']}（{_dayun_for_year(y['year'])}大运）"
        for y in liunian
    )

    # Per-year structural facts
    day_branch = profile.get("branches", ["", "", "", ""])[2]
    year_facts_lines = []
    for r in yearly_rels:
        palace_note = ""
        if day_branch:
            ly_branch = r["liunian_pillar"][1]
            dy_branch = r["dayun_pillar"][1]
            if ly_branch == day_branch or dy_branch == day_branch:
                palace_note = f"；夫妻宫日支{day_branch}伏吟"
            elif (ly_branch, day_branch) in _SIX_CHONG or (day_branch, ly_branch) in _SIX_CHONG:
                palace_note = f"；夫妻宫日支{day_branch}与流年支{ly_branch}相冲（反吟）"
            elif (dy_branch, day_branch) in _SIX_CHONG or (day_branch, dy_branch) in _SIX_CHONG:
                palace_note = f"；夫妻宫日支{day_branch}与大运支{dy_branch}相冲（反吟）"
            else:
                palace_note = f"；夫妻宫日支{day_branch}本年未受冲合刑害"
        line = (
            f"{r['year']}年 {r['liunian_pillar']}（{r['dayun_pillar']}大运）："
            f"流年干{r['liunian_stem_shishen']}、流年支{r['liunian_branch_shishen']}；"
            f"天干合：{r['tian_gan_he_text']}；"
            f"地支关系：{r['di_zhi_relations_text']}{palace_note}"
        )
        year_facts_lines.append(line)
    year_facts_text = "\n".join(year_facts_lines)

    # Group liunian by dayun for clearer prompting.
    def _dayun_for_year(year: int) -> Optional[Dict]:
        age = year - birth_year
        for d in dayun:
            if d["start_age"] <= age < d["end_age"]:
                return d
        return dayun[-1] if dayun else None

    grouped_lines: List[str] = []
    for d in dayun:
        years_in_d = [y for y in liunian if d["start_age"] <= (y["year"] - birth_year) < d["end_age"]]
        if not years_in_d:
            continue
        line_years = "、".join(f"{y['year']} {y['pillar']}" for y in years_in_d)
        grouped_lines.append(
            f"{d['pillar']} 大运（{d['start_age']}-{d['end_age']}岁，"
            f"{birth_year + int(d['start_age'])}-{birth_year + int(d['end_age']) - 1}年）：{line_years}"
        )
    grouped_liunian_text = "\n".join(grouped_lines) if grouped_lines else liunian_text

    scope = "未来10年" if mode == "10y" else "一生（到80岁）"
    if mode == "10y":
        yearly_instruction = f"""流年结构事实（必须以这些事实为依据，禁止编造）：
{year_facts_text}

大运与流年分组（必须按此分组输出逐年分析，每一年都要先说它落在哪一步大运）：
{grouped_liunian_text}

表达风格要求：
- 像真人命理师逐年讲给命主听，用"你"和"我"。
- 禁止"首先……其次……综上……"等条目式结构。
- 每一年 overview 要像一句话把"大运背景 + 流年触发 + 会出什么事"串起来。
- 四个领域结论要像小段对话，有场景、有细节、有建议，不是标签。
- 少用"适合""注意""宜""不宜""建议"，多用"你可以……""你要当心……""对你来说……"

请严格按指定 JSON 格式输出，并遵守：
- 只输出上面列出的大运和年份，禁止扩展范围。
- 每一年的 overview 必须严格以如下事实格式开头："{{流年干支}}，{{流年天干十神}}透干、{{流年地支十神}}坐支；所在{{大运干支}}，{{大运天干十神}}透干、{{大运地支十神}}坐支。" 然后接具体事件断语。
- 必须将命局、大运、流年三者结合：先说明大运对命局的作用，再说明流年如何在大运基础上引发事件。
- 涉及合化、冲克、刑害时，只能引用【命局结构事实】和【流年结构事实】中列出的内容，禁止自行发明。
- 涉及夫妻宫、父母宫、子女宫等宫位论断时，必须核对【宫位】事实：只有日支才是夫妻宫。禁止把年支、月支、时支或大运支/流年支之间的冲合错误归到夫妻宫。
- 特别重要：大运支与流年支的冲合（如丙辰大运遇庚戌流年之辰戌冲）只代表大运与流年互动，不等于冲日支/夫妻宫。只有当流年支或大运支与命局日支产生冲合刑害时，才允许说夫妻宫受影响。
- 正误示例：若日支为申，大运支为卯，流年支为酉，则卯酉冲是大运与流年之冲，不允许写“夫妻宫受冲”；若日支为申，流年支为寅，则寅申冲才允许写“冲夫妻宫”。
- 事业、财运、感情、健康四项，每一项必须给出“具体事件 + 触发原因 + 应验场景 + 时间/人物/金额细节”，不准只给方向性建议。
  - 错误示例（禁止）：“财运平平，宜守不宜攻”“事业有压力，需低调”“感情多沟通”“注意脾胃”。
  - 正确示例（必须达到此具体度）：
    - 事业：“辰戌冲开财库，原公司架构调整，大概率被调岗或裁员；若主动跳槽，3-6月机会最大，但新offer薪资涨幅有限，且新领导风格严厉。”
    - 财运：“丑未冲开月柱财库，母亲或长辈有医疗/房产支出，命主需贴补3-8万；自己忌做股票、虚拟货币，易因熟人消息亏损5万以上。”
    - 感情：“寅申冲日支夫妻宫，配偶因工作出差或异地产生误会，9-11月争吵高发，有冷战分居风险；单身者易遇短暂异地桃花，对方可能已婚或有前任纠缠。”
    - 健康：“金木相战，注意肝胆、筋骨、腰椎间盘，上半年慎防运动拉伤或交通事故，尤其注意农历三月、九月。”
- 每一年在 career/wealth/marriage/health 中，必须至少写出 1-2 个可验证的具体场景，并尽量包含：
  - 时间窗口：季度、农历月份、上下半年
  - 人物关系：父母、兄弟、配偶、子女、上司、同事、朋友、异性
  - 金额范围：具体数字区间（如 1-3万、5-10万）
  - 事件类型：升职、裁员、跳槽、创业失败、投资亏损、买房、分手、离婚、手术、车祸等
- 必须指出触发事件的关键因素：是哪个十神、哪组合冲刑害、哪一柱六亲被引动。
- 如果某年确实没有明显事件，允许该年 career/wealth/marriage/health 中部分写“无显著事件”，甚至四栏全写“无显著事件”也比编造强。
- 每一年输出 `key_event`：有明显事件时直接点明（如：结婚、离婚、升职、跳槽、破财、发财、生子、手术、搬迁、创业失败、官司、桃花等）；无明显事件时必须写“平稳过渡，无重大事件”。禁止为凑数编造事件。
- 全局 `milestones` 只汇总真正高置信度的人生节点（婚动、生子、事业转折、财富转折、重大疾病、搬迁等），证据不足时留空数组 `[]`，禁止每年硬凑一个节点。
- 禁用词汇：逐步、平稳、顺其自然、按部就班、宜守不宜攻、量入为出、规律作息、保持现状、整体平顺、稳步前进、心态平和、多沟通、多包容、低调行事、谨慎、观望、无大碍、总体尚可、一般、普通、平淡、按年度节奏推进。
- liuqin_analysis 必须独立输出，按以下格式逐柱写：
  - 年柱XX：主祖上/父母，说明祖上家境、父母关系及对命主早年的影响。
  - 月柱XX：主父母/兄弟，说明家庭环境、兄弟缘、事业根基。
  - 日柱XX：主命主自身与配偶，说明命主性格、配偶特点、婚姻基调。
  - 时柱XX：主子女/晚辈，说明子女缘、晚年运势、下属关系。
- 不要输出任何额外文字或 markdown 代码块。"""
    else:
        yearly_instruction = """请重点分析每步大运的主题、与命局用神忌神的关系，以及一生运势的分阶段总结。
- 不需要输出逐年流年（yearly_analysis 可留空数组 []）。
- 必须输出 dayun_summary、liuqin_analysis、overall_guidance、milestones 和 caveats。
- milestones 只需列出人生中最重要的几个节点（婚动、事业转折、财富转折、重大疾病、搬迁等），不必逐年列出。
- 涉及合化、冲克、刑害时，只能引用【命局结构事实】中列出的内容，禁止自行发明。
- liuqin_analysis 按年柱、月柱、日柱、时柱逐柱说明六亲状态。
- 不要输出任何额外文字或 markdown 代码块。"""
    return f"""请为以下八字做{scope}大运精排。

八字：{bazi}
性别：{"男" if gender == "male" else "女" if gender == "female" else "未知"}

{structural_facts}

大运列表（只分析这些大运，括号内为该运覆盖的公历年份）：
{dayun_text}

{yearly_instruction}
"""


def _rule_based_yearly(
    bazi: str,
    dayun: List[Dict],
    liunian: List[Dict],
    birth_year: int,
    last_error: Optional[Exception] = None,
) -> Dict:
    """Return a structured fallback that combines dayun and liunian."""
    from tools.bazi_ai.bazi_validator import extract_pillars

    try:
        pillars = extract_pillars(bazi)
        day_master_stem = pillars[2][0]
    except ValueError:
        day_master_stem = ""

    # 五行与阴阳
    _STEM_ELEMENT = {
        "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
        "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
    }
    _YIN_YANG = {
        "甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳",
        "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴",
    }
    _GENERATING = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    _RESTRAINING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    _BRANCH_MAIN = {
        "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土",
        "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金",
        "戌": "土", "亥": "水",
    }
    _SIX_HE = {
        ("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
        ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土",
    }
    _SIX_CHONG = {
        ("子", "午"), ("丑", "未"), ("寅", "申"),
        ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
    }

    dm_element = _STEM_ELEMENT.get(day_master_stem, "")
    dm_yy = _YIN_YANG.get(day_master_stem, "")

    def _shishen(target_stem: str) -> str:
        """Return the 十神 of target_stem relative to day master."""
        if not day_master_stem or target_stem == day_master_stem:
            return "比肩"
        t_el = _STEM_ELEMENT.get(target_stem, "")
        t_yy = _YIN_YANG.get(target_stem, "")
        if not dm_element or not t_el:
            return "未知"
        same_yy = dm_yy == t_yy
        if t_el == dm_element:
            return "劫财" if same_yy else "比肩"
        if _GENERATING.get(dm_element) == t_el:
            return "食神" if same_yy else "伤官"
        if _RESTRAINING.get(dm_element) == t_el:
            return "偏财" if same_yy else "正财"
        if _GENERATING.get(t_el) == dm_element:
            return "偏印" if same_yy else "正印"
        if _RESTRAINING.get(t_el) == dm_element:
            return "七杀" if same_yy else "正官"
        return "未知"

    def _element_relation(target_element: str) -> str:
        if not dm_element or not target_element:
            return "平"
        if target_element == dm_element:
            return "比劫"
        if _GENERATING.get(dm_element) == target_element:  # 我生它 -> 泄耗
            return "泄耗"
        if _GENERATING.get(target_element) == dm_element:  # 它生我 -> 生助
            return "生助"
        if _RESTRAINING.get(dm_element) == target_element:  # 我克它 -> 克制
            return "克制"
        if _RESTRAINING.get(target_element) == dm_element:  # 它克我 -> 受克
            return "受克"
        return "平"

    def _pillar_relation(pillar: str) -> Dict[str, str]:
        stem_shishen = _shishen(pillar[0])
        stem_rel = _element_relation(_STEM_ELEMENT.get(pillar[0], ""))
        branch_rel = _element_relation(_BRANCH_MAIN.get(pillar[1], ""))
        return {
            "stem_shishen": stem_shishen,
            "stem_rel": stem_rel,
            "branch_rel": branch_rel,
        }

    def _branch_interaction(b1: str, b2: str) -> Optional[str]:
        pair = (b1, b2)
        if pair in _SIX_CHONG or pair[::-1] in _SIX_CHONG:
            return "冲"
        for he in _SIX_HE:
            if pair == he or pair[::-1] == he:
                return f"合({_SIX_HE[he]})"
        return None

    def _dayun_focus(stem_rel: str, branch_rel: str) -> str:
        good = stem_rel in ("生助", "比劫") or branch_rel in ("生助", "比劫")
        bad = stem_rel == "受克" or branch_rel == "受克"
        if good and not bad:
            return "宜进取、拓展，把握贵人助力"
        if bad and not good:
            return "宜稳守、避险，注意健康与口舌"
        return "机遇与压力并存，稳中求进"

    def _build_overview(
        yr_pillar: str,
        dy_pillar: str,
        yr_stem_rel: str,
        yr_branch_rel: str,
        dy_stem_rel: str,
        dy_branch_rel: str,
        interaction: Optional[str],
    ) -> str:
        parts = [f"流年{yr_pillar}（{dy_pillar}大运）"]
        if yr_stem_rel == dy_stem_rel:
            parts.append(f"天干{yr_stem_rel}势能增强")
        else:
            parts.append(f"天干{yr_stem_rel}，大运天干{dy_stem_rel}")
        if interaction:
            parts.append(f"地支{interaction}")
        else:
            parts.append(f"地支{yr_branch_rel}")
        return "，".join(parts)

    def _build_domains(
        yr_stem: str,
        yr_branch: str,
        yr_stem_rel: str,
        yr_branch_rel: str,
        dy_stem: str,
        dy_branch: str,
        dy_stem_rel: str,
        dy_branch_rel: str,
        interaction: Optional[str],
        age: int,
    ) -> Dict[str, str]:
        yr_stem_shishen = _shishen(yr_stem)
        yr_branch_shishen = _shishen(yr_branch)
        dy_stem_shishen = _shishen(dy_stem)
        chong = interaction and interaction.startswith("冲")

        # Only emit specific warnings when there is a concrete trigger.
        has_strong_trigger = chong or (yr_stem_rel == "受克" and yr_branch_rel in ("受克", "泄耗"))

        def career() -> str:
            if not has_strong_trigger:
                return "事业无显著波动"
            if yr_stem_shishen in ("正官", "七杀") or dy_stem_shishen in ("正官", "七杀"):
                return "官杀引动，职场压力增加，可能面临考核或岗位调整"
            if yr_stem_shishen in ("正印", "偏印") or dy_stem_shishen in ("正印", "偏印"):
                return "印星生身，利考证、进修或争取晋升"
            if yr_stem_shishen in ("食神", "伤官") or dy_stem_shishen in ("食神", "伤官"):
                return "食伤泄秀，创意输出多，项目推进可能反复"
            if yr_stem_shishen in ("比肩", "劫财") or dy_stem_shishen in ("比肩", "劫财"):
                return "比劫争竞，合作方或同事分夺资源"
            if chong:
                return "地支逢冲，工作环境或岗位职责可能有变动"
            return "事业无显著波动"

        def wealth() -> str:
            if not has_strong_trigger:
                return "财运无显著波动"
            if yr_stem_shishen in ("正财", "偏财") or dy_stem_shishen in ("正财", "偏财"):
                if yr_stem_shishen in ("比肩", "劫财") or dy_stem_shishen in ("比肩", "劫财"):
                    return "财星透干但比劫同现，易因合作、借贷分歧破财"
                return "财星引动，有收入增加或偏财机会，但需见好就收"
            if yr_stem_shishen in ("比肩", "劫财") or dy_stem_shishen in ("比肩", "劫财"):
                return "比劫夺财，开销增大或被朋友拖累"
            if yr_stem_rel == "受克" or dy_stem_rel == "受克":
                return "求财受阻，现金流紧张，避免扩张与担保"
            return "财运无显著波动"

        def marriage() -> str:
            if not has_strong_trigger:
                return "感情无显著事件"
            if chong:
                return "夫妻宫或感情宫被冲，争吵冷战增多"
            if yr_stem_shishen in ("正财", "偏财", "正官", "七杀"):
                return "异性缘被引动，桃花机会多，需分辨正缘与烂桃花"
            if yr_stem_shishen in ("伤官", "劫财"):
                return "感情中易因自我或竞争起摩擦"
            return "感情无显著事件"

        def health() -> str:
            if not has_strong_trigger:
                return "健康无显著隐患"
            if chong:
                return "地支相冲，注意突发伤病、交通安全与急性炎症"
            if yr_stem_rel == "受克" and yr_branch_rel == "受克":
                return "流年干支皆克耗日主，免疫力下降，需防慢性病复发"
            if yr_stem_rel == "泄耗" and yr_branch_rel == "泄耗":
                return "泄耗过重，精力不济，注意睡眠与消化系统"
            if yr_branch_shishen in ("七杀", "伤官"):
                return "七杀/伤官临支，注意筋骨、肝胆与意外伤害"
            return "健康无显著隐患"

        qualifier = ""
        if age < 10:
            qualifier = "（童年阶段，多反映家庭与成长环境）"
        elif age < 20:
            qualifier = "（青少年阶段，多与学业、家庭关系相关）"
        elif age > 60:
            qualifier = "（中老年阶段，多与退休、健康、子女相关）"

        return {
            "career": career() + qualifier,
            "wealth": wealth() + qualifier,
            "marriage": marriage() + qualifier,
            "health": health(),
        }

    def _build_caution(
        yr_stem: str,
        yr_branch: str,
        yr_stem_rel: str,
        yr_branch_rel: str,
        interaction: Optional[str],
    ) -> str:
        if interaction and interaction.startswith("冲"):
            return f"流年{yr_branch}与大运/原局相冲，防突发变动与冲突"
        if yr_stem_rel == "受克" and yr_branch_rel == "受克":
            return "流年干支皆不利日主，重大决策宜保守"
        if yr_stem_rel == "受克":
            return f"流年天干{yr_stem}克耗日主，注意人际与决策"
        if yr_branch_rel == "受克":
            return f"流年地支{yr_branch}不利，注意健康与出行"
        if yr_stem_rel in ("生助", "比劫"):
            return "得助之年可进取，但忌冲动与过度扩张"
        return "本年无重大刑冲，按常规节奏行事"

    def _build_key_event(
        yr_stem_shishen: str,
        yr_branch_shishen: str,
        yr_stem_rel: str,
        yr_branch_rel: str,
        interaction: Optional[str],
        domains: Dict[str, str],
    ) -> str:
        # Keep rule-based fallback conservative: only flag a key event when
        # there is a strong concrete trigger. Default to "no major event" to
        # avoid dramatizing every year.
        if interaction and interaction.startswith("冲"):
            return "地支逢冲，可能有工作、感情或居住环境的变动"
        if yr_stem_rel == "受克" and yr_branch_rel == "受克":
            return "流年干支皆不利日主，压力较大，宜保守行事"
        return "平稳过渡，无重大事件"

    # Dayun summaries with simple themes
    dayun_summary = []
    for d in dayun:
        rel = _pillar_relation(d["pillar"])
        stem_shen = rel["stem_shishen"]
        theme_parts = [f"大运{d['pillar']}"]
        if rel["stem_rel"] in ("生助", "比劫"):
            theme_parts.append(f"天干{stem_shen}帮身")
        elif rel["stem_rel"] == "受克":
            theme_parts.append(f"天干{stem_shen}施压")
        elif rel["stem_rel"] == "泄耗":
            theme_parts.append(f"天干{stem_shen}泄秀")
        else:
            theme_parts.append(f"天干{stem_shen}")
        if rel["branch_rel"] in ("生助", "比劫"):
            theme_parts.append("地支得根")
        elif rel["branch_rel"] == "受克":
            theme_parts.append("地支逢克")
        dayun_summary.append(
            {
                "pillar": d["pillar"],
                "start_age": d["start_age"],
                "end_age": d["end_age"],
                "theme": "，".join(theme_parts),
                "focus": _dayun_focus(rel["stem_rel"], rel["branch_rel"]),
            }
        )

    # Yearly analysis combining dayun
    yearly_analysis = []
    for y in liunian:
        age = y["year"] - birth_year
        active_dayun = None
        for d in dayun:
            if d["start_age"] <= age < d["end_age"]:
                active_dayun = d
                break
        if active_dayun is None and dayun:
            active_dayun = dayun[-1]

        yr_rel = _pillar_relation(y["pillar"])
        yr_stem_rel = yr_rel["stem_rel"]
        yr_branch_rel = yr_rel["branch_rel"]

        if active_dayun is not None:
            dy_rel = _pillar_relation(active_dayun["pillar"])
            dy_stem_rel = dy_rel["stem_rel"]
            dy_branch_rel = dy_rel["branch_rel"]
            yr_stem, yr_branch = y["pillar"][0], y["pillar"][1]
            dy_stem, dy_branch = active_dayun["pillar"][0], active_dayun["pillar"][1]
            interaction = _branch_interaction(yr_branch, dy_branch)
            overview = _build_overview(
                y["pillar"], active_dayun["pillar"], yr_stem_rel, yr_branch_rel,
                dy_stem_rel, dy_branch_rel, interaction,
            )
            domains = _build_domains(
                yr_stem, yr_branch, yr_stem_rel, yr_branch_rel,
                dy_stem, dy_branch, dy_stem_rel, dy_branch_rel, interaction, age,
            )
            caution = _build_caution(
                yr_stem, yr_branch, yr_stem_rel, yr_branch_rel, interaction,
            )
            key_event = _build_key_event(
                _shishen(yr_stem), _shishen(yr_branch), yr_stem_rel, yr_branch_rel, interaction, domains
            )
        else:
            overview = f"流年{y['pillar']}，日主{yr_stem_rel}"
            domains = {
                "career": "本年事业无显著波动",
                "wealth": "本年财运无显著波动",
                "marriage": "本年感情无显著事件",
                "health": "本年健康无显著隐患",
            }
            caution = "无大运信息，流年按原局简断"
            key_event = "本年运势相对平稳，无重大事件"
        yearly_analysis.append(
            {
                "year": y["year"],
                "pillar": y["pillar"],
                "overview": overview,
                "key_event": key_event,
                "career": domains["career"],
                "wealth": domains["wealth"],
                "marriage": domains["marriage"],
                "health": domains["health"],
                "caution": caution,
            }
        )

    # Derive simple milestones from yearly key events.
    milestones = []
    for y in yearly_analysis:
        event = y.get("key_event", "")
        age = y["year"] - birth_year
        milestone_type = None
        if "职场" in event or "工作" in event or "跳槽" in event:
            milestone_type = "事业转折"
        elif "财星" in event or "破财" in event or "投资" in event:
            milestone_type = "财富转折"
        elif "感情" in event or "夫妻" in event or "婚姻" in event:
            milestone_type = "婚动"
        elif "健康" in event:
            milestone_type = "健康"
        elif "居住" in event or "搬迁" in event:
            milestone_type = "搬迁"
        if milestone_type and "无重大" not in event:
            milestones.append({
                "year": y["year"],
                "age": age,
                "type": milestone_type,
                "description": event,
            })

    user_caveats = [
        "当前为规则化兜底分析，流年细节可能不够具体。",
        "算法排盘，结果仅供参考。",
    ]

    return {
        "dayun_summary": dayun_summary,
        "yearly_analysis": yearly_analysis,
        "liuqin_analysis": "",
        "milestones": milestones,
        "overall_guidance": "当前为本地规则兜底分析，已将大运与流年结合推断。",
        "confidence": "low",
        "caveats": user_caveats,
        "_rule_based": True,
    }


async def analyze_yearly(
    bazi: str,
    *,
    gender: str = "",
    birth_date: str = "",
    birth_time: str = "00:00",
    calendar_type: str = "solar",
    mode: str = "10y",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    knowledge_base_path: Optional[Path] = None,
) -> Dict:
    """Analyze yearly luck (liunian) based on dayun and birth info.

    *mode* can be ``"10y"`` for the next 10 years, or ``"lifetime"`` for a
    full reading until age 80.
    """
    normalized = normalize_bazi(bazi)
    if normalized is None:
        return {
            "error": "无效的八字格式",
            "dayun_summary": [],
            "yearly_analysis": [],
            "overall_guidance": "",
        }
    bazi = normalized

    current_year = datetime.now().year
    try:
        birth_year = int(birth_date.split("-")[0]) if birth_date else current_year
    except (ValueError, AttributeError):
        birth_year = current_year

    until_age = 80
    dayun = calendar.dayun_list(
        bazi,
        gender,
        birth_date,
        birth_time,
        calendar_type,
        until_age=until_age,
    )

    if mode == "10y":
        start_year = current_year
        end_year = current_year + 9
    else:
        start_year = birth_year
        end_year = birth_year + until_age - 1

    liunian = calendar.liunian_list(start_year, end_year)

    # Filter dayun to those overlapping the analyzed years.
    dayun_active = [
        d
        for d in dayun
        if d["end_age"] >= (start_year - birth_year)
        and d["start_age"] <= (end_year - birth_year)
    ]

    rule_primer_paths = [Path("./bazi_knowledge/rule_primer.md")]
    if knowledge_base_path is not None and knowledge_base_path.exists():
        rule_primer_paths.append(knowledge_base_path)
    rule_primer = await _build_rule_primer(rule_primer_paths, max_chars=12000)
    profile = bazi_structural.structural_profile(bazi) or {}
    yearly_rels = []
    for y in liunian:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun_active if d["start_age"] <= age < d["end_age"]),
            dayun_active[-1] if dayun_active else None,
        )
        if active is None:
            continue
        rel = bazi_structural.yearly_relations(bazi, active["pillar"], y["pillar"])
        if rel is not None:
            rel["year"] = y["year"]
            rel["age"] = age
            yearly_rels.append(rel)

    system_prompt = _build_yearly_system_prompt(rule_primer)
    user_prompt = _build_yearly_user_prompt(
        bazi, gender, dayun_active, liunian, mode, profile, yearly_rels, birth_year
    )

    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key or aiohttp is None:
        return _rule_based_yearly(bazi, dayun_active, liunian, birth_year)

    base = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    mdl = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

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
                    parsed = _parse_json(content, bazi, [])
                    if "error" in parsed:
                        return parsed
                    if parsed.get("parse_error"):
                        raw_snippet = (parsed.get("raw_content") or "")[:500]
                        logger.warning(
                            "流年分析 JSON 解析失败，使用兜底分析。原始输出片段：%s",
                            raw_snippet,
                        )
                        return _rule_based_yearly(
                            bazi,
                            dayun_active,
                            liunian,
                            birth_year,
                        )
                    # Ensure required keys exist.
                    parsed.setdefault("dayun_summary", [])
                    parsed.setdefault("yearly_analysis", [])
                    parsed.setdefault("liuqin_analysis", "")
                    parsed.setdefault("milestones", [])
                    parsed.setdefault("overall_guidance", "")
                    parsed.setdefault("confidence", "low")
                    # Ensure each yearly entry has a key_event.
                    for y in parsed["yearly_analysis"]:
                        if isinstance(y, dict) and "key_event" not in y:
                            y["key_event"] = ""
                    parsed["caveats"] = list(parsed.get("caveats", []))
                    # Strip any technical fallback markers that the model may echo.
                    parsed["caveats"] = [
                        c for c in parsed["caveats"]
                        if not any(m in c for m in ("AI 输出无法解析", "服务暂时不可用", "已切换兜底", "原始输出"))
                    ]
                    parsed["caveats"].append("算法排盘，结果仅供参考")

                    if mode == "lifetime":
                        # Lifetime mode: avoid huge AI output truncation by
                        # letting the model produce dayun themes only, and fill
                        # yearly_analysis with the age-aware rule-based fallback.
                        rule_fallback = _rule_based_yearly(
                            bazi, dayun_active, liunian, birth_year
                        )
                        parsed["yearly_analysis"] = rule_fallback.get("yearly_analysis", [])
                        if not parsed.get("overall_guidance"):
                            parsed["overall_guidance"] = rule_fallback.get("overall_guidance", "")
                        existing = set(parsed["caveats"])
                        for c in rule_fallback.get("caveats", []):
                            # Avoid the generic fallback message because lifetime
                            # mode does use AI for dayun themes.
                            if "当前为本地规则分析" in c:
                                continue
                            if c not in existing:
                                parsed["caveats"].append(c)
                                existing.add(c)
                        return parsed

                    return _validate_yearly_output(
                        parsed, bazi, dayun_active, liunian, birth_year
                    )
        except ClientResponseError as exc:
            logger.warning(
                "流年分析请求失败 (attempt %d/2): status=%s message=%s",
                attempt,
                exc.status,
                exc.message,
            )
            if attempt < 2:
                await asyncio.sleep(2.0)
        except asyncio.TimeoutError:
            logger.warning("流年分析请求超时 (attempt %d/2)", attempt)
            if attempt < 2:
                await asyncio.sleep(2.0)
        except Exception as exc:
            logger.warning("流年分析请求失败 (attempt %d/2): %s", attempt, exc)
            if attempt < 2:
                await asyncio.sleep(2.0)

    return _rule_based_yearly(bazi, dayun_active, liunian, birth_year)


_TEMPLATE_PHRASES = {
    "顺其自然",
    "按部就班",
    "按年度节奏推进",
    "量入为出",
    "规律作息",
    "整体平顺",
    "稳步前进",
    "保持现状",
    "心态平和",
    "多沟通",
    "多包容",
    "低调行事",
    "宜守不宜攻",
    "财运平平",
    "事业平平",
    "感情平平",
}


def _is_short_yearly(y: Dict) -> bool:
    """Return True if all four domain fields are too short."""
    fields = ("career", "wealth", "marriage", "health")
    values = [str(y.get(k, "")).strip() for k in fields]
    return all(len(v) < 15 for v in values)


def _is_template_yearly(yearly_analysis: List[Dict]) -> bool:
    """Return True if too many yearly entries use generic filler phrases."""
    if not yearly_analysis:
        return True
    template_count = 0
    for y in yearly_analysis:
        text = " ".join(
            str(y.get(k, "")) for k in ("overview", "career", "wealth", "marriage", "health")
        )
        if any(phrase in text for phrase in _TEMPLATE_PHRASES):
            template_count += 1
        elif _is_short_yearly(y):
            template_count += 1
    # If more than 25% look templated, treat the whole result as low quality.
    return template_count / len(yearly_analysis) > 0.25


# Relations strong enough to justify a concrete yearly prediction.
_STRONG_BRANCH_RELATIONS = {"冲", "刑", "害", "破", "绝"}


def _has_strong_yearly_trigger(
    bazi: str,
    dayun_pillar: str,
    liunian_pillar: str,
) -> bool:
    """Return True if the liunian year has a strong trigger vs the day branch."""
    from tools.bazi_ai.bazi_validator import extract_pillars

    try:
        pillars = extract_pillars(bazi)
        day_branch = pillars[2][1]
    except ValueError:
        return False

    ly_branch = liunian_pillar[1]
    dy_branch = dayun_pillar[1]

    # 伏吟 / 反吟 on the day branch.
    if ly_branch == day_branch or dy_branch == day_branch:
        return True

    rel = bazi_structural.yearly_relations(bazi, dayun_pillar, liunian_pillar)
    if rel is None:
        return False

    for a, b, t, _ in rel.get("di_zhi_relations", []):
        if "日支" not in (a, b):
            continue
        other = a if b == "日支" else b
        # Only count relations caused by liunian or dayun branch.
        if not (other.startswith("流年支") or other.startswith("大运支")):
            continue
        if t in _STRONG_BRANCH_RELATIONS:
            return True
        # 合日支 sometimes changes the spouse-palace nature; treat as moderate trigger.
        if t == "合":
            return True

    # 天克地冲 between liunian and dayun is also a strong trigger.
    ly_stem, dy_stem = liunian_pillar[0], dayun_pillar[0]
    _STEM_ELEMENT = {
        "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
        "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
    }
    _RESTRAINING = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    _SIX_CHONG = {
        ("子", "午"), ("丑", "未"), ("寅", "申"),
        ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
    }
    ly_el = _STEM_ELEMENT.get(ly_stem)
    dy_el = _STEM_ELEMENT.get(dy_stem)
    stems_clash = (
        ly_el is not None
        and dy_el is not None
        and ly_stem != dy_stem
        and (_RESTRAINING.get(ly_el) == dy_el or _RESTRAINING.get(dy_el) == ly_el)
    )
    branches_clash = (ly_branch, dy_branch) in _SIX_CHONG or (dy_branch, ly_branch) in _SIX_CHONG
    if stems_clash and branches_clash:
        return True

    return False


def _validate_yearly_output(
    result: Dict,
    bazi: str,
    dayun: List[Dict],
    liunian: List[Dict],
    birth_year: int,
) -> Dict:
    """Sanity-check yearly output; fall back to rule-based if too generic or factually off."""
    yearly = result.get("yearly_analysis", [])
    if not yearly or len(yearly) < len(liunian) * 0.8:
        logger.warning("流年分析返回年份不足，使用兜底分析")
        return _rule_based_yearly(bazi, dayun, liunian, birth_year)

    # Ensure each entry has the required fields.
    required = ("year", "pillar", "overview", "key_event", "career", "wealth", "marriage", "health", "caution")
    for y in yearly:
        if not all(k in y for k in required):
            logger.warning("流年分析字段缺失，使用兜底分析")
            return _rule_based_yearly(bazi, dayun, liunian, birth_year)

    # Sanitize all text fields in each yearly entry.
    text_keys = ("overview", "key_event", "career", "wealth", "marriage", "health", "caution")
    for y in yearly:
        if not isinstance(y, dict):
            continue
        for key in text_keys:
            y[key] = _sanitize_text(y.get(key, ""))

    # Tone down years that lack a strong structural trigger. The model tends to
    # invent dramatic key events for every year; we mark "no major event" when
    # the day branch is not directly involved in 冲/合/刑/害/伏吟. The detailed
    # domain advice is kept as a "what to watch" reminder, not as a prophecy.
    trigger_years: set = set()
    for y in yearly:
        if not isinstance(y, dict):
            continue
        age = y.get("year", birth_year) - birth_year
        active = next(
            (d for d in dayun if d["start_age"] <= age < d["end_age"]),
            dayun[-1] if dayun else None,
        )
        if active is None:
            continue
        if _has_strong_yearly_trigger(bazi, active["pillar"], y.get("pillar", "")):
            trigger_years.add(y["year"])
            continue
        y["key_event"] = "平稳过渡，无重大事件"
        # Keep the overview but append a note that no strong trigger exists.
        overview = y.get("overview", "")
        if overview and "无强触发" not in overview:
            y["overview"] = f"{overview}（本年无强触发，以上为常态提醒）"

    # Clean and de-duplicate milestones; keep only the most concrete ones,
    # and only from years that actually have a strong trigger.
    milestones = result.get("milestones", [])
    if isinstance(milestones, list):
        cleaned = []
        for m in milestones:
            if not isinstance(m, dict):
                continue
            year = m.get("year")
            age = m.get("age")
            try:
                year = int(year)
                age = int(age)
            except (TypeError, ValueError):
                continue
            cleaned.append({
                "year": year,
                "age": age,
                "type": str(m.get("type", "其他")).strip() or "其他",
                "description": _sanitize_text(str(m.get("description", "")).strip()),
            })
        # Score milestones by concreteness: prefer those with numbers, strong
        # triggers, or specific time references.
        trigger_words = ("冲", "合", "刑", "害", "破", "绝", "空", "墓", "伏吟", "反吟")
        def _milestone_score(m: Dict) -> int:
            desc = m.get("description", "")
            score = 0
            if re.search(r"\d", desc):
                score += 3
            if any(w in desc for w in trigger_words):
                score += 2
            if any(w in desc for w in ("年", "月", "季度", "上半年", "下半年")):
                score += 1
            return score
        cleaned = [m for m in cleaned if m["year"] in trigger_years]
        cleaned.sort(key=_milestone_score, reverse=True)
        # Cap density at roughly 3 milestones per 10-year window.
        max_milestones = max(1, len(yearly) // 3)
        result["milestones"] = cleaned[:max_milestones]
    else:
        result["milestones"] = []

    # Sanitize overall guidance and liuqin_analysis.
    if isinstance(result.get("overall_guidance"), str):
        result["overall_guidance"] = _sanitize_text(result["overall_guidance"])
    if isinstance(result.get("liuqin_analysis"), str):
        result["liuqin_analysis"] = _sanitize_text(result["liuqin_analysis"])

    if _is_template_yearly(yearly):
        logger.warning("流年分析模板化严重，使用兜底分析")
        return _rule_based_yearly(bazi, dayun, liunian, birth_year)

    # Check for common palace misattributions.
    direct_errors, vague_claims = _check_palace_claims(
        yearly, bazi, dayun, liunian, birth_year
    )
    if direct_errors:
        logger.warning("年份 %s 存在日支/夫妻宫事实误归，使用兜底分析", direct_errors)
        return _rule_based_yearly(bazi, dayun, liunian, birth_year)

    # Validate the opening 10-god template for each year.
    shishen_errors = _check_shishen_template(yearly, bazi, dayun, liunian, birth_year)
    if shishen_errors:
        logger.warning("年份 %s 十神模板与结构事实不符", shishen_errors)

    return result



def _check_palace_claims(
    yearly: List[Dict],
    bazi: str,
    dayun: List[Dict],
    liunian: List[Dict],
    birth_year: int,
) -> Tuple[List[int], List[int]]:
    """Return (direct_error_years, vague_claim_years) for spouse palace claims.

    Direct errors claim the *day branch* itself is collided/combined when it is not.
    Vague claims use "夫妻宫" loosely without the day branch being directly involved.
    """
    try:
        pillars = extract_pillars(bazi)
        day_branch = pillars[2][1]
    except ValueError:
        return [], []

    # Claims that explicitly name 日支 (the day branch) as acted upon.
    direct_patterns = (
        "日支受", "日支逢", "日支被", "冲日支", "合日支", "刑日支", "害日支",
        f"日支{day_branch}受", f"日支{day_branch}逢", f"日支{day_branch}被",
        f"日支{day_branch}冲", f"日支{day_branch}合", f"日支{day_branch}刑", f"日支{day_branch}害",
    )
    # Vague claims using the spouse-palace term without explicitly naming the day branch.
    # Any mention of 夫妻宫 is treated as a claim unless it is explicitly negated/stable.
    vague_palace_term = "夫妻宫"
    vague_negations = (
        "夫妻宫无", "夫妻宫不", "夫妻宫未", "夫妻宫没", "夫妻宫安静",
        "夫妻宫稳定", "夫妻宫平稳", "夫妻宫无事",
    )
    branch_map = {
        "年支": pillars[0][1],
        "月支": pillars[1][1],
        "日支": pillars[2][1],
        "时支": pillars[3][1],
    }

    def _is_day_branch_involved(y: Dict) -> bool:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun if d["start_age"] <= age < d["end_age"]),
            dayun[-1] if dayun else None,
        )
        if active is None:
            return False
        rel = bazi_structural.yearly_relations(bazi, active["pillar"], y["pillar"])
        if rel is None:
            return False
        interacting: set = set()
        for a, b, _, _ in rel.get("di_zhi_relations", []):
            for label in (a, b):
                if label.startswith("流年支") or label.startswith("大运支"):
                    continue
                interacting.add(branch_map.get(label, label[-1]))
        interacting.add(active["pillar"][1])
        ly_branch = y["pillar"][1]
        dy_branch = active["pillar"][1]
        if ly_branch == day_branch or dy_branch == day_branch:
            interacting.add(day_branch)
        if (ly_branch, day_branch) in _SIX_CHONG or (day_branch, ly_branch) in _SIX_CHONG:
            interacting.add(day_branch)
        if (dy_branch, day_branch) in _SIX_CHONG or (day_branch, dy_branch) in _SIX_CHONG:
            interacting.add(day_branch)
        return day_branch in interacting

    direct_errors: List[int] = []
    vague_claims: List[int] = []
    for y in yearly:
        text = " ".join(str(y.get(k, "")) for k in ("overview", "career", "wealth", "marriage", "health", "caution"))
        has_direct = any(p in text for p in direct_patterns)
        has_vague = (
            vague_palace_term in text
            and not any(neg in text for neg in vague_negations)
        )
        if not has_direct and not has_vague:
            continue
        involved = _is_day_branch_involved(y)
        if involved:
            continue
        if has_direct:
            direct_errors.append(y["year"])
        elif has_vague:
            vague_claims.append(y["year"])
    return direct_errors, vague_claims


def _check_shishen_template(
    yearly: List[Dict],
    bazi: str,
    dayun: List[Dict],
    liunian: List[Dict],
    birth_year: int,
) -> List[int]:
    """Return years where the opening 10-god template contradicts structural facts."""
    errors: List[int] = []
    for y in yearly:
        age = y["year"] - birth_year
        active = next(
            (d for d in dayun if d["start_age"] <= age < d["end_age"]),
            dayun[-1] if dayun else None,
        )
        if active is None:
            continue
        rel = bazi_structural.yearly_relations(bazi, active["pillar"], y["pillar"])
        if rel is None:
            continue
        overview = str(y.get("overview", ""))
        parts = overview.split("。", 1)
        first_sentence = parts[0] if parts else overview
        clauses = [c.strip() for c in first_sentence.split("；") if c.strip()]
        if len(clauses) < 2:
            errors.append(y["year"])
            continue
        ly_clause, dy_clause = clauses[0], clauses[1]
        all_shishen = {
            "比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印",
        }
        ly_found = {term for term in all_shishen if term in ly_clause}
        dy_found = {term for term in all_shishen if term in dy_clause}
        # The first clause should mention the expected liunian stem 10-god;
        # the second clause should mention the expected dayun stem 10-god.
        ly_ok = rel["liunian_stem_shishen"] in ly_found
        dy_ok = rel["dayun_stem_shishen"] in dy_found
        if not (ly_ok and dy_ok):
            logger.warning(
                "年份 %s 十神模板不符：流年干预期 %s 实际 %s，大运干预期 %s 实际 %s",
                y["year"], rel["liunian_stem_shishen"], ly_found,
                rel["dayun_stem_shishen"], dy_found,
            )
            errors.append(y["year"])
    return errors


def _structural_summary(bazi: str) -> List[str]:
    """Generate a few surface-level observations for the mock result."""
    try:
        pillars = extract_pillars(bazi)
    except ValueError:
        return ["八字格式无法解析"]

    year_pillar, month_pillar, day_pillar, hour_pillar = pillars
    day_stem = day_pillar[0]
    month_branch_char = month_pillar[1]

    stem_element = {
        "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
        "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
    }
    branch_element = {
        "寅": "木", "卯": "木", "巳": "火", "午": "火",
        "辰": "土", "戌": "土", "丑": "土", "未": "土",
        "申": "金", "酉": "金", "亥": "水", "子": "水",
    }
    generating = {
        "木": "火", "火": "土", "土": "金", "金": "水", "水": "木",
    }
    restraining = {
        "木": "土", "土": "水", "水": "火", "火": "金", "金": "木",
    }
    dm_element = stem_element.get(day_stem, "")
    mb_element = branch_element.get(month_branch_char, "")

    lines = [f"日主为 {day_stem}（{dm_element}），生于 {month_branch_char} 月（{mb_element}旺）"]

    if dm_element == mb_element:
        lines.append("月令与日主同气，得令有助")
    elif generating.get(dm_element) == mb_element:
        lines.append(f"月令 {mb_element} 泄耗日主 {dm_element}，需察食伤")
    elif restraining.get(mb_element) == dm_element:
        lines.append(f"月令 {mb_element} 生助日主 {dm_element}，得生")
    else:
        lines.append(f"月令 {mb_element} 克制日主 {dm_element}，宜寻通关")

    lines.append(f"四柱：{year_pillar} {month_pillar} {day_pillar} {hour_pillar}")
    return lines


def _mock_analyze(bazi: str, question: str, similar_cases: List[Dict]) -> Dict:
    """Return a realistic placeholder analysis when no API key is configured."""
    refs = [c.get("bazi") for c in similar_cases[:2]]
    pillars = extract_pillars(bazi)
    dm = pillars[2][0]
    mb = pillars[1][1]

    domain_focus = _detect_question_domains(question)
    domain_texts = {
        "career": "适合技术/专业型行业，早年需积累。",
        "wealth": "财星有根，中年后财源渐稳。",
        "marriage": "配偶宫平和，宜晚婚。",
        "health": "注意脾胃与呼吸系统。",
        "family": "与父母缘分中等，子女宫较稳。",
    }
    if domain_focus:
        default_text = "其他领域待详细排盘后补充。"
    else:
        default_text = "待 DeepSeek 分析"

    domain_analysis = {}
    for domain in ["career", "wealth", "marriage", "health"]:
        if domain in domain_focus:
            domain_analysis[domain] = domain_texts[domain]
        else:
            domain_analysis[domain] = default_text if domain_focus else domain_texts[domain]

    caveats = ["未调用真实模型，当前为结构展示", "请配置 DEEPSEEK_API_KEY 以获取 AI 深度分析"]
    if refs:
        caveats.append(f"参考相似案例：{', '.join(refs)}")

    personality = (
        f"日主为{dm}，性情随五行旺衰而定。身强则主观果断、自尊心强；"
        "身弱则思虑周全、善于借势。具体气质需结合十神与调候进一步判断。"
    )
    events = [
        "早年求学或初入职场时易有变动，宜稳扎稳打。",
        "中年阶段逢喜用神大运，事业财运多有上升之机。",
        "婚恋宜晚不宜早，配偶选择以互补五行为佳。",
    ]

    return {
        "basic_info": {
            "bazi": bazi,
            "day_master": dm,
            "month_branch": mb,
            "pattern": "待 DeepSeek 分析",
            "useful_gods": [],
            "taboo_gods": [],
        },
        "reasoning": "当前未配置 DEEPSEEK_API_KEY，仅返回八字结构信息。请设置环境变量后重试。",
        "domain_analysis": domain_analysis,
        "wealth_level": "需细断",
        "wealth_evidence": "未调用真实模型，无法判断财富等级。",
        "marriage_status": "需细断",
        "marriage_evidence": "未调用真实模型，无法判断婚姻状况。",
        "milestones": [],
        "personality": personality,
        "events": events,
        "summary": _structural_summary(bazi),
        "confidence": "low",
        "caveats": caveats,
        "_mock": True,
    }


def _strip_confidence_annotations(text: str) -> str:
    """Remove per-field confidence markers such as (置信度：low)."""
    if not isinstance(text, str):
        return text
    return re.sub(r"[（(]置信度[：:][^）)]+[）)]", "", text).strip()


# Vague filler / advice phrases the model is instructed not to use.
# Note: "无显著波动/事件/隐患" are allowed because they are factual statements
# for years that genuinely lack strong triggers.
_FORBIDDEN_PHRASES = {
    "顺其自然",
    "按部就班",
    "按年度节奏推进",
    "量入为出",
    "规律作息",
    "整体平顺",
    "稳步前进",
    "保持现状",
    "心态平和",
    "多沟通",
    "多包容",
    "低调行事",
    "宜守不宜攻",
    "守成",
    "观望",
    "谨慎",
    "无大碍",
    "总体尚可",
    "一般",
    "普通",
    "平淡",
    "财运平平",
    "事业平平",
    "感情平平",
    "健康平平",
    "总体平稳",
    "整体平稳",
}


def _sanitize_text(text: str) -> str:
    """Remove forbidden filler phrases from a text string."""
    if not isinstance(text, str):
        return text
    cleaned = _strip_confidence_annotations(text)
    for phrase in _FORBIDDEN_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    # Clean up any double punctuation or trailing fragments left by removals.
    cleaned = re.sub(r"[，。；：\s]+[，。；：]", "，", cleaned)
    cleaned = re.sub(r"，+", "，", cleaned)
    return cleaned.strip("，。；： ")


def _validate_output(result: Dict, bazi: str) -> Dict:
    """Sanity-check model output and add caveats for obvious mismatches."""
    basic = result.get("basic_info", {})
    caveats = list(result.get("caveats", []))

    # Strip accidental per-field confidence annotations and forbidden filler phrases.
    domain_analysis = result.get("domain_analysis", {})
    if isinstance(domain_analysis, dict):
        for key in domain_analysis:
            domain_analysis[key] = _sanitize_text(domain_analysis[key])
        result["domain_analysis"] = domain_analysis
    if isinstance(result.get("summary"), list):
        result["summary"] = [_sanitize_text(s) for s in result["summary"]]
    if isinstance(result.get("events"), list):
        result["events"] = [_sanitize_text(e) for e in result["events"]]
    if isinstance(result.get("personality"), str):
        result["personality"] = _sanitize_text(result["personality"])
    if isinstance(result.get("wealth_evidence"), str):
        result["wealth_evidence"] = _sanitize_text(result["wealth_evidence"])
    if isinstance(result.get("marriage_evidence"), str):
        result["marriage_evidence"] = _sanitize_text(result["marriage_evidence"])
    if isinstance(result.get("liuqin_analysis"), str):
        result["liuqin_analysis"] = _sanitize_text(result["liuqin_analysis"])

    # Normalize and validate wealth/marriage levels.
    _WEALTH_LEVELS = {"贫", "温饱", "小康", "中产", "小富", "中富", "大富", "巨富"}
    _MARRIAGE_STATUSES = {"未婚", "早婚", "晚婚", "一婚稳定", "二婚", "多婚", "孤独"}

    wealth_level = result.get("wealth_level")
    if not isinstance(wealth_level, str) or not any(level in wealth_level for level in _WEALTH_LEVELS):
        result["wealth_level"] = "需细断"
    else:
        # Pick the first matched level.
        for level in _WEALTH_LEVELS:
            if level in wealth_level:
                result["wealth_level"] = level
                break

    marriage_status = result.get("marriage_status")
    if not isinstance(marriage_status, str) or not any(status in marriage_status for status in _MARRIAGE_STATUSES):
        result["marriage_status"] = "需细断"
    else:
        for status in _MARRIAGE_STATUSES:
            if status in marriage_status:
                result["marriage_status"] = status
                break

    # Ensure milestones is a list with the expected shape.
    milestones = result.get("milestones")
    if not isinstance(milestones, list):
        result["milestones"] = []
    else:
        cleaned = []
        for m in milestones:
            if not isinstance(m, dict):
                continue
            year = m.get("year")
            age = m.get("age")
            if not isinstance(year, int) or not isinstance(age, int):
                try:
                    year = int(year)
                    age = int(age)
                except (TypeError, ValueError):
                    continue
            cleaned.append({
                "year": year,
                "age": age,
                "type": str(m.get("type", "其他")).strip() or "其他",
                "description": _strip_confidence_annotations(str(m.get("description", "")).strip()),
            })
        result["milestones"] = cleaned

    # Ensure liuqin_analysis is at least a string.
    liuqin_analysis = result.get("liuqin_analysis")
    if not isinstance(liuqin_analysis, str):
        result["liuqin_analysis"] = ""

    if basic.get("bazi") and basic.get("bazi") != bazi:
        caveats.append(f"模型输出八字 {basic.get('bazi')} 与输入 {bazi} 不一致，已修正")
        basic["bazi"] = bazi

    expected_day_master = day_master(bazi)
    if basic.get("day_master") and expected_day_master and basic.get("day_master") != expected_day_master:
        caveats.append(
            f"模型日主 {basic.get('day_master')} 与八字实际日主 {expected_day_master} 不一致，已修正"
        )
        basic["day_master"] = expected_day_master

    expected_month_branch = month_branch(bazi)
    if basic.get("month_branch") and expected_month_branch and basic.get("month_branch") != expected_month_branch:
        caveats.append(
            f"模型月令 {basic.get('month_branch')} 与八字实际月令 {expected_month_branch} 不一致，已修正"
        )
        basic["month_branch"] = expected_month_branch

    if caveats and "caveats" in result:
        result["caveats"] = caveats

    result, _ = check_analysis(result)
    return result


def _parse_json(content: str, bazi: str, similar_cases: List[Dict]) -> Dict:
    """Parse model output as JSON, with fallback."""
    content = content.strip()
    if not content:
        return {
            "basic_info": {"bazi": bazi},
            "parse_error": True,
            "raw_content": "",
            "similar_cases": [c.get("bazi") for c in similar_cases],
        }

    # Direct JSON parse.
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Markdown fenced JSON.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any JSON object in the text.
    obj_match = re.search(r"(\{.*\})", content, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(1))
        except json.JSONDecodeError:
            pass

    # Final fallback: return raw content for inspection.
    return {
        "basic_info": {"bazi": bazi},
        "parse_error": True,
        "raw_content": content,
        "similar_cases": [c.get("bazi") for c in similar_cases],
    }
