"""Align per-system outputs to the unified destiny domain vocabulary."""

from __future__ import annotations

from typing import Any, Dict, List

from tools.destiny.contract import DomainConclusion

# Canonical domains used by the multi-system ensemble layer.
_CANONICAL_DOMAINS = {"career", "wealth", "marriage", "health", "general"}

# Some systems may emit Chinese keys; map them to the canonical set.
_DOMAIN_ALIASES = {
    "事业": "career",
    "职业": "career",
    "工作": "career",
    "财运": "wealth",
    "财富": "wealth",
    "婚姻": "marriage",
    "感情": "marriage",
    "健康": "health",
    "身体": "health",
    "家庭": "general",
    "六亲": "general",
    "综合": "general",
}


def _normalize_domain(key: str) -> str:
    key = str(key).strip().lower()
    if key in _CANONICAL_DOMAINS:
        return key
    return _DOMAIN_ALIASES.get(key, "general")


def _extract_confidence(raw_result: Dict[str, Any]) -> str:
    confidence = raw_result.get("confidence", "medium")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"
    return confidence


def align(raw_result: Dict[str, Any], system: str) -> List[DomainConclusion]:
    """Extract canonical domain conclusions from a single system's output.

    Args:
        raw_result: the dict returned by a destiny analyzer (bazi/ziwei/qizheng).
        system: identifier of the system, e.g. "bazi".

    Returns:
        A list of DomainConclusion objects in the unified vocabulary.
    """
    domain_analysis = raw_result.get("domain_analysis") or {}
    if not isinstance(domain_analysis, dict):
        return []

    confidence = _extract_confidence(raw_result)
    conclusions: List[DomainConclusion] = []
    for key, value in domain_analysis.items():
        if not value:
            continue
        domain = _normalize_domain(key)
        # Some systems (e.g. ziwei) emit dicts with a "text" field.
        if isinstance(value, dict):
            text = value.get("text") or value.get("description") or str(value)
        else:
            text = str(value)
        if not text or text in ("待详细分析", "待详细排盘后补充"):
            continue
        conclusions.append(
            DomainConclusion(
                domain=domain,
                text=text,
                confidence=confidence,
            )
        )
    return conclusions
