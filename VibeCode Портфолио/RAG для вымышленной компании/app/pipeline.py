"""RAG-пайплайн: загрузка документов, индексация, ответ на вопрос.

Отдельный слой оркестрации, чтобы FastAPI-роуты оставались тонкими,
а пайплайн можно было использовать без HTTP (например, в eval-скрипте).
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import numpy as np

from .chunking import chunk_document
from .config import settings
from .embeddings import Embedder, get_embedder
from .llm import LLMClient
from .retrieval import Hit, HybridRetriever
from .store import VectorStore

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def extractive_answer(question: str, hits: list[Hit], embedder: Embedder, max_sentences: int = 5) -> str:
    """Fallback без LLM: предложения, ближайшие к запросу по эмбеддингу.

    Честный поисковый ответ: пользователь видит, какие именно фрагменты
    базы знаний релевантны вопросу, с ссылками на источники.
    """
    sentences: list[tuple[int, int, str]] = []  # (№ источника, позиция, текст)
    for i, hit in enumerate(hits, start=1):
        for j, raw in enumerate(_SENT_SPLIT_RE.split(hit.chunk.text)):
            sentence = " ".join(raw.split())
            if len(sentence) >= 40 and not sentence.startswith("#"):
                sentences.append((i, j, sentence))
    if not sentences:
        return (
            "По вашему запросу ничего не нашлось в базе знаний. "
            "Попробуйте переформулировать вопрос или загрузите документы."
        )

    candidates = sentences[:40]
    sent_vecs = embedder.embed_documents([s for _, _, s in candidates])
    query_vec = embedder.embed_query(question)
    sims = sent_vecs @ query_vec

    top = np.argsort(-sims)[:max_sentences]
    ordered = sorted(top, key=lambda idx: (candidates[idx][0], candidates[idx][1]))

    header = (
        "ℹ️ *LLM не подключён (не задан `LLM_API_KEY`) — показываю наиболее "
        "релевантные фрагменты базы знаний:*\n\n"
    )
    lines = [f"- {candidates[idx][2]} [{candidates[idx][0]}]" for idx in ordered]
    return header + "\n".join(lines)


class RAGPipeline:
    def __init__(self):
        self.embedder = get_embedder(settings.embed_model)
        self.store = VectorStore.load(settings.index_dir, self.embedder.dim)
        self.retriever = HybridRetriever(
            self.store,
            self.embedder,
            rrf_k=settings.rrf_k,
            sparse_rel_threshold=settings.sparse_rel_threshold,
        )
        self.llm = LLMClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
        )

    # ---------- индексация ----------

    def list_documents(self) -> list[str]:
        if not settings.documents_dir.exists():
            return []
        return sorted(
            p.name for p in settings.documents_dir.iterdir()
            if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )

    def reindex(self) -> dict:
        """Полная переиндексация каталога документов (просто и надёжно)."""
        self.store.reset()
        all_chunks = []
        for name in self.list_documents():
            path = settings.documents_dir / name
            text = self._read_document(path)
            if len(text.strip()) < 40:
                logger.warning("Пропускаю пустой/слишком короткий документ: %s", name)
                continue
            all_chunks.extend(
                chunk_document(Path(name).stem, text, settings.chunk_size, settings.chunk_overlap)
            )
        if all_chunks:
            vectors = self.embedder.embed_documents([c.text for c in all_chunks])
            self.store.add(all_chunks, vectors)
            self.store.save(settings.index_dir)
        self.retriever.invalidate()
        logger.info("Проиндексировано: %d документов, %d чанков", len(self.list_documents()), len(all_chunks))
        return {"documents": len(self.list_documents()), "chunks": len(all_chunks)}

    @staticmethod
    def _read_document(path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        return path.read_text(encoding="utf-8", errors="ignore")

    # ---------- ответ ----------

    def answer(self, question: str, top_k: int, mode: str = "hybrid") -> dict:
        t0 = time.perf_counter()
        hits = self.retriever.search(
            question,
            top_k=top_k,
            mode=mode,
            candidates=settings.candidates_per_retriever,
        )
        retrieval_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        if self.llm.enabled:
            answer_text = self.llm.generate(question, hits)
        else:
            answer_text = extractive_answer(question, hits, self.embedder)
        generation_ms = (time.perf_counter() - t1) * 1000

        return {
            "answer": answer_text,
            "llm_used": self.llm.enabled,
            "mode": mode,
            "sources": [
                {
                    "n": i,
                    "chunk_id": h.chunk.id,
                    "doc_title": h.chunk.doc_title,
                    "score": round(h.score, 5),
                    "dense_rank": h.dense_rank,
                    "bm25_rank": h.bm25_rank,
                    "text": h.chunk.text,
                }
                for i, h in enumerate(hits, start=1)
            ],
            "timings": {"retrieval_ms": round(retrieval_ms, 1), "generation_ms": round(generation_ms, 1)},
        }

    def stats(self) -> dict:
        return {
            "documents": len(self.list_documents()),
            "chunks": len(self.store),
            "embed_model": settings.embed_model,
            "llm_enabled": self.llm.enabled,
            "llm_model": settings.llm_model if self.llm.enabled else None,
        }
