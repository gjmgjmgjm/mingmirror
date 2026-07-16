#!/usr/bin/env python3
"""一键生成可解释命盘报告 —— 演示命镜「可解释、可验证、不胡说」的护城河。

默认 **零 API、秒出**:直接展示确定性结构层(排盘 / 格局 / 用神忌神 / 六亲 /
刑冲合化),不依赖任何模型 key。这正是把项目最稀缺的资产(确定性、可验证)
翻译成用户能感知的专业感与信任。

接入 `DEEPSEEK_API_KEY`(或 `config.yml` 的 `bazi_ai` 段)后,`--full` 可在
结构层之上叠加 AI 解读章节(取象 / 四领域 / 性格 / 关键节点)。

Examples
--------
零 API,秒出结构层报告::

    python -m tools.bazi_ai.demo_report --bazi "乙卯 戊寅 庚子 丙子" --gender male

完整版(叠加 AI 解读)::

    python -m tools.bazi_ai.demo_report --bazi "乙卯 戊寅 庚子 丙子" --full

排大运 + 存文件::

    python -m tools.bazi_ai.demo_report --bazi "..." --birth-date 1975-03-08 -o report.md
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from tools.bazi_ai.report_template import render_report

_DEFAULT_BAZI = "乙卯 戊寅 庚子 丙子"  # 杨炎案例库真实命主,庚金日主
_DEFAULT_GENDER = "male"


def _load_bazi_config() -> Dict[str, Any]:
    """从 config.yml 读 bazi_ai 配置(api_key / base_url / model),不存在则空。"""
    for cand in (Path("config.yml"), Path("config.yaml")):
        if cand.exists():
            try:
                import yaml  # type: ignore

                with open(cand, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return data.get("bazi_ai") or {}
            except Exception:
                return {}
    return {}


async def _run_full(bazi: str, gender: str, birth_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """调 analyze_bazi 叠加 AI 解读。无 key 时 engine 走 mock 模式。"""
    from tools.bazi_ai.engine import analyze_bazi

    cfg = _load_bazi_config()
    api_key = os.environ.get("DEEPSEEK_API_KEY") or cfg.get("api_key")
    return await analyze_bazi(
        bazi,
        gender=gender,
        birth_date=(birth_info or {}).get("birth_date", ""),
        birth_time=(birth_info or {}).get("birth_time", "00:00"),
        calendar_type=(birth_info or {}).get("calendar_type", "solar"),
        api_key=api_key,
        base_url=cfg.get("base_url"),
        model=cfg.get("model"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="一键生成可解释命盘报告(命镜护城河演示)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bazi", default=_DEFAULT_BAZI,
                        help='四柱八字,空格分隔,如 "乙卯 戊寅 庚子 丙子"(默认:杨炎案例)')
    parser.add_argument("--gender", default=_DEFAULT_GENDER, help="性别 male/female/男/女(默认 male)")
    parser.add_argument("--birth-date", default=None, help="出生日期 YYYY-MM-DD,用于确定性排大运")
    parser.add_argument("--birth-time", default=None, help="出生时间 HH:MM")
    parser.add_argument("--calendar", default="solar", choices=["solar", "lunar"], help="历法(默认 solar)")
    parser.add_argument("--full", action="store_true",
                        help="叠加 AI 解读(需 DEEPSEEK_API_KEY 或 config.yml;失败优雅降级)")
    parser.add_argument("--output", "-o", default=None, help="输出到文件,默认 stdout")
    args = parser.parse_args()

    birth_info: Optional[Dict[str, Any]] = None
    if args.birth_date:
        birth_info = {
            "birth_date": args.birth_date,
            "birth_time": args.birth_time or "00:00",
            "calendar_type": args.calendar,
        }

    result: Optional[Dict[str, Any]] = None
    if args.full:
        try:
            result = asyncio.run(_run_full(args.bazi, args.gender, birth_info))
        except Exception as exc:  # noqa: BLE001 —— demo 必须总能出报告
            print(f"[warn] AI 解读失败({exc}),降级为纯结构层报告。\n", file=sys.stderr)
            result = None

    md = render_report(args.bazi, gender=args.gender, result=result, birth_info=birth_info)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"报告已写入 {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
