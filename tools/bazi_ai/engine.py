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
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiofiles

from tools.bazi_ai import bazi_structural, calendar

try:
    import aiohttp
    from aiohttp import ClientResponseError
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]
    ClientResponseError = Exception  # type: ignore[assignment,misc]

from tools.bazi_ai.bazi_structural import (
    liuqin_profile,
    structural_profile,
    wealth_power_resource_flow,
)
from tools.bazi_ai.shensha import shensha_profile
from tools.bazi_ai.bazi_validator import (
    day_master,
    extract_pillars,
    month_branch,
    normalize_bazi,
)
from tools.bazi_ai.embeddings import EmbeddingStore
from tools.bazi_ai.knowledge_retriever import retrieve_knowledge_snippets
from tools.bazi_ai.rule_checker import check_analysis

logger = logging.getLogger(__name__)

# Branch six-clash pairs for palace checks.
_SIX_CHONG = {
    ("子", "午"), ("丑", "未"), ("寅", "申"),
    ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
}

# Domain keywords used to boost retrieval when the user asks a domain question.
_DOMAIN_KEYWORDS = {
    "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁", "贵人", "从事", "职位"],
    "wealth": ["财", "钱", "富", "收入", "资产", "赚钱", "百万", "千万", "小康", "贫富"],
    "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚", "离婚"],
    "health": ["健康", "病", "身体", "手术", "肾", "妇科", "心脏", "血液", "子宫", "困扰"],
    "family": ["父母", "父亲", "母亲", "子女", "孩子", "兄弟", "姐妹"],
    "kinship": ["父母", "父亲", "母亲", "子女", "孩子", "兄弟", "姐妹", "六亲"],
    "education": ["学历", "读书", "学业", "毕业", "学校", "大学", "文凭"],
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


def _case_relevance(
    case: Dict, bazi: str, question: str, *, boost_domains: Optional[List[str]] = None
) -> int:
    """Keyword relevance score for RAG, with domain-aware boosts.

    Important (2026-07-13): exact-bazi matches from a *different domain* must not
    dominate retrieval.  LOO probes showed career questions retrieving the same
    person's marriage/children Qs (bazi +100) and drowning domain-similar cases.
    """
    score = 0
    text = " ".join(
        [
            case.get("bazi", ""),
            case.get("analysis_corrected", ""),
            " ".join(case.get("key_terms", [])),
            " ".join(case.get("conclusions", [])),
        ]
    )
    case_domains = case.get("domains", {}) or {}
    case_domain_keys = set(case_domains.keys())

    query_domains = _detect_question_domains(question)
    if boost_domains:
        query_domains = list(set(query_domains) | set(boost_domains))
    query_domain_set = set(query_domains)
    domain_overlap = bool(query_domain_set & case_domain_keys) if query_domain_set else False

    # Exact bazi: strong only when domain aligns (or query has no domain).
    if case.get("bazi") == bazi:
        if not query_domain_set or domain_overlap:
            score += 80
        else:
            # Same chart, wrong domain — still a mild signal, not a nuke.
            score += 15

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

    # Domain-aware boost: same-domain cases beat cross-domain same-bazi noise.
    for domain in query_domains:
        if case_domains.get(domain):
            score += 35  # was 12 — domain match is the main transfer signal
        domain_text = " ".join(case_domains.get(domain, []))
        for kw in _DOMAIN_KEYWORDS.get(domain, []):
            if kw in domain_text or kw in text:
                score += 3

    # Extra soft boost for explicitly boosted domains.
    if boost_domains:
        for domain in boost_domains:
            if case_domains.get(domain):
                score += 15  # was 8

    # Penalty when query has a clear domain but case is only in other domains.
    if query_domain_set and case_domain_keys and not domain_overlap:
        score -= 20

    # Question keyword overlap.
    if question:
        for kw in re.split(r"[，。！？、\s]", question):
            kw = kw.strip()
            if len(kw) >= 2 and kw in text:
                score += 10

    # Prefer cases that explicitly state the gold answer (BaziQA reverse cases).
    if "正确答案" in text or "答案：" in text:
        score += 5
    return score


async def retrieve_similar_cases(
    bazi: str,
    question: str,
    cases_path: Path,
    top_k: int = 3,
    embedding_cache_path: Optional[Path] = None,
    extra_cases_paths: Optional[List[Path]] = None,
    exclude_case_matcher: Optional[Callable[[Dict], bool]] = None,
    domain_filter: Optional[List[str]] = None,
    domain_boost: Optional[List[str]] = None,
) -> List[Dict]:
    """Return the top-k most relevant cases.

    If *embedding_cache_path* exists and sentence-transformers is installed,
    semantic similarity is combined with the keyword heuristic for ranking.

    *extra_cases_paths* allows users to load additional private/local case
    databases without mixing them into the default public case file.

    *exclude_case_matcher* is an optional predicate. Any case for which it
    returns ``True`` is removed from retrieval, which is useful for leave-one-out
    or cross-domain benchmarks where the target case must not leak into RAG.

    *domain_filter* restricts retrieval to cases whose ``domains`` keys overlap
    with the supplied list. When fewer than *top_k* domain cases are available,
    the remainder is filled from the general ranking.

    *domain_boost* is a softer alternative: cases whose ``domains`` overlap with
    the supplied list receive an extra score bump, but cases from other domains
    are still allowed to rank higher if they are structurally very similar.
    """
    cases = await _load_cases(cases_path)
    for path in extra_cases_paths or []:
        cases.extend(await _load_cases(path))
    if exclude_case_matcher:
        cases = [c for c in cases if not exclude_case_matcher(c)]
    if not cases:
        return []

    if domain_filter:
        domain_set = set(domain_filter)

        def _has_domain(case: Dict) -> bool:
            case_domains = case.get("domains", {})
            if not case_domains:
                return False
            return not domain_set.isdisjoint(case_domains.keys())

        domain_cases = [c for c in cases if _has_domain(c)]
    else:
        domain_cases = cases

    def _rank(active_cases: List[Dict]) -> List[Dict]:
        """Return *active_cases* ranked by keyword + optional embedding score."""
        bonus: Dict[int, float] = {}
        if embedding_cache_path is not None and embedding_cache_path.exists():
            store = EmbeddingStore()
            if store.load_cache(embedding_cache_path):
                query = f"{bazi}\n{question}".strip()
                for rank, (case, score) in enumerate(
                    store.search(query, top_k=min(len(active_cases), top_k * 3))
                ):
                    for idx, c in enumerate(active_cases):
                        if c is case:
                            bonus[idx] = max(0.0, score * 30 - rank * 3)
                            break

        scored = []
        for idx, case in enumerate(active_cases):
            keyword_score = _case_relevance(
                case, bazi, question, boost_domains=domain_boost
            )
            emb_bonus = bonus.get(idx, 0.0)
            scored.append((keyword_score + emb_bonus, case))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    ranked = _rank(domain_cases)
    if domain_filter:
        domain_ids = {id(c) for c in domain_cases}
        other_cases = [c for c in cases if id(c) not in domain_ids]
        other_ranked = _rank(other_cases)
        ranked = ranked[:top_k] + other_ranked[: max(0, top_k - len(ranked))]

    return ranked[:top_k]


async def _build_rule_primer(
    knowledge_base_paths: List[Path], max_chars: int = 40000
) -> str:
    """Load a rule primer from one or more knowledge base files.

    Default 40000 chars (~13K tokens) fits the 盲派 rulebook + mnemonics in a
    long-context model (DeepSeek/Qwen). The previous 10000-char cap silently
    truncated most of the 盲派 knowledge — see docs/bazi_ai_error_analysis.md.
    """
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


def _build_system_prompt(knowledge_context: str) -> str:
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
1. **取象优先，公式为辅**：先用盲派取象/象法把干支、十神、宫位"看作具体的人事物场景"，再以子平格局与旺衰喜用做骨架校验。不要一上来就套"七杀=压力/武职""财星=钱"这类刻板对应——同一个十神在不同季节(令)、通根、刑冲合化、喜忌下取象完全不同（例：庚金七杀，春月有火炼取刀剑/执法/武职之象；冬月水冷金寒取道路/法律/医疗/冰冷之金的象）。结论要落到"像什么生活场景"，而不是干巴巴的十神标签。
2. **两步取象推理（必须执行，结果写入 `quxiang` 字段）**：对日主、关键十神、职业、健康，先①列出该干支/十神在本局至少 3–5 种可能的取象，②结合季节、通根、刑冲合化、喜忌，选出最贴切的一种并说明为什么排除其他。取不出 3 个象、或讲不清取舍理由，说明这个判断不稳，必须在 confidence 里下调。这一步是核心，禁止跳过直接下结论。
3. 推理过程要连贯自然，像你在解释给命主听。关键判断和取象取舍都要在 reasoning 中体现。
4. 结论要具体，但必须有命局依据，禁止为了迎合用户而编造不存在的吉凶事件。
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
   - 婚动/结婚（盲派象法应期，满足任一即可，不要只认配偶星一种）：①流年/大运与夫妻宫（日支）六合、三合、暗合；②配偶星（男命正财/偏财、女命正官/七杀）透干合身或坐夫妻宫；③**比劫合入夫妻宫→应期找比劫年/大运**（比劫即命主自身"进"了夫妻宫，主成家）；④桃花（子午卯亥，按年支/日支查）引动夫妻宫；⑤夫妻宫逢冲而动（冲开原局合绊也为应期）。
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
11. **事件/流年是"命理趋势概率"，不是定数**：八字对具体事件/年份的预测本质上不确定性极高（开放式事件预测准确率接近随机）。所以 milestones/events 必须用概率语气——"易有X倾向""需防X""X可能性较高"，**禁止"必发生/一定/肯定"等断言**。结构层（格局/用神/六亲/财富等级）当确定判断直断；事件层当趋势提示。这才是负责任的真人命理表达。

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

基础知识参考（以下是从本地知识库中检索出的最相关片段，请优先结合它们进行推断）：
{knowledge_context}
"""


def _build_user_prompt(
    bazi: str,
    question: str,
    similar_cases: List[Dict],
    *,
    gender: str = "male",
    liuqin_facts: Optional[Dict] = None,
    structural_facts: Optional[Dict] = None,
    dayun_list: Optional[List[Dict]] = None,
    flow_facts: Optional[Dict] = None,
    shensha_facts: Optional[Dict] = None,
) -> str:
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

    liuqin_text = ""
    if liuqin_facts:
        members = ["father", "mother", "spouse", "son", "daughter", "brother", "sister"]
        labels = {
            "father": "父亲", "mother": "母亲", "spouse": "配偶",
            "son": "儿子", "daughter": "女儿", "brother": "兄弟", "sister": "姐妹",
        }
        lines = []
        for m in members:
            info = liuqin_facts.get(m, {})
            if info.get("exists"):
                lines.append(f"【{labels[m]}】{info.get('description', '')}")
            else:
                lines.append(f"【{labels[m]}】{info.get('description', '')}")
        liuqin_text = "\n".join(lines)

    structural_text = ""
    if structural_facts:
        stem_shishen_text = "、".join(f"{k}：{v}" for k, v in structural_facts.get("stem_shishen", {}).items())
        branch_shishen_text = "、".join(f"{k}：{v}" for k, v in structural_facts.get("branch_shishen", {}).items())
        structural_text = f"""【命局结构事实】（由程序严格计算，你必须以此为依据，禁止自行发明）
