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

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from tools.bazi_ai.bazi_validator import (
    day_master,
    extract_pillars,
    month_branch,
    normalize_bazi,
)

# Domain keywords used to boost retrieval when the user asks a domain question.
_DOMAIN_KEYWORDS = {
    "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁", "贵人"],
    "wealth": ["财", "钱", "富", "收入", "资产", "赚钱", "百万", "千万", "小康"],
    "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚", "离婚"],
    "health": ["健康", "病", "身体", "手术", "肾", "妇科", "心脏", "血液", "子宫"],
    "family": ["父母", "父亲", "母亲", "子女", "孩子", "兄弟", "姐妹"],
}


def _load_cases(cases_path: Path) -> List[Dict]:
    if not cases_path.exists():
        return []
    cases = []
    with cases_path.open("r", encoding="utf-8") as f:
        for line in f:
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


def retrieve_similar_cases(
    bazi: str,
    question: str,
    cases_path: Path,
    top_k: int = 3,
) -> List[Dict]:
    """Return the top-k most relevant cases."""
    cases = _load_cases(cases_path)
    scored = [(_case_relevance(c, bazi, question), c) for c in cases]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _build_rule_primer(knowledge_base_path: Path, max_chars: int = 10000) -> str:
    """Load a short rule primer from the PDF knowledge base."""
    if not knowledge_base_path.exists():
        return ""
    text = knowledge_base_path.read_text(encoding="utf-8")
    # Truncate to avoid blowing up the prompt.
    return text[:max_chars]


def _build_system_prompt(rule_primer: str) -> str:
    return f"""你是一位经验丰富的八字命理师，风格务实、断语明确。

分析原则：
1. 以子平格局和旺衰喜用为主，必要时参考盲派做功思路。
2. 必须一步一步推理：排盘 → 定日主旺衰 → 取格局 → 取用神/忌神 → 分领域断事。每一步都要在 reasoning 中写明。
3. 结论要具体，避免泛泛而谈（如"运势不错"）。要给出可验证的判断：适合什么行业、婚姻早晚、财运量级、健康注意部位等。
4. 如果八字有争议或时辰不准，必须给出置信度和 caveat。
5. 输出必须是 JSON，不要有任何额外解释文字。
6. 在给出最终结论前，先用基础知识交叉验证：日主、月令、格局、用神忌神的组合是否合理。

示例输出格式（仅供参考，不要直接照搬内容）：
{{
  "basic_info": {{
    "bazi": "甲子 丙寅 戊辰 庚午",
    "day_master": "戊",
    "month_branch": "寅",
    "pattern": "七杀格",
    "useful_gods": ["火", "土"],
    "taboo_gods": ["木", "水"]
  }},
  "reasoning": "戊土生于寅月，木旺土虚，日主偏弱。年支子水、月干丙火生土，时支午火为根，综合来看身弱喜印比。月令寅木七杀当令，取七杀格。用神取火土，忌神为木水。事业上宜从事稳定、技术或管理类岗位，不宜高风险投机。",
  "domain_analysis": {{
    "career": "适合技术、工程、管理类岗位，30岁后渐入佳境。",
    "wealth": "财星不显，正财为主，小康水平，不宜大额借贷投资。",
    "marriage": "配偶宫午火为喜，夫妻关系稳定，宜晚婚。",
    "health": "注意脾胃消化与肝胆问题，避免熬夜。"
  }},
  "summary": ["身弱杀旺，喜印比扶身", "事业宜稳不宜险", "婚姻宫为喜，感情稳定", "中年后运势渐顺"],
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

    return f"""请为以下八字做详细分析。

八字：{bazi}
命主提问：{question or "全面分析事业、财运、婚姻、健康"}

{focus_instruction}

参考案例（仅作风格与论证参考，不要直接照搬结论）：
{cases_text}

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
    "career": "事业分析",
    "wealth": "财运分析",
    "marriage": "婚姻/感情分析",
    "health": "健康分析"
  }},
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
    knowledge_base_path: Path = Path("./bazi_knowledge/knowledge_base.md"),
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    top_k: int = 3,
) -> Dict:
    """Analyze a bazi using DeepSeek (or mock mode if no API key)."""
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
        similar_cases = retrieve_similar_cases(bazi, question, cases_path, top_k=top_k)
    else:
        similar_cases = []
    rule_primer = _build_rule_primer(knowledge_base_path)
    system_prompt = _build_system_prompt(rule_primer)
    user_prompt = _build_user_prompt(bazi, question, similar_cases)

    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return _mock_analyze(bazi, question, similar_cases)

    base = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    mdl = model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

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
            parsed = _parse_json(content, bazi, similar_cases)
            return _validate_output(parsed, bazi)


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

    return {
        "basic_info": {
            "bazi": bazi,
            "day_master": dm,
            "month_branch": mb,
            "pattern": "待 DeepSeek 分析",
            "useful_gods": [],
            "taboo_gods": [],
        },
        "reasoning": "当前未配置 DEEPSEEK_API_KEY，仅返回 RAG 检索结果与八字结构信息。请设置环境变量后重试。",
        "domain_analysis": domain_analysis,
        "summary": [f"参考相似案例：{', '.join(refs)}" if refs else "未找到相似案例"],
        "confidence": "low",
        "caveats": ["未调用真实模型", "请配置 DEEPSEEK_API_KEY"],
        "_mock": True,
    }


def _validate_output(result: Dict, bazi: str) -> Dict:
    """Sanity-check model output and add caveats for obvious mismatches."""
    basic = result.get("basic_info", {})
    caveats = list(result.get("caveats", []))

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
