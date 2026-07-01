"""Unified retrieval for destiny example cases across bazi/ziwei/qizheng."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.destiny.contract import ChartInfo

_DEFAULT_CASE_PATHS = {
    "bazi": Path("./bazi_knowledge/cases.jsonl"),
    "ziwei": Path("./tools/ziwei/cases.jsonl"),
    "qizheng": Path("./tools/qizheng/cases.jsonl"),
}


def _case_text(case: Dict[str, Any]) -> str:
    """Build a single retrieval text from a case record."""
    parts = [
        case.get("bazi", ""),
        case.get("chart", ""),
        case.get("analysis_corrected", ""),
        case.get("analysis", ""),
        case.get("text", ""),
        " ".join(str(k) for k in case.get("keywords", [])),
        " ".join(str(k) for k in case.get("key_terms", [])),
    ]
    for domain, snippets in (case.get("domains", {}) or {}).items():
        if isinstance(snippets, list):
            parts.append(f"[{domain}] " + " ".join(str(s) for s in snippets))
        elif isinstance(snippets, str):
            parts.append(f"[{domain}] {snippets}")
    return "\n".join(p for p in parts if p).strip()


class DestinyRetriever:
    """Retrieve similar cases for a chart across one or more destiny systems.

    If ``sentence-transformers`` is installed and a cache path is provided,
    dense semantic retrieval is used. Otherwise the retriever falls back to
    a keyword/heuristic scorer that does not require any extra dependencies.
    """

    def __init__(
        self,
        system: str = "bazi",
        cases_path: Optional[Path] = None,
        embedding_cache_path: Optional[Path] = None,
        top_k: int = 3,
    ) -> None:
        self.system = system
        self.cases_path = cases_path or _DEFAULT_CASE_PATHS.get(system, Path(f"./{system}_cases.jsonl"))
        self.embedding_cache_path = embedding_cache_path
        self.top_k = max(0, min(top_k, 10))
        self._cases: Optional[List[Dict[str, Any]]] = None

    def _load_cases(self) -> List[Dict[str, Any]]:
        if self._cases is not None:
            return self._cases
        cases: List[Dict[str, Any]] = []
        if not self.cases_path.exists():
            self._cases = cases
            return cases
        with self.cases_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        self._cases = cases
        return cases

    def retrieve(
        self,
        chart_info: ChartInfo,
        question: str = "",
    ) -> List[Dict[str, Any]]:
        """Return the top-k most relevant cases for *chart_info*."""
        cases = self._load_cases()
        if not cases:
            return []

        semantic_hits = self._semantic_search(chart_info, question, cases)
        if semantic_hits:
            return [case for case, _score in semantic_hits[: self.top_k]]

        return self._keyword_search(chart_info, question, cases)[: self.top_k]

    def _semantic_search(
        self,
        chart_info: ChartInfo,
        question: str,
        cases: List[Dict[str, Any]],
    ) -> List[Tuple[Dict[str, Any], float]]:
        """Try dense retrieval using the bazi EmbeddingStore if available."""
        try:
            from tools.bazi_ai.embeddings import EmbeddingStore
        except Exception:  # pragma: no cover - optional dependency
            return []

        store = EmbeddingStore()
        if self.embedding_cache_path and self.embedding_cache_path.exists():
            if not store.load_cache(self.embedding_cache_path):
                store.build(cases, cache_path=self.embedding_cache_path)
        else:
            store.build(cases, cache_path=self.embedding_cache_path)

        if store._vectors is None:
            return []

        query = f"{chart_info.bazi}\n{question}".strip()
        return store.search(query, top_k=min(len(cases), self.top_k * 3))

    def _keyword_search(
        self,
        chart_info: ChartInfo,
        question: str,
        cases: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Fallback keyword/heuristic scorer."""
        query_pillars = chart_info.bazi.split()
        day_master = query_pillars[2][0] if len(query_pillars) == 4 else ""

        def score(case: Dict[str, Any]) -> int:
            s = 0
            case_bazi = case.get("bazi") or case.get("chart", "")
            if case_bazi == chart_info.bazi:
                s += 100
            case_pillars = str(case_bazi).split()
            if len(query_pillars) == 4 and len(case_pillars) == 4:
                if query_pillars[2][0] == case_pillars[2][0]:
                    s += 20
                if query_pillars[1][1] == case_pillars[1][1]:
                    s += 15
            case_day_master = case.get("day_master", "")
            if case_day_master and case_day_master == day_master:
                s += 10
            text = _case_text(case)
            for kw in question.replace("。", " ").replace("，", " ").replace("？", " ").split():
                if len(kw) >= 2 and kw in text:
                    s += 5
            return s

        scored = [(score(c), c) for c in cases]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [c for _s, c in scored]


def retrieve_for_chart(
    chart_info: ChartInfo,
    systems: Optional[List[str]] = None,
    question: str = "",
    top_k: int = 3,
) -> Dict[str, List[Dict[str, Any]]]:
    """Convenience helper: retrieve cases for multiple systems at once."""
    systems = systems or ["bazi", "ziwei", "qizheng"]
    return {
        system: DestinyRetriever(system=system, top_k=top_k).retrieve(chart_info, question)
        for system in systems
    }
