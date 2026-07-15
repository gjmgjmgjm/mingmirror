"""Tests for the Qi Zheng CLI subcommand in cli/main.py."""

from types import SimpleNamespace

import pytest

main_module = pytest.importorskip("cli.main")
qizheng_engine = pytest.importorskip("tools.qizheng.engine")


def _make_args(**kwargs):
    defaults = {
        "analyze_qizheng": None,
        "qizheng_yearly": None,
        "qizheng_birth_datetime": None,
        "qizheng_latitude": None,
        "qizheng_longitude": None,
        "qizheng_timezone_offset": None,
        "qizheng_precession_mode": "tropical",
        "qizheng_dignity_table": "default",
        "qizheng_question": "",
        "qizheng_gender": "male",
        "qizheng_birth_year": 0,
        "qizheng_mode": "10y",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_run_qizheng_analyze_with_bazi(monkeypatch, tmp_path, capsys):
    config = main_module.ConfigLoader()
    config.update(path=str(tmp_path))

    called = {}

    class _FakeAnalyzer:
        async def analyze(self, chart_info, question=""):
            called["chart_info"] = chart_info
            called["question"] = question
            return {"basic_info": {"chart": chart_info.get("bazi")}, "_mock": True}

    monkeypatch.setattr(
        qizheng_engine,
        "QiZhengAnalyzer",
        lambda **kwargs: _FakeAnalyzer(),
    )

    args = _make_args(analyze_qizheng="甲子 丙寅 戊辰 庚午", qizheng_question="事业")
    await main_module._run_qizheng_subcommand(args, config)

    assert called["chart_info"]["bazi"] == "甲子 丙寅 戊辰 庚午"
    assert called["question"] == "事业"


@pytest.mark.asyncio
async def test_run_qizheng_analyze_with_datetime(monkeypatch, tmp_path, capsys):
    config = main_module.ConfigLoader()
    config.update(path=str(tmp_path))

    called = {}

    class _FakeAnalyzer:
        async def analyze(self, chart_info, question=""):
            called["chart_info"] = chart_info
            return {"basic_info": {"chart": "computed"}, "_mock": True}

    monkeypatch.setattr(
        qizheng_engine,
        "QiZhengAnalyzer",
        lambda **kwargs: _FakeAnalyzer(),
    )

    args = _make_args(
        analyze_qizheng="",
        qizheng_birth_datetime="1990-05-15T08:00:00",
        qizheng_latitude=39.9042,
        qizheng_longitude=116.4074,
        qizheng_timezone_offset=8.0,
        qizheng_precession_mode="sidereal_lahiri",
    )
    await main_module._run_qizheng_subcommand(args, config)

    assert called["chart_info"]["birth_datetime"] == "1990-05-15T08:00:00"
    assert called["chart_info"]["latitude"] == 39.9042
    assert called["chart_info"]["precession_mode"] == "sidereal_lahiri"


@pytest.mark.asyncio
async def test_run_qizheng_analyze_missing_input(tmp_path, capsys):
    config = main_module.ConfigLoader()
    config.update(path=str(tmp_path))

    args = _make_args(analyze_qizheng="")
    with pytest.raises(SystemExit):
        await main_module._run_qizheng_subcommand(args, config)


@pytest.mark.asyncio
async def test_run_qizheng_yearly_with_bazi(monkeypatch, tmp_path, capsys):
    config = main_module.ConfigLoader()
    config.update(path=str(tmp_path))

    called = {}

    async def _fake_analyze_yearly(chart, **kwargs):
        called["chart"] = chart
        called["kwargs"] = kwargs
        return {"dayun_summary": [], "yearly_analysis": []}

    monkeypatch.setattr(qizheng_engine, "analyze_yearly", _fake_analyze_yearly)

    args = _make_args(
        qizheng_yearly="甲子 丙寅 戊辰 庚午",
        qizheng_gender="male",
        qizheng_birth_year=1984,
        qizheng_mode="10y",
    )
    await main_module._run_qizheng_subcommand(args, config)

    assert called["chart"] == "甲子 丙寅 戊辰 庚午"
    assert called["kwargs"]["gender"] == "male"
    assert called["kwargs"]["birth_year"] == 1984
    assert "dignity_table" in called["kwargs"]


@pytest.mark.asyncio
async def test_run_qizheng_yearly_with_yang_dignity_table(monkeypatch, tmp_path, capsys):
    config = main_module.ConfigLoader()
    config.update(path=str(tmp_path))

    called = {}

    async def _fake_analyze_yearly(chart, **kwargs):
        called["chart"] = chart
        called["kwargs"] = kwargs
        return {"dayun_summary": [], "yearly_analysis": []}

    monkeypatch.setattr(qizheng_engine, "analyze_yearly", _fake_analyze_yearly)

    from tools.qizheng.star_tables import MIAO_WANG_YANG

    args = _make_args(
        qizheng_yearly="甲子 丙寅 戊辰 庚午",
        qizheng_gender="male",
        qizheng_birth_year=1984,
        qizheng_mode="10y",
        qizheng_dignity_table="yang",
    )
    await main_module._run_qizheng_subcommand(args, config)

    assert called["kwargs"]["dignity_table"] is MIAO_WANG_YANG
