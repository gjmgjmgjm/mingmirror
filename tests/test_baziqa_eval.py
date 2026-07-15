"""Tests for the BaziQA benchmark evaluator."""

from pathlib import Path

import pytest

from tools.bazi_ai.baziqa_eval import (
    _extract_answer,
    _format_options,
    _person_key_from_qid,
    _structural_case_match,
    load_baziqa,
    person_to_bazi,
    run_evaluation,
)
from tools.bazi_ai.engine import _case_relevance


@pytest.fixture
def data_dir():
    return Path("benchmarks/baziqa/data")


class TestLoadBaziQA:
    def test_loads_contest_and_celebrity(self, data_dir):
        contest, celebrity = load_baziqa(data_dir)
        assert len(contest) > 0
        assert len(celebrity) > 0
        assert "person_id" in contest[0]
        assert "questions" in contest[0]


class TestPersonToBazi:
    def test_converts_profile_to_bazi(self, data_dir):
        contest, _ = load_baziqa(data_dir)
        person = contest[0]
        bazi = person_to_bazi(person)
        assert bazi is not None
        assert len(bazi.split()) == 4

    def test_normalizes_bazi_format(self, data_dir):
        contest, _ = load_baziqa(data_dir)
        person = contest[0]
        bazi = person_to_bazi(person)
        # Each pillar should be two Chinese characters.
        for pillar in bazi.split():
            assert len(pillar) == 2


class TestHelpers:
    def test_person_key_from_qid(self):
        assert _person_key_from_qid("P026-Q6") == "P026"
        assert _person_key_from_qid("P026-Q7") == "P026"
        assert _person_key_from_qid("margaret_thatcher_P031-Q3") == "margaret_thatcher_P031"
        assert _person_key_from_qid("") == ""

    def test_structural_case_match(self):
        assert _structural_case_match("癸亥 壬戌 庚辰 辛巳", "乙丑 丙戌 庚午 壬午")  # same day master 庚
        assert _structural_case_match("癸亥 壬戌 庚辰 辛巳", "甲子 壬戌 乙卯 丙子")  # same month 戌
        assert not _structural_case_match("癸亥 壬戌 庚辰 辛巳", "甲子 乙丑 丙寅 丁卯")
        assert not _structural_case_match("bad", "癸亥 壬戌 庚辰 辛巳")

    def test_case_relevance_prefers_same_domain_over_same_bazi_other_domain(self):
        bazi = "癸亥 壬戌 庚辰 辛巳"
        career_case = {
            "bazi": "乙丑 丙戌 庚午 壬午",  # different chart
            "domains": {"career": ["公职"]},
            "analysis_corrected": "职业公职 正确答案：B",
            "key_terms": ["职业"],
            "conclusions": ["从事公职"],
        }
        same_bazi_marriage = {
            "bazi": bazi,
            "domains": {"marriage": ["离婚再婚"]},
            "analysis_corrected": "第二婚年份 正确答案：D",
            "key_terms": ["结婚"],
            "conclusions": ["2020结婚"],
        }
        q = "命主目前的职业是什么？"
        career_score = _case_relevance(career_case, bazi, q, boost_domains=["career"])
        marriage_score = _case_relevance(
            same_bazi_marriage, bazi, q, boost_domains=["career"]
        )
        assert career_score > marriage_score

    def test_format_options(self):
        options = ["富裕", "贫穷", "父从商母是村干部", "父母当官"]
        text = _format_options(options)
        assert "A. 富裕" in text
        assert "D. 父母当官" in text

    def test_format_options_five_choices(self):
        options = ["一", "二", "三", "四", "五"]
        text = _format_options(options)
        assert "A. 一" in text
        assert "E. 五" in text
        assert "F" not in text

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("答案是 A", "A"),
            ("选 B", "B"),
            ("C 选项", "C"),
            ("", None),
            ("没有答案", None),
        ],
    )
    def test_extract_answer(self, raw, expected):
        assert _extract_answer(raw) == expected

    def test_extract_answer_five_choices(self):
        assert _extract_answer("答案是 E", max_label="E") == "E"
        assert _extract_answer("选 E", max_label="E") == "E"
        assert _extract_answer("答案是 E", max_label="D") is None


class TestRunEvaluation:
    @pytest.mark.asyncio
    async def test_mock_evaluation_runs_and_scores(self, data_dir):
        summary = await run_evaluation(
            data_dir,
            mode="enhanced",
            datasets=["contest8"],
            limit=4,
            mock_answer="A",
        )
        assert summary["total"] == 4
        assert summary["mode"] == "enhanced"
        assert "accuracy" in summary
        assert 0 <= summary["accuracy"] <= 1
        for result in summary["results"]:
            assert result["predicted"] == "A"

    @pytest.mark.asyncio
    async def test_mock_evaluation_with_output(self, data_dir, tmp_path):
        output = tmp_path / "predictions.jsonl"
        await run_evaluation(
            data_dir,
            mode="baseline",
            datasets=["contest8"],
            limit=2,
            mock_answer="B",
            output=output,
        )
        assert output.exists()
        lines = output.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_mock_evaluation_leave_one_out(self, data_dir):
        summary = await run_evaluation(
            data_dir,
            mode="enhanced",
            datasets=["contest8"],
            limit=4,
            mock_answer="A",
            leave_one_out=True,
            max_concurrency=2,
        )
        assert summary["total"] == 4
        for result in summary["results"]:
            assert result["predicted"] == "A"

    @pytest.mark.asyncio
    async def test_mock_evaluation_cross_domain_exclude(self, data_dir):
        summary = await run_evaluation(
            data_dir,
            mode="enhanced",
            datasets=["celebrity50"],
            limit=4,
            mock_answer="B",
            exclude_datasets=["celebrity50"],
            leave_one_out=True,
            max_concurrency=2,
        )
        assert summary["total"] == 4
        assert summary["datasets"] == ["celebrity50"]
        for result in summary["results"]:
            assert result["predicted"] == "B"
