"""Prompt templates for the Qi Zheng Si Yu analyzer."""

from pathlib import Path
from typing import Dict, List, Optional


def _load_rule_primer(rule_primer_path: Optional[Path], max_chars: int = 8000) -> str:
    if rule_primer_path is None or not rule_primer_path.exists():
        return ""
    text = rule_primer_path.read_text(encoding="utf-8")
    return text[:max_chars]


def build_system_prompt(rule_primer_path: Optional[Path]) -> str:
    """Return the system prompt for the Qi Zheng Si Yu analysis model."""
    primer = _load_rule_primer(rule_primer_path)
    primer_section = f"\n基础知识参考：\n{primer}" if primer else ""

    return f"""你是一位精通七政四余（Qi Zheng Si Yu）的命理师。七政四余以日、月、金、木、水、火、土七政为主，结合紫气、月孛、罗睺、计都四余，推断人的命运格局。

分析原则：
1. 先排定命盘：命宫、身宫、主星（日、月、命主、身主）分布。
2. 判断日主强弱、七政得时失时、四余吉凶。
3. 结合十二宫分野，逐步推断事业、财运、婚姻、健康。
4. 结论要具体、可验证，避免空泛。
5. 输出必须是 JSON，不要有任何额外解释文字。

示例输出格式（仅供参考，不要直接照搬内容）：
{{
  "basic_info": {{
    "chart": "甲子 丙寅 戊辰 庚午",
    "day_master": "戊",
    "life_palace": "巳",
    "body_palace": "亥",
    "dominant_stars": ["太阳", "太阴"]
  }},
  "reasoning": "日主戊土，生于寅月木旺之时，土气稍弱。命宫在巳，太阳守命，主贵显。财星透干，中年后财源渐稳。",
  "domain_analysis": {{
    "career": "适合管理、技术或公职，中年后有升迁之机。",
    "wealth": "正财运稳，偏财需谨慎，不宜高风险投机。",
    "marriage": "夫妻宫平和，配偶得力，宜晚婚。",
    "health": "注意脾胃与肝胆，避免过劳。"
  }},
  "summary": ["日主偏弱喜印比", "事业中年后顺遂", "财运稳健", "婚姻宫平和"],
  "confidence": "medium",
  "caveats": ["时辰若不准，命宫位置会变化"]
}}{primer_section}
"""


def build_user_prompt(
    chart: str,
    question: str,
    similar_cases: List[Dict],
) -> str:
    """Return the user prompt for a specific chart and question."""
    cases_text = "\n\n".join(
        f"案例 {i+1}：\n命盘：{c.get('chart', '')}\n分析：{c.get('analysis', '')[:500]}"
        for i, c in enumerate(similar_cases)
    )
    if not cases_text:
        cases_text = "（暂无相似案例）"

    focus_instruction = (
        "请全面分析事业、财运、婚姻、健康四个领域。"
        if not question
        else f"命主提问：{question}。请围绕提问重点分析，同时兼顾其他领域简要说明。"
    )

    return f"""请为以下七政四余命盘做详细分析。

命盘：{chart}

{focus_instruction}

参考案例（仅作风格与论证参考，不要直接照搬结论）：
{cases_text}

请按以下 JSON 格式输出（不要输出 markdown 代码块，只输出 JSON）：
{{
  "basic_info": {{
    "chart": "{chart}",
    "day_master": "日主",
    "life_palace": "命宫地支",
    "body_palace": "身宫地支",
    "dominant_stars": ["主星1", "主星2"]
  }},
  "reasoning": "完整的逐步推理过程，300-800字。",
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
