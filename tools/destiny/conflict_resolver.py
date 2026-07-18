"""Resolve conflicts and low-confidence situations across destiny systems."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.destiny.contract import DomainConclusion


def resolve_domain(
    domain: str,
    conclusions: List[DomainConclusion],
    system_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Build a consensus conclusion for one domain.

    Exact-text matches count as agreement. When ``system_weights`` is provided
    (e.g. from event calibration ``adjusted_weights``), each system's vote is
    weighted; otherwise every system counts as 1.0 (legacy majority).

    Returns:
        dict with keys: consensus, confidence, dissent, vote_weights (optional).
    """
    if not conclusions:
        return {
            "consensus": "",
            "confidence": "low",
            "dissent": [],
        }

    weights = system_weights or {}

    def _w(conclusion: DomainConclusion) -> float:
        sys = conclusion.system or ""
        if sys and sys in weights:
            return max(0.0, float(weights[sys]))
        return 1.0

    # Group by exact text; accumulate weighted votes.
    groups: Dict[str, List[DomainConclusion]] = {}
    group_weight: Dict[str, float] = {}
    for conclusion in conclusions:
        groups.setdefault(conclusion.text, []).append(conclusion)
        group_weight[conclusion.text] = group_weight.get(conclusion.text, 0.0) + _w(
            conclusion
        )

    majority_text = max(group_weight, key=lambda text: group_weight[text])
    majority_weight = group_weight[majority_text]
    total_weight = sum(group_weight.values()) or 1.0
    majority_count = len(groups[majority_text])
    total = len(conclusions)

    # Confidence: prefer weight share when weights are non-uniform; else headcount.
    weight_share = majority_weight / total_weight
    if majority_count == total or weight_share >= 0.99:
        confidence = "high"
    elif majority_count > total / 2 or weight_share > 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    dissent = [text for text in groups if text != majority_text]

    result: Dict[str, Any] = {
        "consensus": majority_text,
        "confidence": confidence,
        "dissent": dissent,
    }
    if weights:
        result["vote_weights"] = {
            text: round(w, 3) for text, w in group_weight.items()
        }
        result["weight_share"] = round(weight_share, 3)
    return result


def overall_confidence(domain_confidences: List[str]) -> str:
    """Return the overall confidence given per-domain confidences."""
    if not domain_confidences:
        return "low"
    if any(c == "low" for c in domain_confidences):
        return "low"
    if all(c == "high" for c in domain_confidences):
        return "high"
    return "medium"