- 日主：{structural_facts.get("day_master", "")}
- 月令：{structural_facts.get("month_branch", "")}
- 格局（月令定格，程序判定，**直接采用，禁止自行另取**）：{structural_facts.get("geju", "") or "（月令比劫，需另寻透干格局）"}
- 天干十神：{stem_shishen_text}
- 地支十神（本气）：{branch_shishen_text}
- 五行统计（天干0.5+地支1.0）：{structural_facts.get("element_weighted_text", "")}
- 参考旺衰：{structural_facts.get("strength", "")}
- 用神（程序按扶抑/调候/通关三法判定，**直接采用，原局取用以此为准**）：{structural_facts.get("useful_gods", "")}
- 忌神（程序判定，**直接采用**）：{structural_facts.get("taboo_gods", "")}
- 天干合化：{structural_facts.get("tian_gan_he_text", "无")}
- 地支合冲刑害：{structural_facts.get("di_zhi_relations_text", "无")}
- 地支综合关系（含三合/半合/三会/藏干合/冲合互解）：
{structural_facts.get("di_zhi_comprehensive_text", "无")}
- 空亡：{structural_facts.get("kong_wang", "")}
- 宫位：{structural_facts.get("palace_text", "")}
"""

    dayun_text = ""
    if dayun_list:
        lines = []
        for d in dayun_list[:8]:
            lines.append(f"{d['start_age']:.2f}-{d['end_age']:.2f}岁：{d['pillar']}大运")
        dayun_text = "【大运走势】\n" + "\n".join(lines)

    flow_text = ""
    if flow_facts and flow_facts.get("exists"):
        flow_text = f"【特殊流通结构】\n{flow_facts.get('description', '')}"

    shensha_text = ""
    if shensha_facts:
        present = [s for s in (shensha_facts.get("stars") or []) if s.get("present")]
        if present:
            star_lines = []
            for s in present:
                locs = "、".join(
                    f"{l.get('pillar', '')}{l.get('position', '')}{l.get('char', '')}"
                    for l in s.get("locations", [])
                )
                star_lines.append(f"- {s['name']}（{s.get('category', '')}）落：{locs}——{s.get('description', '')}")
            shensha_text = (
                "【神煞事实】（由程序查表严格计算，存在性非此即彼，以此为依据、禁止发明星曜）\n"
                + shensha_facts.get("summary_text", "") + "\n"
                + "\n".join(star_lines)
            )

    gender_label = (
        "女命"
        if (gender or "").strip() in ("female", "女", "f", "F")
        else "男命"
    )

    return f"""请为以下八字做详细分析，像一位真人命理师面对面跟命主交谈那样回答。

八字：{bazi}
性别：{gender_label}
命主提问：{question or "全面分析事业、财运、婚姻、健康"}

{focus_instruction}

{structural_text}

{dayun_text}

{flow_text}

{shensha_text}

【六亲星宫事实】（由程序严格计算，你必须以此为依据，禁止把星和宫的位置说错）
**六亲强弱（每条末尾括号内 强/弱）由程序按"星根是否被冲/合化坏"判定，直接采用。** 尤其"有根、但被逢冲/合化坏根，实为虚浮无力"必须判**弱**——不要因为字面看到"有根/透干"就自行改判强。
**【强制·禁止改判】** 你必须把上方每一条【父亲/母亲/配偶/儿子/女儿/兄弟/姐妹】末尾括号里的"强"或"弱"**逐字**填入输出 JSON 的 `liuqin_strength` 字段对应键（father/mother/spouse/son/daughter/brother/sister），每个值只能是"强"或"弱"二选一，禁止综合折中、禁止凭自己的旺衰感觉改判、禁止留空。`liuqin_analysis` 里每一方的"真假强弱"叙述也必须与 `liuqin_strength` 完全一致——这是把程序判定的强弱搬进读盘结论的唯一通道，违反即判错。
{liuqin_text}

夫妻宫：日支{liuqin_facts.get('spouse_palace', {}).get('branch', '')}，本气十神为{liuqin_facts.get('spouse_palace', {}).get('shishen_main', '')}。
父母宫：月支{liuqin_facts.get('parents_palace', {}).get('branch', '')}。
子女宫：时支{liuqin_facts.get('children_palace', {}).get('branch', '')}。

参考案例（仅作风格与论证参考，不要直接照搬结论）：
{cases_text}

