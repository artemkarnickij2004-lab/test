"""Структуро-осведомлённый чанкинг документов.

Рекурсивный сплиттер с приоритетом разделителей: сначала пытается резать
по абзацам, затем по строкам, предложениям, словам — чтобы чанки не ломали
смысловые границы. Это один из самых недооценённых факторов качества RAG.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Порядок важен: от самых «сильных» границ к самым слабым.
SEPARATORS: list[str] = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

_TITLE_RE = re.compile(r"^#\s+(.+)$", flags=re.MULTILINE)


@dataclass
class Chunk:
    """Атомарная единица индексации и поиска."""

    id: str
    doc_id: str
    doc_title: str
    chunk_index: int
    text: str


def extract_title(text: str, fallback: str) -> str:
    """Берём первый Markdown-заголовок H1 как название документа."""
    match = _TITLE_RE.search(text)
    return match.group(1).strip() if match else fallback


def _recursive_split(text: str, chunk_size: int, seps: list[str]) -> list[str]:
    """Рекурсивно режем текст на куски не длиннее chunk_size."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    sep_idx = next((i for i, s in enumerate(seps) if s and s in text), None)
    if sep_idx is None:
        # Ни один разделитель не найден (очень длинное «слово») — режем жёстко.
        return [t for i in range(0, len(text), chunk_size) if (t := text[i : i + chunk_size].strip())]

    sep = seps[sep_idx]
    parts = text.split(sep)
    # Возвращаем разделитель в конец каждого куска, чтобы не терять текст.
    pieces = [p + sep for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])

    out: list[str] = []
    for piece in pieces:
        if len(piece) <= chunk_size:
            out.append(piece)
        else:  # кусок всё ещё велик — рекурсия с более слабыми разделителями
            out.extend(_recursive_split(piece, chunk_size, seps[sep_idx + 1 :]))
    return out


def _word_boundary_tail(text: str, overlap: int) -> str:
    """Хвост предыдущего чанка для перекрытия, начинающийся с границы слова."""
    if overlap <= 0 or not text:
        return ""
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def _merge_splits(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    """Склеиваем мелкие куски в чанки целевого размера с перекрытием."""
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if len(current) + len(piece) <= chunk_size:
            current += piece
            continue
        if current.strip():
            chunks.append(current.strip())
        tail = _word_boundary_tail(current, overlap)
        current = (tail + piece) if len(tail) + len(piece) <= chunk_size else piece
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_document(doc_id: str, text: str, chunk_size: int = 1100, overlap: int = 200) -> list[Chunk]:
    """Разбивает документ на чанки с метаданными (название, номер чанка)."""
    title = extract_title(text, fallback=doc_id)
    pieces = _recursive_split(text, chunk_size, SEPARATORS)
    merged = _merge_splits(pieces, chunk_size, overlap)
    return [
        Chunk(id=f"{doc_id}::c{i}", doc_id=doc_id, doc_title=title, chunk_index=i, text=chunk)
        for i, chunk in enumerate(merged)
    ]
