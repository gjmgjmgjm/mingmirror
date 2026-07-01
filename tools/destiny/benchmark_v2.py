"""Quantitative benchmark for multi-destiny analysis systems.

Runs bazi / ziwei / qizheng / ensemble (with optional strategies) against a set
of human-annotated cases and computes domain-level precision / recall / F1,
inter-system consistency, and confidence calibration.

When no DeepSeek API key is present, the script still runs in mock mode and
validates output structure / coverage / consistency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.destiny.contract import ChartInfo
from tools.destiny.ensemble import MultiDestinyAnalyzer

_BENCHMARK_DATA_DIR = Path(__file__).resolve().parent / "benchmark_data"
_ANNOTATED_CASES_PATH = _BENCHMARK_DATA_DIR / "annotated_cases.jsonl"
_REPORT_PATH = _BENCHMARK_DATA_DIR / "benchmark_report.json"

_DOMAINS = ("career", "wealth", "marriage", "health", "general")


def load_annotated_cases(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load annotated cases from a JSONL file."""
    path = path or _ANNOTATED_CASES_PATH
    if not path.exists():
        return []
    cases: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return cases


def _extract_text(value: Any) -> str:
    """Extract a text string from a possibly structured domain value."""
    if isinstance(value, dict):
        return str(value.get("text") or value.get("description") or value.get("consensus", ""))
    return str(value) if value else ""


def _extract_keywords(value: Any) -> List[str]:
    """Extract keywords from a possibly structured domain value."""
    if isinstance(value, dict):
        return [str(k) for k in (value.get("keywords") or [])]
    return []


