"""Multi-destiny ensemble: bazi + ziwei + qizheng alignment and fusion."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional

from tools.destiny.aligner import align
from tools.destiny.conflict_resolver import overall_confidence, resolve_domain
from tools.destiny.contract import ChartInfo, DomainConclusion, SystemResult
from tools.destiny.strategies.debate import DebateStrategy
from tools.destiny.strategies.reflection import ReflectionStrategy
from tools.destiny.strategies.tool_caller import ToolCaller

SystemCallable = Callable[[ChartInfo, str], Awaitable[Dict[str, Any]]]

_DOMAINS = ("career", "wealth", "marriage", "health", "general")


def _load_default_callables() -> Dict[str, SystemCallable]:
    """Load the built-in system callables when no custom registry is provided.

    Missing optional subsystems are silently skipped; the ensemble will report
    them as unavailable rather than crashing on import.
    """
    callables: Dict[str, SystemCallable] = {}

    try:
        from tools.bazi_ai.engine import analyze_bazi

        async def _bazi_caller(chart: ChartInfo, question: str) -> Dict[str, Any]:
            return await analyze_bazi(chart.bazi, question=question)

        callables["bazi"] = _bazi_caller
    except Exception as exc:  # pragma: no cover
        from utils.logger import setup_logger

        logger = setup_logger("MultiDestinyAnalyzer")
        logger.debug("Bazi analyzer not available for ensemble: %s", exc)

    try:
        from tools.qizheng.engine import QiZhengAnalyzer

        _qz_analyzer = QiZhengAnalyzer()

        async def _qizheng_caller(chart: ChartInfo, question: str) -> Dict[str, Any]:
            return await _qz_analyzer.analyze({"bazi": chart.bazi}, question=question)

        callables["qizheng"] = _qizheng_caller
    except Exception as exc:  # pragma: no cover
        from utils.logger import setup_logger

        logger = setup_logger("MultiDestinyAnalyzer")
        logger.debug("Qi Zheng analyzer not available for ensemble: %s", exc)

    try:
        from tools.ziwei.engine import ZiWeiAnalyzer

        _zw_analyzer = ZiWeiAnalyzer()

        async def _ziwei_caller(chart: ChartInfo, question: str) -> Dict[str, Any]:
            return await _zw_analyzer.analyze(
                chart.ziwei_chart_info(), question=question
            )

        callables["ziwei"] = _ziwei_caller
    except Exception as exc:  # pragma: no cover
        from utils.logger import setup_logger

        logger = setup_logger("MultiDestinyAnalyzer")
        logger.debug("Zi Wei analyzer not available for ensemble: %s", exc)

    return callables


class MultiDestinyAnalyzer:
    """Run multiple destiny systems concurrently and fuse their conclusions."""

    def __init__(
        self,
        systems: Optional[List[str]] = None,
        callables: Optional[Dict[str, SystemCallable]] = None,
        config: Optional[Dict[str, Any]] = None,
        strategy: str = "single",
        system_weights: Optional[Dict[str, float]] = None,
    ):
        self.systems = list(systems or ["bazi", "ziwei", "qizheng"])
        self.callables = dict(callables or _load_default_callables())
        self.config = dict(config or {})
        self.strategy = strategy if strategy in (
            "single", "reflection", "debate", "tool_augmented"
        ) else "single"
        # Optional per-system fusion weights (e.g. from event calibration).
        # Missing keys default to 1.0 inside resolve_domain.
        self.system_weights: Dict[str, float] = {
            str(k): float(v)
            for k, v in (system_weights or {}).items()
            if v is not None
        }

    def _get_callable(self, system: str) -> Optional[SystemCallable]:
        if system in self.callables:
            return self.callables[system]
        # Zi Wei Dou Shu requires full birth data (location); callers with that
        # data should inject it via the `callables` mapping.
        return None

    async def analyze(
        self,
        chart_info: ChartInfo,
        question: str = "",
    ) -> Dict[str, Any]:
        """Analyze a chart across all configured systems and aggregate results.

        Args:
            chart_info: the chart to analyze.
            question: optional user question.

        Returns:
            A dict with per-system results, aligned consensus, summary and
            overall confidence.
        """
        if isinstance(chart_info, dict):
            chart_info = ChartInfo(**chart_info)

        tasks = []
        for system in self.systems:
            caller = self._get_callable(system)
            if caller is None:
                # Placeholder task that returns an unavailable error.
                async def _unavailable(
                    _chart: ChartInfo = chart_info,
                    _question: str = question,
                    _system: str = system,
                ) -> Dict[str, Any]:
                    return {
                        "error": f"system {_system} is not available",
                        "domain_analysis": {},
                        "confidence": "low",
                    }

                tasks.append(_unavailable(chart_info, question))
            else:
                tasks.append(self._run_with_error_handling(caller, chart_info, question))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Apply reflection to each successful system result when requested.
        if self.strategy == "reflection":
            reflector = ReflectionStrategy()
            reflected = []
            for system, raw in zip(self.systems, raw_results):
                if isinstance(raw, dict):
                    raw = await reflector.reflect(system, raw, chart_info)
                reflected.append(raw)
            raw_results = reflected

        # Apply rule-based tool validation to inject feedback into reasoning.
        if self.strategy == "tool_augmented":
            tool_caller = ToolCaller(chart_info)
            augmented = []
            for system, raw in zip(self.systems, raw_results):
                if isinstance(raw, dict):
                    raw = tool_caller.apply(raw)
                augmented.append(raw)
            raw_results = augmented

        system_results: List[SystemResult] = []
        for system, raw in zip(self.systems, raw_results):
            if isinstance(raw, BaseException):
                raw_result: Dict[str, Any] = {
                    "error": f"{type(raw).__name__}: {raw}",
                    "domain_analysis": {},
                    "confidence": "low",
                }
            else:
                raw_result = raw if isinstance(raw, dict) else {}
            conclusions = align(raw_result, system)
            system_results.append(
                SystemResult(
                    system=system,
                    chart_info=chart_info,
                    raw_result=raw_result,
                    domain_conclusions=conclusions,
                )
            )

        aligned = self._build_aligned(system_results)

        # Debate strategy: let subsystems challenge each other and refine consensus.
        if self.strategy == "debate":
            debate = DebateStrategy()
            debate_consensus = await debate.debate(
                chart_info,
                {sr.system: sr.domain_conclusions for sr in system_results},
            )
            for domain, entry in debate_consensus.items():
                if domain in aligned and entry.get("text"):
                    aligned[domain] = {
                        "consensus": entry["text"],
                        "confidence": entry.get("confidence", "medium"),
                        "dissent": aligned[domain].get("dissent", []),
                        "_debate": True,
                    }

        overall = overall_confidence(
            [v["confidence"] for v in aligned.values() if v.get("consensus")]
        )
        summary = self._build_summary(chart_info, aligned, question)

        result = {
            "bazi": chart_info.bazi,
            "question": question,
            "per_system": [sr.to_dict() for sr in system_results],
            "aligned": aligned,
            "final_summary": summary,
            "overall_confidence": overall,
        }
        if self.strategy != "single":
            result["strategy"] = self.strategy
        if self.system_weights:
            result["system_weights"] = dict(self.system_weights)
            result["weights_source"] = "calibration"
        return result

    async def _run_with_error_handling(
        self,
        caller: SystemCallable,
        chart_info: ChartInfo,
        question: str,
    ) -> Dict[str, Any]:
        try:
            return await caller(chart_info, question)
        except Exception as exc:  # pragma: no cover - safety net
            return {
                "error": f"{type(exc).__name__}: {exc}",
                "domain_analysis": {},
                "confidence": "low",
            }

    def _build_aligned(self, system_results: List[SystemResult]) -> Dict[str, Any]:
        """Aggregate per-domain conclusions across all systems."""
        by_domain: Dict[str, List[DomainConclusion]] = {domain: [] for domain in _DOMAINS}
        for result in system_results:
            for conclusion in result.domain_conclusions:
                # Ensure system id is present for weighted voting.
                if not conclusion.system:
                    conclusion.system = result.system
                by_domain.setdefault(conclusion.domain, []).append(conclusion)

        weights = self.system_weights or None
        aligned: Dict[str, Any] = {}
        for domain in _DOMAINS:
            aligned[domain] = resolve_domain(
                domain, by_domain[domain], system_weights=weights
            )
        return aligned

    def _build_summary(
        self,
        chart_info: ChartInfo,
        aligned: Dict[str, Any],
        question: str,
    ) -> str:
        """Generate a human-readable summary of the aligned conclusions."""
        parts = [f"八字：{chart_info.bazi}"]
        if question:
            parts.append(f"提问：{question}")
        for domain in _DOMAINS:
            entry = aligned.get(domain)
            if not entry or not entry.get("consensus"):
                continue
            label = {
                "career": "事业",
                "wealth": "财运",
                "marriage": "婚姻",
                "health": "健康",
                "general": "综合",
            }.get(domain, domain)
            parts.append(f"{label}：{entry['consensus']}（置信度：{entry['confidence']}）")
        return "；".join(parts)
