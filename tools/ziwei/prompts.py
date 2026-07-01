"""Prompt builders for the Zi Wei Dou Shu analyzer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles


async def _load_cases(cases_path: Path) -> List[Dict[str, Any]]:
    """Load example cases from a JSONL file."""
    if not cases_path.exists():
        return []
    cases: List[Dict[str, Any]] = []
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
    """Return life domains mentioned in the question."""
    if not question:
        return []
    keywords = {
        "career": ["事业", "工作", "职业", "创业", "上班", "行业", "升迁", "贵人"],
        "wealth": ["财", "钱", "富", "收入", "资产", "赚钱", "百万", "千万", "小康"],
        "marriage": ["婚姻", "感情", "桃花", "老公", "老婆", "配偶", "恋爱", "结婚", "离婚"],
        "health": ["健康", "病", "身体", "手术", "肾", "妇科", "心脏", "血液", "子宫"],
        "general": ["运势", "命运", "命盘", "整体", "综合", "运程", "运气"],
    }
    domains = []
    for domain, kws in keywords.items():
        if any(kw in question for kw in kws):
            domains.append(domain)
    return domains


async def _retrieve_similar_cases(
    chart_info: Dict[str, Any],
    question: str,
    cases_path: Path,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Return the most relevant example cases using simple keyword heuristics."""
    cases = await _load_cases(cases_path)
    if not cases:
        return []

    gender = chart_info.get("gender", "").lower()
    question_domains = set(_detect_question_domains(question))

    def score(case: Dict[str, Any]) -> int:
        s = 0
        if case.get("gender", "").lower() == gender:
            s += 5
        case_domains = set(case.get("domains", []))
        s += len(question_domains & case_domains) * 10
        if question:
            text = " ".join(
                [
                    case.get("text", ""),
                    " ".join(case.get("keywords", [])),
                ]
            )
            for kw in question.replace("。", " ").replace("，", " ").replace("？", " ").split():
                if len(kw) >= 2 and kw in text:
                    s += 2
        return s

    cases.sort(key=score, reverse=True)
    return cases[:top_k]


async def _load_rule_primer(rule_primer_path: Path, max_chars: int = 8000) -> str:
    """Load a compact rule primer from markdown."""
    if not rule_primer_path.exists():
        return ""
    async with aiofiles.open(rule_primer_path, "r", encoding="utf-8") as f:
        text = await f.read()
    return text[:max_chars]


async def build_system_prompt(rule_primer_path: Optional[Path] = None) -> str:
    """Build the system prompt for the Zi Wei Dou Shu analyzer."""
    primer = await _load_rule_primer(rule_primer_path) if rule_primer_path else ""
    return f"""你是一位精通紫微斗数的命理师，风格务实、断语明确。

分析原则：
1. 依据出生年月日时排定紫微斗数命盘，确定命宫、身宫、主星、辅星、四化、十二宫分布。
2. 必须一步一步推理：排盘 → 定命宫/身宫 → 安主星辅星 → 看四化飞伏 → 分宫断事 → 给出各领域评分与关键词。每一步都要在 reasoning 中写明。
3. 结论要具体，避免泛泛而谈（如"运势不错"）。要给出可验证的判断：适合什么行业、财富量级、婚姻早晚、健康注意部位等。
4. 如果出生时辰有争议或真太阳时换算可能不准，必须给出置信度说明和 caveat。
5. 输出必须是合法 JSON，不要有任何额外解释文字。
6. 评分基于星曜组合与宫位吉凶：0-40 为弱/多阻，41-60 为平/需努力，61-80 为佳/有助力，81-100 为强/大吉。

示例输出格式（仅供参考，不要直接照搬内容）：
{{
  "system": "ziwei",
  "basic_info": {{
    "ming_gong": "巳宫",
    "shen_gong": "亥宫",
    "zhu_xing": ["紫微", "天府"],
    "si_hua": ["禄在迁移", "权在事业", "科在财帛", "忌在疾厄"]
  }},
  "reasoning": "命宫在巳，紫微天府同宫，主星得力，格局稳重。身宫在亥，与命宫相对，中年以后重心转移。...",
  "domain_analysis": {{
    "career": {{"score": 78, "text": "事业宫有天相、左辅，适合管理、行政、技术类岗位，中年后易得贵人提携。", "keywords": ["管理", "贵人", "中年后发"]}},
    "wealth": {{"score": 65, "text": "财帛宫有禄存，正财运稳，但偏财运一般，宜稳健理财。", "keywords": ["正财", "稳健", "忌投机"]}},
    "marriage": {{"score": 70, "text": "夫妻宫有天同、天梁，配偶温和顾家，宜晚婚更稳。", "keywords": ["晚婚", "温和", "顾家"]}},
    "health": {{"score": 55, "text": "疾厄宫见擎羊，注意肠胃与肝胆，避免熬夜与饮食不节。", "keywords": ["肠胃", "肝胆", "作息"]}},
    "general": {{"score": 72, "text": "整体格局中上，主星得力，四化流通，一生有贵人扶助，需注意情绪管理。", "keywords": ["贵人", "稳重", "情绪管理"]}}
  }},
  "summary": ["紫微天府坐命，格局稳重", "事业中年后渐入佳境", "财运宜守不宜攻", "婚姻宜晚婚", "注意肠胃肝胆"],
  "confidence": "medium",
  "caveats": ["若出生时辰不准，命宫位置与主星会发生偏移"]
}}

基础知识参考：
{primer}
"""


