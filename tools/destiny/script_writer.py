"""Destiny Script: transform a chart into an RPG-style character card + life chapters.

PRD module 6: lower the barrier of understanding destiny analysis by presenting
it as a playable life narrative that young people want to read and share.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    from aiohttp import ClientResponseError
except Exception:  # pragma: no cover - optional dependency
    aiohttp = None  # type: ignore
    ClientResponseError = Exception  # type: ignore

from tools.destiny.contract import ChartInfo


@dataclass
class Talent:
    name: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Weakness:
    name: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CharacterCard:
    day_master: str = ""
    pattern: str = ""
    strength: str = ""
    talents: List[Talent] = field(default_factory=list)
    weaknesses: List[Weakness] = field(default_factory=list)
    current_chapter: str = ""
    next_chapter_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day_master": self.day_master,
            "pattern": self.pattern,
            "strength": self.strength,
            "talents": [t.to_dict() for t in self.talents],
            "weaknesses": [w.to_dict() for w in self.weaknesses],
            "current_chapter": self.current_chapter,
            "next_chapter_preview": self.next_chapter_preview,
        }


@dataclass
class Chapter:
    index: int = 0
    pillar: str = ""
    age_range: str = ""
    year_range: str = ""
    theme: str = ""
    challenge: str = ""
    opportunity: str = ""
    advice: str = ""
    key_events: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DestinyScript:
    character_card: CharacterCard = field(default_factory=CharacterCard)
    chapters: List[Chapter] = field(default_factory=list)
    opening: str = ""
    closing: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_card": self.character_card.to_dict(),
            "chapters": [c.to_dict() for c in self.chapters],
            "opening": self.opening,
            "closing": self.closing,
        }


_DEFAULT_TALENTS = [
    Talent(name="韧性", description="压力下能稳住阵脚，越难越能熬出来。"),
    Talent(name="觉察", description="对人和事的直觉比较准，能提前避开一些坑。"),
]

_DEFAULT_WEAKNESSES = [
    Weakness(name="急脾气", description="容易心急，做决定前最好缓一缓。"),
    Weakness(name="过度承担", description="容易把压力往自己身上揽，要学会放手。"),
]


_SYSTEM_PROMPT = """你是一位会讲故事的命理师。你的任务是把八字命盘翻译成一份"人生 RPG 角色卡"和"章节式剧本"，让普通人读起来像在看自己人生的游戏攻略。

表达风格：
- 像真人跟朋友聊天，有温度、有画面感。
- 用第二人称"你"，让命主有代入感。
- 语言轻松、年轻化，但命理依据要扎实。
- 避免说教和空洞鼓励，每个判断都要有命局依据。

角色卡要求：
- day_master: 日主
- pattern: 格局
- strength: 身强身弱
- talents: 2–4 个天赋技能，每个有 name 和 description。名字要有 RPG 感（如"杀印相生""食伤生财"），description 用一句话讲清楚这个天赋在生活中的表现。
- weaknesses: 2–4 个弱点 debuff，每个有 name 和 description。名字也要有游戏感（如"财星破印""比劫夺财"），description 讲清楚这个弱点会带来什么麻烦。
- current_chapter: 当前所在大运的主题，一句话。
- next_chapter_preview: 下一步大运的关键词，一句话。

章节剧本要求：
- 按大运把人生分成章节，每章包含：
  - index: 章节序号，从 1 开始
  - pillar: 大运干支
  - age_range: 年龄段，如"27-37"
  - year_range: 年份范围，如"2015-2024"
  - theme: 该章主题，像游戏章节标题
  - challenge: 该章主要挑战
  - opportunity: 该章主要机遇
  - advice: 给命主的一句通关建议
  - key_events: 该章可能出现的关键事件类型数组（如["事业转折", "婚动"]）
- opening: 剧本开场白，100 字以内，像游戏开场旁白。
- closing: 剧本结束语，50 字以内，有温度、不鸡汤。