表达要求：
- 用自然、口语化的中文，像真人说话。
- 避免"根据子平法……""从八字来看……""综上所述……"等学术腔和公文腔开头。
- 每个结论都要像一段话，有依据、有场景、有具体建议。
- 六亲断语必须星宫同参：先说明该六亲的"星"是什么十神、落在哪一柱/天干/地支藏干，再结合所在宫位下断语。
- 禁止把日主自己当作兄弟姐妹星。兄弟星必须看命局中除日干外的比肩，姐妹星看除日干外的劫财。
- 六亲十神必须以日干为准，禁止凭直觉编造。本局日干为甲木、男命，所以：父星=偏财戊土，母星=正印癸水，妻星=正财己土，儿子=七杀庚金，女儿=正官辛金，兄弟=比肩甲木（日干除外），姐妹=劫财乙木。
- 判断六亲对命主好坏时，必须结合用神忌神：为用神则助我，为忌神则带来压力或健康隐患。

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
  "reasoning": "完整的逐步推理过程，300-800字。必须包含：日主旺衰判断、格局取法、用神忌神选择、各领域推断依据。取象的展开过程写在 quxiang 字段，这里只做骨架推理。",
  "quxiang": {{
    "day_master": "对日主天干【在本局季节(令)/通根/刑冲合化下】的取象：先列出至少3种可能的取象(如庚金在不同条件可取刀剑/道路/法律/医疗/矿石等)，再标出本局最贴切的一种，并说明为什么排除其他。",
    "key_shishen": "挑命局最关键的1-2个十神(如最旺的财/官/杀/食伤)逐一取象：每个先列≥3种取象→再择优→并给出排除其他取象的理由。禁止直接套'七杀=压力'这类刻板对应。",
    "career": "由关键十神的取象落到具体职业场景：先列≥3种可能的职业方向(如外科/法律/机械/金融/文教)，再结合用神与季节择优，说明为什么排除其他。",
    "health": "五行偏枯与受克脏腑的取象：先列≥3种可能的健康隐患脏腑，再结合最失衡的五行择优，说明排除理由。"
  }},
  "liuqin_strength": {{
    "father": "强 或 弱——逐字复制【六亲星宫事实】中【父亲】末尾括号内的判定，禁止自行改判",
    "mother": "强 或 弱——逐字复制【母亲】末尾括号内的判定",
    "spouse": "强 或 弱——逐字复制【配偶】末尾括号内的判定",
    "son": "强 或 弱——逐字复制【儿子】末尾括号内的判定",
    "daughter": "强 或 弱——逐字复制【女儿】末尾括号内的判定",
    "brother": "强 或 弱——逐字复制【兄弟】末尾括号内的判定",
    "sister": "强 或 弱——逐字复制【姐妹】末尾括号内的判定"
  }},
  "domain_analysis": {{
    "career": "事业分析（只写结论，禁止写置信度）",
    "wealth": "财运分析（只写结论，禁止写置信度）",
    "marriage": "婚姻/感情分析（只写结论，禁止写置信度）",
    "health": "健康分析（只写结论，禁止写置信度）"
  }},
  "wealth_level": "从「贫、温饱、小康、中产、小富、中富、大富、巨富」中选择一级，只写原局财富潜力等级，不写具体金额。具体赚多少钱、在哪一年线城市达到什么资产规模，应放在大运流年分析中再细断。",
  "wealth_evidence": "给出财富等级的依据，必须说明：1）原局财星/食伤/库的情况；2）日主能否担财；3）是否有财杀印流通；4）哪几步大运对财富最有利/最不利。禁止在这里写'一线城市XX万'这类具体金额。",
  "marriage_status": "从「未婚、早婚、晚婚、一婚稳定、二婚、多婚、孤独」中选择一项",
  "marriage_evidence": "给出婚姻状况的简要依据",
  "liuqin_analysis": "详细的六亲断语，必须是完整段落，不要只列标签。【强制要求】对父亲、母亲、配偶、子女每一方，都必须明确给出三句定性：①该六亲星是真是假（真星=通根得令有力；假星=虚浮无根受克）；②是强是弱（旺/衰）；③与命主缘深缘薄、助力还是拖累。禁止含糊其辞、禁止只描述不下结论。必须包含以下小节，每节都要先说星宫依据再下断语：\\n【父亲】父星是什么十神、落在哪一柱天干/地支藏干，真假强弱，父亲性格、能力、健康、与命主关系缘深缘薄。\\n【母亲】母星是什么十神、落在哪一柱，真假强弱，母亲性格、能力、健康、与命主关系。\\n【配偶】男命以正财为妻星/女命以正官为夫星，落在哪一柱；夫妻宫日支是什么、本气十神是什么。配偶星真假强弱，配偶性格、能力、健康、外貌、与命主婚姻状态。\\n【子女】先判断命中偏向儿子、女儿还是儿女双全，并给出命局依据。再分别写儿子和女儿的性格、能力、健康、与命主关系。\\n【兄弟姐妹】兄弟星比肩、姐妹星劫财分别落在哪一柱，兄弟几人、姐妹几人、是否得力、与命主关系。\\n【六亲关系】父亲与母亲关系、配偶与父母关系、命主与手足关系等互动特点。",
  "milestones": [
    {{"year": 年份, "age": 年龄, "type": "婚动/子女/事业转折/财富转折/重大疾病/搬迁/学业/其他", "description": "必须有命局依据，证据不足时宁可留空数组"}}
  ],
  "personality": "根据日主、十神、五行喜忌，描述命主的性格、行为模式与气质特点，200字以内。",
  "events": ["趋势1：用概率语气的事件倾向（如'中年易有感情波折'，禁止'必离婚'）", "趋势2", "趋势3"],
  "summary": ["3-5条核心断语"],
  "shensha_summary": "（可选）若命局有显著神煞（天乙贵人/文昌/羊刃/驿马/桃花/空亡/魁罡等），用1-3句说明其吉凶倾向与对命局的影响；无显著神煞可留空字符串。星曜是否存在以上方【神煞事实】为准，禁止发明星曜。",
  "confidence": "high|medium|low",
  "caveats": ["可能的误差来源"]
}}
"""


async def analyze_bazi(
    bazi: str,
    *,
    question: str = "",
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
    calendar_type: str = "solar",
    cases_path: Optional[Path] = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Optional[Path] = None,
    extra_cases_paths: Optional[List[Path]] = None,
    extra_knowledge_base_paths: Optional[List[Path]] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
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

    # Retrieve the most relevant knowledge snippets instead of dumping whole files.
    knowledge_paths = [Path("./bazi_knowledge/rule_primer.md")]
    if knowledge_base_path is not None and knowledge_base_path.exists():
        knowledge_paths.append(knowledge_base_path)
    for path in extra_knowledge_base_paths or []:
        if path.exists():
            knowledge_paths.append(path)

    knowledge_context = await retrieve_knowledge_snippets(
        query=f"{bazi}\n{question}".strip(),
        knowledge_paths=knowledge_paths,
        cache_path=knowledge_embedding_cache_path,
        top_k=6,
        max_chars=10000,
    )

    # Compute structural facts to ground the AI and prevent invented stars/palaces.
    structural_facts = structural_profile(bazi) or {}
    liuqin_facts = liuqin_profile(bazi, gender=gender) or {}
    flow_facts = wealth_power_resource_flow(bazi)
    shensha_facts = shensha_profile(bazi, gender=gender) or {}

    # Compute dayun if birth info is available so wealth/destiny levels can be
    # judged against the full life trajectory, not just the static chart.
    dayun_list_data: List[Dict] = []
    if birth_date:
        try:
            dayun_list_data = calendar.dayun_list(
                bazi,
                gender,
                birth_date,
                birth_time,
                calendar_type,
                until_age=60,
            )
        except Exception:
            dayun_list_data = []

    system_prompt = _build_system_prompt(knowledge_context)
    user_prompt = _build_user_prompt(
        bazi,
        question,
        similar_cases,
        gender=gender,
        liuqin_facts=liuqin_facts,
        structural_facts=structural_facts,
        dayun_list=dayun_list_data,
        flow_facts=flow_facts,
        shensha_facts=shensha_facts,
    )
    # Ground LLM 六亲 with det 细断 (性格/健康/应期提要)；强弱不得改判。
    try:
        from tools.bazi_ai.liuqin_dossier import (
            build_liuqin_dossier,
            format_liuqin_dossier_prompt,
        )

        _dq = build_liuqin_dossier(
            bazi,
            gender=gender,
            birth_date=birth_date or "",
            birth_time=birth_time or "00:00",
        )
        if _dq:
            user_prompt = user_prompt + "\n\n" + format_liuqin_dossier_prompt(_dq)
    except Exception:
        pass

    key = (
        api_key
        or os.environ.get("MINIMAX_API_KEY")
        or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
    )
    if not key:
        mock = _mock_analyze(bazi, question, similar_cases)
        return _attach_year_timing(
            mock,
            bazi,
            question=question,
            gender=gender,
            birth_date=birth_date,
            birth_time=birth_time,
        )

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

    if aiohttp is None:  # pragma: no cover
        raise ImportError("需要 aiohttp 来调用 DeepSeek API")

    is_reasoner = "reasoner" in mdl.lower()
    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # deepseek-reasoner does not support json_object response_format and
        # needs a larger final-answer budget (reasoning tokens are billed
        # separately). deepseek-chat gets json mode + a smaller budget.
        "max_tokens": 8000 if is_reasoner else 5000,
    }
    if not is_reasoner:
        payload["temperature"] = 0.2
        # MiniMax / some OpenAI-compatible gateways reject response_format.
        if "minimax" not in base.lower() and "abab" not in mdl.lower():
            payload["response_format"] = {"type": "json_object"}

    last_error: Optional[Exception] = None
    for attempt in range(1, 4):
        try:
            # deepseek-reasoner needs much longer for a full deep reading.
            timeout = aiohttp.ClientTimeout(total=240 if is_reasoner else 60)
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
                    return _validate_output(
                        parsed,
                        bazi,
                        liuqin_facts=liuqin_facts,
                        structural_facts=structural_facts,
                        gender=gender,
                        question=question,
                        birth_date=birth_date,
                        birth_time=birth_time,
                    )
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
    return _attach_year_timing(
        fallback,
        bazi,
        question=question,
        gender=gender,
        birth_date=birth_date,
        birth_time=birth_time,
    )


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


def _build_yearly_system_prompt(knowledge_context: str) -> str:
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
4. 十二字关系必须全面考虑，不能只看六合、六冲。每论一年，必须检查命局四柱地支、大运地支、流年地支之间的：六合、六冲、六害、三刑、三合局（如申子辰合水）、半合局、三会局（如寅卯辰会木）、藏干合（如午中丁火与未中己土），以及冲合互解（某支本可合局，但被另一支冲开；或某支本可相冲，但被第三支合住解冲）。把这些关系放在大运背景下判断：大运是趋势，流年是应期；若大运与命局已成合局，流年来冲才引发变动；若流年与命局成合，能解原局或大运的冲。
5. 事业、财运、感情、健康四个领域禁止写空话。要给出命主能听懂、能操作的判断，比如"上半年有机会跳槽，但薪资涨幅有限""偏财不稳，别追热点""有桃花，但多半是烂桃花""肠胃和睡眠要注意"。
6. 若某年与大运、命局形成明显冲克（子午冲、寅申冲、卯酉冲、辰戌冲、巳亥冲、丑未冲），必须在 overview 或 caution 中明确指出。
7. 每一年 overview 控制在 80 字以内，必须包含：本年所在大运、流年十神作用、关键触发（十神/合冲刑害）、具体事件预测。
8. 四个领域每栏控制在 60 字以内，caution 控制在 40 字以内。整体要凝练、有断语。
9. 如果某一年没有明显吉凶事件，允许写“这一年没什么大动静，平顺过渡”，禁止硬凑四栏套话。
10. 六亲断语必须覆盖命主身边的每一位亲人，按人物分节写成，每节都要像命理师在跟命主聊家里的事。禁止出现半截话，禁止把人物关系堆在最后的“family_relations”里敷衍。每个字段必须是一个语法完整、没有截断的句子；如果某方面信息不足，也要写成完整判断，例如“姐妹缘分较浅，命中姐妹星不显”，禁止写成“姐妹缘分”。要求如下：
    【父亲】以偏财/正财为父星，说明父星落在哪一柱（年/月/日/时）、天干还是地支藏干，父亲性格、能力、健康、与命主关系，以及父亲与母亲的关系如何。
    【母亲】以正印/偏印为母星，说明母星落在哪一柱，母亲性格、能力、健康、与命主关系，以及母亲与父亲、与命主配偶（婆媳/翁婿）的关系如何。
    【配偶】以日支为夫妻宫，结合男命财星/女命官杀为配偶星，说明配偶性格、能力、健康、外貌、与命主婚姻状态。必须根据夫妻宫和配偶星的刑冲合害、清浊混杂，直接判断：婚姻是否稳定、是否容易二婚/多婚、感情中的主要矛盾是什么。同时说明配偶与命主父母相处如何。
    【子女】男命以正官/七杀为子女星（七杀多主儿子、正官多主女儿，仅供参考），女命以食神/伤官为子女星（伤官多主儿子、食神多主女儿，仅供参考）。必须先判断命中偏向生儿子、女儿，还是儿女双全，并给出依据（哪一柱子女星旺、哪一柱受克）。再分别写儿子和女儿的性格、能力、健康、与命主关系。若子女星弱或受冲，则说明子女缘薄、来得晚或需操心。
    【兄弟姐妹】以比肩/劫财为手足星，说明兄弟姐妹缘分、数量倾向、是否得力、与命主关系。
    `family_relations` 字段只作为补充，不要在这里重复写父母关系、夫妻关系；这些关系必须分别写在父亲、母亲、配偶的章节里。
    错误示例（禁止）："祖上家境""父亲身体""兄弟缘""配偶对你""婚姻中需""子女缘较好"；
    正确示例："你命中七杀透干，先论儿子：儿子性格刚强有主见，将来适合技术或军警类方向，小时候你管得严，他反而逆反，长大后关系才会缓和""女儿星正官藏而不透，女儿缘分比儿子浅一些，性格偏内向乖巧""夫妻宫坐七杀无制，配偶脾气大、控制欲强，婚姻中容易冷战，若再逢冲刑，二婚概率不低"。
11. 每一年输出 `key_event`：有明显事件时直接点明（结婚、离婚、升职、跳槽、破财、发财、生子、手术、搬迁、创业失败、官司、桃花、学业、长辈灾等）；无明显事件时写“平稳过渡，无重大事件”。禁止为凑数而编造事件。
12. 全局 `milestones` 只汇总真正高置信度的人生节点：
    - 婚动/结婚：流年或大运冲合夫妻宫，或配偶星透干合身。
    - 离婚/感情危机：夫妻宫被冲刑穿，且配偶星受制。
    - 生子：子女宫或子女星被引动。
    - 事业转折：官杀/印星/食伤发生重大变化。
    - 财富转折：财星、财库、食伤被强烈引动。
    - 重大疾病：对应脏腑被严重冲克。
    - 搬迁：驿马被冲。
    证据不足时宁可留空数组，禁止每年硬凑一个节点。
13. 财富必须给出具体金额估算（不要只写'财运好'）。每一年 `wealth` 字段都要写：收入/支出大致范围、是否适合投资、有没有偏财机会。同时要在顶层 `wealth_forecast` 中给出一生财富上限的估算，并按城市 tier 分开：
    - 一线城市（北上广深杭等）：房产+流动资产合计达到什么量级
    - 二线城市（省会/强三线）：同上
    - 三四线/县城：同上
    金额用区间表示，例如"300-800万""1000-3000万"，并说明依据（哪步大运是财富爆发期、哪年是关键节点）。禁止写"小康/中产/小富"这类模糊词，必须给数字区间。
14. 宫位论断必须精确：年支是祖上/父母宫，月支是父母/兄弟宫，日支是夫妻宫，时支是子女宫。大运支、流年支本身不是命局宫位，只有当它们与命局四柱地支发生作用时，才允许说某宫位被引动。禁止把大运支与流年支之间的冲合（如丙辰大运遇庚戌流年之辰戌冲）错误说成夫妻宫/父母宫受冲。提到三合/半合/三会/藏干合时，必须写明具体是哪几个地支在作用，不能笼统地说"父母宫与夫妻宫皆动"。

输出格式：
{{
  "wealth_forecast": {{
    "lifetime_potential": "按八字结构和大运判断，一生财富上限的简短结论",
    "tier1_cities": "一线城市资产规模区间，例如'房产+流动资产约1000-3000万'",
    "tier2_cities": "二线城市资产规模区间",
    "tier3_cities": "三四线/县城资产规模区间",
    "peak_period": "财富高峰期年龄段及大运",
    "key_years": [2028, 2031],
    "evidence": "给出金额依据：财杀印流通、哪步大运助身、哪几年财星/财库被引动"
  }},
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
      "wealth": "财运具体建议，必须包含金额区间或具体数字（例如'正财收入10-20万，偏财不稳，忌投资'）",
      "marriage": "感情具体建议",
      "health": "健康具体建议",
      "caution": "注意事项，突出刑冲合害或重大决策提示"
    }}
  ],
  "liuqin_analysis": {{
    "father": {{"star": "父星十神及所在柱（完整句）", "character": "性格（完整句）", "ability": "能力（完整句）", "health": "健康（完整句）", "relationship": "与命主关系及父母关系（完整句）"}},
    "mother": {{"star": "母星十神及所在柱（完整句）", "character": "性格（完整句）", "ability": "能力（完整句）", "health": "健康（完整句）", "relationship": "与命主关系、父母关系、婆媳/翁婿关系（完整句）"}},
    "spouse": {{"palace": "夫妻宫日支（完整句）", "star": "配偶星（完整句）", "character": "性格（完整句）", "ability": "能力（完整句）", "health": "健康（完整句）", "appearance": "外貌（完整句）", "relationship": "婚姻状态、是否易二婚/多婚、与命主及父母关系（完整句）"}},
    "children": {{"overview": "先判断命主命中偏向儿子、女儿还是儿女双全，并给出命局依据（完整句）", "sons": "儿子：性格、能力、健康、与命主关系（完整句；若无儿子缘则写清楚）", "daughters": "女儿：性格、能力、健康、与命主关系（完整句；若无女儿缘则写清楚）", "relationship": "命主与子女整体关系（完整句）"}},
    "siblings": {{"brothers": "兄弟情况（完整句）", "sisters": "姐妹情况（完整句）", "relationship": "与命主关系（完整句）"}},
    "family_relations": "补充说明全家互动的核心特点，不要重复父母关系、夫妻关系（完整句）"
  }},

  非常重要：liuqin_analysis 的每个字段值都必须是独立、完整、通顺的句子。
  - 不要以字段名或称谓开头加逗号，例如禁止写成"母亲能力，……""父亲性格，……"；要直接写"她做事细致，擅长持家""父亲为人务实，有积蓄观念"。
  - 禁止半截话，例如"需要和理解"必须写成"需要互相理解"；"姐妹缘分"必须写成"姐妹缘分较浅，平时往来不多"。
  - 如果某方面确实信息不足，也要给出一个完整判断，例如"姐妹星不显，命中姐妹缘浅"。
  "milestones": [
    {{"year": 2026, "age": 33, "type": "婚动", "description": "夫妻宫被冲，感情关系剧变，可能结婚或分手"}}
  ],
  "overall_guidance": "综合建议，300字以内，分阶段总结",
  "confidence": "high|medium|low",
  "caveats": ["至少2条具体注意事项"]
}}

禁用词汇清单（绝对禁止出现，同义词也禁止）：顺其自然、按部就班、按年度节奏推进、量入为出、规律作息、平稳、平顺、逐步、稳步前进、保持现状、整体平顺、心态平和、多沟通、多包容、低调行事、宜守不宜攻、守成、观望、谨慎、注意即可、无大碍、总体尚可、一般、普通、平淡。

基础知识参考（以下是从本地知识库中检索出的最相关片段，请优先结合它们进行推断）：
{knowledge_context}
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
    similar_cases: List[Dict],
) -> str:
    cases_text = "\n\n".join(
        f"案例 {i+1}：\n八字：{c.get('bazi')}\n命理师分析：{c.get('analysis_corrected', '')[:600]}"
        for i, c in enumerate(similar_cases)
    )
    if not cases_text:
        cases_text = "（暂无相似案例）"

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
- 地支综合关系（含三合/半合/三会/藏干合/冲合互解）：
{profile.get("di_zhi_comprehensive_text", "无")}
- 空亡：{profile.get("kong_wang", "")}
- 宫位：{palace_text}
- 六亲：{profile.get("liuqin_text", "")}"""

    # Per-year structural facts: only include years with notable triggers to keep prompt short.
    day_branch = profile.get("branches", ["", "", "", ""])[2]
    year_facts_lines = []
    for r in yearly_rels:
        ly_branch = r["liunian_pillar"][1]
        dy_branch = r["dayun_pillar"][1]
        comp_text = r.get("di_zhi_comprehensive_text", "")
        has_relations = bool(
            (r.get("tian_gan_he_text") and r["tian_gan_he_text"] != "无")
            or (r.get("di_zhi_relations_text") and r["di_zhi_relations_text"] != "无")
            or (comp_text and comp_text != "无特殊组合")
        )
        palace_hit = bool(day_branch) and (
            ly_branch == day_branch
            or dy_branch == day_branch
            or (ly_branch, day_branch) in _SIX_CHONG
            or (day_branch, ly_branch) in _SIX_CHONG
            or (dy_branch, day_branch) in _SIX_CHONG
            or (day_branch, dy_branch) in _SIX_CHONG
        )
        if not (has_relations or palace_hit):
            continue
        palace_note = ""
        if day_branch:
            if ly_branch == day_branch or dy_branch == day_branch:
                palace_note = f"；夫妻宫日支{day_branch}伏吟"
            elif (ly_branch, day_branch) in _SIX_CHONG or (day_branch, ly_branch) in _SIX_CHONG:
                palace_note = f"；夫妻宫日支{day_branch}与流年支{ly_branch}相冲（反吟）"
            elif (dy_branch, day_branch) in _SIX_CHONG or (day_branch, dy_branch) in _SIX_CHONG:
                palace_note = f"；夫妻宫日支{day_branch}与大运支{dy_branch}相冲（反吟）"
        comp_relations = r.get("di_zhi_comprehensive_text", "")
        comp_part = f"；地支综合关系：{comp_relations}" if comp_relations and comp_relations != "无特殊组合" else ""
        line = (
            f"{r['year']}年 {r['liunian_pillar']}（{r['dayun_pillar']}大运）："
            f"流年干{r['liunian_stem_shishen']}、流年支{r['liunian_branch_shishen']}；"
            f"天干合：{r['tian_gan_he_text']}；"
            f"地支关系：{r['di_zhi_relations_text']}{comp_part}{palace_note}"
        )
        year_facts_lines.append(line)
    year_facts_text = "\n".join(year_facts_lines) if year_facts_lines else "（十年内无特别强烈的流年结构触发，按大运大趋势分析即可）"

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
    grouped_liunian_text = "\n".join(grouped_lines) if grouped_lines else "\n".join(f"{y['year']}年 {y['pillar']}" for y in liunian)

    scope = {"10y": "未来10年", "20y": "未来20年"}.get(mode, "一生（到80岁）")
    if mode in ("10y", "20y"):
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
- 涉及夫妻宫、父母宫、子女宫等宫位论断时，必须核对【宫位】事实：只有日支才是夫妻宫，只有月支才是父母宫/兄弟宫，只有时支才是子女宫。禁止把年支、月支、时支或大运支/流年支之间的冲合错误归到这些宫位。
- 特别重要：大运支与流年支的冲合（如丙辰大运遇庚戌流年之辰戌冲）只代表大运与流年互动，不等于冲任何命局宫位。只有当流年支或大运支与命局日支/月支/时支产生冲合刑害时，才允许说对应宫位受影响。
- 正误示例：
  - 若日支为申，大运支为卯，流年支为酉，则卯酉冲是大运与流年之冲，不允许写“夫妻宫受冲”；若日支为申，流年支为寅，则寅申冲才允许写“冲夫妻宫”。
  - 若月支为未，大运支为辰，流年支为戌，则辰戌冲只是大运与流年互动，不允许写“父母宫受冲”；只有流年支或大运支与月支未产生作用时，才允许写“父母宫动”。
  - 错误示例（禁止）：“辰戌冲，父母宫与夫妻宫皆动”。正确写法：“辰戌冲，大运与流年交战，引动全局土气，长辈健康或家庭房产易有波动；夫妻宫日支申因申辰半合被牵连，配偶事务亦有变化”。
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

