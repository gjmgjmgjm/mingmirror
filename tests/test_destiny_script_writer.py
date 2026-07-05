"""Tests for the Destiny Script writer."""

import pytest

from tools.destiny.contract import ChartInfo
from tools.destiny.script_writer import (
    Chapter,
    CharacterCard,
    DestinyScript,
    ScriptWriter,
    Talent,
    Weakness,
    _find_current_and_next_chapter,
)


class TestDataClasses:
    def test_character_card_to_dict(self):
        card = CharacterCard(
            day_master="庚",
            pattern="七杀格",
            strength="身弱",
            talents=[Talent(name="杀印相生", description="压力下出成绩")],
            weaknesses=[Weakness(name="财来坏印", description="容易因钱分心")],
            current_chapter="印比扶身运",
            next_chapter_preview="财官旺地",
        )
        data = card.to_dict()
        assert data["day_master"] == "庚"
        assert data["talents"][0]["name"] == "杀印相生"

    def test_destiny_script_to_dict(self):
        script = DestinyScript(
            character_card=CharacterCard(day_master="庚"),
            chapters=[Chapter(index=1, pillar="甲申")],
            opening="开场白",
            closing="结束语",
        )
        data = script.to_dict()
        assert data["opening"] == "开场白"
        assert data["chapters"][0]["pillar"] == "甲申"


class TestFindCurrentAndNextChapter:
    def test_finds_current_and_next(self):
        chapters = [
            Chapter(index=1, year_range="1990-2020"),
            Chapter(index=2, year_range="2021-2030"),
            Chapter(index=3, year_range="2031-2040"),
        ]
        current, next_ch = _find_current_and_next_chapter(chapters)
        assert current is not None
        assert current.index == 2
        assert next_ch is not None
        assert next_ch.index == 3

    def test_fallback_to_first_when_no_match(self):
        chapters = [Chapter(index=1, year_range="1900-1909")]
        current, next_ch = _find_current_and_next_chapter(chapters)
        assert current.index == 1
        assert next_ch is None


class TestScriptWriter:
    @pytest.mark.asyncio
    async def test_write_without_api_key_returns_fallback(self):
        writer = ScriptWriter(api_key="")
        chart = ChartInfo(
            bazi="庚午 辛巳 庚辰 壬午",
            gender="male",
            birth_datetime="1990-05-20T10:00:00",
        )
        result = await writer.write(chart, birth_year=1990)
        assert "character_card" in result
        assert "chapters" in result
        assert "opening" in result
        assert "closing" in result
        assert result["character_card"]["talents"]
        assert result["character_card"]["weaknesses"]

    @pytest.mark.asyncio
    async def test_write_with_explicit_analysis(self):
        writer = ScriptWriter(api_key="")
        chart = ChartInfo(bazi="庚午 辛巳 庚辰 壬午")
        analysis = {
            "basic_info": {
                "day_master": "庚",
                "pattern": "七杀格",
                "useful_gods": ["土", "金"],
                "taboo_gods": ["木", "火"],
            },
            "domain_analysis": {
                "career": "事业有压力",
                "wealth": "财运一般",
                "marriage": "婚姻稳定",
                "health": "注意心肺",
            },
            "summary": ["身弱杀旺"],
        }
        dayun = [
            {"pillar": "壬午", "start_age": 7, "end_age": 17, "start_year": 1997, "end_year": 2006},
            {"pillar": "癸未", "start_age": 17, "end_age": 27, "start_year": 2007, "end_year": 2016},
        ]
        result = await writer.write(chart, analysis=analysis, dayun=dayun, birth_year=1990)
        assert len(result["chapters"]) == 2
        assert result["chapters"][0]["pillar"] == "壬午"
        assert result["chapters"][0]["year_range"] == "1997-2006"
