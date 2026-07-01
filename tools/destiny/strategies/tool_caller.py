"""Rule-based tool caller for destiny analysis validation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from tools.destiny.contract import ChartInfo


def _safe_import_bazi_validator() -> Optional[Any]:
    try:
        from tools.bazi_ai import bazi_validator

        return bazi_validator
    except Exception:  # pragma: no cover - bazi_ai may be unavailable
        return None


def _safe_import_rule_checker() -> Optional[Any]:
    try:
        from tools.bazi_ai import rule_checker

        return rule_checker
    except Exception:  # pragma: no cover - bazi_ai may be unavailable
        return None


class ToolCaller:
    """Call lightweight rule validators and feed results back into reasoning."""

    def __init__(self, chart_info: ChartInfo) -> None:
        self.chart_info = chart_info

    def validate_bazi(self) -> Dict[str, Any]:
        """Return syntactic validation results for the bazi string."""
        bazi = self.chart_info.bazi
        validator = _safe_import_bazi_validator()
        if validator is None:
            return {
                "bazi": bazi,
                "valid": None,
                "normalized": None,
                "error": "bazi_validator not available",
            }
        normalized = validator.normalize_bazi(bazi)
        return {
            "bazi": bazi,
            "valid": validator.validate_bazi(bazi),
            "normalized": normalized,
            "day_master": validator.day_master(bazi) if normalized else None,
            "month_branch": validator.month_branch(bazi) if normalized else None,
        }

    def check_analysis(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Run rule checks on a system result and append feedback."""
        feedback: Dict[str, Any] = {"rule_warnings": [], "rule_notes": []}
        bazi = self.chart_info.bazi

        validator = _safe_import_bazi_validator()
        if validator is not None and not validator.validate_bazi(bazi):
            feedback["rule_warnings"].append(f"八字 {bazi} 未能通过六十甲子合法性校验")
            return feedback

        checker = _safe_import_rule_checker()
        if checker is None:
            feedback["rule_notes"].append("rule_checker not available")
            return feedback

        basic = result.get("basic_info", {})
        if basic.get("day_master_strength"):
            warnings = checker.check_day_master_strength(
                bazi, basic.get("day_master_strength")
            )
            feedback["rule_warnings"].extend(warnings)

        useful_gods = basic.get("useful_gods", [])
        taboo_gods = basic.get("taboo_gods", [])
        if useful_gods or taboo_gods:
            warnings = checker.check_useful_gods(bazi, useful_gods, taboo_gods)
            feedback["rule_warnings"].extend(warnings)

        if not feedback["rule_warnings"]:
            feedback["rule_notes"].append("基础规则校验通过")

        return feedback

    def build_feedback_text(self, result: Dict[str, Any]) -> str:
        """Return a human-readable feedback string for prompt injection."""
        feedback = self.check_analysis(result)
        lines = []
        if feedback.get("rule_warnings"):
            lines.append("规则校验警告：")
            lines.extend(f"- {w}" for w in feedback["rule_warnings"])
        if feedback.get("rule_notes"):
            lines.extend(feedback["rule_notes"])
        return "\n".join(lines) or "暂无规则校验反馈。"

    def apply(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of *result* with rule feedback injected into reasoning."""
        result = dict(result)
        feedback_text = self.build_feedback_text(result)
        if feedback_text:
            reasoning = result.get("reasoning", "")
            result["reasoning"] = f"{reasoning}\n\n[规则校验反馈]\n{feedback_text}".strip()
            result["rule_feedback"] = self.check_analysis(result)
        return result
