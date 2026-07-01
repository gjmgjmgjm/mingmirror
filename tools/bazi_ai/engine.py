#!/usr/bin/env python3
"""
engine.py — DeepSeek-powered bazi analysis engine.

Design:
    1. Retrieve similar cases from the structured case database (RAG).
    2. Inject a compact rule primer from the PDF knowledge base.
    3. Ask DeepSeek to reason step-by-step and return structured JSON.

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


def _load_cases(cases_path: Path) -> List[Dict]:
    if not cases_path.exists():
        return []
    cases = []
    with cases_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            cases.append(json.loads(line))
    return cases


def _case_relevance(case: Dict, bazi: str, question: str) -> int:
    """Simple keyword relevance score for RAG."""
    score = 0
    text = " ".join(
        [
            case.get("bazi", ""),
            case.get("analysis_corrected", ""),
            " ".join(case.get("key_terms", [])),
            " ".join(case.get("conclusions", [])),
        ]
    )
    # Exact bazi match is the strongest signal.
    if case.get("bazi") == bazi:
        score += 100

    # Day master / month branch match.
    query_pillars = bazi.split()
    case_pillars = case.get("bazi", "").split()
    if len(query_pillars) == 4 and len(case_pillars) == 4:
        if query_pillars[2][0] == case_pillars[2][0]:  # day master
            score += 20
        if query_pillars[1][1] == case_pillars[1][1]:  # month branch
            score += 15

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
2. 必须一步一步推理：排盘 → 定日主旺衰 → 取格局 → 取用神/忌神 → 分领域断事。
3. 结论要具体，避免泛泛而谈（如"运势不错"）。要给出可验证的判断：适合什么行业、婚姻早晚、财运量级、健康注意部位等。
4. 如果八字有争议或时辰不准，必须给出置信度和 caveat。
5. 输出必须是 JSON，不要有任何额外解释文字。

基础知识参考：
{rule_primer}
"""


def _build_user_prompt(bazi: str, question: str, similar_cases: List[Dict]) -> str:
    cases_text = "\n\n".join(
        f"案例 {i+1}：\n八字：{c.get('bazi')}\n命理师分析：{c.get('analysis_corrected', '')[:400]}"
        for i, c in enumerate(similar_cases)
    )
    if not cases_text:
        cases_text = "（暂无相似案例）"

    return f"""请为以下八字做详细分析。

八字：{bazi}
命主提问：{question or "全面分析事业、财运、婚姻、健康"}

参考案例：
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
  "reasoning": "完整的逐步推理过程，300-800字",
  "domain_analysis": {{
    "career": "事业分析",
    "wealth": "财运分析",
    "marriage": "婚姻/感情分析",
    "health": "健康分析"
  }},
  "summary": "3-5条核心断语",
  "confidence": "high|medium|low",
  "caveats": ["可能的误差来源"]
}}
"""


async def analyze_bazi(
    bazi: str,
    *,
    question: str = "",
    cases_path: Path = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Path = Path("./bazi_knowledge/knowledge_base.md"),
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    top_k: int = 3,
) -> Dict:
    """Analyze a bazi using DeepSeek (or mock mode if no API key)."""
    similar_cases = retrieve_similar_cases(bazi, question, cases_path, top_k=top_k)
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
        "temperature": 0.3,
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
            return _parse_json(content, bazi, similar_cases)


def _mock_analyze(bazi: str, question: str, similar_cases: List[Dict]) -> Dict:
    """Return a placeholder analysis when no API key is configured."""
    refs = [c.get("bazi") for c in similar_cases[:2]]
    return {
        "basic_info": {
            "bazi": bazi,
            "day_master": bazi.split()[2][0] if len(bazi.split()) == 4 else "",
            "month_branch": bazi.split()[1][1] if len(bazi.split()) == 4 else "",
            "pattern": "待 DeepSeek 分析",
            "useful_gods": [],
            "taboo_gods": [],
        },
        "reasoning": "当前未配置 DEEPSEEK_API_KEY，仅返回 RAG 检索结果。请设置环境变量后重试。",
        "domain_analysis": {
            "career": "待分析",
            "wealth": "待分析",
            "marriage": "待分析",
            "health": "待分析",
        },
        "summary": [f"参考相似案例：{', '.join(refs)}" if refs else "未找到相似案例"],
        "confidence": "low",
        "caveats": ["未调用真实模型", "请配置 DEEPSEEK_API_KEY"],
        "_mock": True,
    }


def _parse_json(content: str, bazi: str, similar_cases: List[Dict]) -> Dict:
    """Parse model output as JSON, with fallback."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Sometimes models wrap JSON in markdown fences.
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Final fallback: return raw content for inspection.
    return {
        "basic_info": {"bazi": bazi},
        "parse_error": True,
        "raw_content": content,
        "similar_cases": [c.get("bazi") for c in similar_cases],
    }
