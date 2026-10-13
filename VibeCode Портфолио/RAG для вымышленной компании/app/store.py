"""Векторное хранилище на NumPy с точным косинусным поиском.

Почему не FAISS/Qdrant из коробки? На демонстрационном масштабе (тысячи чанков)
brute-force по матрице — это миллисекунды и ТОЧНЫЙ (не приближённый) top-k,
ноль внешних сервисов и зависимостей. Интерфейс класса сознательно выделен так,
чтобы хранилище можно было заменить на Qdrant/pgvector без правок пайплайна —
см. раздел Design Decisions в README.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .chunking import Chunk


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.chunks: list[Chunk] = []
        self.matrix = np.zeros((0, dim), dtype=np.float32)

    def __len__(self) -> int:
        return len(self.chunks)

    def add(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        assert len(chunks) == len(vectors), "chunks и vectors должны совпадать по длине"
        if not chunks:
            return
        self.chunks.extend(chunks)
        self.matrix = np.vstack([self.matrix, vectors.astype(np.float32)])

    def reset(self) -> None:
        self.chunks = []
        self.matrix = np.zeros((0, self.dim), dtype=np.float32)

    def search(self, query: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        """Top-k чанков по косинусной близости (векторы L2-нормализованы → dot = cosine)."""
        if len(self) == 0:
            return []
        sims = self.matrix @ query
        k = min(k, len(self))
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [(self.chunks[int(i)], float(sims[i])) for i in idx]

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "vectors.npy", self.matrix)
        with open(path / "chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in self.chunks:
                f.write(json.dumps(chunk.__dict__, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: Path, dim: int) -> "VectorStore":
        store = cls(dim)
        vectors_file, chunks_file = path / "vectors.npy", path / "chunks.jsonl"
        if vectors_file.exists() and chunks_file.exists():
            store.matrix = np.load(vectors_file).astype(np.float32)
            with open(chunks_file, encoding="utf-8") as f:
                store.chunks = [Chunk(**json.loads(line)) for line in f if line.strip()]
        return store
