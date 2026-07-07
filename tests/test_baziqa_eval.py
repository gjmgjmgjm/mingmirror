"""Tests for the BaziQA benchmark evaluator."""

from pathlib import Path

import pytest

from tools.bazi_ai.baziqa_eval import (
    _extract_answer,
    _format_options,
    load_baziqa,
    person_to_bazi,
    run_evaluation,
)


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
    def test_format_options(self):
        options = ["富裕", "贫穷", "父从商母是村干部", "父母当官"]
        text = _format_options(options)
        assert "A. 富裕" in text
        assert "D. 父母当官" in text

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
