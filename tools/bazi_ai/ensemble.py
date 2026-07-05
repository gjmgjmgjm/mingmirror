#!/usr/bin/env python3
"""
ensemble.py — run the bazi engine multiple times and aggregate the results.

This improves accuracy by reducing single-sample LLM variance. The aggregated
output keeps the most frequent pattern, useful gods, and domain conclusions.
"""

import asyncio
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from tools.bazi_ai.engine import analyze_bazi


def _majority(items: List[str]) -> str:
    """Return the most common non-empty item, or empty string."""
    filtered = [i for i in items if i]
    if not filtered:
        return ""
    return Counter(filtered).most_common(1)[0][0]


def _majority_list(lists: List[List[str]]) -> List[str]:
    """Return items that appear in more than half of the lists."""
    counts: Dict[str, int] = {}
    for lst in lists:
        for item in lst:
            counts[item] = counts.get(item, 0) + 1
    threshold = len(lists) / 2
    return [item for item, count in counts.items() if count > threshold]


def _aggregate(results: List[Dict]) -> Dict:
    """Aggregate multiple analysis results into a single consensus output."""
    if not results:
        return {}
    if len(results) == 1:
        return results[0]

    base = results[0]
    basics = [r.get("basic_info", {}) for r in results]
    domains_list = [r.get("domain_analysis", {}) for r in results]
    confidences = [r.get("confidence", "") for r in results]
    all_caveats = []
    all_rule_warnings = []
    for r in results:
        all_caveats.extend(r.get("caveats", []))
        all_rule_warnings.extend(r.get("rule_warnings", []))

    aggregated_domains = {}
    for key in ["career", "wealth", "marriage", "health"]:
        texts = [d.get(key, "") for d in domains_list]
        aggregated_domains[key] = _majority(texts)

    # Confidence: downgrade to the lowest if any run is low.
    final_confidence = "high"
    if any(c == "low" for c in confidences):
        final_confidence = "low"
    elif any(c == "medium" for c in confidences):
        final_confidence = "medium"

    return {
        "basic_info": {
            "bazi": base.get("basic_info", {}).get("bazi", ""),
            "day_master": _majority([b.get("day_master", "") for b in basics]),
            "month_branch": _majority([b.get("month_branch", "") for b in basics]),
            "pattern": _majority([b.get("pattern", "") for b in basics]),
            "useful_gods": _majority_list([b.get("useful_gods", []) for b in basics]),
            "taboo_gods": _majority_list([b.get("taboo_gods", []) for b in basics]),
        },
        "reasoning": base.get("reasoning", ""),
        "domain_analysis": aggregated_domains,
        "summary": _majority_list([r.get("summary", []) for r in results]),
        "confidence": final_confidence,
        "caveats": list(dict.fromkeys(all_caveats)),
        "rule_warnings": list(dict.fromkeys(all_rule_warnings)),
        "_ensemble_runs": len(results),
    }


async def analyze_bazi_ensemble(
    bazi: str,
    *,
    question: str = "",
    runs: int = 3,
    cases_path: Optional[Path] = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Path = Path("./bazi_knowledge/knowledge_base.md"),
    extra_cases_paths: Optional[List[Path]] = None,
    extra_knowledge_base_paths: Optional[List[Path]] = None,
    embedding_cache_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    top_k: int = 3,
) -> Dict:
    """Run analyze_bazi *runs* times and return an aggregated consensus result."""
    results = await asyncio.gather(
        *[
            analyze_bazi(
                bazi,
                question=question,
                cases_path=cases_path,
                knowledge_base_path=knowledge_base_path,
                extra_cases_paths=extra_cases_paths,
                extra_knowledge_base_paths=extra_knowledge_base_paths,
                embedding_cache_path=embedding_cache_path,
                api_key=api_key,
                base_url=base_url,
                model=model,
                top_k=top_k,
            )
            for _ in range(runs)
        ]
    )
    return _aggregate(results)


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="八字多轮一致性分析")
    parser.add_argument("bazi", help="八字")
    parser.add_argument("-q", "--question", default="")
    parser.add_argument("-r", "--runs", type=int, default=3)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    result = asyncio.run(
        analyze_bazi_ensemble(
            args.bazi,
            question=args.question,
            runs=args.runs,
            api_key=args.api_key,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
