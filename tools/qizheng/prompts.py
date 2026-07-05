"""Prompt templates for the Qi Zheng Si Yu analyzer."""

import json
from pathlib import Path
from typing import Dict, List, Optional

import aiofiles


async def _load_rule_primer(rule_primer_path: Optional[Path], max_chars: int = 8000) -> str:
    if rule_primer_path is None or not rule_primer_path.exists():
        return ""
    async with aiofiles.open(rule_primer_path, "r", encoding="utf-8") as handle:
        text = await handle.read()
    return text[:max_chars]


async def build_system_prompt(rule_primer_path: Optional[Path]) -> str:
    """Return the system prompt for the Qi Zheng Si Yu analysis model."""
    primer = await _load_rule_primer(rule_primer_path)
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
    "career": "命宫太阳得地，利公职或管理岗；30-32岁有升职窗口，但33岁火星犯官禄，易与直属领导冲突或被调岗。",
    "wealth": "财帛宫太阴守照，正财稳定；偏财忌股票、虚拟货币，易因熟人消息亏损3-8万。35岁前后有房产或长辈医疗支出。",
    "marriage": "夫妻宫金星落陷，配偶性格强势；28岁、34岁为感情高危年，易因异地或金钱争吵，有冷战分居风险。",
    "health": "疾厄宫土星受克，注意脾胃、腰椎、皮肤过敏；农历三月、九月慎防运动拉伤或交通事故。"
  }},
  "summary": ["日主偏弱喜印比", "事业中年后顺遂", "财运稳健", "婚姻宫平和"],
  "confidence": "medium",
  "caveats": ["时辰若不准，命宫位置会变化"]
}}{primer_section}
"""


def _load_few_shot_examples(examples_path: Optional[Path]) -> List[Dict]:
    """Load few-shot examples from a JSONL file."""
    if examples_path is None or not examples_path.exists():
        return []
    examples: List[Dict] = []
    with examples_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return examples


def _format_example(example: Dict) -> str:
    """Format a few-shot example for prompt inclusion."""
    chart = example.get("chart", "")
    output = json.dumps(example.get("output", {}), ensure_ascii=False, indent=2)
    return f"""输入：\n命盘：{chart}\n\n输出：\n{output}"""


def build_user_prompt(
    chart: str,
    question: str,
    similar_cases: List[Dict],
    profile: Optional[Dict] = None,
    few_shot_examples: Optional[List[Dict]] = None,
) -> str:
    """Return the user prompt for a specific chart and question."""
    cases_text = "\n\n".join(
        f"案例 {i+1}：\n命盘：{c.get('chart', '')}\n分析：{c.get('analysis', '')[:500]}"
        for i, c in enumerate(similar_cases)
    )
    if not cases_text:
        cases_text = "（暂无相似案例）"

    examples_text = "\n\n".join(
        f"示例 {i + 1}：\n{_format_example(ex)}"
        for i, ex in enumerate(few_shot_examples or [])
    )
    examples_section = (
        f"\n\n以下是 few-shot 示例（仅作格式与风格参考）：\n{examples_text}"
        if examples_text
        else ""
    )

    focus_instruction = (
        "请全面分析事业、财运、婚姻、健康四个领域。"
        if not question
        else f"命主提问：{question}。请围绕提问重点分析，同时兼顾其他领域简要说明。"
    )

    profile_text = ""
    if profile:
        from tools.qizheng.calendar import profile_text as _profile_text
        profile_text = "\n\n" + _profile_text(profile)

    return f"""请为以下七政四余命盘做详细分析。

命盘：{chart}{profile_text}

{focus_instruction}

分析要求：
1. 以上【七政四余结构事实】由程序严格计算，必须以之为依据；禁止自行发明命宫、身宫、十二宫位置。
2. 先排定命宫、身宫、十二宫主星，再判断日主强弱、七政得时失时、四余吉凶。
2. 事业、财运、婚姻、健康必须直接断具体事件，不要写泛泛建议。
   - 错误示例（禁止）：“事业平稳发展”“财运一般，宜守不宜攻”“注意身体”“感情多沟通”。
   - 正确示例：
     - 事业：“官禄宫火星受克，32岁前后易与上司冲突或被调岗；若跳槽，新工作薪资涨幅有限且压力大。”
     - 财运：“财帛宫太阴化忌，忌股票、虚拟货币，易因熟人消息亏损3-8万；35岁前后有房产或长辈医疗支出。”
     - 婚姻：“夫妻宫金星落陷，配偶性格强势；28岁、34岁为感情高危年，易因异地或金钱争吵，有冷战分居风险。”
     - 健康：“疾厄宫土星受克，注意脾胃、腰椎、皮肤过敏；农历三月、九月慎防运动拉伤或交通事故。”
3. 每项分析尽量包含：时间窗口（年龄/年份/农历月份）、人物关系、金额范围、具体事件类型。
4. 必须解释十二宫与六亲的对应：命宫主自身、兄弟宫主兄弟、夫妻宫主配偶、子女宫主子女、财帛宫主财运、疾厄宫主健康、迁移宫主外出、奴仆宫主同事朋友、官禄宫主事业、田宅宫主房产家庭、福德宫主精神福报、父母宫主父母长辈。
5. 输出必须是 JSON，不要有任何额外解释文字。

参考案例（仅作风格与论证参考，不要直接照搬结论）：
{cases_text}{examples_section}

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