参考案例（仅供断语风格与应验场景参考，不要直接照搬结论）：
{cases_text}

{yearly_instruction}
"""


def _rule_based_yearly(
    bazi: str,
    dayun: List[Dict],
    liunian: List[Dict],
    birth_year: int,
    last_error: Optional[Exception] = None,
    gender: str = "",
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
    _BRANCH_MAIN_QI = {
        "子": "癸", "丑": "己", "寅": "甲", "卯": "乙", "辰": "戊",
        "巳": "丙", "午": "丁", "未": "己", "申": "庚", "酉": "辛",
        "戌": "戊", "亥": "壬",
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
        yr_stem, yr_branch = yr_pillar[0], yr_pillar[1]
        dy_branch = dy_pillar[1]
        yr_stem_shishen = _shishen(yr_stem)

        if interaction and interaction.startswith("冲"):
            return (
                f"{yr_pillar}这一年落在{dy_pillar}大运，地支{yr_branch}和{dy_branch}一冲，"
                f"生活上容易有变动，工作、住处或感情都可能被牵动。"
            )

        stem_phrase = ""
        if yr_stem_rel in ("生助", "比劫"):
            stem_phrase = f"流年天干{yr_stem}是{yr_stem_shishen}，对你有助益"
        elif yr_stem_rel == "受克":
            stem_phrase = f"流年天干{yr_stem}是{yr_stem_shishen}，会给你带来一些压力"
        elif yr_stem_rel == "泄耗":
            stem_phrase = f"流年天干{yr_stem}是{yr_stem_shishen}，想法、表达或输出会变多"
        elif yr_stem_rel == "克制":
            stem_phrase = f"流年天干{yr_stem}是{yr_stem_shishen}，有掌控、支配的意味"
        else:
            stem_phrase = f"流年天干{yr_stem}是{yr_stem_shishen}"

        branch_phrase = ""
        if yr_branch_rel in ("生助", "比劫"):
            branch_phrase = f"地支{yr_branch}得助"
        elif yr_branch_rel == "受克":
            branch_phrase = f"地支{yr_branch}受克"
        elif yr_branch_rel == "泄耗":
            branch_phrase = f"地支{yr_branch}泄耗"
        elif yr_branch_rel == "克制":
            branch_phrase = f"地支{yr_branch}有掌控力"
        else:
            branch_phrase = f"地支{yr_branch}平和"

        dy_phrase = ""
        if dy_stem_rel in ("生助", "比劫") and yr_stem_rel not in ("生助", "比劫"):
            dy_phrase = f"{dy_pillar}大运本身是帮你的，能缓冲流年的压力"
        elif dy_stem_rel == "受克" and yr_stem_rel != "受克":
            dy_phrase = f"{dy_pillar}大运本身压力不小，流年再来只能稳中求进"

        parts = [f"{yr_pillar}这一年，{stem_phrase}，{branch_phrase}。"]
        if dy_phrase:
            parts.append(dy_phrase)
        return "".join(parts)

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
        import random

        yr_stem_shishen = _shishen(yr_stem)
        yr_branch_shishen = _shishen(yr_branch)
        dy_stem_shishen = _shishen(dy_stem)
        chong = interaction and interaction.startswith("冲")
        has_strong_trigger = chong or (yr_stem_rel == "受克" and yr_branch_rel in ("受克", "泄耗"))

        # Stable-year sentence pools to avoid repetitive "no significant fluctuation".
        stable_career = [
            "这一年工作节奏平稳，大的变动不多，适合把手头事做扎实。",
            "职场相对平稳，没有特别强的外力推动，稳住节奏更重要。",
            "事业上没太大的波澜，保持现有状态，积累比冒进更稳妥。",
            "这一年工作上机会和压力都不突出，把基本功补好是关键。",
        ]
        stable_wealth = [
            "财运不温不火，收入和支出大致平衡，别做大额冒险投资。",
            "这一年钱来得不猛，但也不会有大窟窿，控制好支出节奏就好。",
            "财务上没明显起伏，适合守财、清账，而不是扩张。",
            "求财动力一般，偏财运弱，正财靠踏实积累。",
        ]
        stable_marriage = [
            "感情生活比较平淡，没什么大冲突，也没什么特别的节点。",
            "这一年感情上没有强烈波动，单身者缘分不浓，有伴者维持现状。",
            "感情宫没被明显引动，关系稳定，但缺少突破性进展。",
            "感情上没太多新鲜事，重点在相处细节和日常沟通。",
        ]
        stable_health = [
            "身体没有大毛病，但别透支，规律作息比进补更重要。",
            "健康整体平稳，注意小毛病别拖着，体检可以安排上。",
            "这一年精力中等，不宜长期熬夜或高强度连轴转。",
            "身体没明显隐患，保持运动习惯和饮食节奏即可。",
        ]

        random.seed(yr_stem + yr_branch + str(age))

        def career() -> str:
            if not has_strong_trigger:
                return random.choice(stable_career)
            if yr_stem_shishen in ("正官", "七杀") or dy_stem_shishen in ("正官", "七杀"):
                return "官杀压顶，职场上容易遇到考核、竞争或领导变动，别正面硬顶。"
            if yr_stem_shishen in ("正印", "偏印") or dy_stem_shishen in ("正印", "偏印"):
                return "印星发力，适合考证、进修或争取上级支持，贵人运不错。"
            if yr_stem_shishen in ("食神", "伤官") or dy_stem_shishen in ("食神", "伤官"):
                return "食伤透出，创意和表达欲变强，但项目推进容易反复，别急于求成。"
            if yr_stem_shishen in ("比肩", "劫财") or dy_stem_shishen in ("比肩", "劫财"):
                return "比劫争竞，同事或合作方可能分夺资源，重要利益要白纸黑字。"
            if chong:
                return "地支逢冲，工作环境或岗位职责可能有变动，提前做准备。"
            return random.choice(stable_career)

        def wealth() -> str:
            if not has_strong_trigger:
                return random.choice(stable_wealth)
            if yr_stem_shishen in ("正财", "偏财") or dy_stem_shishen in ("正财", "偏财"):
                if yr_stem_shishen in ("比肩", "劫财") or dy_stem_shishen in ("比肩", "劫财"):
                    return "财星透干但比劫同现，容易因合作、借贷或人情破财，别轻易担保。"
                return "财星被引动，有收入增加或偏财机会，但来得快去得也快，见好就收。"
            if yr_stem_shishen in ("比肩", "劫财") or dy_stem_shishen in ("比肩", "劫财"):
                return "比劫夺财，开销增大或被朋友拖累，借钱和投资都要谨慎。"
            if yr_stem_rel == "受克" or dy_stem_rel == "受克":
                return "求财受阻，现金流偏紧，这一年不宜扩张，先把账算清楚。"
            return random.choice(stable_wealth)

        def marriage() -> str:
            if not has_strong_trigger:
                return random.choice(stable_marriage)
            if chong:
                return "夫妻宫或感情宫被冲，容易有争吵、冷战或关系变动，遇事别冲动。"
            if yr_stem_shishen in ("正财", "偏财", "正官", "七杀"):
                return "异性缘被引动，桃花机会多，但要分辨正缘和烂桃花。"
            if yr_stem_shishen in ("伤官", "劫财"):
                return "感情里容易因自我或外部竞争起摩擦，多退一步更稳。"
            return random.choice(stable_marriage)

        def health() -> str:
            if not has_strong_trigger:
                return random.choice(stable_health)
            if chong:
                return "地支相冲，注意突发伤病、交通安全和急性炎症，出行留点余量。"
            if yr_stem_rel == "受克" and yr_branch_rel == "受克":
                return "流年干支都克耗日主，免疫力容易下降，慢性病要防复发。"
            if yr_stem_rel == "泄耗" and yr_branch_rel == "泄耗":
                return "泄耗太重，精力不济，睡眠和消化系统容易亮黄灯。"
            if yr_branch_shishen in ("七杀", "伤官"):
                return "七杀或伤官临支，注意筋骨、肝胆和意外伤害，别逞强。"
            return random.choice(stable_health)

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
            return f"{yr_branch}逢冲，这一年容易有突发变动，重大决定尽量避开冲动时刻。"
        if yr_stem_rel == "受克" and yr_branch_rel == "受克":
            return "流年干支都对你不利，重大投资和人事变动尽量保守。"
        if yr_stem_rel == "受克":
            return f"天干{yr_stem}带来压力，人际关系和重要决策上多留余地。"
        if yr_branch_rel == "受克":
            return f"地支{yr_branch}不利，健康、出行和日常起居要更上心。"
        if yr_stem_rel in ("生助", "比劫"):
            return "这年有助力，可以主动争取，但别贪大求全，留条后路。"
        return "本年没有明显刑冲，按自己的节奏走就可以。"

    def _build_key_event(
        yr_stem_shishen: str,
        yr_branch_shishen: str,
        yr_stem_rel: str,
        yr_branch_rel: str,
        interaction: Optional[str],
        domains: Dict[str, str],
    ) -> str:
        if interaction and interaction.startswith("冲"):
            return "地支逢冲，工作、感情或住处可能有变动"
        if yr_stem_rel == "受克" and yr_branch_rel == "受克":
            return "流年干支皆不利日主，整体压力偏大，宜守不宜攻"
        if yr_stem_rel == "受克":
            return f"天干{yr_stem_shishen}施压，人事和决策上容易遇到阻力"
        if yr_branch_rel == "受克":
            return f"地支{yr_branch_shishen}临支，健康和出行方面要多留意"
        return "整体平顺，没有特别突出的重大节点"

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
                _shishen(yr_stem),
                _shishen(_BRANCH_MAIN_QI.get(yr_branch, "")),
                yr_stem_rel,
                yr_branch_rel,
                interaction,
                domains,
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
        "当前未连接大模型，使用的是本地规则兜底，语气上比纯模板自然，但细节深度有限。",
        "算法排盘，结果仅供参考。",
    ]

    # Palace+star synthesis liuqin interpretation.
    # For each family member we look at both the "star" (target shishen) and
    # the "palace" (pillar) where it sits, following standard Bazi theory.
    _SHISHEN_CHARACTER = {
        "正印": "心地善良、重情义、好学、保守、有依赖性，遇事习惯找靠山。",
        "偏印": "心思细腻、敏感、有独特才华，性格偏孤、想法与众不同。",
        "正官": "正直、守规矩、有责任感，注重名声，容易给自己压力。",
        "七杀": "果断、有魄力、不服输，性格偏刚、好胜心强，也易冲动。",
        "正财": "务实、节俭、重信用、顾家，对金钱和现实比较敏感。",
        "偏财": "大方、善交际、机灵、爱冒险，花钱随性，人缘广。",
        "食神": "温和、乐观、有口福、有才艺，表达自然，不喜争斗。",
        "伤官": "聪明、有才华、傲气、不服管，说话直接，容易得罪人。",
        "比肩": "独立、自信、固执、讲义气，凡事喜欢自己来。",
        "劫财": "冲动、好胜、重义气、行动力强，但也容易破财或与人争。",
    }
    _SHISHEN_APPEARANCE = {
        "正印": "气质端庄、面色白皙、身形偏圆润。",
        "偏印": "眼神有特点、气质清冷、身形偏瘦。",
        "正官": "五官端正、举止得体、给人可靠感。",
        "七杀": "眉眼有神、轮廓分明、气场偏强。",
        "正财": "相貌敦厚、身形匀称、给人踏实感。",
        "偏财": "长相有亲和力、善于打扮、显得活络。",
        "食神": "面带福相、体态偏丰满、笑容温和。",
        "伤官": "眉目清秀、气质灵动、显得聪明。",
        "比肩": "体格结实、线条硬朗、独立性外露。",
        "劫财": "身形有力量感、动作快、气势外露。",
    }
    _SHISHEN_ABILITY = {
        "正印": "适合学习、研究、教育、文书、稳定型工作。",
        "偏印": "适合技术、艺术、玄学、冷门专业、需要独创性的领域。",
        "正官": "适合管理、行政、公职、规范化、需要责任心的岗位。",
        "七杀": "适合开拓、军警、外科、工程、高压挑战性行业。",
        "正财": "适合财务、实业、稳定经营、细水长流的赚钱方式。",
        "偏财": "适合销售、投资、贸易、自由职业、偏门财源。",
        "食神": "适合演艺、餐饮、教育、创意、表达类工作。",
        "伤官": "适合技术、策划、表演、写作、需要创新和口才的工作。",
        "比肩": "适合独立创业、技术专长、体育、竞争性行业。",
        "劫财": "适合业务拓展、合作经营、需要魄力和执行力的领域。",
    }
    _SHISHEN_HEALTH = {
        "正印": "注意脾胃、消化系统，思虑过多影响睡眠。",
        "偏印": "注意神经、呼吸系统，容易多思多虑。",
        "正官": "注意血压、心脏，压力管理很重要。",
        "七杀": "注意外伤、肝胆、急性炎症，避免高危活动。",
        "正财": "注意脾胃、皮肤，饮食规律是关键。",
        "偏财": "注意肝胆、眼睛，避免熬夜和纵欲。",
        "食神": "注意肠胃、体重，消化系统偏弱。",
        "伤官": "注意眼睛、口腔、妇科（女命），情绪易上火。",
        "比肩": "注意筋骨、四肢，运动过量易受伤。",
        "劫财": "注意外伤、肝胆、血压，冲动行事易招意外。",
    }
    _PALACE_NAME = {
        0: "年柱（祖上/父母/早年）",
        1: "月柱（父母/兄弟/青年）",
        2: "日柱（自己/配偶）",
        3: "时柱（子女/晚年）",
    }

    def _element_appearance(element: str) -> str:
        return {
            "木": "身形偏修长，骨架明显。",
            "火": "脸型偏尖，气色红润，眼神有光。",
            "土": "体格敦厚，肤色偏黄，给人稳重感。",
            "金": "肤色偏白，轮廓分明，骨架适中。",
            "水": "体态圆润，肤色偏黑或偏润，眼神灵活。",
        }.get(element, "")

    def _describe_star_location(star: str, palace_idx: int, palace_pillar: str) -> str:
        """Generic star+palace description used when listing where a star appears."""
        palace = _PALACE_NAME.get(palace_idx, "某柱")
        base = f"{star}落在{palace}{palace_pillar}"
        if palace_idx == 0:
            return (
                f"{base}，与祖上、父母、早年环境相关。"
                f"此人{_SHISHEN_CHARACTER.get(star, '')}"
            )
        if palace_idx == 1:
            return (
                f"{base}，与父母、兄弟、青年阶段相关。"
                f"此人{_SHISHEN_CHARACTER.get(star, '')}"
            )
        if palace_idx == 2:
            return (
                f"{base}，落在日柱夫妻宫附近，与你自己或配偶关系密切。"
                f"此人{_SHISHEN_CHARACTER.get(star, '')}"
            )
        if palace_idx == 3:
            return (
                f"{base}，落在子女宫，与子女、晚辈、晚年相关。"
                f"此人{_SHISHEN_CHARACTER.get(star, '')}"
            )
        return base

    def _find_star_locations(star_names: Tuple[str, ...]) -> List[Tuple[int, str, str]]:
        """Find all (palace_idx, location_label, shishen) for given stars.

        If both the stem and branch main qi of the same pillar carry the same
        star, merge them into one entry to avoid repetition.
        """
        results: List[Tuple[int, str, str]] = []
        for idx, pillar in enumerate(pillars):
            stem_shishen = _shishen(pillar[0])
            branch_qi = _BRANCH_MAIN_QI.get(pillar[1], "")
            branch_shishen = _shishen(branch_qi) if branch_qi else ""
            stem_match = stem_shishen in star_names
            branch_match = branch_shishen in star_names
            if stem_match and branch_match and stem_shishen == branch_shishen:
                results.append((idx, f"天干{pillar[0]}、地支本气{branch_qi}", stem_shishen))
            else:
                if stem_match:
                    results.append((idx, f"天干{pillar[0]}", stem_shishen))
                if branch_match:
                    results.append((idx, f"地支本气{branch_qi}", branch_shishen))
        return results

    def _star_present(star_names: Tuple[str, ...]) -> bool:
        return len(_find_star_locations(star_names)) > 0

    def _count_relationship(rel: str) -> int:
        """Count stems/branches by their element relationship to day master."""
        count = 0
        for idx, pillar in enumerate(pillars):
            stem_rel = _element_relation(_STEM_ELEMENT.get(pillar[0], ""))
            if stem_rel == rel:
                count += 1
            branch_rel = _element_relation(_BRANCH_MAIN.get(pillar[1], ""))
            if branch_rel == rel:
                count += 1
        return count

    try:
        pillars = extract_pillars(bazi)
        day_master_stem = pillars[2][0]
        dm_element = _STEM_ELEMENT.get(day_master_stem, "")
        dm_yy = _YIN_YANG.get(day_master_stem, "")
        palace_pillars = [f"{p[0]}{p[1]}" for p in pillars]

        # --- Self portrait: based on day-master strength from the whole chart.
        support = _count_relationship("生助") + _count_relationship("比劫")
        drain = _count_relationship("泄耗") + _count_relationship("克制") + _count_relationship("受克")
        if support > drain + 1:
            strength = "身强"
            strength_desc = "日主周围生助多，自身能量足，性格上比较自信、主动，能担财官。"
        elif drain > support + 1:
            strength = "身弱"
            strength_desc = "日主周围克泄耗多，自身能量偏弱，性格上偏谨慎、多思，需要贵人或印比帮扶。"
        else:
            strength = "中和"
            strength_desc = "日主能量相对中和，性格不偏不倚，能屈能伸。"

        # Collect all shishen for dominant-force analysis.
        all_branch_qi = [_BRANCH_MAIN_QI.get(p[1], "") for p in pillars]
        all_shishen = [_shishen(s) for s in [p[0] for p in pillars] + all_branch_qi if s]

        def count_shishen(*names: str) -> int:
            return sum(1 for s in all_shishen if s in names)

        biji_count = count_shishen("比肩", "劫财")
        yin_count = count_shishen("正印", "偏印")
        cai_count = count_shishen("正财", "偏财")
        guan_count = count_shishen("正官", "七杀")
        shishang_count = count_shishen("食神", "伤官")

        # Dominant usable force.
        dominant = ""
        if yin_count >= 3:
            dominant = "印星旺，你学习能力强、有贵人缘，但也容易依赖、想得多。"
        elif guan_count >= 3:
            dominant = "官杀旺，你自律、有责任感，但也容易压力大、被约束。"
        elif cai_count >= 3:
            dominant = "财星旺，你现实感强、善交际，一生和钱、人际关系绑得紧。"
        elif shishang_count >= 3:
            dominant = "食伤旺，你表达欲、创造力强，聪明外露，但也容易不服管。"
        elif biji_count >= 3:
            dominant = "比劫旺，你独立、好胜、讲义气，但也要注意破财和同辈竞争。"

        lines: List[str] = []
        lines.append("【一、日主自身画像】")
        lines.append(
            f"你日主是{day_master_stem}（{dm_element}，{dm_yy}），"
            f"全局看属于{strength}。{strength_desc}"
        )
        lines.append(
            f"从五行形貌看，{dm_element}日主 {_element_appearance(dm_element)}"
        )
        if dominant:
            lines.append(dominant)
        # Ability from the most usable star.
        usable_stars = []
        if strength == "身强":
            if cai_count > 0:
                usable_stars.append("财")
            if guan_count > 0:
                usable_stars.append("官杀")
            if shishang_count > 0:
                usable_stars.append("食伤")
        elif strength == "身弱":
            if yin_count > 0:
                usable_stars.append("印")
            if biji_count > 0:
                usable_stars.append("比劫")
        _usable_ability_map = {
            "财": _SHISHEN_ABILITY.get("正财"),
            "官杀": _SHISHEN_ABILITY.get("正官"),
            "食伤": _SHISHEN_ABILITY.get("食神"),
            "印": _SHISHEN_ABILITY.get("正印"),
            "比劫": _SHISHEN_ABILITY.get("比肩"),
        }
        if usable_stars:
            ability_text = _usable_ability_map.get(usable_stars[0], "根据命局特点选择方向。")
            lines.append(
                f"按你的旺衰，适合走的是{ '、'.join(usable_stars) }路线：{ability_text}"
            )
        lines.append(
            f"健康上要注意：{_SHISHEN_HEALTH.get(_shishen(day_master_stem), '平时注意劳逸结合。')}"
        )

        # --- Parents.
        lines.append("\n【二、父母与祖上】")
        father_stars = ("偏财", "正财")
        mother_stars = ("正印", "偏印")
        father_locations = _find_star_locations(father_stars)
        mother_locations = _find_star_locations(mother_stars)

        if father_locations:
            lines.append("父亲（以财星为星）：")
            for idx, label, star in father_locations:
                lines.append(f"  · {_describe_star_location(star, idx, palace_pillars[idx])}")
                lines.append(f"    外貌：{_SHISHEN_APPEARANCE.get(star, '')}")
        else:
            lines.append("父亲（以财星为星）：命局财星不显，父亲缘分较淡，或父亲在你生命中存在感不强。")

        if mother_locations:
            lines.append("母亲（以印星为星）：")
            for idx, label, star in mother_locations:
                lines.append(f"  · {_describe_star_location(star, idx, palace_pillars[idx])}")
                lines.append(f"    外貌：{_SHISHEN_APPEARANCE.get(star, '')}")
        else:
            lines.append("母亲（以印星为星）：命局印星不显，母亲缘分较淡，或成长过程中独立色彩重。")

        # Add palace-level observations for parents.
        year_month_influences = []
        if yin_count >= 2:
            year_month_influences.append("印星在年月柱多见，母亲或长辈对你人生影响大，早年有贵人庇护。")
        if cai_count >= 2:
            year_month_influences.append("财星在年月柱多见，父亲或家庭经济状况是你成长中的重要变量。")
        if biji_count >= 2:
            year_month_influences.append("比劫在年月柱多见，家中同辈竞争或合作色彩重。")
        for note in year_month_influences:
            lines.append(note)

        # --- Spouse.
        lines.append("\n【三、配偶与婚姻】")
        spouse_branch = pillars[2][1]
        spouse_branch_qi = _BRANCH_MAIN_QI.get(spouse_branch, "")
        spouse_shishen = _shishen(spouse_branch_qi) if spouse_branch_qi else "未知"
        lines.append(
            f"夫妻宫在日支{spouse_branch}，本气{spouse_branch_qi}为{spouse_shishen}。"
            f"这是配偶的『家』，直接反映配偶性格和婚姻状态。"
        )
        lines.append(
            f"夫妻宫本气{spouse_shishen}，配偶{_SHISHEN_CHARACTER.get(spouse_shishen, '')}"
        )
        lines.append(f"配偶外貌：{_SHISHEN_APPEARANCE.get(spouse_shishen, '')}")

        # Spouse star (male: 财, female: 官杀).
        if gender in ("男", "male"):
            spouse_star_names = ("正财", "偏财")
            spouse_star_label = "妻星"
        elif gender in ("女", "female"):
            spouse_star_names = ("正官", "七杀")
            spouse_star_label = "夫星"
        else:
            spouse_star_names = ()
            spouse_star_label = "配偶星"
        spouse_star_locations = _find_star_locations(spouse_star_names)
        if spouse_star_locations:
            lines.append(f"{spouse_star_label}（{ '、'.join(spouse_star_names) }）在命中的位置：")
            for idx, label, star in spouse_star_locations:
                lines.append(f"  · {label}{star}在{_PALACE_NAME.get(idx, '某柱')}，"
                           f"{_SHISHEN_CHARACTER.get(star, '')}")
        else:
            lines.append(f"{spouse_star_label}不显，配偶缘分可能来得晚，或婚姻关系偏淡。")

        # --- Children.
        lines.append("\n【四、子女与晚辈】")
        if gender in ("男", "male"):
            child_star_names = ("正官", "七杀")
            child_star_label = "官杀（男命子女星）"
        elif gender in ("女", "female"):
            child_star_names = ("食神", "伤官")
            child_star_label = "食伤（女命子女星）"
        else:
            child_star_names = ()
            child_star_label = "子女星"
        child_locations = _find_star_locations(child_star_names)
        lines.append(
            f"子女宫在时柱{pillars[3][0]}{pillars[3][1]}，"
            f"天干{_shishen(pillars[3][0])}、地支本气{_BRANCH_MAIN_QI.get(pillars[3][1], '')}"
            f"为{_shishen(_BRANCH_MAIN_QI.get(pillars[3][1], ''))}。"
        )
        if child_locations:
            lines.append(f"{child_star_label}分布：")
            for idx, label, star in child_locations:
                lines.append(f"  · {_describe_star_location(star, idx, palace_pillars[idx])}")
                lines.append(f"    外貌：{_SHISHEN_APPEARANCE.get(star, '')}")
        else:
            lines.append(f"{child_star_label}不显，子女缘可能较淡，或得子较晚。")

        # --- Siblings / friends.
        lines.append("\n【五、兄弟与朋友】")
        sibling_stars = ("比肩", "劫财")
        sibling_locations = _find_star_locations(sibling_stars)
        if sibling_locations:
            lines.append("比劫星（兄弟朋友星）分布：")
            for idx, label, star in sibling_locations:
                lines.append(f"  · {_describe_star_location(star, idx, palace_pillars[idx])}")
        else:
            lines.append("比劫星不显，兄弟姐妹缘分较薄，或你从小独立意识强。")

        # --- Synthesis.
        family_relations_notes: List[str] = []
        if yin_count + guan_count >= 4:
            family_relations_notes.append(
                "印星、官杀旺，家庭规矩感重，你的一生容易受长辈、权威或婚姻对象影响。"
            )
        if cai_count + shishang_count >= 4:
            family_relations_notes.append(
                "财星、食伤旺，你重实际、重表达，六亲关系中金钱和价值观的冲突会多些。"
            )
        if biji_count >= 3:
            family_relations_notes.append(
                "比劫旺，兄弟朋友对你助力大，但也要注意同辈分夺和人际摩擦。"
            )
        family_relations_notes.append(
            "以上为本地规则结合星宫同参的解读，对每位六亲都同时参考了"
            "『星』（对应十神）和『宫』（所在柱位）。"
        )

        # Helper to summarize a list of star locations into a single readable string.
        def _star_summary(locations: List[Tuple[int, str, str]]) -> str:
            if not locations:
                return "不显"
            parts = []
            for idx, label, star in locations:
                parts.append(f"{star}在{_PALACE_NAME.get(idx, '某柱')}{palace_pillars[idx]}（{label}）")
            return "、".join(parts)

        # Father summary.
        father_primary = father_locations[0] if father_locations else None
        father_shishen = father_primary[2] if father_primary else ""
        father_relationship = ""
        if father_shishen:
            if cai_count >= 2:
                father_relationship = "父亲或家庭经济状况对你影响较大，你从小就对金钱和现实比较敏感。"
            else:
                father_relationship = "父亲对你的影响平稳，家风务实。"
        else:
            father_relationship = "父亲星不显，父亲缘分较淡，或父亲在你生命中存在感不强。"

        # Mother summary.
        mother_primary = mother_locations[0] if mother_locations else None
        mother_shishen = mother_primary[2] if mother_primary else ""
        mother_relationship = ""
        if mother_shishen:
            if yin_count >= 2:
                mother_relationship = "母亲或长辈对你人生影响大，早年有贵人庇护。"
            else:
                mother_relationship = "母亲对你的影响温和，关系稳定。"
        else:
            mother_relationship = "母亲星不显，母亲缘分较淡，或成长过程中独立色彩重。"

        # Spouse summary.
        spouse_relationship = (
            f"夫妻宫在日支{spouse_branch}，本气{spouse_branch_qi}为{spouse_shishen}。"
        )
        if gender in ("男", "male") and spouse_star_locations:
            spouse_relationship += "男命以财星为妻星，妻星透出则婚姻动得早。"
        elif gender in ("女", "female") and spouse_star_locations:
            spouse_relationship += "女命以官杀为夫星，夫星有力则配偶有能力。"

        # Children summary.
        if gender in ("男", "male"):
            son_star = "七杀"
            daughter_star = "正官"
        elif gender in ("女", "female"):
            son_star = "伤官"
            daughter_star = "食神"
        else:
            son_star = daughter_star = ""
        son_locations = [loc for loc in child_locations if loc[2] == son_star]
        daughter_locations = [loc for loc in child_locations if loc[2] == daughter_star]
        son_text = _star_summary(son_locations) if son_locations else "信息不显"
        daughter_text = _star_summary(daughter_locations) if daughter_locations else "信息不显"
        children_relationship = ""
        if child_locations:
            if len(child_locations) >= 2:
                children_relationship = "子女星多见，子女缘不浅，但也要防管教过严或期望过高。"
            else:
                children_relationship = "子女星适中，子女运平稳，教育上重引导而非压制。"
        else:
            children_relationship = "子女星不显，子女缘分可能较淡，或得子较晚。"

        # Siblings summary.
        brother_locations = [loc for loc in sibling_locations if loc[2] == "比肩"]
        sister_locations = [loc for loc in sibling_locations if loc[2] == "劫财"]
        brother_text = _star_summary(brother_locations) if brother_locations else "信息不显"
        sister_text = _star_summary(sister_locations) if sister_locations else "信息不显"
        siblings_relationship = ""
        if biji_count >= 3:
            siblings_relationship = (
                "比劫星多见，兄弟朋友缘分深，关键时刻有人帮衬，"
                "但同辈之间也容易有竞争、分夺或借钱不还的情况。"
            )
        elif biji_count == 0:
            siblings_relationship = (
                "比劫星不显，兄弟姐妹缘分较薄，或者你从小独立意识强，"
                "很多事情习惯自己扛。"
            )
        else:
            siblings_relationship = (
                "比劫星适中，兄弟朋友能给你助力，合作与竞争并存，"
                "重要利益最好白纸黑字说清楚。"
            )

        liuqin_obj = {
            "father": {
                "star": _star_summary(father_locations),
                "character": _SHISHEN_CHARACTER.get(father_shishen, "父星不显，难以论断。"),
                "ability": _SHISHEN_ABILITY.get(father_shishen, "信息不足。"),
                "health": _SHISHEN_HEALTH.get(father_shishen, "平时注意劳逸结合。"),
                "relationship": father_relationship,
            },
            "mother": {
                "star": _star_summary(mother_locations),
                "character": _SHISHEN_CHARACTER.get(mother_shishen, "母星不显，难以论断。"),
                "ability": _SHISHEN_ABILITY.get(mother_shishen, "信息不足。"),
                "health": _SHISHEN_HEALTH.get(mother_shishen, "平时注意劳逸结合。"),
                "relationship": mother_relationship,
            },
            "spouse": {
                "palace": f"日支{spouse_branch}，本气{spouse_branch_qi}为{spouse_shishen}",
                "star": _star_summary(spouse_star_locations),
                "character": _SHISHEN_CHARACTER.get(spouse_shishen, "夫妻宫信息不足。"),
                "ability": _SHISHEN_ABILITY.get(spouse_shishen, "信息不足。"),
                "health": _SHISHEN_HEALTH.get(spouse_shishen, "平时注意劳逸结合。"),
                "appearance": _SHISHEN_APPEARANCE.get(spouse_shishen, ""),
                "relationship": spouse_relationship,
            },
            "children": {
                "sons": f"儿子以{son_star}为参考：{son_text}" if son_star else "信息不足",
                "daughters": f"女儿以{daughter_star}为参考：{daughter_text}" if daughter_star else "信息不足",
                "relationship": children_relationship,
            },
            "siblings": {
                "brothers": f"兄弟以比肩为参考：{brother_text}",
                "sisters": f"姐妹以劫财为参考：{sister_text}",
                "relationship": siblings_relationship,
            },
            "family_relations": "\n".join(family_relations_notes),
        }
    except Exception:
        liuqin_obj = {
            "father": {"star": "", "character": "", "ability": "", "health": "", "relationship": ""},
            "mother": {"star": "", "character": "", "ability": "", "health": "", "relationship": ""},
            "spouse": {"palace": "", "star": "", "character": "", "ability": "", "health": "", "appearance": "", "relationship": ""},
            "children": {"sons": "", "daughters": "", "relationship": ""},
            "siblings": {"brothers": "", "sisters": "", "relationship": ""},
            "family_relations": "",
        }

    overall = (
        "目前大模型暂时不可用，这里用的是本地规则分析。"
        "已经把大运和流年的干支关系、十神作用理了一遍，给出了相对自然的解读。"
        "如果你想得到更深入、更像面对面聊天的分析，可以等 Agnes API 恢复后重试。"
    )

    return {
        "dayun_summary": dayun_summary,
        "yearly_analysis": yearly_analysis,
        "liuqin_analysis": liuqin_obj,
        "milestones": milestones,
        "overall_guidance": overall,
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
    start_year: Optional[int] = None,
    years: Optional[int] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    knowledge_base_path: Optional[Path] = None,
    extra_knowledge_base_paths: Optional[List[Path]] = None,
    cases_path: Optional[Path] = None,
    extra_cases_paths: Optional[List[Path]] = None,
    embedding_cache_path: Optional[Path] = None,
    knowledge_embedding_cache_path: Optional[Path] = None,
    top_k: int = 3,
) -> Dict:
    """Analyze yearly luck (liunian) based on dayun and birth info.

    *mode* can be ``"10y"`` / ``"20y"`` / ``"lifetime"``.
    Optional *start_year* + *years* override the mode-derived calendar range
    (aligned with 紫微/七政 frontend controls).
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

    if start_year is not None and years is not None:
        start_year = int(start_year)
        span = max(1, min(int(years), 80))
        end_year = start_year + span - 1
    elif mode == "10y":
        start_year = current_year
        end_year = current_year + 9
    elif mode == "20y":
        start_year = current_year
        end_year = current_year + 19
    else:
        start_year = birth_year
        end_year = birth_year + until_age - 1

    liunian = calendar.liunian_list(start_year, end_year)

    # Filter dayun to those strictly overlapping the analyzed years.
    # A dayun that ends exactly when the analysis starts (or vice versa) is a
    # boundary case and is not considered active for the period.
    period_start_age = start_year - birth_year
    period_end_age = end_year - birth_year
    dayun_active = [
        d
        for d in dayun
        if d["end_age"] > period_start_age and d["start_age"] < period_end_age
    ]

    knowledge_paths = [Path("./bazi_knowledge/rule_primer.md")]
    if knowledge_base_path is not None and knowledge_base_path.exists():
        knowledge_paths.append(knowledge_base_path)
    for path in extra_knowledge_base_paths or []:
        if path.exists():
            knowledge_paths.append(path)
    knowledge_context = await retrieve_knowledge_snippets(
        query=f"{bazi}\n大运流年精排".strip(),
        knowledge_paths=knowledge_paths,
        cache_path=knowledge_embedding_cache_path,
        top_k=6,
        max_chars=10000,
    )

    # Retrieve similar cases for more grounded, chart-specific predictions.
    similar_cases = []
    if cases_path is not None and cases_path.exists():
        similar_cases = await retrieve_similar_cases(
            bazi,
            question="",
            cases_path=cases_path,
            top_k=max(0, min(top_k, 10)),
            embedding_cache_path=embedding_cache_path,
            extra_cases_paths=extra_cases_paths,
        )

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

    system_prompt = _build_yearly_system_prompt(knowledge_context)
    user_prompt = _build_yearly_user_prompt(
        bazi, gender, dayun_active, liunian, mode, profile, yearly_rels, birth_year, similar_cases
    )

    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key or aiohttp is None:
        return _rule_based_yearly(bazi, dayun_active, liunian, birth_year, gender=gender)

    base = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    mdl = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.25,
        "max_tokens": 8000 if mode == "20y" else 7000,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, 3):
        try:
            timeout = aiohttp.ClientTimeout(total=200 if mode == "20y" else 150)
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
                            gender=gender,
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
                            bazi, dayun_active, liunian, birth_year, gender=gender
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

    return _rule_based_yearly(bazi, dayun_active, liunian, birth_year, gender=gender)


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

    # 三合/半合/三会/藏干合等复杂关系若引动日支，也算强触发。
    dz_comp = rel.get("di_zhi_comprehensive", {})
    for name in ("三合", "半合", "三会", "藏干合"):
        for item in dz_comp.get(name, []):
            if "日支" in item:
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


