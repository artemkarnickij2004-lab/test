"""Гибридный поиск: dense (векторная семантика) + sparse (BM25 по ключевым словам).

Слияние ранжирований — Reciprocal Rank Fusion (RRF), устойчивый к различиям
шкал скоров two retrievers. Гибрид стабильно выигрывает чистый векторный поиск
на запросах с терминами, числами и аббревиатурами (это видно и в eval-метриках).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from .chunking import Chunk
from .embeddings import Embedder
from .store import VectorStore

_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")

# Стоп-слова BM25: частотные служебные слова с почти нулевой информативностью.
# Без их фильтрации выдача засоряется совпадениями по «на», «и», «сколько» и т.п.
STOPWORDS = frozenset(
    "и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только "
    "ее мне было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни "
    "быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где "
    "есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж "
    "тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее "
    "кажется сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над "
    "больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо свою "
    "этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между "
    "сколько какой какие какая какое какова каково каковы каким каких какими каком "
    "the a an and or of to in is are was for on with at by as it this that these those from "
    "do does did how much many what which who whom when where why".split()
)


def tokenize(text: str, remove_stopwords: bool = True) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    if remove_stopwords:
        return [t for t in tokens if t not in STOPWORDS or len(t) > 20]
    return tokens


@dataclass
class Hit:
    chunk: Chunk
    score: float
    dense_rank: int | None = None
    bm25_rank: int | None = None


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(d) = Σ 1 / (k + rank_i(d))."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    def __init__(self, store: VectorStore, embedder: Embedder, rrf_k: int = 60, sparse_rel_threshold: float = 0.0):
        self.store = store
        self.embedder = embedder
        self.rrf_k = rrf_k
        self.sparse_rel_threshold = sparse_rel_threshold
        self._bm25: BM25Okapi | None = None
        self._bm25_size = -1  # инвалидация при изменении индекса

    def invalidate(self) -> None:
        self._bm25 = None
        self._bm25_size = -1

    def _ensure_bm25(self) -> None:
        if self._bm25 is None or self._bm25_size != len(self.store):
            corpus = [tokenize(f"{c.doc_title} {c.text}") for c in self.store.chunks]
            self._bm25 = BM25Okapi(corpus) if corpus else None
            self._bm25_size = len(self.store)

    def _dense_ranking(self, query: str, n: int) -> list[str]:
        query_vec = self.embedder.embed_query(query)
        return [chunk.id for chunk, _score in self.store.search(query_vec, n)]

    def _sparse_ranking(self, query: str, n: int, rel_threshold: float = 0.0) -> list[str]:
        self._ensure_bm25()
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        positive = scores[scores > 0]
        if len(positive) == 0:
            return []
        # Отсев слабых совпадений до RRF: без порога «шумные» документы
        # со случайными общими словами демпфируют точные dense-результаты.
        min_score = float(positive.max()) * rel_threshold
        top = np.argsort(-scores)[:n]
        return [self.store.chunks[int(i)].id for i in top if scores[i] >= min_score and scores[i] > 0]

    def search(self, query: str, top_k: int = 4, mode: str = "hybrid", candidates: int = 12) -> list[Hit]:
        """Возвращает top_k чанков. mode: 'hybrid' | 'vector' | 'bm25'."""
        dense = self._dense_ranking(query, candidates) if mode in ("hybrid", "vector") else []
        sparse = (
            self._sparse_ranking(query, candidates, rel_threshold=self.sparse_rel_threshold)
            if mode in ("hybrid", "bm25")
            else []
        )

        dense_rank = {cid: r for r, cid in enumerate(dense, start=1)}
        sparse_rank = {cid: r for r, cid in enumerate(sparse, start=1)}
        fused = rrf_fuse([dense, sparse], k=self.rrf_k)

        by_id = {c.id: c for c in self.store.chunks}
        hits = [
            Hit(chunk=by_id[cid], score=score, dense_rank=dense_rank.get(cid), bm25_rank=sparse_rank.get(cid))
            for cid, score in fused.items()
        ]
        hits.sort(key=lambda h: h.score, reverse=True)

        # Гарантия представительства экспертов: top-1 каждого использованного
        # retriever'а всегда попадает в выдачу. Без этого RRF «наказывает»
        # документ, найденный только одним из двух, — даже если он истинный
        # ответ (классическая слабость чистого RRF, показана в README на метриках).
        promoted_ids = [ranking[0] for ranking in (dense, sparse) if ranking]
        seen: set[str] = set()
        final: list[Hit] = []
        for cid in promoted_ids:
            if cid not in seen:
                seen.add(cid)
                final.append(next(h for h in hits if h.chunk.id == cid))
        final.extend(h for h in hits if h.chunk.id not in seen)
        return final[:top_k]