def build_yearly_system_prompt(rule_primer: str) -> str:
    """Return the system prompt for Qi Zheng yearly luck analysis."""
    primer_section = f"\n基础知识参考：\n{rule_primer}" if rule_primer else ""
    return f"""你是一位精通七政四余（Qi Zheng Si Yu）的命理师，擅长大限流年推演，风格直断、具体、可操作。

分析原则：
1. 以命宫为体、大限为纲、流年为应。每步大限先点明所入宫位、该宫主星意义、与命宫的冲合关系。
2. 逐年分析时，必须结合流年干支、流年地支与命局/大限宫支的刑冲合害，给出具体判断。
3. 事业、财运、婚姻、健康四个领域禁止写空话。必须给出可执行建议，如"适合跳槽/创业/守成/收缩""有偏财机会/忌投资""有桃花/防口角""注意心血管/肠胃/睡眠"。
4. 若某年大限宫支与流年地支相冲，必须在 overview 或 caution 中明确指出。
5. 输出必须是合法 JSON，不要有任何额外解释文字。
6. 每一年 overview 控制在 60 字以内，四个领域每栏控制在 40 字以内，caution 控制在 30 字以内。整体要凝练、有断语。

输出格式：
{{
  "dayun_summary": [
    {{"pillar": "大限宫支", "palace": "宫位名称", "start_age": 数字, "end_age": 数字, "theme": "该运主题", "focus": "重点关注"}}
  ],
  "yearly_analysis": [
    {{
      "year": 2024,
      "pillar": "流年干支",
      "overview": "整体运势",
      "career": "事业具体建议",
      "wealth": "财运具体建议",
      "marriage": "感情具体建议",
      "health": "健康具体建议",
      "caution": "注意事项"
    }}
  ],
  "overall_guidance": "综合建议，300字以内",
  "confidence": "high|medium|low",
  "caveats": ["至少2条具体注意事项"]
}}{primer_section}
"""


def build_yearly_user_prompt(
    chart: str,
    gender: str,
    dayun: List[Dict],
    liunian: List[Dict],
    mode: str,
    profile: Dict,
    yearly_rels: List[Dict],
    birth_year: int,
) -> str:
    """Return the user prompt for Qi Zheng yearly analysis."""
    dayun_text = "\n".join(
        f"{d['start_age']}-{d['end_age']}岁: {d['palace']}（{d['pillar']}）"
        f"({birth_year + int(d['start_age'])}-{birth_year + int(d['end_age']) - 1})"
        for d in dayun
    )

    def _dayun_for_year(year: int) -> str:
        age = year - birth_year
        for d in dayun:
            if d["start_age"] <= age < d["end_age"]:
                return d["pillar"]
        return dayun[-1]["pillar"] if dayun else "未知"

    palaces = profile.get("twelve_palaces", {})
    palace_line = "、".join(f"{name}在{br}" for name, br in palaces.items())
    structural_facts = f"""【七政四余结构事实】（由程序严格计算，必须以此为依据）
- 八字：{profile.get('chart')}
- 日主：{profile.get('day_master')}
- 年柱纳音：{profile.get('nayin')}（五行局：{profile.get('five_element_pattern')}）
- 命宫：{profile.get('life_palace')}
- 身宫：{profile.get('body_palace')}
- 身主：{profile.get('body_lord')}
- 十二宫排布：{palace_line}"""

    liunian_text = "\n".join(
        f"{y['year']}年: {y['pillar']}（{_dayun_for_year(y['year'])}大限）"
        for y in liunian
    )

    year_facts_lines = []
    for r in yearly_rels:
        parts = [
            f"{r['year']}年 {r['liunian_pillar']}（{r['dayun_pillar']}大限）",
        ]
        if r.get("dayun_life_palace_interaction"):
            parts.append(f"大限宫与命宫：{r['dayun_life_palace_interaction']}")
        if r.get("liunian_life_palace_interaction"):
            parts.append(f"流年与命宫：{r['liunian_life_palace_interaction']}")
        if r.get("dayun_liunian_interaction"):
            parts.append(f"大限宫与流年支：{r['dayun_liunian_interaction']}")
        year_facts_lines.append("；".join(parts))
    year_facts_text = "\n".join(year_facts_lines)

    scope = "未来10年" if mode == "10y" else "一生（到80岁）"
    if mode == "10y":
        yearly_instruction = f"""流年结构事实（必须以这些事实为依据，禁止编造）：
{year_facts_text}

流年列表（只分析这些年份，括号内为该年所在大限宫支）：
{liunian_text}

请严格按指定 JSON 格式输出，并遵守：
- 只输出上面列出的大限和年份，禁止扩展范围。
- 每一年 overview 必须点明所在大限宫位与流年地支的互动。
- 涉及合化、冲克时，只能引用【七政四余结构事实】和【流年结构事实】中列出的内容，禁止自行发明。
- 事业、财运、婚姻、健康四项，每一项必须给出具体可执行建议，不准只给方向性建议。
- 不要输出任何额外文字或 markdown 代码块。"""
    else:
        yearly_instruction = """请重点分析每步大限的主题、与命宫身宫的关系，以及一生运势的分阶段总结。
- 不需要输出逐年流年（yearly_analysis 可留空数组 []）。
- 必须输出 dayun_summary、overall_guidance 和 caveats。
- 不要输出任何额外文字或 markdown 代码块。"""

    return f"""请为以下七政四余命盘做{scope}大限流年精排。

命盘：{chart}
性别：{"男" if gender == "male" else "女" if gender == "female" else "未知"}

{structural_facts}

大限列表（只分析这些大限，括号内为该运覆盖的公历年份）：
{dayun_text}

{yearly_instruction}
"""
