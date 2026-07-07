#!/usr/bin/env python3
"""
knowledge_retriever.py — semantic retrieval over local bazi knowledge files.

Chunks markdown/plain-text knowledge bases, encodes them with a sentence
transformer, and retrieves the top-k passages relevant to a query.

If `sentence-transformers` is not installed or no cache can be built, the
retriever falls back to returning the first `top_k` chunks (or an empty list).
"""

import asyncio
import hashlib
import json
import os
import pickle
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore


def _normalize_text(text: str) -> str:
    """Collapse whitespace and strip blank lines."""
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


@dataclass
class KnowledgeChunk:
    text: str
    source: str
    headings: str  # Hierarchical headings for context, e.g. "第一章 > 第一节"


_CHUNKS: Dict[str, List[KnowledgeChunk]] = {}


def _split_oversized(text: str, max_chars: int = 1500) -> List[str]:
    """Split a long section into smaller pieces at paragraph or sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    # First try splitting on blank lines.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        result: List[str] = []
        current = ""
        for p in paragraphs:
            if current and len(current) + len(p) + 2 > max_chars:
                result.append(current)
                current = p
            else:
                current = f"{current}\n\n{p}" if current else p
        if current:
            result.append(current)
        return result

    # Fallback: split at sentence boundaries.
    sentences = re.split(r"([。！？\.\n])", text)
    result = []
    current = ""
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else "")
        if len(current) + len(sent) > max_chars:
            result.append(current)
            current = sent
        else:
            current += sent
    if current:
        result.append(current)
    return result or [text]


def _chunk_markdown(text: str, source: str, max_chars: int = 1500) -> List[KnowledgeChunk]:
    """Split markdown text into chunks anchored at headings."""
    lines = text.splitlines()
    chunks: List[KnowledgeChunk] = []
    current_body: List[str] = []
    heading_stack: List[Tuple[int, str]] = []

    def _flush():
        if not current_body:
            return
        body_text = _normalize_text("\n".join(current_body))
        if not body_text:
            return
        headings = " > ".join(h for _, h in heading_stack)
        for piece in _split_oversized(body_text, max_chars):
            full = f"【{source}】{headings}\n{piece}" if headings else f"【{source}】\n{piece}"
            chunks.append(KnowledgeChunk(text=full, source=source, headings=headings))

    for line in lines:
        stripped = line.strip()
        match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if match:
            _flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            # Pop headings that are same or deeper level.
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            current_body = []
            continue
        if stripped == "---":
            _flush()
            current_body = []
            continue
        current_body.append(line)

    _flush()
    return chunks


def _chunk_plain(text: str, source: str, max_chars: int = 1500) -> List[KnowledgeChunk]:
    """Fallback chunking for files without markdown headings."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: List[KnowledgeChunk] = []
    current = ""
    for p in paragraphs:
        if current and len(current) + len(p) + 2 > max_chars:
            chunks.append(KnowledgeChunk(text=f"【{source}】\n{current}", source=source, headings=""))
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(KnowledgeChunk(text=f"【{source}】\n{current}", source=source, headings=""))
    return chunks


def _file_hashes(paths: List[Path]) -> str:
    """Return a stable hash of the knowledge file contents and mtimes."""
    hasher = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            stat = p.stat()
            hasher.update(p.resolve().as_posix().encode("utf-8"))
            hasher.update(str(stat.st_mtime).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("utf-8"))
    return hasher.hexdigest()


# Terms commonly used in bazi analysis for keyword-based fallback retrieval.
_BAZI_TERMS = [
    "比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印",
    "金", "木", "水", "火", "土",
    "甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸",
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
    "冲", "合", "刑", "害", "穿", "破", "墓", "库", "空", "旺", "衰",
    "身强", "身弱", "用神", "忌神", "大运", "流年", "夫妻宫", "子女宫",
    "父亲", "母亲", "配偶", "妻子", "丈夫", "儿子", "女儿", "兄弟", "姐妹",
    "事业", "财运", "婚姻", "健康", "子女",
]


def _extract_terms(text: str) -> List[str]:
    """Extract bazi-relevant terms from *text*."""
    terms = []
    for term in _BAZI_TERMS:
        if term in text:
            terms.append(term)
    # Also include 2-character Chinese n-grams as a crude semantic signal.
    cleaned = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    for i in range(len(cleaned) - 1):
        terms.append(cleaned[i : i + 2])
    return terms


def _keyword_score(query: str, text: str) -> int:
    """Simple keyword overlap score for environments without embeddings."""
    query_terms = _extract_terms(query)
    if not query_terms:
        return 0
    text_terms = _extract_terms(text)
    text_counter: Dict[str, int] = {}
    for t in text_terms:
        text_counter[t] = text_counter.get(t, 0) + 1
    score = 0
    for term in query_terms:
        score += text_counter.get(term, 0)
    return score


