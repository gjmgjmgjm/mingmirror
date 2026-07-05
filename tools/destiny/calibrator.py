"""Event calibration engine for MingMirror.

Users record life events (e.g. marriage, job change, illness). The calibrator
compares each event against predictions made by configured destiny systems and
produces per-system match scores, optional hour-offset suggestions, and
adjusted system weights.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from tools.destiny.contract import ChartInfo

# Canonical event types aligned with PRD module 3.
EVENT_TYPES = (
    "study",
    "job",
    "job_change",
    "startup",
    "marriage",
    "breakup",
    "house",
    "illness",
    "surgery",
    "award",
    "move",
    "other",
)

# Map event type to the destiny domain used for scoring.
_EVENT_DOMAIN_MAP = {
    "study": "general",
    "job": "career",
    "job_change": "career",
    "startup": "career",
    "marriage": "marriage",
    "breakup": "marriage",
    "house": "wealth",
    "illness": "health",
    "surgery": "health",
    "award": "general",
    "move": "general",
    "other": "general",
}

# Positive signal keywords per domain (Chinese). A simple heuristic: the more
# keywords that appear in a system's prediction, the higher the match score.
_DOMAIN_KEYWORDS = {
    "career": ["升职", "晋升", "入职", "跳槽", "创业", "事业", "工作", "贵人", "领导"],
    "marriage": ["结婚", "婚姻", "感情", "桃花", "恋爱", "配偶", "夫妻", "正缘"],
    "health": ["病", "手术", "医院", "健康", "身体", "意外", "伤", "疾"],
    "wealth": ["财", "买房", "置业", "投资", "赚钱", "收入", "资产", "富"],
    "general": ["变动", "变化", "重要", "转折", "机遇", "挑战"],
}

# Year extractor for event happened_at strings.
_YYYY_PREFIX = 4

AnalyzerCallable = Callable[[ChartInfo, str], Awaitable[Dict[str, Any]]]


@dataclass
class LifeEvent:
    """A user-recorded life event used to calibrate destiny predictions."""

    id: str
    chart_id: str
    event_type: str
    happened_at: str
    description: str = ""
    predicted_by_agent: Optional[str] = None
    match_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        chart_id: str,
        event_type: str,
        happened_at: str,
        description: str = "",
        predicted_by_agent: Optional[str] = None,
    ) -> "LifeEvent":
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unsupported event_type: {event_type}")
        return cls(
            id=str(uuid.uuid4()),
            chart_id=chart_id,
            event_type=event_type,
            happened_at=happened_at,
            description=description,
            predicted_by_agent=predicted_by_agent,
        )


class InMemoryEventStore:
    """Simple in-memory store for life events, scoped by chart_id."""

    def __init__(self) -> None:
        self._events: Dict[str, List[LifeEvent]] = {}

    def add(self, event: LifeEvent) -> None:
        self._events.setdefault(event.chart_id, []).append(event)

    def list(self, chart_id: str) -> List[LifeEvent]:
        return list(self._events.get(chart_id, []))

    def delete(self, chart_id: str, event_id: str) -> bool:
        events = self._events.get(chart_id, [])
        for idx, event in enumerate(events):
            if event.id == event_id:
                events.pop(idx)
                return True
        return False


def _extract_year(happened_at: str) -> Optional[int]:
    """Extract a 4-digit year from an ISO-like date/datetime string."""
    if not happened_at:
        return None
    text = happened_at.strip()
    if len(text) >= _YYYY_PREFIX and text[:_YYYY_PREFIX].isdigit():
        return int(text[:_YYYY_PREFIX])
    return None


def _score_text(text: str, domain: str) -> float:
    """Heuristic score [0, 1] based on keyword overlap."""
    if not text:
        return 0.0
    keywords = _DOMAIN_KEYWORDS.get(domain, [])
    if not keywords:
        return 0.5
    hits = sum(1 for kw in keywords if kw in text)
    # Normalize by keyword count; cap at 1.0.
    return min(1.0, hits / max(1, len(keywords) * 0.4))


def _system_score(raw_result: Dict[str, Any], domain: str) -> float:
    """Compute a match score for a single system's raw result."""
    if not isinstance(raw_result, dict):
        return 0.0
    if raw_result.get("error"):
        return 0.1

    # Prefer aligned domain analysis if present.
    domain_analysis = raw_result.get("domain_analysis") or {}
    if isinstance(domain_analysis, dict) and domain in domain_analysis:
        value = domain_analysis[domain]
        if isinstance(value, dict):
            text = value.get("text") or value.get("description") or str(value)
        else:
            text = str(value)
        return 0.4 + 0.6 * _score_text(text, domain)

    # Fall back to any conclusion text in the raw result.
    raw_text = str(raw_result)
    return 0.2 + 0.5 * _score_text(raw_text, domain)


