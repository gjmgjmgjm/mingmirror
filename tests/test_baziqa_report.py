"""Tests for the BaziQA result comparison reporter."""

import json

from tools.bazi_ai.baziqa_report import compare, load_results, summarize


class TestLoadResults:
    def test_loads_jsonl(self, tmp_path):
        path = tmp_path / "results.jsonl"
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"question_id": "Q1", "correct": True}, ensure_ascii=False) + "\n")
            f.write(json.dumps({"question_id": "Q2", "correct": False}, ensure_ascii=False) + "\n")
        results = load_results(path)
        assert len(results) == 2
        assert results[0]["question_id"] == "Q1"

    def test_loads_summary_json(self, tmp_path):
        path = tmp_path / "summary.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(
                {"results": [{"question_id": "Q1", "correct": True}]},
                f,
                ensure_ascii=False,
            )
        results = load_results(path)
        assert len(results) == 1


class TestSummarize:
    def test_accuracy(self):
        results = [
            {"question_id": "Q1", "correct": True, "predicted": "A"},
            {"question_id": "Q2", "correct": False, "predicted": "B"},
            {"question_id": "Q3", "error": "timeout"},
            {"question_id": "Q4", "predicted": ""},
        ]
        summary = summarize(results)
        assert summary["total"] == 4
        assert summary["correct"] == 1
        assert summary["errors"] == 1
        assert summary["unanswered"] == 1
        assert summary["accuracy"] == 0.25


class TestCompare:
    def test_compare_two_files(self, tmp_path, capsys):
        enhanced = tmp_path / "enhanced.jsonl"
        baseline = tmp_path / "baseline.jsonl"
        with enhanced.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"question_id": "Q1", "correct": True}) + "\n")
            f.write(json.dumps({"question_id": "Q2", "correct": False}) + "\n")
        with baseline.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"question_id": "Q1", "correct": False}) + "\n")
            f.write(json.dumps({"question_id": "Q2", "correct": True}) + "\n")

        compare(enhanced, baseline)
        captured = capsys.readouterr()
        assert "Enhanced wins:  1" in captured.out
        assert "Baseline wins:  1" in captured.out
        assert "Ties:           0" in captured.out
