"""Тесты поисковой математики: RRF-фьюжн и токенизация. Без загрузки моделей."""
from app.retrieval import rrf_fuse, tokenize


def test_tokenize_unicode_and_case():
    tokens = tokenize("Отпуск, Vacation! 365 дней.")
    assert tokens == ["отпуск", "vacation", "365", "дней"]


def test_rrf_prefers_item_high_in_both_rankings():
    # "a" — первый в обеих выдачах; "b" — первый только в одной, в другой отсутствует
    fused = rrf_fuse([["a", "b", "c"], ["a", "c", "d"]], k=60)
    assert fused["a"] > fused["b"]
    # a: 1/61 + 1/61, c: 1/63 + 1/62, d: только 1/63, b: только 1/62
    assert fused["a"] > fused["c"] > fused["d"]


def test_rrf_scores_match_formula():
    fused = rrf_fuse([["x", "y"], ["y", "z"]], k=60)
    assert abs(fused["y"] - (1 / 62 + 1 / 61)) < 1e-9
    assert abs(fused["x"] - 1 / 61) < 1e-9
    assert abs(fused["z"] - 1 / 62) < 1e-9


def test_rrf_missing_document_gets_no_points():
    fused = rrf_fuse([["a"], []], k=60)
    assert "b" not in fused
    assert fused["a"] == 1 / 61
