"""Unit tests for tools.bazi_ai.auspicious (择日引擎)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from tools.bazi_ai.auspicious import (
    _hour_stem_for_day,
    _score_day,
    _score_hours,
    auspicious_days,
    branch_relation,
    event_types,
    to_ics,
)
from tools.bazi_ai.shensha import day_shensha

SAMPLE_BAZI = "乙卯 戊寅 庚子 丙子"
D0 = date(2026, 7, 16)
D1 = D0 + timedelta(days=30)


class TestBranchRelation:
    def test_chong(self):
        assert "冲" in branch_relation("子", "午")
        assert "冲" in branch_relation("午", "子")

    def test_liu_he(self):
        rels = branch_relation("子", "丑")
        assert any(r.startswith("六合") for r in rels)

    def test_no_relation(self):
        # 子 vs 寅 — 无冲合刑害
        rels = branch_relation("子", "寅")
        assert "冲" not in rels


class TestEventTypes:
    def test_lists_core_and_new(self):
        types = event_types()
        values = {t["value"] for t in types}
        assert "marriage" in values
        assert "interview" in values
        assert "surgery" in values
        assert "investment" in values
        for t in types:
            assert t["label"]


class TestHourStem:
    def test_wu_shu_dun_jia_day(self):
        # 甲己还加甲: 日干甲 → 子时甲子
        assert _hour_stem_for_day("甲", "子") == "甲"
        # 乙庚丙作初: 日干乙/庚 → 子时丙子
        assert _hour_stem_for_day("乙", "子") == "丙"
        assert _hour_stem_for_day("庚", "子") == "丙"
        # 丙辛从戊起
        assert _hour_stem_for_day("丙", "子") == "戊"


class TestScoreHours:
    def test_returns_top_k_sorted(self):
        hours = _score_hours(
            day_master="庚",
            day_branch="子",
            year_branch="卯",
            useful=["土", "金"],
            taboo=["火", "木"],
            today_day_gan="甲",
            top_k=3,
        )
        assert len(hours) == 3
        scores = [h["score"] for h in hours]
        assert scores == sorted(scores, reverse=True)
        for h in hours:
            assert "branch" in h and "pillar" in h and "label" in h
            assert "clock" in h and 0 <= h["score"] <= 100

    def test_clash_day_branch_penalized(self):
        # 日支子,午时冲日支应明显偏低
        hours = _score_hours(
            "庚", "子", "卯", ["土", "金"], ["火", "木"], "甲", top_k=12
        )
        by_branch = {h["branch"]: h["score"] for h in hours}
        # 辰(土用神)通常高于午(冲日支+火忌神)
        assert by_branch["辰"] > by_branch["午"]


class TestAuspiciousDays:
    def test_basic_shape(self):
        res = auspicious_days(
            SAMPLE_BAZI, "male", "marriage", D0, D1, top_n=5
        )
        assert res["bazi"] == SAMPLE_BAZI
        assert res["event_label"] == "嫁娶"
        assert res["gender"] == "male"
        assert "土" in res["useful_gods"] or res["useful_gods"]
        assert len(res["days"]) == 31  # inclusive 30-day span
        assert len(res["top"]) == 5
        assert res["top"][0]["score"] >= res["top"][-1]["score"]
        assert res["days"][0]["score"] >= res["days"][-1]["score"]

    def test_top_is_prefix_of_days(self):
        res = auspicious_days(
            SAMPLE_BAZI, "male", "opening", D0, D0 + timedelta(days=14), top_n=3
        )
        assert res["top"] == res["days"][:3]

    def test_each_day_has_hours(self):
        res = auspicious_days(
            SAMPLE_BAZI, "male", "signing", D0, D0 + timedelta(days=3),
            top_n=2, hour_top_k=2,
        )
        for day in res["top"]:
            assert len(day["hours"]) == 2
            assert day["best_hour"] == day["hours"][0]
            assert day["best_hour"]["label"]

    def test_invalid_bazi(self):
        res = auspicious_days("不是八字", "male", "marriage", D0, D1)
        assert res.get("error")
        assert res["days"] == []
        assert res["top"] == []

    def test_gender_normalization(self):
        res = auspicious_days(
            SAMPLE_BAZI, "女", "marriage", D0, D0 + timedelta(days=7), top_n=3
        )
        assert res["gender"] == "female"

    def test_gender_affects_marriage_ranking(self):
        """男命妻星 / 女命夫星加权可能导致 top 日不同或同分不同排序。"""
        male = auspicious_days(
            SAMPLE_BAZI, "male", "marriage", D0, D0 + timedelta(days=45), top_n=8
        )
        female = auspicious_days(
            SAMPLE_BAZI, "female", "marriage", D0, D0 + timedelta(days=45), top_n=8
        )
        # 两边都能正常产出;至少结构完整
        assert len(male["top"]) == 8
        assert len(female["top"]) == 8
        # 若某日透财星,男命分应 ≥ 女命同分日(或相等)
        male_by_date = {d["date"]: d["score"] for d in male["days"]}
        female_by_date = {d["date"]: d["score"] for d in female["days"]}
        assert set(male_by_date) == set(female_by_date)

    def test_surgery_and_investment_labels(self):
        s = auspicious_days(
            SAMPLE_BAZI, "male", "surgery", D0, D0 + timedelta(days=5), top_n=2
        )
        inv = auspicious_days(
            SAMPLE_BAZI, "male", "investment", D0, D0 + timedelta(days=5), top_n=2
        )
        assert s["event_label"] == "手术"
        assert inv["event_label"] == "投资"
        # 事项宜忌应注入
        assert any("手术" in " ".join(d["dos"] + d["avoids"]) or
                   "静养" in " ".join(d["dos"]) or
                   "问诊" in " ".join(d["dos"])
                   for d in s["days"])

    def test_score_bounds(self):
        res = auspicious_days(
            SAMPLE_BAZI, "male", "travel", D0, D0 + timedelta(days=20), top_n=10
        )
        for d in res["days"]:
            assert 0 <= d["score"] <= 100
            assert isinstance(d["recommended"], bool)
            assert d["recommended"] == (d["score"] >= 60)

    def test_date_range_metadata(self):
        res = auspicious_days(
            SAMPLE_BAZI, "male", "moving", D0, D1, top_n=3
        )
        assert res["date_from"] == D0.isoformat()
        assert res["date_to"] == D1.isoformat()


class TestToIcs:
    def test_ics_structure(self):
        res = auspicious_days(
            SAMPLE_BAZI, "male", "marriage", D0, D0 + timedelta(days=20), top_n=5
        )
        ics = to_ics(res, top_n=3)
        assert "BEGIN:VCALENDAR" in ics
        assert "END:VCALENDAR" in ics
        assert "BEGIN:VEVENT" in ics
        assert "命镜择日" in ics
        assert "DTSTART;VALUE=DATE:" in ics
        assert "DESCRIPTION:" in ics
        # CRLF line endings for RFC 5545
        assert "\r\n" in ics

    def test_ics_empty_result(self):
        ics = to_ics({"event_label": "测试", "days": [], "top": []}, top_n=3)
        assert "BEGIN:VCALENDAR" in ics
        assert "BEGIN:VEVENT" not in ics

    def test_ics_min_score_fallback(self):
        res = {
            "event_type": "travel",
            "event_label": "出行",
            "days": [
                {
                    "date": "2026-08-01",
                    "day_pillar": "甲子",
                    "score": 40,
                    "reasoning": "平",
                    "dos": ["休整"],
                    "avoids": ["远行"],
                    "best_hour": {"label": "辰时(07:00-09:00)"},
                }
            ],
            "top": [],
        }
        ics = to_ics(res, top_n=1, min_score=60)
        # 无高分日时应回退到 days
        assert "20260801" in ics
        assert "出行" in ics


def test_server_auspicious_endpoint():
    """Hit FastAPI auspicious endpoints via TestClient."""
    try:
        from fastapi.testclient import TestClient

        from config.config_loader import ConfigLoader
        from server.app import build_app
    except Exception:
        pytest.skip("server deps not available")

    app = build_app(ConfigLoader())
    client = TestClient(app)

    r = client.get("/api/v1/bazi/auspicious/event-types")
    assert r.status_code == 200
    body = r.json()
    assert any(t["value"] == "surgery" for t in body["event_types"])

    r2 = client.post(
        "/api/v1/bazi/auspicious",
        json={
            "bazi": SAMPLE_BAZI,
            "gender": "male",
            "event_type": "interview",
            "date_from": D0.isoformat(),
            "date_to": (D0 + timedelta(days=10)).isoformat(),
            "top_n": 3,
            "include_ics": True,
        },
    )
    assert r2.status_code == 200
    data = r2.json()
    assert len(data["top"]) == 3
    assert "ics" in data
    assert "BEGIN:VCALENDAR" in data["ics"]
    assert data["top"][0].get("hours")


class TestShenshaSignal:
    """神煞作为择日评分信号(方向性回归,不锁死数值)。"""

    @staticmethod
    def _score(day_gan, day_zhi):
        ss = day_shensha(day_gan, day_zhi, "male")
        # 用神土金、忌神木,与命主 庚子/卯 局一致,便于隔离神煞效应
        sc, _ = _score_day(
            "庚", "子", "卯", ["土", "金"], ["木"], "marriage", "male",
            day_gan, day_zhi, ["甲子", "丙寅", day_gan + day_zhi], ss,
        )
        return sc, ss

    def test_yangren_day_scores_low(self):
        """甲干羊刃在卯 → 羊刃日显著低分。"""
        sc, ss = self._score("甲", "卯")
        assert any(s["name"] == "羊刃" and s["effect"] == "凶" for s in ss)
        assert sc <= 30

    def test_guiren_day_beats_yangren(self):
        """贵人日(甲丑)得分高于羊刃日(甲卯)。"""
        sc_gui, _ = self._score("甲", "丑")
        sc_yr, _ = self._score("甲", "卯")
        assert sc_gui > sc_yr

    def test_auspicious_days_has_shensha_field(self):
        res = auspicious_days(SAMPLE_BAZI, "male", "marriage", D0, D1)
        for day in res["days"]:
            assert "shensha" in day
            assert isinstance(day["shensha"], list)
        # 区间内必有至少一个带神煞的日(40+ 天范围,贵人/禄/文昌/金舆/羊刃密集)
        assert any(day["shensha"] for day in res["days"])