def build_user_prompt(
    chart_info: Dict[str, Any],
    question: str,
    similar_cases: List[Dict[str, Any]],
) -> str:
    """Build the user prompt for a specific chart."""
    cases_text = "\n\n".join(
        f"案例 {i + 1}：\n{_format_case(c)}"
        for i, c in enumerate(similar_cases)
    )
    if not cases_text:
        cases_text = "（暂无相似案例）"

    domains = _detect_question_domains(question)
    if domains:
        domain_names = {
            "career": "事业",
            "wealth": "财运",
            "marriage": "婚姻/感情",
            "health": "健康",
            "general": "整体运势",
        }
        focus = "、".join(domain_names.get(d, d) for d in domains)
        focus_instruction = f"请重点分析：{focus}。其他领域可简要说明，但仍需给出 score 与 keywords。"
    else:
        focus_instruction = "请全面分析事业、财运、婚姻、健康与整体运势五个领域。"

    return f"""请为以下命盘做紫微斗数详细分析。

出生时间：{chart_info.get('birth_datetime')}
性别：{chart_info.get('gender')}
出生地：经度 {chart_info.get('location', {}).get('longitude')}，纬度 {chart_info.get('location', {}).get('latitude')}，时区 {chart_info.get('location', {}).get('timezone')}
已知八字：{chart_info.get('bazi', '未提供')}
命主提问：{question or "全面分析事业、财运、婚姻、健康与整体运势"}

{focus_instruction}

参考案例（仅作风格与论证参考，不要直接照搬结论）：
{cases_text}

请按以下 JSON 格式输出（不要输出 markdown 代码块，只输出 JSON）：
{{
  "system": "ziwei",
  "basic_info": {{
    "ming_gong": "命宫所在地支宫",
    "shen_gong": "身宫所在地支宫",
    "zhu_xing": ["主星1", "主星2"],
    "si_hua": ["禄在xx", "权在xx", "科在xx", "忌在xx"]
  }},
  "reasoning": "完整的逐步推理过程，300-800字。必须包含：命宫/身宫确定、主星辅星组合、四化飞伏、各领域推断依据。",
  "domain_analysis": {{
    "career": {{"score": 0-100, "text": "事业分析", "keywords": ["关键词1", "关键词2"]}},
    "wealth": {{"score": 0-100, "text": "财运分析", "keywords": ["关键词1", "关键词2"]}},
    "marriage": {{"score": 0-100, "text": "婚姻/感情分析", "keywords": ["关键词1", "关键词2"]}},
    "health": {{"score": 0-100, "text": "健康分析", "keywords": ["关键词1", "关键词2"]}},
    "general": {{"score": 0-100, "text": "整体运势分析", "keywords": ["关键词1", "关键词2"]}}
  }},
  "summary": ["3-5条核心断语"],
  "confidence": "high|medium|low",
  "caveats": ["可能的误差来源"]
}}
"""


def _format_case(case: Dict[str, Any]) -> str:
    """Format a single case for prompt inclusion."""
    lines = []
    if "birth_datetime" in case:
        lines.append(f"出生时间：{case['birth_datetime']}")
    if "gender" in case:
        lines.append(f"性别：{case['gender']}")
    if "ming_gong" in case:
        lines.append(f"命宫：{case['ming_gong']}")
    if "zhu_xing" in case:
        lines.append(f"主星：{' '.join(case['zhu_xing'])}")
    if "text" in case:
        lines.append(f"分析：{case['text'][:400]}")
    return "\n".join(lines)


def retrieve_cases(
    chart_info: Dict[str, Any],
    question: str,
    cases_path: Optional[Path] = None,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Public helper to retrieve similar cases for a chart."""
    if cases_path is None or not cases_path.exists():
        return []
    return _retrieve_similar_cases(chart_info, question, cases_path, top_k=top_k)
