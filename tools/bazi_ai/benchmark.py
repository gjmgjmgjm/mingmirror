#!/usr/bin/env python3
"""
benchmark.py — CLI wrapper around evaluator.evaluate_leave_one_out().

Usage:
    python -m tools.bazi_ai.benchmark
    python -m tools.bazi_ai.benchmark --raw --output benchmark.json
"""

import argparse
import asyncio
import json
from pathlib import Path

from tools.bazi_ai.evaluator import evaluate_leave_one_out


def main():
    parser = argparse.ArgumentParser(description="八字 AI leave-one-out benchmark")
    parser.add_argument("-c", "--cases", default="./bazi_knowledge/cases.jsonl")
    parser.add_argument("-k", "--knowledge", default="./bazi_knowledge/rule_primer.md")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--raw", action="store_true", help="输出每条预测详情")
    parser.add_argument("-o", "--output", help="将完整报告写入 JSON 文件")
    args = parser.parse_args()

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

    if args.raw or args.output:
        raw = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(raw, encoding="utf-8")
            print(f"报告已保存：{args.output}")
        if args.raw:
            print(raw)


if __name__ == "__main__":
    main()