def _sanitize_dayun_summary(
    dayun_summary: List[Dict],
    dayun_active: List[Dict],
) -> List[Dict]:
    """Ensure the AI's dayun summary matches the structurally computed dayun list.

    The model often drops start_age/end_age or invents a wrong pillar. This
    function rewrites the summary to contain exactly the active dayun periods,
    preserving the AI-generated theme/focus text when possible.
    """
    if not dayun_active:
        return dayun_summary

    # Build a lookup by pillar for AI-generated theme/focus.
    ai_by_pillar: Dict[str, Dict] = {}
    for d in dayun_summary or []:
        if isinstance(d, dict) and d.get("pillar"):
            ai_by_pillar[d["pillar"]] = d

    cleaned: List[Dict] = []
    for d in dayun_active:
        ai = ai_by_pillar.get(d["pillar"], {})
        cleaned.append(
            {
                "pillar": d["pillar"],
                "start_age": d["start_age"],
                "end_age": d["end_age"],
                "theme": _sanitize_text(str(ai.get("theme", "") or "")),
                "focus": _sanitize_text(str(ai.get("focus", "") or "")),
            }
        )
    return cleaned


def _validate_yearly_output(
    result: Dict,
    bazi: str,
    dayun: List[Dict],
    liunian: List[Dict],
    birth_year: int,
) -> Dict:
    """Sanity-check yearly output; fall back to rule-based if too generic or factually off."""
    # Align dayun summary with computed dayun list before any other checks.
    result["dayun_summary"] = _sanitize_dayun_summary(
        result.get("dayun_summary", []), dayun
    )

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
    liuqin = result.get("liuqin_analysis")
    if isinstance(liuqin, str):
        result["liuqin_analysis"] = _sanitize_liuqin(_sanitize_text(liuqin))
    elif isinstance(liuqin, dict):
        result["liuqin_analysis"] = _sanitize_liuqin_object(liuqin)

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
        # 必须把三合/半合/三会/藏干合等复杂关系也算作日支被引动，否则模型正确引用
        # 申辰半合、寅卯辰三会等事实时会被误判为夫妻宫误归。
        for item in rel.get("di_zhi_comprehensive", {}).get("三合", []):
            if "日支" in item:
                interacting.add(day_branch)
        for item in rel.get("di_zhi_comprehensive", {}).get("半合", []):
            if "日支" in item:
                interacting.add(day_branch)
        for item in rel.get("di_zhi_comprehensive", {}).get("三会", []):
            if "日支" in item:
                interacting.add(day_branch)
        for item in rel.get("di_zhi_comprehensive", {}).get("藏干合", []):
            if "日支" in item:
                interacting.add(day_branch)
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


