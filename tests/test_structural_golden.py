"""Zero-API structural golden suite for MingMirror trust layer.

Covers: solar pillars, late 子时, true solar time hour boundary, lunar leap,
dayun gender direction, and ziwei life-palace nayin bureau (20+ charts).

Gold lives in tests/fixtures/structural_golden.json — update intentionally
when algorithms change, never silently.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "structural_golden.json"


@pytest.fixture(scope="module")
def gold() -> dict:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert int(data.get("version") or 0) >= 1
    return data


def _is_true_solar_case(case: dict) -> bool:
    return case.get("kind") == "true_solar" or case.get("id", "").startswith("true_solar")


def _is_wuhu_case(case: dict) -> bool:
    return "year_stem" in case and "bazi" not in case


# ---------------------------------------------------------------------------
# Bazi pillars
# ---------------------------------------------------------------------------


def test_solar_pillars_match_gold(gold):
    from tools.bazi_ai.calendar import pillars_for_datetime

    cases = [c for c in gold["pillars_solar"] if not _is_true_solar_case(c)]
    assert len(cases) >= 8, "expected expanded solar edge cases"
    for case in cases:
        dt = datetime.fromisoformat(case["birth_datetime"])
        got = pillars_for_datetime(dt)
        assert got == case["pillars"], f"{case['id']}: {got} != {case['pillars']}"


def test_late_zi_matches_next_day_early_zi(gold):
    """23:15 and next-day 00:15 must share day+hour pillars under 子时归次日."""
    late = next(c for c in gold["pillars_solar"] if c["id"] == "late_zi_next_day")
    early = next(c for c in gold["pillars_solar"] if c["id"] == "early_zi_same_as_late")
    assert late["pillars"]["day"] == early["pillars"]["day"]
    assert late["pillars"]["hour"] == early["pillars"]["hour"]


def test_y2k_late_zi_rolls_day_pillar(gold):
    early = next(c for c in gold["pillars_solar"] if c["id"] == "y2k_early_zi")
    late = next(c for c in gold["pillars_solar"] if c["id"] == "y2k_late_zi")
    assert early["pillars"]["day"] != late["pillars"]["day"]
    assert late["pillars"]["hour"].endswith("子")


def test_true_solar_time_can_change_hour_pillar(gold):
    from tools.bazi_ai.calendar import pillars_for_datetime

    case = next(c for c in gold["pillars_solar"] if _is_true_solar_case(c))
    dt = datetime.fromisoformat(case["birth_datetime"])
    wall = pillars_for_datetime(dt)
    assert wall["hour"] == case["wall_hour"]

    lon = float(case["longitude"])
    eff = dt + timedelta(minutes=4.0 * (lon - 120.0))
    true_p = pillars_for_datetime(eff)
    assert true_p["hour"] == case["true_solar_hour"]
    assert true_p == case["true_solar_pillars"]
    assert true_p["hour"] != wall["hour"]


def test_lunar_leap_changes_month_pillar(gold):
    pytest.importorskip("sxtwl")
    from tools.bazi_ai.calendar import pillars_for_lunar_datetime

    non = next(c for c in gold["pillars_lunar"] if not c["leap"])
    leap = next(c for c in gold["pillars_lunar"] if c["leap"])
    p_non = pillars_for_lunar_datetime(
        non["lunar_year"],
        non["lunar_month"],
        non["lunar_day"],
        non["hour"],
        non["minute"],
        leap=False,
    )
    p_leap = pillars_for_lunar_datetime(
        leap["lunar_year"],
        leap["lunar_month"],
        leap["lunar_day"],
        leap["hour"],
        leap["minute"],
        leap=True,
    )
    assert p_non == non["pillars"]
    assert p_leap == leap["pillars"]
    assert p_non["month"] != p_leap["month"]


# ---------------------------------------------------------------------------
# Dayun gender
# ---------------------------------------------------------------------------


def test_dayun_gender_direction_gold(gold):
    from tools.bazi_ai.calendar import dayun_list

    assert len(gold["dayun"]) >= 6
    for case in gold["dayun"]:
        rows = dayun_list(
            case["bazi"],
            case["gender"],
            case["birth_date"],
            case.get("birth_time") or "00:00",
        )
        assert rows, case["id"]
        assert rows[0]["pillar"] == case["first_pillar"], case["id"]
        if "second_pillar" in case:
            assert rows[1]["pillar"] == case["second_pillar"], case["id"]


def test_dayun_male_and_female_diverge_pairs(gold):
    from tools.bazi_ai.calendar import dayun_list

    pairs = [
        ("male_forward", "female_reverse"),
        ("jiazi_male", "jiazi_female"),
        ("yimao_male", "yimao_female"),
        ("renyin_male", "renyin_female"),
    ]
    by_id = {c["id"]: c for c in gold["dayun"]}
    for mid, fid in pairs:
        m = by_id[mid]
        f = by_id[fid]
        m_rows = dayun_list(m["bazi"], "male", m["birth_date"], m["birth_time"])
        f_rows = dayun_list(f["bazi"], "female", f["birth_date"], f["birth_time"])
        assert m_rows[0]["pillar"] != f_rows[0]["pillar"], f"{mid}/{fid}"


# ---------------------------------------------------------------------------
# Ziwei structural
# ---------------------------------------------------------------------------


def test_ziwei_wuhu_nayin_bureau_cases(gold):
    from tools.ziwei.chart import five_element_bureau, life_palace_stem

    cases = [c for c in gold["ziwei"] if _is_wuhu_case(c)]
    assert len(cases) >= 2
    for case in cases:
        assert life_palace_stem(case["year_stem"], case["life_palace"]) == case[
            "palace_stem"
        ], case["id"]
        el, bureau = five_element_bureau(
            year_stem=case["year_stem"], life_palace=case["life_palace"]
        )
        assert el == case["element"], case["id"]
        assert bureau == case["bureau"], case["id"]


def test_ziwei_structural_charts_match_gold(gold):
    from tools.ziwei.chart import structural_chart

    chart_cases = [c for c in gold["ziwei"] if "bazi" in c]
    assert len(chart_cases) >= 15, "expected 15+ ziwei structural gold charts"
    for case in chart_cases:
        chart = structural_chart(
            case["bazi"],
            gender="male",
            day_of_month=int(case.get("day_of_month") or 15),
        )
        assert chart is not None, case["id"]
        assert chart["life_palace"] == case["life_palace"], case["id"]
        assert chart["bureau_label"] == case["bureau_label"], case["id"]
        assert chart["ziwei_branch"] == case["ziwei_branch"], case["id"]
        if case.get("bureau_source"):
            assert chart.get("bureau_source") == case["bureau_source"]
        for star in case.get("ming_main_contains") or []:
            ming = next(p for p in chart["palaces"] if p["name"] == "命宫")
            pool = list(ming.get("main_stars") or []) + list(chart.get("zhu_xing") or [])
            assert star in pool, f"{case['id']} missing {star} in {pool}"


def test_ziwei_deterministic_rerun(gold):
    from tools.ziwei.chart import structural_chart

    case = next(c for c in gold["ziwei"] if c["id"] == "z3")
    a = structural_chart(case["bazi"], day_of_month=15)
    b = structural_chart(case["bazi"], day_of_month=15)
    assert a is not None and b is not None
    assert a["ziwei_branch"] == b["ziwei_branch"]
    assert a["bureau"] == b["bureau"]
    assert a["palaces"] == b["palaces"]


def test_ziwei_all_bureaus_represented(gold):
    """Sanity: expanded set should hit multiple 五行局 numbers."""
    bureaus = {
        c["bureau_label"]
        for c in gold["ziwei"]
        if "bureau_label" in c
    }
    assert len(bureaus) >= 4, bureaus