def _keyword_overlap(
    annotation: Dict[str, Any],
    prediction: Any,
) -> Tuple[float, float, float]:
    """Return (precision, recall, f1) for keyword overlap.

    Precision = matched / output_keywords_count
    Recall    = matched / annotation_keywords_count
    """
    annotation_keywords = set(str(k) for k in annotation.get("keywords", []))
    if not annotation_keywords:
        return 0.0, 0.0, 0.0

    output_text = _extract_text(prediction)
    output_keywords = set(_extract_keywords(prediction))
    if output_text:
        # Also treat any annotation keyword that appears in the output text as matched.
        for kw in annotation_keywords:
            if kw in output_text:
                output_keywords.add(kw)

    if not output_keywords:
        return 0.0, 0.0, 0.0

    matched = annotation_keywords & output_keywords
    precision = len(matched) / len(output_keywords)
    recall = len(matched) / len(annotation_keywords)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def _normalized_predictions(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return a domain_analysis-like dict from either system or ensemble output."""
    if "domain_analysis" in result:
        return result["domain_analysis"] or {}
    # Ensemble outputs consensus in `aligned`.
    aligned = result.get("aligned", {})
    return {
        domain: entry.get("consensus", "")
        for domain, entry in aligned.items()
        if isinstance(entry, dict)
    }


def _coverage(
    annotations: Dict[str, Any],
    result: Dict[str, Any],
) -> float:
    """Return the fraction of annotated domains that have a non-empty prediction."""
    expected = {d for d in _DOMAINS if d in annotations}
    if not expected:
        return 0.0
    predictions = _normalized_predictions(result)
    covered = {
        d
        for d in expected
        if d in predictions and _extract_text(predictions[d]).strip()
    }
    return len(covered) / len(expected)


def _confidence_to_numeric(confidence: str) -> float:
    mapping = {"high": 1.0, "medium": 0.5, "low": 0.0}
    return mapping.get(confidence, 0.5)


def _aggregate_scores(scores: Sequence[float]) -> Dict[str, Any]:
    if not scores:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "count": 0, "scores": []}
    return {
        "mean": sum(scores) / len(scores),
        "min": min(scores),
        "max": max(scores),
        "count": len(scores),
        "scores": list(scores),
    }


def _system_domain_f1s(
    cases: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Dict[str, List[float]]:
    """Collect per-domain F1 scores for one system across all cases."""
    domain_f1s: Dict[str, List[float]] = {d: [] for d in _DOMAINS}
    for case, result in zip(cases, results):
        annotations = case.get("annotations", {})
        predictions = _normalized_predictions(result)
        for domain in _DOMAINS:
            if domain not in annotations:
                continue
            _, _, f1 = _keyword_overlap(annotations[domain], predictions.get(domain))
            domain_f1s[domain].append(f1)
    return domain_f1s


def _system_consistency(results_by_system: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Compute pairwise inter-system agreement."""
    systems = list(results_by_system.keys())
    if len(systems) < 2:
        return {"mean": 0.0, "pairs": []}

    pair_scores: List[float] = []
    pair_details: List[Dict[str, Any]] = []
    for i in range(len(systems)):
        for j in range(i + 1, len(systems)):
            sys_a, sys_b = systems[i], systems[j]
            case_scores: List[float] = []
            for res_a, res_b in zip(results_by_system[sys_a], results_by_system[sys_b]):
                dom_scores: List[float] = []
                for domain in _DOMAINS:
                    text_a = _extract_text(_normalized_predictions(res_a).get(domain))
                    text_b = _extract_text(_normalized_predictions(res_b).get(domain))
                    if not text_a or not text_b:
                        continue
                    # Simple agreement: exact text match gives 1.0; keyword overlap gives partial.
                    if text_a == text_b:
                        dom_scores.append(1.0)
                    else:
                        kw_a = set(_extract_keywords(_normalized_predictions(res_a).get(domain)))
                        kw_b = set(_extract_keywords(_normalized_predictions(res_b).get(domain)))
                        if kw_a or kw_b:
                            union = kw_a | kw_b
                            inter = kw_a & kw_b
                            dom_scores.append(len(inter) / len(union) if union else 0.0)
                        else:
                            dom_scores.append(0.0)
                if dom_scores:
                    case_scores.append(sum(dom_scores) / len(dom_scores))
            mean_score = sum(case_scores) / len(case_scores) if case_scores else 0.0
            pair_scores.append(mean_score)
            pair_details.append({
                "system_a": sys_a,
                "system_b": sys_b,
                "agreement": mean_score,
            })

    return {
        "mean": sum(pair_scores) / len(pair_scores) if pair_scores else 0.0,
        "pairs": pair_details,
    }


def _confidence_calibration(
    cases: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute average F1 per confidence level."""
    buckets: Dict[str, List[float]] = {"high": [], "medium": [], "low": []}
    for case, result in zip(cases, results):
        annotations = case.get("annotations", {})
        predictions = _normalized_predictions(result)
        confidence = result.get("confidence", "medium")
        if confidence not in buckets:
            confidence = "medium"
        f1s = []
        for domain in _DOMAINS:
            if domain not in annotations:
                continue
            _, _, f1 = _keyword_overlap(annotations[domain], predictions.get(domain))
            f1s.append(f1)
        if f1s:
            buckets[confidence].append(sum(f1s) / len(f1s))

    return {
        level: {
            "mean_f1": sum(scores) / len(scores) if scores else 0.0,
            "count": len(scores),
        }
        for level, scores in buckets.items()
    }


def _evaluate_system(
    system: str,
    cases: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute all metrics for a single system."""
    coverages = []
    for case, result in zip(cases, results):
        coverages.append(_coverage(case.get("annotations", {}), result))

    domain_f1s = _system_domain_f1s(cases, results)
    domain_metrics: Dict[str, Any] = {}
    for domain in _DOMAINS:
        scores = domain_f1s.get(domain, [])
        if scores:
            precision_scores: List[float] = []
            recall_scores: List[float] = []
            for case, result in zip(cases, results):
                annotations = case.get("annotations", {})
                if domain not in annotations:
                    continue
                p, r, _ = _keyword_overlap(annotations[domain], result.get("domain_analysis", {}).get(domain))
                precision_scores.append(p)
                recall_scores.append(r)
            domain_metrics[domain] = {
                "precision": _aggregate_scores(precision_scores),
                "recall": _aggregate_scores(recall_scores),
                "f1": _aggregate_scores(scores),
            }
        else:
            domain_metrics[domain] = {
                "precision": _aggregate_scores([]),
                "recall": _aggregate_scores([]),
                "f1": _aggregate_scores([]),
            }

    return {
        "coverage": _aggregate_scores(coverages),
        "domain_metrics": domain_metrics,
        "calibration": _confidence_calibration(cases, results),
    }


def _build_analyzers() -> Tuple[
    Dict[str, Any],
    MultiDestinyAnalyzer,
    MultiDestinyAnalyzer,
    MultiDestinyAnalyzer,
    MultiDestinyAnalyzer,
]:
    """Build bazi/ziwei/qizheng callables and ensemble variants."""
    from tools.bazi_ai.engine import analyze_bazi
    from tools.qizheng.engine import QiZhengAnalyzer
    from tools.ziwei.engine import ZiWeiAnalyzer

    async def bazi_caller(chart: ChartInfo, question: str) -> Dict[str, Any]:
        return await analyze_bazi(chart.bazi, question=question)

    qz = QiZhengAnalyzer()

    async def qizheng_caller(chart: ChartInfo, question: str) -> Dict[str, Any]:
        return await qz.analyze({"bazi": chart.bazi}, question=question)

    zw = ZiWeiAnalyzer()

    async def ziwei_caller(chart: ChartInfo, question: str) -> Dict[str, Any]:
        chart_info = {
            "birth_datetime": chart.birth_datetime or "1990-01-01T12:00:00",
            "gender": chart.gender or "male",
            "location": {"longitude": 116.4, "latitude": 39.9, "timezone": "Asia/Shanghai"},
            "bazi": chart.bazi,
        }
        return await zw.analyze(chart_info, question=question)

    callables = {
        "bazi": bazi_caller,
        "qizheng": qizheng_caller,
        "ziwei": ziwei_caller,
    }

    ensemble_single = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
        strategy="single",
    )
    ensemble_reflection = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
        strategy="reflection",
    )
    ensemble_debate = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
        strategy="debate",
    )
    ensemble_tool = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={"bazi": bazi_caller, "qizheng": qizheng_caller},
        strategy="tool_augmented",
    )

    return (
        callables,
        ensemble_single,
        ensemble_reflection,
        ensemble_debate,
        ensemble_tool,
    )