def _sanitize_liuqin(text: str) -> str:
    """Patch common sentence fragments in liuqin analysis."""
    if not isinstance(text, str):
        return text
    # Strip redundant leading labels that the model often echoes (e.g. "母亲能力，...").
    text = re.sub(r"^(父亲能力|母亲能力|配偶能力|子女缘|命主与子女关系|命主与兄弟姐妹关系|婚姻稳定性|夫妻宫|夫妻星|配偶与命主父母关系)，\s*", "", text)
    # Drop mid-sentence relation labels that the model leaves as placeholders.
    text = text.replace("配偶与命主父母关系，", "")
    text = text.replace("婆媳关系，", "")
    # Complete common trailing fragments so sentences do not end abruptly.
    fragment_completions = {
        "祖上家境": "祖上家境普通",
        "早年家境": "早年家境普通",
        "父亲身体": "父亲身体偏弱",
        "母亲身体": "母亲身体偏弱",
        "父亲能力": "父亲能力中等，属于踏实稳重的类型",
        "母亲能力": "母亲能力温和，以持家和精神支持为主",
        "兄弟缘": "兄弟缘一般",
        "姐妹缘": "姐妹缘一般",
        "配偶对你": "配偶对你有帮助",
        "配偶对": "配偶对你有帮助",
        "子女缘": "子女缘一般",
        "晚年运势": "晚年运势平稳",
        "下属关系": "下属关系一般",
        "与命主关系": "与命主关系一般",
        "与子女关系": "与子女关系一般",
        "与兄弟姐妹关系": "与兄弟姐妹关系一般",
        "父母关系": "父母关系一般",
        "夫妻关系": "夫妻关系一般",
        "婚姻中需": "婚姻中需要互相包容",
        "需": "需要多磨合",
        "需和理解": "需要互相理解",
        "需要和理解": "需要互相理解",
    }
    for fragment, completion in fragment_completions.items():
        # Only patch when the fragment is at the very end of the text
        # (optionally followed by punctuation), avoiding mid-sentence replacements.
        text = re.sub(
            rf"{re.escape(fragment)}[，。；]?\s*$",
            completion,
            text,
        )
    # Remove dangling trailing conjunctions/fragments.
    text = re.sub(r"[，。；]+\s*(但|而|不过|只是|因为|所以|而且|此外)$", "。", text)
    # Drop trailing "关系" or "关系，" that leaves the sentence unfinished.
    text = re.sub(r"[，。；]+\s*关系\s*$", "。", text)
    # Patch common trailing fragment forms that the model often leaves open.
    text = re.sub(r"姐妹缘分\s*$", "姐妹缘分较浅，与命主往来不多", text)
    text = re.sub(r"兄弟缘分\s*$", "兄弟缘分一般，彼此独立", text)
    text = re.sub(r"[，。；]{2,}", "，", text)
    return text.strip("，。； ")


