#!/usr/bin/env python3
"""
evaluator.py — evaluate the consistency and quality of AI bazi analysis.

Proxy metrics:
    1. Consistency: run the same bazi N times and check whether core fields are stable.
    2. Format compliance: every output must contain required structured fields.
    3. Case overlap: compare model output against retrieved master cases.
    4. Leave-one-out benchmark: predict each known case's conclusions and measure
       structural overlap.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

from tools.bazi_ai.bazi_validator import normalize_bazi
from tools.bazi_ai.engine import analyze_bazi, retrieve_similar_cases

REQUIRED_FIELDS = [
    "basic_info",
    "reasoning",
    "domain_analysis",
    "summary",
    "confidence",
    "caveats",
]

REQUIRED_BASIC_FIELDS = ["bazi", "day_master", "month_branch", "pattern", "useful_gods", "taboo_gods"]
REQUIRED_DOMAIN_FIELDS = ["career", "wealth", "marriage", "health"]


def check_format(result: Dict) -> List[str]:
    """Return missing required top-level or nested fields."""
    missing = [f for f in REQUIRED_FIELDS if f not in result]
    if "basic_info" in result:
        basic = result["basic_info"]
        missing.extend(f"basic_info.{f}" for f in REQUIRED_BASIC_FIELDS if f not in basic)
    if "domain_analysis" in result:
        domains = result["domain_analysis"]
        missing.extend(f"domain_analysis.{f}" for f in REQUIRED_DOMAIN_FIELDS if f not in domains)
    return missing


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
    return "|".join(str(p) for p in parts)


def case_overlap(result: Dict, similar_cases: List[Dict]) -> float:
    """Compute a simple overlap score between model output and retrieved cases.

    Returns a float in [0, 1] based on keyword intersection in conclusions and
    domain snippets.
    """
    if not similar_cases:
        return 0.0

    result_text = " ".join([
        " ".join(result.get("summary", [])),
        " ".join(result.get("reasoning", "").split()),
    ])
    for text in result.get("domain_analysis", {}).values():
        result_text += " " + text

    result_tokens = set(result_text.split())
    if not result_tokens:
        return 0.0

    overlaps = []
    for case in similar_cases:
        case_text = case.get("analysis_corrected", "")
        case_text += " " + " ".join(case.get("conclusions", []))
        for snippets in case.get("domains", {}).values():
            case_text += " " + " ".join(snippets)
        case_tokens = set(case_text.split())
        if not case_tokens:
            overlaps.append(0.0)
            continue
        intersection = result_tokens & case_tokens
        union = result_tokens | case_tokens
        overlaps.append(len(intersection) / len(union) if union else 0.0)
    return sum(overlaps) / len(overlaps)


async def evaluate_consistency(
    bazi: str,
    *,
    question: str = "",
    runs: int = 3,
    cases_path: Path = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Path = Path("./bazi_knowledge/knowledge_base.md"),
    embedding_cache_path: Optional[Path] = None,
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
            embedding_cache_path=embedding_cache_path,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        results.append(result)

    signatures = [core_signature(r) for r in results]
    unique = set(signatures)

    format_issues = [check_format(r) for r in results]
    overlaps = []
    for r in results:
        similar = retrieve_similar_cases(bazi, question, cases_path, top_k=3)
        overlaps.append(case_overlap(r, similar))

    return {
        "bazi": bazi,
        "runs": runs,
        "unique_signatures": len(unique),
        "consistent": len(unique) == 1,
        "signatures": signatures,
        "format_issues": format_issues,
        "case_overlaps": overlaps,
        "avg_case_overlap": sum(overlaps) / len(overlaps) if overlaps else 0.0,
        "raw_results": results,
    }


async def evaluate_leave_one_out(
    cases_path: Path = Path("./bazi_knowledge/cases.jsonl"),
    knowledge_base_path: Path = Path("./bazi_knowledge/knowledge_base.md"),
    embedding_cache_path: Optional[Path] = None,
    api_key: str = None,
    base_url: str = None,
    model: str = None,
) -> Dict:
    """Benchmark the engine by predicting each case while excluding it from RAG.

    This measures how well the model can reconstruct known case conclusions from
    similar (but not identical) examples and the rule primer.
    """
    all_cases = []
    if cases_path.exists():
        with cases_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        all_cases.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    predictions = []
    for i, target in enumerate(all_cases):
        bazi = target.get("bazi", "")
        if normalize_bazi(bazi) is None:
            continue

        # Build a temporary cases file that excludes the target case.
        others = [c for j, c in enumerate(all_cases) if j != i and normalize_bazi(c.get("bazi", ""))]
        # Filter out duplicate bazi so the target isn't reconstructed verbatim.
        seen = set()
        filtered = []
        for c in others:
            key = c.get("bazi")
            if key and key not in seen:
                seen.add(key)
                filtered.append(c)

        result = await analyze_bazi(
            bazi,
            question="",
            cases_path=None,
            knowledge_base_path=knowledge_base_path,
            embedding_cache_path=embedding_cache_path,
            api_key=api_key,
            base_url=base_url,
            model=model,
            top_k=3,
        )

        target_conclusions = " ".join(target.get("conclusions", []))
        target_domains = target.get("domains", {})
        target_text = target_conclusions + " " + " ".join(
            " ".join(snippets) for snippets in target_domains.values()
        )
        pred_text = " ".join(result.get("summary", [])) + " " + " ".join(
            result.get("domain_analysis", {}).values()
        )

        target_tokens = set(target_text.split())
        pred_tokens = set(pred_text.split())
        overlap = 0.0
        if target_tokens and pred_tokens:
            overlap = len(target_tokens & pred_tokens) / len(target_tokens)

        predictions.append({
            "bazi": bazi,
            "format_issues": check_format(result),
            "case_overlap": overlap,
            "prediction": result,
        })

    if not predictions:
        return {"total": 0, "avg_overlap": 0.0, "format_clean_rate": 0.0, "predictions": []}

    return {
        "total": len(predictions),
        "avg_overlap": sum(p["case_overlap"] for p in predictions) / len(predictions),
        "format_clean_rate": sum(1 for p in predictions if not p["format_issues"]) / len(predictions),
        "predictions": predictions,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="评测 AI 八字分析的一致性和格式合规性")
    parser.add_argument("bazi", nargs="?", help="八字（为空则运行 leave-one-out benchmark）")
    parser.add_argument("-q", "--question", default="", help="问题")
    parser.add_argument("-r", "--runs", type=int, default=3, help="重复运行次数")
    parser.add_argument("-c", "--cases", default="./bazi_knowledge/cases.jsonl")
    parser.add_argument("-k", "--knowledge", default="./bazi_knowledge/rule_primer.md")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--benchmark", action="store_true", help="运行 leave-one-out benchmark")
    parser.add_argument("--raw", action="store_true", help="输出完整 JSON")
    args = parser.parse_args()

    if args.benchmark or not args.bazi:
        report = asyncio.run(
            evaluate_leave_one_out(
                cases_path=Path(args.cases),
                knowledge_base_path=Path(args.knowledge),
                api_key=args.api_key,
            )
        )
        print(f"Benchmark cases: {report['total']}")
        print(f"平均结论重叠率: {report['avg_overlap']:.2%}")
        print(f"格式完整率: {report['format_clean_rate']:.2%}")
        if args.raw:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return

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

    print(f"八字：{report['bazi']}")
    print(f"运行次数：{report['runs']}")
    print(f"唯一签名数：{report['unique_signatures']}")
    print(f"一致性：{'通过' if report['consistent'] else '不通过'}")
    print(f"平均案例重叠率：{report['avg_case_overlap']:.2%}")
    if not report["consistent"]:
        print("签名差异：")
        for i, sig in enumerate(report["signatures"], 1):
            print(f"  第{i}次：{sig[:120]}...")
    for i, issues in enumerate(report["format_issues"], 1):
        if issues:
            print(f"  第{i}次缺少字段：{issues}")


if __name__ == "__main__":
    main()
