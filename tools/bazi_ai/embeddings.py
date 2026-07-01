#!/usr/bin/env python3
"""
embeddings.py — optional semantic retrieval for bazi cases.

If `sentence-transformers` is installed, case texts are encoded into dense vectors
and retrieval uses cosine similarity. Otherwise the engine falls back to the
keyword-based `_case_relevance()` scorer.

Recommended model for Chinese: ``BAAI/bge-small-zh-v1.5``.
"""

import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore


def _case_text(case: Dict) -> str:
    """Build a single retrieval text from a case record."""
    parts = [
        case.get("bazi", ""),
        case.get("analysis_corrected", ""),
        " ".join(case.get("key_terms", [])),
        " ".join(case.get("conclusions", [])),
    ]
    for domain, snippets in case.get("domains", {}).items():
        parts.append(f"[{domain}] " + " ".join(snippets))
    return "\n".join(p for p in parts if p).strip()


class EmbeddingStore:
    """Manage case embeddings with optional on-disk cache."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._cases: List[Dict] = []
        self._texts: List[str] = []
        self._vectors: Optional[np.ndarray] = None

    @property
    def available(self) -> bool:
        """Return True if sentence-transformers can be imported and loaded."""
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False

    def _load_model(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        return self._model

    def build(
        self,
        cases: List[Dict],
        cache_path: Optional[Path] = None,
    ) -> "EmbeddingStore":
        """Encode *cases* and optionally persist to *cache_path*."""
        self._cases = cases
        self._texts = [_case_text(c) for c in cases]
        if not self.available or not self._texts or np is None:
            self._vectors = None
            return self

        model = self._load_model()
        self._vectors = model.encode(self._texts, convert_to_numpy=True, show_progress_bar=False)

        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("wb") as f:
                pickle.dump({
                    "model_name": self.model_name,
                    "texts": self._texts,
                    "vectors": self._vectors,
                }, f)
        return self

    def load_cache(self, cache_path: Path) -> bool:
        """Load a previously built embedding cache."""
        if not cache_path.exists():
            return False
        with cache_path.open("rb") as f:
            data = pickle.load(f)
        if data.get("model_name") != self.model_name:
            return False
        self._texts = data["texts"]
        self._vectors = data["vectors"]
        return True

    def search(
        self,
        query: str,
        top_k: int = 3,
    ) -> List[Tuple[Dict, float]]:
        """Return top-k (case, score) pairs by cosine similarity."""
        if self._vectors is None or not self.available or np is None:
            return []
        model = self._load_model()
        query_vec = model.encode([query], convert_to_numpy=True)
        query_vec = query_vec / (np.linalg.norm(query_vec, axis=1, keepdims=True) + 1e-10)
        vectors = self._vectors / (np.linalg.norm(self._vectors, axis=1, keepdims=True) + 1e-10)
        scores = np.dot(vectors, query_vec.T).flatten()
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(self._cases[i], float(score)) for i, score in ranked[:top_k]]


def build_embedding_cache(
    cases_path: Path,
    cache_path: Path,
    model_name: str = "BAAI/bge-small-zh-v1.5",
) -> Dict[str, int]:
    """CLI helper: build an embedding cache from *cases_path*."""
    cases = []
    if cases_path.exists():
        with cases_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        cases.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    store = EmbeddingStore(model_name=model_name)
    store.build(cases, cache_path=cache_path)
    return {
        "total_cases": len(cases),
        "cached": store._vectors is not None,
        "cache_path": str(cache_path),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="预计算 bazi 案例的 embedding 缓存")
    parser.add_argument("-c", "--cases", default="./bazi_knowledge/cases.jsonl")
    parser.add_argument("-o", "--output", default="./bazi_knowledge/cases.pkl")
    parser.add_argument("-m", "--model", default="BAAI/bge-small-zh-v1.5")
    args = parser.parse_args()

    result = build_embedding_cache(Path(args.cases), Path(args.output), args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