def _sanitize_liuqin_object(liuqin: Dict) -> Dict:
    """Sanitize a structured liuqin object and ensure required keys exist.

    The model may return either nested dicts or plain paragraph strings for
    each family member; both shapes are normalized so the frontend can render
    them uniformly.
    """
    cleaned: Dict[str, Any] = {}
    defaults = {
        "father": {"star": "", "character": "", "ability": "", "health": "", "relationship": ""},
        "mother": {"star": "", "character": "", "ability": "", "health": "", "relationship": ""},
        "spouse": {"palace": "", "star": "", "character": "", "ability": "", "health": "", "appearance": "", "relationship": ""},
        "children": {"sons": "", "daughters": "", "relationship": ""},
        "siblings": {"brothers": "", "sisters": "", "relationship": ""},
        "family_relations": "",
    }
    for key, default in defaults.items():
        value = liuqin.get(key, default)
        if isinstance(value, dict):
            cleaned[key] = {
                k: _sanitize_liuqin(_sanitize_text(str(v)))
                for k, v in {**default, **value}.items()
            }
        else:
            cleaned[key] = _sanitize_liuqin(_sanitize_text(str(value)))
    return cleaned


def _force_det_fields(
    result: Dict,
    bazi: str,
    *,
    liuqin_facts: Optional[Dict] = None,
    structural_facts: Optional[Dict] = None,
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
) -> Dict:
    """Overwrite symbolic fields with deterministic engine values.

    Prompt instructions alone are insufficient: models still rewrite 用神 / 六亲强弱.
    Post-process is the hard guarantee that det accuracy reaches the product surface.
    """
    caveats = list(result.get("caveats") or [])
    if structural_facts is None:
        structural_facts = structural_profile(bazi) or {}
    if liuqin_facts is None:
        liuqin_facts = liuqin_profile(bazi, gender=gender) or {}

    basic = result.get("basic_info")
    if not isinstance(basic, dict):
        basic = {}
        result["basic_info"] = basic

    def _as_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        text = str(value).replace("、", ",").replace("，", ",")
        return [p.strip() for p in text.split(",") if p.strip()]

    det_useful = _as_list(structural_facts.get("useful_gods"))
    det_taboo = _as_list(structural_facts.get("taboo_gods"))
    if det_useful:
        prev = basic.get("useful_gods")
        basic["useful_gods"] = det_useful
        if prev is not None and _as_list(prev) != det_useful:
            caveats.append("用神已按程序扶抑/调候结果强制覆盖")
    if det_taboo:
        prev = basic.get("taboo_gods")
        basic["taboo_gods"] = det_taboo
        if prev is not None and _as_list(prev) != det_taboo:
            caveats.append("忌神已按程序结果强制覆盖")

    # Strength from structural profile when available
    det_strength = structural_facts.get("strength") or structural_facts.get("day_master_strength")
    if det_strength:
        basic["day_master_strength"] = det_strength

    lq_keys = ("father", "mother", "spouse", "son", "daughter", "brother", "sister")
    forced_lq: Dict[str, str] = {}
    for key in lq_keys:
        info = liuqin_facts.get(key) if isinstance(liuqin_facts, dict) else None
        if not isinstance(info, dict):
            forced_lq[key] = "弱"
            continue
        strength = info.get("strength")
        if strength in ("强", "弱"):
            forced_lq[key] = strength
        else:
            # 不现 / 缘薄 → 产品层按弱处理（避免空值被模型回填）
            forced_lq[key] = "弱"

    prev_lq = result.get("liuqin_strength")
    result["liuqin_strength"] = forced_lq
    result["_det_enforced"] = {
        "liuqin_strength": True,
        "useful_gods": bool(det_useful),
        "taboo_gods": bool(det_taboo),
    }
    if prev_lq != forced_lq:
        caveats.append("六亲强弱已按程序 det 层强制覆盖（禁止模型改判）")

    # Detailed det 六亲细断 (性格/健康/关系/大运应期提要)
    dossier = None
    try:
        from tools.bazi_ai.liuqin_dossier import (
            build_liuqin_dossier,
            format_liuqin_dossier_markdown,
        )

        dossier = build_liuqin_dossier(
            bazi,
            gender=gender,
            birth_date=birth_date or "",
            birth_time=birth_time or "00:00",
        )
    except Exception:
        dossier = None
    if dossier:
        result["liuqin_dossier"] = dossier
        result["_det_enforced"]["liuqin_dossier"] = True

    # Soft-align free-text liuqin_analysis: inject a machine-readable prefix block.
    prefix_lines = ["【程序六亲强弱·强制】"]
    label = {
        "father": "父亲",
        "mother": "母亲",
        "spouse": "配偶",
        "son": "儿子",
        "daughter": "女儿",
        "brother": "兄弟",
        "sister": "姐妹",
    }
    for key in lq_keys:
        prefix_lines.append(f"{label[key]}：{forced_lq[key]}")
    if dossier and dossier.get("children_bias"):
        prefix_lines.append(f"子女偏向：{dossier['children_bias']}")
    prefix = "\n".join(prefix_lines) + "\n\n"
    analysis = result.get("liuqin_analysis")
    if isinstance(analysis, str) and analysis.strip():
        if not analysis.startswith("【程序六亲强弱"):
            result["liuqin_analysis"] = prefix + analysis
    elif not analysis:
        # Prefer full det narratives when model omitted the field.
        if dossier:
            bits = [
                (dossier.get("members") or {}).get(k, {}).get("narrative")
                or f"{label[k]}：{forced_lq[k]}"
                for k, _ in (
                    ("father", None),
                    ("mother", None),
                    ("spouse", None),
                    ("son", None),
                    ("daughter", None),
                    ("brother", None),
                    ("sister", None),
                )
            ]
            result["liuqin_analysis"] = prefix + "\n\n".join(b for b in bits if b)
        else:
            bits = []
            for key in lq_keys:
                info = (liuqin_facts or {}).get(key) or {}
                desc = info.get("description") or f"{label[key]}星{forced_lq[key]}"
                bits.append(desc)
            result["liuqin_analysis"] = prefix + "\n".join(bits)

    if caveats:
        result["caveats"] = caveats
    return result


