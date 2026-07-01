"""Shared data contract for multi-destiny analysis.

This module is intentionally dependency-light so that it can be imported by
bazi, ziwei, qizheng and the REST layer without pulling in heavy optional
packages.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChartInfo:
    """Minimal chart metadata shared across all destiny systems."""

    bazi: str
    system: str = ""
    question: str = ""
    gender: Optional[str] = None
    birth_datetime: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DomainConclusion:
    """One system's conclusion for a single life domain."""

    domain: str
    text: str
    confidence: str = "medium"

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
