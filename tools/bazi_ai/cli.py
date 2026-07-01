#!/usr/bin/env python3
"""
cli.py — command-line interface for the AI bazi analyzer.
"""

import argparse
import asyncio
import json
from pathlib import Path

from tools.bazi_ai.engine import analyze_bazi


def main():
    parser = argparse.ArgumentParser(description="AI 八字分析器（DeepSeek + RAG）")
    parser.add_argument("bazi", help="八字，例如：甲子 丙寅 戊辰 庚午")
    parser.add_argument("-q", "--question", default="", help="命主具体问题")
    parser.add_argument("-c", "--cases", default="./bazi_knowledge/cases.jsonl", help="案例库路径")
    parser.add_argument("-k", "--knowledge", default="./bazi_knowledge/rule_primer.md", help="基础知识库路径")
    parser.add_argument("--top-k", type=int, default=3, help="检索相似案例数量")
    parser.add_argument("--api-key", default=None, help="DeepSeek API Key（默认读取 DEEPSEEK_API_KEY 环境变量）")
    parser.add_argument("--base-url", default=None, help="DeepSeek API Base URL")
    parser.add_argument("--model", default=None, help="DeepSeek 模型名称")
    parser.add_argument("--raw", action="store_true", help="输出原始 JSON")
    args = parser.parse_args()

    result = asyncio.run(
        analyze_bazi(
            args.bazi,
            question=args.question,
            cases_path=Path(args.cases),
            knowledge_base_path=Path(args.knowledge),
            top_k=args.top_k,
            api_key=args.api_key,
            base_url=args.base_url,
            model=args.model,
        )
    )

    if args.raw or result.get("_mock") or result.get("parse_error"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    basic = result.get("basic_info", {})
    domains = result.get("domain_analysis", {})

    print(f"八字：{basic.get('bazi')}")
    print(f"日主：{basic.get('day_master')}，月令：{basic.get('month_branch')}，格局：{basic.get('pattern')}")
    print(f"用神：{', '.join(basic.get('useful_gods', []))}")
    print(f"忌神：{', '.join(basic.get('taboo_gods', []))}")
    print()
    print("推理过程：")
    print(result.get("reasoning", "（无）"))
    print()
    print("分领域分析：")
    for domain, text in domains.items():
        label = {"career": "事业", "wealth": "财运", "marriage": "婚姻/感情", "health": "健康"}.get(domain, domain)
        print(f"  [{label}] {text}")
    print()
    print("核心断语：")
    for item in result.get("summary", []):
        print(f"  - {item}")
    print()
    print(f"置信度：{result.get('confidence', 'unknown')}")
    if result.get("caveats"):
        print("注意：")
        for c in result["caveats"]:
            print(f"  - {c}")


if __name__ == "__main__":
    main()
