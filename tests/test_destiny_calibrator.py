"""Tests for the destiny event calibration engine."""

import pytest

from tools.destiny.calibrator import (
    DestinyCalibrator,
    InMemoryEventStore,
    LifeEvent,
    _extract_year,
    _score_text,
    _suggest_hour_offset,
    _system_score,
)
from tools.destiny.contract import ChartInfo


class TestLifeEvent:
    def test_create_valid_event(self):
        event = LifeEvent.create(
            chart_id="庚午 辛巳 庚辰 壬午",
            event_type="marriage",
            happened_at="2020-05-20",
            description="结婚",
        )
        assert event.chart_id == "庚午 辛巳 庚辰 壬午"
        assert event.event_type == "marriage"
        assert event.happened_at == "2020-05-20"
        assert event.description == "结婚"
        assert event.id

    def test_create_invalid_event_type(self):
        with pytest.raises(ValueError):
            LifeEvent.create(
                chart_id="庚午 辛巳 庚辰 壬午",
                event_type="not_a_real_type",
                happened_at="2020-05-20",
            )


class TestInMemoryEventStore:
    def test_add_and_list(self):
        store = InMemoryEventStore()
        event = LifeEvent.create(
            chart_id="庚午 辛巳 庚辰 壬午",
            event_type="job",
            happened_at="2019-06-01",
        )
        store.add(event)
        assert len(store.list("庚午 辛巳 庚辰 壬午")) == 1
        assert len(store.list("other chart")) == 0

    def test_delete_existing(self):
        store = InMemoryEventStore()
        event = LifeEvent.create(
            chart_id="庚午 辛巳 庚辰 壬午",
            event_type="job",
            happened_at="2019-06-01",
        )
        store.add(event)
        assert store.delete("庚午 辛巳 庚辰 壬午", event.id) is True
        assert len(store.list("庚午 辛巳 庚辰 壬午")) == 0

    def test_delete_missing(self):
        store = InMemoryEventStore()
        assert store.delete("庚午 辛巳 庚辰 壬午", "missing") is False


class TestHelpers:
    def test_extract_year(self):
        assert _extract_year("2020-05-20") == 2020
        assert _extract_year("2020-05-20T10:00:00") == 2020
        assert _extract_year("not a date") is None
        assert _extract_year("") is None

    def test_score_text_with_keywords(self):
        # career keywords
        assert _score_text("今年事业上升，有晋升机会", "career") > 0.0
        # marriage keywords
        assert _score_text("婚姻美满，感情稳定", "marriage") > 0.0
        # no keywords
        assert _score_text("平平淡淡的一年", "career") == 0.0

    def test_system_score_with_domain_analysis(self):
        raw = {
            "domain_analysis": {"career": {"text": "今年事业晋升，工作顺利"}},
            "confidence": "high",
        }
        assert _system_score(raw, "career") > 0.5

    def test_system_score_with_error(self):
        raw = {"error": "system unavailable"}
        assert _system_score(raw, "career") == 0.1

    def test_suggest_hour_offset(self):
        assert _suggest_hour_offset(0.6, 3) is None
        assert _suggest_hour_offset(0.4, 3) == 1
        assert _suggest_hour_offset(0.2, 3) == 2


class TestDestinyCalibrator:
    @pytest.mark.asyncio
    async def test_calibrate_no_events(self):
        calibrator = DestinyCalibrator()
        chart = ChartInfo(bazi="庚午 辛巳 庚辰 壬午")
        result = await calibrator.calibrate(chart)
        assert result["event_count"] == 0
        assert result["average_score"] == 0.0
        assert result["system_scores"] == {}
        assert "No events provided" in result["note"]

    @pytest.mark.asyncio
    async def test_calibrate_with_mock_analyzer(self):
        async def mock_analyzer(chart, question):
            return {
                "per_system": [
                    {
                        "system": "bazi",
                        "raw_result": {
                            "domain_analysis": {
                                "career": {"text": "今年事业晋升，工作顺利"}
                            }
                        },
                    },
                    {
                        "system": "qizheng",
                        "raw_result": {
                            "domain_analysis": {
                                "career": {"text": "官禄宫有吉星"}
                            }
                        },
                    },
                ]
            }

        calibrator = DestinyCalibrator(analyzer=mock_analyzer)
        event = LifeEvent.create(
            chart_id="庚午 辛巳 庚辰 壬午",
            event_type="job_change",
            happened_at="2020-06-01",
            description="跳槽到新公司",
        )
        calibrator.event_store.add(event)

        chart = ChartInfo(bazi="庚午 辛巳 庚辰 壬午")
        result = await calibrator.calibrate(chart)
        assert result["event_count"] == 1
        assert result["average_score"] > 0.0
        assert "bazi" in result["system_scores"]
        assert "qizheng" in result["system_scores"]
        assert sum(result["adjusted_weights"].values()) <= 1.05
        assert result["events"][0]["domain"] == "career"

    @pytest.mark.asyncio
    async def test_calibrate_with_explicit_events(self):
        async def mock_analyzer(chart, question):
            return {
                "per_system": [
                    {
                        "system": "bazi",
                        "raw_result": {
                            "domain_analysis": {
                                "marriage": {"text": "今年有结婚之象"}
                            }
                        },
                    }
                ]
            }

        calibrator = DestinyCalibrator(analyzer=mock_analyzer)
        event = LifeEvent.create(
            chart_id="壬申 辛亥 丙寅 己丑",
            event_type="marriage",
            happened_at="2021-10-01",
        )
        result = await calibrator.calibrate(
            ChartInfo(bazi="壬申 辛亥 丙寅 己丑"),
            events=[event],
        )
        assert result["event_count"] == 1
        assert result["system_scores"]["bazi"] > 0.0
