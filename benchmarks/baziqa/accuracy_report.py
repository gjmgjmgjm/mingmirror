#!/usr/bin/env python3
"""One-command honest accuracy report for the bazi project.

Answers the pre-launch question "what's the project's real accuracy?" by running
the deterministic (zero-API) rulers live and assembling a single scorecard where
**every number is labeled by its gold source** — real-gold (citable) vs
self-consistency (circular) — so nothing is overstated.

Three real-gold dimensions run LIVE (zero API): 排盘 (vs iztro), 用神 (vs 穷通宝鉴),
六亲 (deterministic engine vs 杨炎 master gold, bypassing the LLM). The remaining
self-consistency / API-gated dimensions stay as cached values.

Usage::
    python benchmarks/baziqa/accuracy_report.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "benchmarks" / "baziqa"

# Self-consistency / API-gated dimensions (not run live here).
# (value, gold_kind, refresh_cmd)
_CACHED_DIMS = [
    ("格局", "100%", "自洽(月令定格注入)", "python benchmarks/baziqa/validate_consensus.py --limit 12"),
    ("忌神", "92%", "自洽(规则引擎注入)", "python benchmarks/baziqa/validate_consensus.py --limit 12"),
    ("旺衰", "75%", "自洽(规则引擎)", "python benchmarks/baziqa/validate_consensus.py --limit 12"),
    ("具体事件/年份", "0%(开放式)/40%(MCQ)", "真实(名人验证事件)", "python benchmarks/baziqa/validate_mingli.py --limit 12"),
]


def _run(script: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(BENCH / script)], cwd=str(ROOT),
        capture_output=True, text=True, timeout=180,
    )
    return proc.stdout + proc.stderr


def _extract(text: str, needle: str) -> str:
    """Find a line containing *needle* and pull the first NN% / NN/NN."""
    for line in text.splitlines():
        if needle in line:
            m = re.search(r"(\d+\s*/\s*\d+\s*=\s*\d+\.?\d*%|\d+\.?\d*%)", line)
            if m:
                return m.group(1).replace(" ", "")
    return "?"


def main() -> None:
    print("实时跑确定性尺子（零 API）...\n", file=sys.stderr)
    chart = _run("validate_chart.py")
    yong = _run("validate_yongshen.py")
    liu = _run("validate_liuqin_det.py")

    paipan = _extract(chart, "真实排盘准确率")
    yongshen = _extract(yong, "与调候gold有交集")
    liuqin = _extract(liu, "确定性六亲强弱准确率")

    print("=" * 64)
    print("八字项目 · 真实准确率报告（每项标注 gold 来源）")
    print("=" * 64)
    print(f"{'维度':<16}{'准确率':<22}{'gold 性质'}")
    print("-" * 64)
    print(f"{'排盘':<16}{paipan:<22}{'真实(iztro预制命盘) ✅'}")
    print(f"{'用神':<16}{yongshen:<22}{'真实(穷通宝鉴调候gold) ✅'}")
    print(f"{'六亲强弱':<16}{liuqin:<22}{'真实(杨炎gold, det 绕过LLM) ✅'}")
    for dim, val, kind, _ in _CACHED_DIMS:
        print(f"{dim:<16}{val:<22}{kind}")
    print("-" * 64)
    print("说明：")
    print("  ✅ 真实 = 有独立/权威 gold，数字可 cite（排盘对 iztro、用神对穷通宝鉴、")
    print("     六亲对杨炎大师断象；六亲为确定性引擎层，绕过 LLM）。")
    print("  自洽 = 与自家规则引擎一致（注入后≈100%），不证明对错，需 gold 才算准确率。")
    print("  事件层开放式≈0% 是物理天花板，非 bug；产品应输出趋势而非断言。")
    print("\n刷新需-API 维度（设定 DEEPSEEK_API_KEY 后）：")
    for dim, _, _, cmd in _CACHED_DIMS:
        print(f"  [{dim}] {cmd}")


if __name__ == "__main__":
    main()