def _suggest_hour_offset(avg_score: float, event_count: int) -> Optional[int]:
    """Suggest an hour offset when predictions are poorly aligned with events."""
    if event_count == 0 or avg_score >= 0.5:
        return None
    if avg_score < 0.25:
        return 2
    return 1


class DestinyCalibrator:
    """Calibrate destiny system weights against user-recorded life events."""

    def __init__(
        self,
        analyzer: Optional[AnalyzerCallable] = None,
        event_store: Optional[InMemoryEventStore] = None,
    ):
        self.analyzer = analyzer
        self.event_store = event_store or InMemoryEventStore()

    async def calibrate(
        self,
        chart_info: ChartInfo,
        events: Optional[List[LifeEvent]] = None,
    ) -> Dict[str, Any]:
        """Run calibration for a chart.

        Args:
            chart_info: the chart to calibrate.
            events: optional explicit event list; otherwise loaded from store.

        Returns:
            Dict with per-system scores, adjusted weights, suggested hour
            offset, average score, and event-level details.
        """
        if isinstance(chart_info, dict):
            chart_info = ChartInfo(**chart_info)

        event_list = events if events is not None else self.event_store.list(chart_info.bazi)
        if not event_list:
            return {
                "chart_id": chart_info.bazi,
                "event_count": 0,
                "average_score": 0.0,
                "system_scores": {},
                "adjusted_weights": {},
                "suggested_hour_offset": None,
                "events": [],
                "note": "No events provided; calibration requires at least one recorded event.",
            }

        system_scores: Dict[str, List[float]] = {}
        event_details: List[Dict[str, Any]] = []

        for event in event_list:
            domain = _EVENT_DOMAIN_MAP.get(event.event_type, "general")
            year = _extract_year(event.happened_at)
            question = f"{event.event_type}（{event.happened_at}）"
            if year:
                question = f"{year}年 {event.event_type} 方面的运势如何？"

            raw_result: Dict[str, Any] = {}
            if self.analyzer is not None:
                try:
                    raw_result = await self.analyzer(chart_info, question)
                except Exception as exc:  # pragma: no cover - safety net
                    raw_result = {"error": f"{type(exc).__name__}: {exc}"}

            per_event_scores: Dict[str, float] = {}
            per_system_text: Dict[str, str] = {}

            # Score each system found in the analyzer result.
            if isinstance(raw_result, dict):
                per_system = raw_result.get("per_system") or []
                if isinstance(per_system, list):
                    for entry in per_system:
                        if not isinstance(entry, dict):
                            continue
                        system = entry.get("system")
                        if not system:
                            continue
                        score = _system_score(entry.get("raw_result", {}), domain)
                        system_scores.setdefault(system, []).append(score)
                        per_event_scores[system] = round(score, 3)
                        # Extract a snippet for debugging.
                        raw = entry.get("raw_result") or {}
                        snippet = ""
                        da = raw.get("domain_analysis") or {}
                        if isinstance(da, dict) and domain in da:
                            snippet = str(da[domain])[:80]
                        per_system_text[system] = snippet

            event_details.append(
                {
                    "event_id": event.id,
                    "event_type": event.event_type,
                    "happened_at": event.happened_at,
                    "domain": domain,
                    "scores": per_event_scores,
                    "snippets": per_system_text,
                }
            )

        # Aggregate per-system average scores and derive weights.
        aggregated: Dict[str, float] = {}
        all_scores: List[float] = []
        for system, scores in system_scores.items():
            avg = sum(scores) / len(scores)
            aggregated[system] = round(avg, 3)
            all_scores.extend(scores)

        average_score = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0

        # Normalize weights so they sum to 1.0 (only across systems with scores).
        total = sum(aggregated.values()) or 1.0
        adjusted_weights = {
            system: round(score / total, 3) for system, score in aggregated.items()
        }

        suggested_offset = _suggest_hour_offset(average_score, len(event_list))

        return {
            "chart_id": chart_info.bazi,
            "event_count": len(event_list),
            "average_score": average_score,
            "system_scores": aggregated,
            "adjusted_weights": adjusted_weights,
            "suggested_hour_offset": suggested_offset,
            "events": event_details,
        }
