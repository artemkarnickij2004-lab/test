"""Тесты чанкинга: размеры, перекрытие, метаданные. Нейросетевых зависимостей нет."""
from app.chunking import chunk_document, extract_title


SAMPLE = (
    "# Политика отпусков\n\n"
    + "Каждому сотруднику положен отпуск 28 календарных дней. Это базовая гарантия. " * 12
    + "\n\n"
    + "Отпуск можно делить на части, одна из которых не менее двух недель. " * 10
)


def test_extract_title_from_h1():
    assert extract_title(SAMPLE, fallback="doc") == "Политика отпусков"


def test_extract_title_fallback():
    assert extract_title("просто текст без заголовка", fallback="doc") == "doc"


def test_chunks_respect_max_size():
    chunks = chunk_document("doc", SAMPLE, chunk_size=400, overlap=60)
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)
    # весь текст сохранился (нет потерь символов смысловой части)
    joined = " ".join(c.text for c in chunks)
    assert "28 календарных дней" in joined


def test_chunks_have_overlap():
    chunks = chunk_document("doc", SAMPLE, chunk_size=400, overlap=60)
    assert len(chunks) >= 2
    # перекрытие: начало следующего чанка встречается в конце предыдущего
    first, second = chunks[0].text, chunks[1].text
    overlap_part = first[-60:]
    assert any(word and word in second[:80] for word in overlap_part.split())


def test_short_document_single_chunk():
    text = "# Заголовок\n\nКороткий текст."
    chunks = chunk_document("doc", text, chunk_size=1000, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].doc_title == "Заголовок"
    assert chunks[0].id == "doc::c0"


def test_long_word_hard_cut():
    text = "а" * 2500 + " конец"
    chunks = chunk_document("doc", text, chunk_size=1000, overlap=0)
    assert len(chunks) >= 2
    assert all(len(c.text) <= 1000 for c in chunks)
    assert chunks[-1].text.endswith("конец")