class KnowledgeRetriever:
    """Retrieve relevant knowledge passages using dense embeddings."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        use_embeddings: bool = True,
    ):
        self.model_name = model_name
        self._use_embeddings = use_embeddings
        self._model = None
        self._chunks: List[KnowledgeChunk] = []
        self._vectors: Optional[np.ndarray] = None

    @property
    def available(self) -> bool:
        if not self._use_embeddings:
            return False
        try:
            import sentence_transformers  # noqa: F401
            return np is not None
        except ImportError:
            return False

    def _load_model(self):
        if self._model is not None:
            return self._model
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        return self._model

    def _encode(self, texts: List[str]) -> Optional[np.ndarray]:
        if not self.available or not texts:
            return None
        try:
            model = self._load_model()
            return model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        except Exception:
            # Model cannot be loaded or run (e.g. offline, no cache). Fall back
            # to keyword retrieval for this session.
            return None

    def build(
        self,
        knowledge_paths: List[Path],
        cache_path: Optional[Path] = None,
    ) -> "KnowledgeRetriever":
        """Chunk and encode knowledge files; optionally persist to cache."""
        chunks: List[KnowledgeChunk] = []
        for path in knowledge_paths:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"^#{1,6}\s+", text, flags=re.MULTILINE):
                chunks.extend(_chunk_markdown(text, str(path.name)))
            else:
                chunks.extend(_chunk_plain(text, str(path.name)))

        self._chunks = chunks
        vectors = self._encode([c.text for c in chunks])
        self._vectors = vectors

        if cache_path is not None and chunks:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with cache_path.open("wb") as f:
                pickle.dump(
                    {
                        "model_name": self.model_name,
                        "chunks": [asdict(c) for c in chunks],
                        "vectors": vectors,
                        "has_vectors": vectors is not None,
                        "source_hash": _file_hashes(knowledge_paths),
                    },
                    f,
                )
        return self

    def load_cache(
        self,
        cache_path: Path,
        knowledge_paths: List[Path],
    ) -> bool:
        """Load cache if it exists and matches current source files."""
        if not cache_path.exists():
            return False
        try:
            with cache_path.open("rb") as f:
                data = pickle.load(f)
        except Exception:
            return False
        if data.get("model_name") != self.model_name:
            return False
        if data.get("source_hash") != _file_hashes(knowledge_paths):
            return False
        loaded_chunks = data.get("chunks", [])
        if not loaded_chunks:
            return False
        self._chunks = [KnowledgeChunk(**c) for c in loaded_chunks]
        self._vectors = data.get("vectors")
        return True

    def search(self, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        """Return the top-k most relevant chunks for *query*."""
        if not self._chunks:
            return []
        if self._vectors is None or not self.available or np is None:
            # Fallback: keyword-based ranking when embeddings are unavailable.
            scored = [
                (_keyword_score(query, c.text), c)
                for c in self._chunks
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            return [c for _, c in scored[:top_k]]

        model = self._load_model()
        query_vec = model.encode([query], convert_to_numpy=True)
        query_vec = query_vec / (np.linalg.norm(query_vec, axis=1, keepdims=True) + 1e-10)
        vectors = self._vectors / (np.linalg.norm(self._vectors, axis=1, keepdims=True) + 1e-10)
        scores = np.dot(vectors, query_vec.T).flatten()
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [self._chunks[i] for i, _ in ranked[:top_k]]


async def retrieve_knowledge_snippets(
    query: str,
    knowledge_paths: List[Path],
    *,
    cache_path: Optional[Path] = None,
    model_name: str = "BAAI/bge-small-zh-v1.5",
    use_embeddings: Optional[bool] = None,
    top_k: int = 5,
    max_chars: int = 8000,
) -> str:
    """Build/load a knowledge retriever and return top-k snippets as text.

    By default embeddings are disabled unless the environment variable
    ``BAZI_USE_EMBEDDINGS=1`` is set. This prevents accidental downloads of
    sentence-transformer models in offline/air-gapped environments.
    """
    if not knowledge_paths:
        return ""

    if use_embeddings is None:
        use_embeddings = os.environ.get("BAZI_USE_EMBEDDINGS", "").strip() in (
            "1",
            "true",
            "yes",
        )

    retriever = KnowledgeRetriever(model_name=model_name, use_embeddings=use_embeddings)
    cache_hit = False
    if cache_path is not None:
        cache_hit = await asyncio.to_thread(
            retriever.load_cache, cache_path, knowledge_paths
        )
    if not cache_hit:
        await asyncio.to_thread(retriever.build, knowledge_paths, cache_path)

    chunks = await asyncio.to_thread(retriever.search, query, top_k)
    text = "\n\n".join(c.text for c in chunks)
    return text[:max_chars]


def build_knowledge_cache(
    knowledge_paths: List[Path],
    cache_path: Path,
    model_name: str = "BAAI/bge-small-zh-v1.5",
    use_embeddings: Optional[bool] = None,
) -> Dict[str, int]:
    """CLI helper: pre-compute knowledge embedding cache."""
    if use_embeddings is None:
        use_embeddings = os.environ.get("BAZI_USE_EMBEDDINGS", "").strip() in (
            "1",
            "true",
            "yes",
        )
    retriever = KnowledgeRetriever(model_name=model_name, use_embeddings=use_embeddings)
    retriever.build(knowledge_paths, cache_path=cache_path)
    return {
        "total_chunks": len(retriever._chunks),
        "cached": retriever._vectors is not None,
        "cache_path": str(cache_path),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="预计算知识库 embedding 缓存")
    parser.add_argument(
        "-k",
        "--knowledge",
        nargs="+",
        default=["./bazi_knowledge/rule_primer.md"],
    )
    parser.add_argument("-o", "--output", default="./bazi_knowledge/knowledge.pkl")
    parser.add_argument("-m", "--model", default="BAAI/bge-small-zh-v1.5")
    args = parser.parse_args()
    result = build_knowledge_cache([Path(p) for p in args.knowledge], Path(args.output), args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2))