输出必须是合法 JSON，不要有任何额外解释文字。"""


def _build_user_prompt(
    chart: ChartInfo,
    analysis: Dict[str, Any],
    dayun: List[Dict[str, Any]],
    birth_year: int,
) -> str:
    basic = analysis.get("basic_info", {})
    domain = analysis.get("domain_analysis", {})
    summary = analysis.get("summary", [])
    milestones = analysis.get("milestones", [])
    milestones_text = "\n".join(
        f"- {m.get('year', '')}年（{m.get('type', '')}）：{m.get('description', '')}"
        for m in milestones
    ) or "（无明显高置信度节点）"

    dayun_text = "\n".join(
        f"{d.get('pillar', '')} 大运（{d.get('start_age', '')}-{d.get('end_age', '')}岁，"
        f"{birth_year + int(d.get('start_age', 0))}-"
        f"{birth_year + int(d.get('end_age', 0)) - 1}年）"
        for d in dayun
    )

    return f"""请为以下命盘生成命运剧本。

八字：{chart.bazi}
性别：{chart.gender or '未知'}
出生时间：{chart.birth_datetime or '未知'}

命局基础信息：
- 日主：{basic.get('day_master', '')}
- 月令：{basic.get('month_branch', '')}
- 格局：{basic.get('pattern', '')}
- 用神：{'、'.join(basic.get('useful_gods', []))}
- 忌神：{'、'.join(basic.get('taboo_gods', []))}

领域分析：
- 事业：{domain.get('career', '')}
- 财运：{domain.get('wealth', '')}
- 婚姻：{domain.get('marriage', '')}
- 健康：{domain.get('health', '')}

人生要点：
{'；'.join(summary)}

关键节点：
{milestones_text}

大运列表：
{dayun_text}

请按指定 JSON 格式输出角色卡和章节剧本。"""


def _current_year() -> int:
    return datetime.now().year


def _find_current_and_next_chapter(chapters: List[Chapter]) -> tuple:
    year = _current_year()
    current = None
    for ch in chapters:
        try:
            start, end = ch.year_range.split("-")
            if int(start) <= year <= int(end):
                current = ch
                break
        except Exception:  # pragma: no cover
            continue
    if current is None and chapters:
        current = chapters[0]
    next_ch = None
    if current is not None:
        idx = next((i for i, c in enumerate(chapters) if c.index == current.index), None)
        if idx is not None and idx + 1 < len(chapters):
            next_ch = chapters[idx + 1]
    return current, next_ch


def _parse_script_response(content: str) -> Dict[str, Any]:
    """Parse LLM JSON response, with forgiving cleanup."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover
        # Try to extract the first JSON object.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise exc


def _build_default_script(chart: ChartInfo, dayun: List[Dict[str, Any]]) -> DestinyScript:
    """Return a rule-based fallback script when LLM is unavailable."""
    chapters = []
    for i, d in enumerate(dayun, start=1):
        start_age = int(d.get("start_age", 0))
        end_age = int(d.get("end_age", 0))
        chapters.append(
            Chapter(
                index=i,
                pillar=d.get("pillar", ""),
                age_range=f"{start_age}-{end_age}",
                year_range=f"{d.get('start_year', '')}-{d.get('end_year', '')}",
                theme=f"{d.get('pillar', '')} 大运",
                challenge="待结合命局细断",
                opportunity="待结合命局细断",
                advice="稳扎稳打，顺势而为",
                key_events=[],
            )
        )
    current, next_ch = _find_current_and_next_chapter(chapters)
    card = CharacterCard(
        day_master="",
        pattern="",
        strength="",
        talents=list(_DEFAULT_TALENTS),
        weaknesses=list(_DEFAULT_WEAKNESSES),
        current_chapter=current.theme if current else "",
        next_chapter_preview=next_ch.theme if next_ch else "",
    )
    return DestinyScript(
        character_card=card,
        chapters=chapters,
        opening=f"你这一生会走过 {len(chapters)} 个大运章节，每一章都有它的主题和任务。",
        closing="命是底色，运是节奏，怎么演还是看你自己。",
    )