async def run_benchmark_v2(
    cases: List[Dict[str, Any]],
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the full benchmark and return a structured report."""
    if limit:
        cases = cases[:limit]

    (
        callables,
        ensemble_single,
        ensemble_reflection,
        ensemble_debate,
        ensemble_tool,
    ) = _build_analyzers()

    results_by_system: Dict[str, List[Dict[str, Any]]] = {
        "bazi": [],
        "qizheng": [],
        "ziwei": [],
        "ensemble_single": [],
        "ensemble_reflection": [],
        "ensemble_debate": [],
        "ensemble_tool_augmented": [],
    }

    for case in cases:
        chart = ChartInfo(
            bazi=case["bazi"],
            question=case.get("question", ""),
            gender=case.get("gender"),
            birth_datetime=case.get("birth_datetime"),
        )
        results_by_system["bazi"].append(await callables["bazi"](chart, chart.question))
        results_by_system["qizheng"].append(await callables["qizheng"](chart, chart.question))
        results_by_system["ziwei"].append(await callables["ziwei"](chart, chart.question))
        results_by_system["ensemble_single"].append(await ensemble_single.analyze(chart, chart.question))
        results_by_system["ensemble_reflection"].append(await ensemble_reflection.analyze(chart, chart.question))
        results_by_system["ensemble_debate"].append(await ensemble_debate.analyze(chart, chart.question))
        results_by_system["ensemble_tool_augmented"].append(await ensemble_tool.analyze(chart, chart.question))

    system_metrics: Dict[str, Any] = {}
    for system, results in results_by_system.items():
        system_metrics[system] = _evaluate_system(system, cases, results)

    consistency = _system_consistency(
        {k: v for k, v in results_by_system.items() if k in ("bazi", "qizheng", "ziwei")}
    )

    return {
        "cases": len(cases),
        "api_key_present": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "system_metrics": system_metrics,
        "inter_system_consistency": consistency,
        "per_case": [
            {
                "bazi": case["bazi"],
                "question": case.get("question", ""),
                "results": {
                    system: {
                        "confidence": result.get("confidence", "medium"),
                        "coverage": _coverage(
                            case.get("annotations", {}),
                            result,
                        ),
                    }
                    for system, result in zip(results_by_system.keys(), results)
                },
            }
            for case, results in zip(
                cases,
                zip(*results_by_system.values()),
            )
        ],
    }


def _print_table(report: Dict[str, Any]) -> None:
    """Print a concise terminal summary."""
    print("\n=== Destiny Benchmark V2 ===")
    print(f"Cases: {report['cases']} | API key present: {report['api_key_present']}\n")

    header = f"{'System':<22} {'Coverage':>10} {'Avg F1':>10} {'High-F1':>10} {'Med-F1':>10} {'Low-F1':>10}"
    print(header)
    print("-" * len(header))

    for system, metrics in report["system_metrics"].items():
        coverage = metrics["coverage"]["mean"]
        f1_scores: List[float] = []
        for domain_metrics in metrics["domain_metrics"].values():
            f1_scores.extend(domain_metrics["f1"].get("scores", []))
        avg_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0
        cal = metrics["calibration"]
        print(
            f"{system:<22} {coverage:>10.2%} {avg_f1:>10.3f} "
            f"{cal['high']['mean_f1']:>10.3f} {cal['medium']['mean_f1']:>10.3f} {cal['low']['mean_f1']:>10.3f}"
        )

    print("\nInter-system consistency:")
    print(f"  Mean agreement: {report['inter_system_consistency']['mean']:.3f}")
    for pair in report["inter_system_consistency"]["pairs"]:
        print(f"  {pair['system_a']} vs {pair['system_b']}: {pair['agreement']:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="多命理学派准确率 benchmark v2")
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="Path to annotated_cases.jsonl",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of cases to run",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(_REPORT_PATH),
        help="Path to write benchmark_report.json",
    )
    args = parser.parse_args()

    cases_path = Path(args.cases) if args.cases else _ANNOTATED_CASES_PATH
    cases = load_annotated_cases(cases_path)
    if not cases:
        print(f"No annotated cases found at {cases_path}")
        return

    report = asyncio.run(run_benchmark_v2(cases, limit=args.limit))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    _print_table(report)
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    main()
