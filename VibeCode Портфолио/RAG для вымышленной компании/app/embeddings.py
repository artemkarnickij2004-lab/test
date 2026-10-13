"""Embedding-модель: ленивая загрузка и кэширование синглтона.

По умолчанию — intfloat/multilingual-e5-small:
  * многоязычная (русский и английский семантически близки в одном пространстве);
  * 512 токенов контекста (в отличие от multilingual-MiniLM со 128);
  * требует префиксов "query: " / "passage: " — это важная деталь моделей E5,
    без префиксов качество заметно проседает (обрабатывается ниже).
"""
from __future__ import annotations

import threading

import numpy as np


class Embedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.e5_prefixes = "e5" in model_name.lower()
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def _prep(self, texts: list[str], kind: str) -> list[str]:
        if self.e5_prefixes:
            prefix = "query: " if kind == "query" else "passage: "
            return [prefix + t for t in texts]
        return texts

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Эмбеддинги для индексируемых текстов (L2-нормализованные)."""
        vectors = self.model.encode(
            self._prep(texts, "passage"),
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """Эмбеддинг поискового запроса (L2-нормализованный)."""
        return self.embed_documents_queries([text])[0]

    def embed_documents_queries(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(
            self._prep(texts, "query"),
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.astype(np.float32)


_lock = threading.Lock()
_cache: dict[str, Embedder] = {}


def get_embedder(model_name: str) -> Embedder:
    """Потокобезопасный синглтон: модель грузится один раз на процесс."""
    with _lock:
        if model_name not in _cache:
            _cache[model_name] = Embedder(model_name)
        return _cache[model_name]
