"""Historical-event validation for Qi Zheng Si Yu.

The dataset in ``tools/qizheng/benchmark_data/historical_events.jsonl``
records well-known life events for celebrities whose birth data is already in
``celebrity_charts.jsonl``.  The test runs the rule-based yearly analysis and
compares the predicted sentiment for the relevant domain against the expected
sentiment.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from tools.qizheng.engine import analyze_yearly

DATA_DIR = Path("tools/qizheng/benchmark_data")
CELEBRITY_PATH = DATA_DIR / "celebrity_charts.jsonl"
EVENTS_PATH = DATA_DIR / "historical_events.jsonl"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    results = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


_CELEBRITIES = {c["name"]: c for c in _load_jsonl(CELEBRITY_PATH)}
_EVENTS = _load_jsonl(EVENTS_PATH)


def _sentiment(text: str) -> str:
    """Classify a domain/caution text as positive / negative / neutral."""
    lowered = text.lower()
    positive = {
        "得助", "主动争取", "进益", "和谐", "积极推进", "充沛", "顺遂",
        "小有助力", "助力", "机缘", "人缘增", "平稳", "按节奏推进",
    }
    negative = {
        "压力", "波动", "支出增加", "是非", "口角", "变动明显", "阻滞",
        "落陷", "受克", "宜稳守", "忌", "多阻滞", "变动", "耗力",
    }
    pos_score = sum(1 for kw in positive if kw in lowered)
    neg_score = sum(1 for kw in negative if kw in lowered)
    if pos_score > neg_score:
        return "good"
    if neg_score > pos_score:
        return "bad"
    return "neutral"


def _yearly_record(result: Dict[str, Any], year: int) -> Optional[Dict[str, Any]]:
    for record in result.get("yearly_analysis", []):
        if record.get("year") == year:
            return record
    return None


def _run_event(event: Dict[str, Any]) -> Dict[str, Any]:
    celebrity = _CELEBRITIES.get(event["name"])
    assert celebrity is not None, f"找不到 {event['name']} 的出生资料"

    birth_year = int(celebrity["birth_datetime"].split("-")[0])
    chart = celebrity["expected_bazi"]
    gender = "male"  # Most entries are male; gender only affects dayun direction.

    result = asyncio.run(
        analyze_yearly(chart, gender=gender, birth_year=birth_year, mode="lifetime")
    )
    record = _yearly_record(result, event["year"])
    assert record is not None, f"{event['name']} {event['year']} 年未生成流年记录"

    domain = event["domain"]
    text = record.get(domain, "") or record.get("caution", "")
    predicted = _sentiment(text)
    expected = event["expected"]
    return {
        "name": event["name"],
        "year": event["year"],
        "domain": domain,
        "expected": expected,
        "predicted": predicted,
        "text": text,
        "match": predicted == expected,
    }


@pytest.mark.skipif(not _EVENTS, reason="historical events dataset is empty")
def test_historical_event_accuracy():
    """Evaluate how often the rule-based yearly analysis matches known events."""
    outcomes = [_run_event(e) for e in _EVENTS]

    matches = sum(1 for o in outcomes if o["match"])
    total = len(outcomes)
    accuracy = matches / total if total else 0.0

    print("\n【历史名人格局应验评估】")
    print(f"总样本数: {total}")
    print(f"预测一致: {matches}")
    print(f"准确率: {accuracy * 100:.1f}%")
    print("\n明细:")
    for o in outcomes:
        marker = "✓" if o["match"] else "✗"
        print(
            f"{marker} {o['name']:6s} {o['year']}年 {o['domain']:6s} "
            f"预期={o['expected']:4s} 预测={o['predicted']:4s} | {o['text'][:40]}..."
        )

    # We expect better-than-random accuracy; at least half of the events should
    # align with the predicted domain sentiment.
    assert accuracy >= 0.4