def _validate_output(
    result: Dict,
    bazi: str,
    *,
    liuqin_facts: Optional[Dict] = None,
    structural_facts: Optional[Dict] = None,
    gender: str = "male",
    question: str = "",
    birth_date: str = "",
    birth_time: str = "00:00",
) -> Dict:
    """Sanity-check model output and add caveats for obvious mismatches."""
    basic = result.get("basic_info", {})
    if not isinstance(basic, dict):
        basic = {}
        result["basic_info"] = basic
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
    if isinstance(result.get("shensha_summary"), str):
        result["shensha_summary"] = _sanitize_text(result["shensha_summary"])

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

    # Ensure wealth_forecast is a dict with expected keys for yearly analysis.
    wealth_forecast = result.get("wealth_forecast")
    if not isinstance(wealth_forecast, dict):
        result["wealth_forecast"] = {
            "lifetime_potential": "",
            "tier1_cities": "",
            "tier2_cities": "",
            "tier3_cities": "",
            "peak_period": "",
            "key_years": [],
            "evidence": "",
        }

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
    # Hard guarantee: det fields always win over model freestyle.
    result = _force_det_fields(
        result,
        bazi,
        liuqin_facts=liuqin_facts,
        structural_facts=structural_facts,
        gender=gender,
        birth_date=birth_date or "",
        birth_time=birth_time or "00:00",
    )
    # Product honesty layer: year/应期 display mode (never asserts a single year).
    try:
        from tools.bazi_ai.year_timing_surface import resolve_year_timing

        # Free-form analyze has no MCQ options → open-ended path (trend_only or
        # unavailable). Dedicated /bazi/year-timing accepts option lists.
        yts = resolve_year_timing(
            bazi,
            question or "综合运势",
            options=None,
            gender=gender,
            birth_date=birth_date or "",
            birth_time=birth_time or "00:00",
        )
        result["year_timing_surface"] = yts.to_dict()
    except Exception:
        pass
    _link_year_timing_liuqin(
        result,
        question=question or "",
        bazi=bazi,
        gender=gender,
        birth_date=birth_date or "",
        birth_time=birth_time or "00:00",
    )
    return result


def _link_year_timing_liuqin(
    result: Dict,
    *,
    question: str = "",
    bazi: str = "",
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
) -> None:
    """Ensure dossier exists then bridge year_timing ↔ liuqin liunian samples."""
    if not result.get("liuqin_dossier") and bazi:
        try:
            from tools.bazi_ai.liuqin_dossier import build_liuqin_dossier

            result["liuqin_dossier"] = build_liuqin_dossier(
                bazi,
                gender=gender,
                birth_date=birth_date or "",
                birth_time=birth_time or "00:00",
            )
        except Exception:
            pass
    yts = result.get("year_timing_surface")
    dossier = result.get("liuqin_dossier")
    if isinstance(yts, dict) and isinstance(dossier, dict):
        try:
            from tools.bazi_ai.year_timing_surface import enrich_year_timing_with_liuqin

            result["year_timing_surface"] = enrich_year_timing_with_liuqin(
                yts, dossier, question=question or ""
            )
        except Exception:
            pass


def _attach_year_timing(
    result: Dict,
    bazi: str,
    *,
    question: str = "",
    gender: str = "male",
    birth_date: str = "",
    birth_time: str = "00:00",
) -> Dict:
    """Attach year_timing_surface for mock / fallback paths (no LLM)."""
    try:
        from tools.bazi_ai.year_timing_surface import resolve_year_timing

        yts = resolve_year_timing(
            bazi,
            question or "综合运势",
            options=None,
            gender=gender,
            birth_date=birth_date or "",
            birth_time=birth_time or "00:00",
        )
        result["year_timing_surface"] = yts.to_dict()
    except Exception:
        pass
    _link_year_timing_liuqin(
        result,
        question=question,
        bazi=bazi,
        gender=gender,
        birth_date=birth_date,
        birth_time=birth_time,
    )
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
