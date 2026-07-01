"""Tests for tools/bazi_ai/embeddings.py."""

from pathlib import Path

from tools.bazi_ai.embeddings import EmbeddingStore, _case_text, build_embedding_cache


def test_case_text():
    case = {
        "bazi": "乙卯 戊寅 庚子 丙子",
        "analysis_corrected": "庚金日主，伤官格",
        "key_terms": ["伤官"],
        "conclusions": ["事业有成"],
        "domains": {"career": ["技术岗位"]},
    }
    text = _case_text(case)
    assert "乙卯 戊寅 庚子 丙子" in text
    assert "伤官" in text
    assert "技术岗位" in text


def test_embedding_store_degrades_gracefully(tmp_path: Path, monkeypatch):
    """When embeddings are unavailable the store should degrade gracefully."""
    monkeypatch.setattr(EmbeddingStore, "available", property(lambda self: False))
    store = EmbeddingStore()
    cases = [{"bazi": "乙卯 戊寅 庚子 丙子", "analysis_corrected": "test"}]
    store.build(cases, cache_path=tmp_path / "cache.pkl")
    assert store.search("anything", top_k=1) == []


def test_build_embedding_cache_degrades_gracefully(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(EmbeddingStore, "available", property(lambda self: False))
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        '{"bazi": "乙卯 戊寅 庚子 丙子", "analysis_corrected": "test"}\n',
        encoding="utf-8",
    )
    cache_path = tmp_path / "cache.pkl"
    result = build_embedding_cache(cases_path, cache_path)
    assert result["total_cases"] == 1
    assert result["cached"] is False
