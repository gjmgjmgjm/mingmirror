"""Shared data contract for multi-destiny analysis.

This module is intentionally dependency-light so that it can be imported by
bazi, ziwei, qizheng and the REST layer without pulling in heavy optional
packages.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ChartInfo:
    """Minimal chart metadata shared across all destiny systems."""

    bazi: str
    system: str = ""
    question: str = ""
    gender: Optional[str] = None
    birth_datetime: Optional[str] = None
    location: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def ziwei_chart_info(self) -> Dict[str, Any]:
        """Build the chart_info dict expected by ZiWeiAnalyzer."""
        location = self.location or {
            "longitude": 116.4074,
            "latitude": 39.9042,
            "timezone": "Asia/Shanghai",
        }
        return {
            "bazi": self.bazi,
            "gender": self.gender or "male",
            "birth_datetime": self.birth_datetime
            or datetime.now().isoformat(timespec="seconds"),
            "location": location,
        }


@dataclass
class DomainConclusion:
    """One system's conclusion for a single life domain."""

    domain: str
    text: str
    confidence: str = "medium"
    system: str = ""  # optional source system id (bazi/ziwei/qizheng) for weighted fusion

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemResult:
    """Wrapper around one system's raw output plus aligned conclusions."""

    system: str
    chart_info: ChartInfo
    raw_result: Dict[str, Any] = field(default_factory=dict)
    domain_conclusions: List[DomainConclusion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "chart_info": self.chart_info.to_dict(),
            "raw_result": self.raw_result,
            "domain_conclusions": [c.to_dict() for c in self.domain_conclusions],
        }
