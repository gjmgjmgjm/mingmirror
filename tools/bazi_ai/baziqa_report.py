#!/usr/bin/env python3
"""Compare two BaziQA evaluation result files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


def load_results(path: Path) -> List[Dict]:
    results: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            # Support both JSONL and single JSON summary formats.
            if isinstance(data, dict) and "results" in data:
                results.extend(data["results"])
            else:
                results.append(data)
    return results


def summarize(results: List[Dict]) -> Dict:
    total = len(results)
    correct = sum(1 for r in results if r.get("correct"))
    errors = sum(1 for r in results if "error" in r)
    unanswered = sum(1 for r in results if not r.get("predicted") and "error" not in r)
    accuracy = correct / total if total else 0.0
    return {
        "total": total,
        "correct": correct,
        "errors": errors,
        "unanswered": unanswered,
        "accuracy": round(accuracy, 4),
    }


def compare(enhanced_path: Path, baseline_path: Optional[Path]) -> None:
    enhanced = load_results(enhanced_path)
    enhanced_summary = summarize(enhanced)

    print(f"Enhanced ({enhanced_path.name})")
    print(f"  Total:      {enhanced_summary['total']}")
    print(f"  Correct:    {enhanced_summary['correct']}")
    print(f"  Errors:     {enhanced_summary['errors']}")
    print(f"  Unanswered: {enhanced_summary['unanswered']}")
    print(f"  Accuracy:   {enhanced_summary['accuracy']:.2%}")

    if baseline_path is None or not baseline_path.exists():
        return

    baseline = load_results(baseline_path)
    baseline_summary = summarize(baseline)

    print(f"\nBaseline ({baseline_path.name})")
    print(f"  Total:      {baseline_summary['total']}")
    print(f"  Correct:    {baseline_summary['correct']}")
    print(f"  Errors:     {baseline_summary['errors']}")
    print(f"  Unanswered: {baseline_summary['unanswered']}")
    print(f"  Accuracy:   {baseline_summary['accuracy']:.2%}")

    # Per-question delta.
    baseline_by_id = {r["question_id"]: r for r in baseline}
    enhanced_by_id = {r["question_id"]: r for r in enhanced}
    common_ids = sorted(set(baseline_by_id) & set(enhanced_by_id))

    wins = 0
    losses = 0
    ties = 0
    for qid in common_ids:
        b = baseline_by_id[qid].get("correct", False)
        e = enhanced_by_id[qid].get("correct", False)
        if e and not b:
            wins += 1
        elif b and not e:
            losses += 1
        else:
            ties += 1

    print(f"\nHead-to-head (common questions: {len(common_ids)})")
    print(f"  Enhanced wins:  {wins}")
    print(f"  Baseline wins:  {losses}")
    print(f"  Ties:           {ties}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare BaziQA evaluation results")
    parser.add_argument("enhanced", help="Enhanced result JSONL")
    parser.add_argument("--baseline", default=None, help="Baseline result JSONL")
    args = parser.parse_args()
    compare(Path(args.enhanced), Path(args.baseline) if args.baseline else None)


if __name__ == "__main__":
    main()
