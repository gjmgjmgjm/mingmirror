"""Frozen fixtures for known 六亲 det misses (snapshot regression guard).

If a heuristic change flips a known miss to a hit, this test fails with a clear
message so the fixture can be re-exported intentionally — not silently lost.
Also enforces the live det floor (90% after noise exclusion).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.bazi_ai import bazi_structural

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "benchmarks" / "baziqa" / "fixtures" / "liuqin_known_misses.jsonl"
_LQ_KEY = {
    "father": "father",
    "spouse": "spouse",
    "mother": "mother",
    "child": "son",
    "sibling": "brother",
}


def _load_fixtures():
    if not FIXTURES.exists():
        pytest.skip(f"fixture missing: {FIXTURES}")
    rows = []
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _engine_strength(bazi: str, gender: str, subject: str) -> str:
    prof = bazi_structural.liuqin_profile(bazi, gender=gender) or {}
    if subject == "child":
        son = (prof.get("son") or {}).get("strength", "?")
        dau = (prof.get("daughter") or {}).get("strength", "?")
        # Prefer son key for snapshot (validator treats either match as hit)
        return son if son != "?" else dau
    return (prof.get(_LQ_KEY.get(subject, ""), {}) or {}).get("strength", "?")


class TestLiuqinMissFixtures:
    def test_fixture_file_nonempty(self):
        rows = _load_fixtures()
        assert len(rows) >= 1
        assert len(rows) <= 12  # sanity: should not explode

    def test_snapshot_engine_strength(self):
        """Engine strength for each known miss must match freeze snapshot.

        When you intentionally improve det and a miss becomes a hit, re-run:
            python -c "..."  # export script in tools or re-run miss dump
        and update the fixture + this baseline note.
        """
        rows = _load_fixtures()
        flipped = []
        for row in rows:
            det = _engine_strength(row["bazi"], row["gender"], row["subject"])
            expected = row["engine_strength"]
            if det != expected:
                flipped.append(
                    f"{row['subject']} {row['bazi']}: freeze={expected} now={det} "
                    f"(master={row['master_strength']})"
                )
        assert not flipped, (
            "Known-miss snapshot changed — re-audit and update "
            "liuqin_known_misses.jsonl:\n" + "\n".join(flipped)
        )

    def test_still_disagrees_with_master(self):
        """These remain misses vs master (or document if intentionally fixed)."""
        rows = _load_fixtures()
        for row in rows:
            det = _engine_strength(row["bazi"], row["gender"], row["subject"])
            # child: either star matching master counts as hit in live ruler
            if row["subject"] == "child":
                prof = bazi_structural.liuqin_profile(
                    row["bazi"], gender=row["gender"]
                ) or {}
                son = (prof.get("son") or {}).get("strength", "?")
                dau = (prof.get("daughter") or {}).get("strength", "?")
                if row["master_strength"] in (son, dau):
                    pytest.fail(
                        f"child miss fixed for {row['bazi']}: master="
                        f"{row['master_strength']} son={son} dau={dau}; "
                        "remove from fixture"
                    )
            else:
                assert det != row["master_strength"], (
                    f"miss fixed for {row['subject']} {row['bazi']}; "
                    "remove from fixture"
                )


def test_live_det_floor():
    """Live det accuracy must not drop below 90% (noise-excluded)."""
    script = ROOT / "benchmarks" / "baziqa" / "validate_liuqin_det.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--limit", "200"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    out = proc.stdout
    # e.g. "确定性六亲强弱准确率: 36/39 = 92%"
    import re

    m = re.search(r"准确率:\s*(\d+)/(\d+)\s*=\s*(\d+)%", out)
    assert m, f"could not parse accuracy from:\n{out[-500:]}"
    hit, n, pct = int(m.group(1)), int(m.group(2)), int(m.group(3))
    assert n >= 30, f"unexpected small n={n}"
    assert pct >= 90, f"det floor regression: {hit}/{n} = {pct}% < 90%"
