"""Resolve conflicts and low-confidence situations across destiny systems."""

from __future__ import annotations

from typing import Any, Dict, List

from tools.destiny.contract import DomainConclusion


def resolve_domain(domain: str, conclusions: List[DomainConclusion]) -> Dict[str, Any]:
    """Build a consensus conclusion for one domain.

    The logic is intentionally simple: exact-text matches count as agreement.
    Real-world textual differences would need an LLM judge, but that is out of
    scope for this stability window.

    Returns:
        dict with keys: consensus, confidence, dissent.
    """
    if not conclusions:
        return {
            "consensus": "",
            "confidence": "low",
            "dissent": [],
        }

    # Group by exact text.
    groups: Dict[str, List[DomainConclusion]] = {}
    for conclusion in conclusions:
        groups.setdefault(conclusion.text, []).append(conclusion)

    # Pick the text supported by the most systems.
    majority_text = max(groups, key=lambda text: len(groups[text]))
    majority_count = len(groups[majority_text])
    total = len(conclusions)

    if majority_count == total:
        confidence = "high"
    elif majority_count > total / 2:
        confidence = "medium"
    else:
        confidence = "low"

    dissent = [text for text in groups if text != majority_text]

    return {
        "consensus": majority_text,
        "confidence": confidence,
        "dissent": dissent,
    }


def overall_confidence(domain_confidences: List[str]) -> str:
    """Return the overall confidence given per-domain confidences."""
    if not domain_confidences:
        return "low"
    if any(c == "low" for c in domain_confidences):
        return "low"
    if all(c == "high" for c in domain_confidences):
        return "high"
    return "medium"
