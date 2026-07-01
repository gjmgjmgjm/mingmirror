"""Lightweight benchmark: single bazi vs multi-system ensemble.

The benchmark is intentionally dependency-light. When run standalone it uses the
built-in analyzers (which fall back to mock output when no API key is set). For
unit tests, callers can inject deterministic mock analyzers to exercise the
metrics logic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from tools.destiny.contract import ChartInfo
from tools.destiny.ensemble import MultiDestinyAnalyzer

SampleCase = Dict[str, str]
Analyzer = Callable[[ChartInfo, str], Awaitable[Dict[str, Any]]]

DEFAULT_CASES: List[SampleCase] = [
    {"bazi": "甲子 丙寅 戊辰 庚午", "question": "事业如何？"},
    {"bazi": "乙丑 丁卯 己巳 辛未", "question": "财运如何？"},
    {"bazi": "丙寅 戊辰 庚午 壬申", "question": "婚姻如何？"},
    {"bazi": "丁卯 己巳 辛未 癸酉", "question": "健康如何？"},
    {"bazi": "戊辰 庚午 壬申 甲戌", "question": ""},
]

_DOMAINS = ("career", "wealth", "marriage", "health", "general")


def _count_non_empty_domains(result: Dict[str, Any]) -> int:
    domain_analysis = result.get("domain_analysis") or {}
    if not isinstance(domain_analysis, dict):
        return 0
    return sum(1 for v in domain_analysis.values() if v)


def _consensus_coverage(aligned: Dict[str, Any]) -> int:
    return sum(
        1
        for domain in _DOMAINS
        if aligned.get(domain, {}).get("consensus")
    )


def _consistency_with_bazi(
    bazi_result: Dict[str, Any],
    ensemble_result: Dict[str, Any],
) -> float:
    """Return the ratio of ensemble consensus that matches the single bazi text.

    Only domains present in the bazi result are counted.
    """
    bazi_domains = bazi_result.get("domain_analysis") or {}
    if not isinstance(bazi_domains, dict):
        return 0.0

    aligned = ensemble_result.get("aligned", {})
    matched = 0
    total = 0
    for domain, text in bazi_domains.items():
        if not text:
            continue
        total += 1
        consensus = aligned.get(domain, {}).get("consensus", "")
        if consensus == text:
            matched += 1
    if total == 0:
        return 0.0
    return matched / total


async def run_benchmark(
    cases: List[SampleCase],
    bazi_analyzer: Analyzer,
    ensemble_analyzer: MultiDestinyAnalyzer,
) -> Dict[str, Any]:
    """Run the benchmark and return coverage/consistency metrics."""
    bazi_coverages: List[int] = []
    ensemble_coverages: List[int] = []
    consistencies: List[float] = []

    for case in cases:
        chart = ChartInfo(bazi=case["bazi"], question=case.get("question", ""))
        bazi_result = await bazi_analyzer(chart, case.get("question", ""))
        ensemble_result = await ensemble_analyzer.analyze(chart, case.get("question", ""))

        bazi_coverages.append(_count_non_empty_domains(bazi_result))
        ensemble_coverages.append(_consensus_coverage(ensemble_result.get("aligned", {})))
        consistencies.append(_consistency_with_bazi(bazi_result, ensemble_result))

    count = len(cases)
    return {
        "cases": count,
        "bazi_avg_coverage": sum(bazi_coverages) / count if count else 0.0,
        "ensemble_avg_coverage": sum(ensemble_coverages) / count if count else 0.0,
        "consistency_with_bazi": sum(consistencies) / count if count else 0.0,
        "per_case": [
            {
                "bazi": cases[i]["bazi"],
                "bazi_coverage": bazi_coverages[i],
                "ensemble_coverage": ensemble_coverages[i],
                "consistency": consistencies[i],
            }
            for i in range(count)
        ],
    }


def _build_default_analyzers() -> Tuple[Analyzer, MultiDestinyAnalyzer]:
    from tools.bazi_ai.engine import analyze_bazi
    from tools.qizheng.engine import QiZhengAnalyzer

    async def bazi_analyzer(chart: ChartInfo, question: str) -> Dict[str, Any]:
        return await analyze_bazi(chart.bazi, question=question)

    qz = QiZhengAnalyzer()

    async def qizheng_analyzer(chart: ChartInfo, question: str) -> Dict[str, Any]:
        return await qz.analyze({"bazi": chart.bazi}, question=question)

    ensemble = MultiDestinyAnalyzer(
        systems=["bazi", "qizheng"],
        callables={
            "bazi": bazi_analyzer,
            "qizheng": qizheng_analyzer,
        },
    )
    return bazi_analyzer, ensemble


def main() -> None:
    parser = argparse.ArgumentParser(description="单八字 vs 多系统 ensemble benchmark")
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="JSON file with list of {bazi, question} cases",
    )
    args = parser.parse_args()

    cases = DEFAULT_CASES
    if args.cases:
        with open(args.cases, "r", encoding="utf-8") as handle:
            cases = json.load(handle)

    bazi_analyzer, ensemble = _build_default_analyzers()
    result = asyncio.run(run_benchmark(cases, bazi_analyzer, ensemble))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
