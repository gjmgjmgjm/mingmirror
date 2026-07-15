#!/usr/bin/env python3
"""A/B live eval: rule shortlist ON vs OFF on contest8 year questions.

Runs the same shortlist-eligible questions twice (shortlist on/off) against the
configured LLM and reports accuracy.  Uses leave-one-out RAG.

Usage::

    python benchmarks/baziqa/_eval_shortlist_ab.py --limit 12
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.bazi_ai.baziqa_eval import (  # noqa: E402
    evaluate_question,
    load_baziqa,
    person_to_bazi,
    _birth_date_time,
)
from tools.bazi_ai.rule_reasoner import rank_year_candidates  # noqa: E402


def _gender(person: dict) -> str:
    g = person.get("profile", {}).get("gender", "male")
    return "female" if g in ("女", "female", "f", "F") else "male"


def _load_api(config_path: Path):
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    b = cfg.get("bazi_ai", {})
    api_key = (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("DOUYIN_BAZI_AI_API_KEY")
        or b.get("api_key")
    )
    base_url = (
        os.environ.get("DEEPSEEK_BASE_URL")
        or os.environ.get("DOUYIN_BAZI_AI_BASE_URL")
        or b.get("base_url")
    )
    model = (
        os.environ.get("DEEPSEEK_MODEL")
        or os.environ.get("DOUYIN_BAZI_AI_MODEL")
        or b.get("model")
    )
    extra = [Path(p) for p in b.get("extra_cases_paths", []) if isinstance(p, str)]
    return api_key, base_url, model, extra


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--config", default="config.yml")
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument(
        "--output",
        default="benchmarks/baziqa/results/ab_shortlist.jsonl",
    )
    args = ap.parse_args()

    api_key, base_url, model, extra = _load_api(Path(args.config))
    if not api_key:
        print("No API key — abort", file=sys.stderr)
        sys.exit(1)
    print(f"model={model} base={base_url}", file=sys.stderr)

    contest, _ = load_baziqa(Path("benchmarks/baziqa/data"))
    items: List[Dict[str, Any]] = []
    for person in contest:
        bazi = person_to_bazi(person)
        if not bazi:
            continue
        g = _gender(person)
        bd, bt = _birth_date_time(person)
        for q in person.get("questions", []):
            opts = q.get("options", [])
            if not any(re.search(r"19\d{2}|20\d{2}", o) for o in opts):
                continue
            ranked = rank_year_candidates(
                bazi,
                q.get("question", ""),
                opts,
                gender=g,
                birth_date=bd,
                birth_time=bt,
                top_k=2,
                for_shortlist=True,
            )
            if not ranked:
                continue
            items.append(
                {
                    "person": person,
                    "q": q,
                    "bazi": bazi,
                    "gender": g,
                    "bd": bd,
                    "bt": bt,
                    "shortlist": [c.option for c in ranked],
                }
            )
            if len(items) >= args.limit:
                break
        if len(items) >= args.limit:
            break

    print(f"selected {len(items)} shortlist-eligible year questions", file=sys.stderr)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    for arm in ("shortlist_on", "shortlist_off"):
        correct = 0
        for i, it in enumerate(items, 1):
            use_sl = arm == "shortlist_on"
            res = await evaluate_question(
                it["bazi"],
                it["q"],
                mode="enhanced",
                gender=it["gender"],
                birth_date=it["bd"],
                birth_time=it["bt"],
                api_key=api_key,
                base_url=base_url,
                model=model,
                timeout_seconds=args.timeout,
                extra_cases_paths=extra or None,
                leave_one_out=True,
                use_rule_reasoner=True,
                rule_min_confidence="high",
                use_rule_shortlist=use_sl,
                rule_shortlist_k=2,
            )
            res["arm"] = arm
            res["shortlist"] = it["shortlist"]
            results.append(res)
            if res.get("correct"):
                correct += 1
            gold_in = (res.get("answer") or "")[:1] in it["shortlist"]
            print(
                f"[{arm} {i}/{len(items)}] {res.get('question_id')} "
                f"pred={res.get('predicted')} gold={res.get('answer')} "
                f"ok={res.get('correct')} gold_in_sl={gold_in} sl={it['shortlist']}",
                file=sys.stderr,
                flush=True,
            )
        acc = correct / len(items) if items else 0
        print(f"=== {arm}: {correct}/{len(items)} = {acc:.1%}", file=sys.stderr)

    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    summary = {}
    for arm in ("shortlist_on", "shortlist_off"):
        rows = [r for r in results if r.get("arm") == arm]
        ok = sum(1 for r in rows if r.get("correct"))
        summary[arm] = {
            "n": len(rows),
            "correct": ok,
            "accuracy": round(ok / len(rows), 4) if rows else 0,
        }
    # Paired wins
    on = {r["question_id"]: r for r in results if r.get("arm") == "shortlist_on"}
    off = {r["question_id"]: r for r in results if r.get("arm") == "shortlist_off"}
    both = set(on) & set(off)
    on_only = sum(1 for qid in both if on[qid].get("correct") and not off[qid].get("correct"))
    off_only = sum(1 for qid in both if off[qid].get("correct") and not on[qid].get("correct"))
    summary["paired"] = {
        "shortlist_wins": on_only,
        "no_shortlist_wins": off_only,
        "ties": len(both) - on_only - off_only,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
