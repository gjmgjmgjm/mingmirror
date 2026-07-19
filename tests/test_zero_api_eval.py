"""Tests for zero-API dataset loaders, year critic, and eval harness."""

from __future__ import annotations

from benchmarks.baziqa.dataset_loader import (
    load_contest8,
    load_mingli,
    load_summary,
    load_celebrity_extra_charts,
)
from tools.bazi_ai.year_critic import (
    evaluate_year_mcq,
    structural_critic_pick,
    _year_pillar_approx,
)


def test_dataset_inventory_nonzero():
    s = load_summary()
    assert s["contest8"] >= 200
    assert s["mingli"] >= 100
    assert s["celebrity_extra_charts"] >= 50


def test_contest8_item_shape():
    items = load_contest8(years=[2024])
    assert items
    it = items[0]
    assert it.answer in "ABCD"
    assert len(it.options) >= 2
    assert it.birth_date.count("-") == 2
    assert it.gender in ("male", "female")


def test_mingli_item_shape():
    items = load_mingli()
    assert len(items) >= 100
    assert all(i.answer in "ABCD" for i in items[:20])


def test_year_pillar_approx_jiazi():
    # 1984 甲子
    assert _year_pillar_approx(1984) == "甲子"
    assert _year_pillar_approx(2024)[0] in "甲乙丙丁戊己庚辛壬癸"


def test_structural_critic_returns_letter_or_empty():
    items = load_contest8(years=[2024])
    # find a year-ish question
    sample = None
    for it in items:
        if any(k in it.question for k in ("哪年", "何年", "年")):
            sample = it
            break
    if sample is None:
        sample = items[0]
    from benchmarks.baziqa.zero_api_eval import compute_bazi

    bazi = compute_bazi(sample)
    letter, meta = structural_critic_pick(
        bazi,
        sample.question,
        sample.options,
        gender=sample.gender,
        birth_date=sample.birth_date,
        birth_time=sample.birth_time,
        birth_year=sample.birth_year,
    )
    assert isinstance(meta, dict)
    if letter:
        assert letter in "ABCD"


def test_evaluate_year_mcq_keys():
    charts = load_celebrity_extra_charts()
    assert charts
    # synthetic year options around a known chart
    rec = charts[0]
    bazi = rec["bazi"]
    bd = rec.get("birth_date") or "1990-01-01"
    res = evaluate_year_mcq(
        bazi,
        "命主哪年结婚？",
        ["A. 2010", "B. 2015", "C. 2018", "D. 2020"],
        "B",
        gender=rec.get("gender") or "male",
        birth_date=bd,
        birth_time=rec.get("birth_time") or "12:00",
        birth_year=int(bd[:4]),
    )
    assert "top1_hit" in res and "top2_hit" in res and "critic_hit" in res


def test_zero_api_eval_main_runs():
    from benchmarks.baziqa.zero_api_eval import main

    assert main(["--sources", "contest8", "--year-limit", "30"]) == 0
