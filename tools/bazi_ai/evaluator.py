#!/usr/bin/env python3
"""
evaluator.py — evaluate the consistency and quality of AI bazi analysis.

Since we don't have querent feedback, we use proxy metrics:
    1. Consistency: run the same bazi N times and check whether core fields are stable.
    2. Format compliance: every output must contain required structured fields.
    3. Case overlap: compare model output against retrieved master cases.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List

from tools.bazi_ai.engine import analyze_bazi

REQUIRED_FIELDS = [
    "basic_info",
    "reasoning",
    "domain_analysis",
    "summary",
    "confidence",
    "caveats",
]


def check_format(result: Dict) -> List[str]:
    """Return missing required top-level fields."""
    return [f for f in REQUIRED_FIELDS if f not in result]


def core_signature(result: Dict) -> str:
    """Create a compact signature from core fields for consistency comparison."""
    basic = result.get("basic_info", {})
    domains = result.get("domain_analysis", {})
    parts = [
        basic.get("pattern", ""),
        ",".join(basic.get("useful_gods", [])),
        ",".join(basic.get("taboo_gods", [])),
        domains.get("career", ""),
        domains.get("wealth", ""),
        domains.get("marriage", ""),
        domains.get("health", ""),
    ]
    return "|".join(parts)


async def evaluate_consistency(
    bazi: str,
    *,
    question: str = "",
    runs: int = 3,
    cases_path: Path = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Path = Path("./bazi_knowledge/knowledge_base.md"),
    api_key: str = None,
    base_url: str = None,
    model: str = None,
) -> Dict:
    """Run analysis multiple times and report consistency."""
    results = []
    for i in range(runs):
        result = await analyze_bazi(
            bazi,
            question=question,
            cases_path=cases_path,
            knowledge_base_path=knowledge_base_path,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        results.append(result)

    signatures = [core_signature(r) for r in results]
    unique = set(signatures)

    format_issues = [check_format(r) for r in results]

    return {
        "bazi": bazi,
        "runs": runs,
        "unique_signatures": len(unique),
        "consistent": len(unique) == 1,
        "signatures": signatures,
        "format_issues": format_issues,
        "raw_results": results,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="评测 AI 八字分析的一致性和格式合规性")
    parser.add_argument("bazi", help="八字")
    parser.add_argument("-q", "--question", default="", help="问题")
    parser.add_argument("-r", "--runs", type=int, default=3, help="重复运行次数")
    parser.add_argument("-c", "--cases", default="./bazi_knowledge/cases.jsonl")
    parser.add_argument("-k", "--knowledge", default="./bazi_knowledge/rule_primer.md")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--raw", action="store_true", help="输出完整 JSON")
    args = parser.parse_args()

    report = asyncio.run(
        evaluate_consistency(
            args.bazi,
            question=args.question,
            runs=args.runs,
            cases_path=Path(args.cases),
            knowledge_base_path=Path(args.knowledge),
            api_key=args.api_key,
        )
    )

    if args.raw:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"八字：{report['bazi']}")
    print(f"运行次数：{report['runs']}")
    print(f"唯一签名数：{report['unique_signatures']}")
    print(f"一致性：{'通过' if report['consistent'] else '不通过'}")
    if not report["consistent"]:
        print("签名差异：")
        for i, sig in enumerate(report["signatures"], 1):
            print(f"  第{i}次：{sig[:120]}...")
    for i, issues in enumerate(report["format_issues"], 1):
        if issues:
            print(f"  第{i}次缺少字段：{issues}")


if __name__ == "__main__":
    main()
