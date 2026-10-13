"""Конфигурация приложения.

Все параметры задаются через переменные окружения (см. .env.example).
Значения по умолчанию подобраны так, чтобы проект работал «из коробки»
без единой переменной окружения — включая режим без LLM-ключа.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Подхватываем переменные из .env в корне проекта, если файл есть.
# python-dotenv необязателен: без него работают обычные переменные окружения.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    """Параметры пайплайна. Экземпляр-синглтон создаётся при импорте модуля."""

    data_dir: Path = Path(os.getenv("RAG_DATA_DIR", BASE_DIR / "data"))
    documents_subdir: str = "documents"
    index_subdir: str = "index"

    # --- Модель эмбеддингов (многоязычная, 512 токенов контекста) ---
    embed_model: str = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-base")

    # --- Чанкинг ---
    chunk_size: int = _int("CHUNK_SIZE", 1100)
    chunk_overlap: int = _int("CHUNK_OVERLAP", 200)

    # --- Поиск ---
    default_top_k: int = _int("TOP_K", 4)
    candidates_per_retriever: int = _int("CANDIDATES", 12)
    rrf_k: int = _int("RRF_K", 60)  # константа сглаживания Reciprocal Rank Fusion
    # Отсев слабых лексических совпадений до фьюжна: кандидат BM25 должен набрать
    # не меньше этой доли от топ-скора выдачи. Защищает RRF от «шумных» совпадений
    # по общим словам («сотрудник», «компания»), которые иначе вытесняют
    # семантически верные результаты dense-поиска.
    sparse_rel_threshold: float = _float("SPARSE_REL_THRESHOLD", 0.35)

    # --- LLM (OpenAI-совместимый API: OpenAI, Groq, OpenRouter, Ollama и т.д.) ---
    llm_api_key: str = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = _float("LLM_TEMPERATURE", 0.2)

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / self.documents_subdir

    @property
    def index_dir(self) -> Path:
        return self.data_dir / self.index_subdir

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())


settings = Settings()


def ensure_dirs() -> None:
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    settings.index_dir.mkdir(parents=True, exist_ok=True)