def _dict_to_script(data: Dict[str, Any]) -> DestinyScript:
    card_data = data.get("character_card", {})
    card = CharacterCard(
        day_master=card_data.get("day_master", ""),
        pattern=card_data.get("pattern", ""),
        strength=card_data.get("strength", ""),
        talents=[
            Talent(name=t.get("name", ""), description=t.get("description", ""))
            for t in card_data.get("talents", [])
        ],
        weaknesses=[
            Weakness(name=w.get("name", ""), description=w.get("description", ""))
            for w in card_data.get("weaknesses", [])
        ],
        current_chapter=card_data.get("current_chapter", ""),
        next_chapter_preview=card_data.get("next_chapter_preview", ""),
    )

    chapters = []
    for c in data.get("chapters", []):
        chapters.append(
            Chapter(
                index=c.get("index", len(chapters) + 1),
                pillar=c.get("pillar", ""),
                age_range=c.get("age_range", ""),
                year_range=c.get("year_range", ""),
                theme=c.get("theme", ""),
                challenge=c.get("challenge", ""),
                opportunity=c.get("opportunity", ""),
                advice=c.get("advice", ""),
                key_events=c.get("key_events", []),
            )
        )

    current, next_ch = _find_current_and_next_chapter(chapters)
    if not card.current_chapter and current:
        card.current_chapter = current.theme
    if not card.next_chapter_preview and next_ch:
        card.next_chapter_preview = next_ch.theme

    return DestinyScript(
        character_card=card,
        chapters=chapters,
        opening=data.get("opening", ""),
        closing=data.get("closing", ""),
    )


class ScriptWriter:
    """Generate a Destiny Script (character card + life chapters) for a chart."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def write(
        self,
        chart: ChartInfo,
        analysis: Optional[Dict[str, Any]] = None,
        dayun: Optional[List[Dict[str, Any]]] = None,
        birth_year: int = 1990,
    ) -> Dict[str, Any]:
        """Generate the script.

        Args:
            chart: the chart to write about.
            analysis: optional pre-computed bazi analysis result.
            dayun: optional dayun timeline.
            birth_year: birth year for computing year ranges.

        Returns:
            Dict representation of the DestinyScript.
        """
        if isinstance(chart, dict):
            chart = ChartInfo(**chart)

        if analysis is None:
            from tools.bazi_ai.engine import analyze_bazi

            analysis = await analyze_bazi(chart.bazi, question="命运剧本")

        if dayun is None:
            from tools.bazi_ai.calendar import dayun_list

            try:
                birth_date = ""
                birth_time = "00:00"
                if chart.birth_datetime:
                    parts = chart.birth_datetime.split("T")
                    birth_date = parts[0]
                    if len(parts) > 1:
                        birth_time = parts[1][:5]
                dayun = dayun_list(
                    chart.bazi,
                    chart.gender or "male",
                    birth_date,
                    birth_time,
                )
            except Exception:  # pragma: no cover
                dayun = []

        # Fill in year ranges if missing.
        for d in dayun:
            if "start_year" not in d or "end_year" not in d:
                start_age = int(d.get("start_age", 0))
                end_age = int(d.get("end_age", 0))
                d["start_year"] = birth_year + start_age
                d["end_year"] = birth_year + end_age - 1

        key = self.api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not key or aiohttp is None:
            return _build_default_script(chart, dayun).to_dict()

        base = (
            self.base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        mdl = self.model or os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"

        system_prompt = _SYSTEM_PROMPT
        user_prompt = _build_user_prompt(chart, analysis, dayun, birth_year)

        payload = {
            "model": mdl,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.5,
            "max_tokens": 2500,
            "response_format": {"type": "json_object"},
        }

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
                        parsed = _parse_script_response(content)
                        return _dict_to_script(parsed).to_dict()
            except (ClientResponseError, asyncio.TimeoutError, Exception):  # pragma: no cover
                if attempt < 3:
                    await asyncio.sleep(attempt * 1.5)

        # Fallback to rule-based script.
        return _build_default_script(chart, dayun).to_dict()
