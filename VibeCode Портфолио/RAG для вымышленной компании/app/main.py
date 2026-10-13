"""FastAPI-приложение: тонкий HTTP-слой над RAGPipeline."""
from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import BASE_DIR, ensure_dirs, settings
from .pipeline import SUPPORTED_EXTENSIONS, RAGPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

pipeline: RAGPipeline | None = None
STATIC_DIR = BASE_DIR / "static"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 МБ на файл


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    ensure_dirs()
    logger.info("Загружаю embedding-модель %s ...", settings.embed_model)
    pipeline = RAGPipeline()
    if len(pipeline.store) == 0 and pipeline.list_documents():
        logger.info("Индекс пуст — выполняю первичную индексацию документов...")
        result = pipeline.reindex()
        logger.info("Готово: %s", result)
    logger.info("Сервис запущен. LLM-режим: %s", "включён" if pipeline.llm.enabled else "выключен (retrieval-only)")
    yield


app = FastAPI(title="RAG Knowledge Assistant", version="1.0.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=settings.default_top_k, ge=1, le=10)
    search_mode: Literal["hybrid", "vector", "bm25"] = "hybrid"


def get_pipeline() -> RAGPipeline:
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Сервис ещё инициализируется, повторите запрос")
    return pipeline


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def api_status() -> dict:
    return get_pipeline().stats()


@app.get("/api/documents")
def api_documents() -> dict:
    return {"documents": get_pipeline().list_documents()}


@app.post("/api/chat")
def api_chat(request: ChatRequest) -> dict:
    return get_pipeline().answer(request.question, top_k=request.top_k, mode=request.search_mode)


@app.post("/api/upload")
async def api_upload(files: list[UploadFile] = File(...)) -> dict:
    pipe = get_pipeline()
    saved: list[str] = []
    for upload in files:
        filename = Path(upload.filename or "document.txt").name
        safe_name = re.sub(r"[^\w.\-]", "_", filename)
        if Path(safe_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Формат не поддерживается: {safe_name}. Допустимы: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            )
        data = await upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail=f"Файл {safe_name} больше 10 МБ")
        (settings.documents_dir / safe_name).write_bytes(data)
        saved.append(safe_name)
    result = pipe.reindex()
    return {"saved": saved, **result}


@app.post("/api/reindex")
def api_reindex() -> dict:
    return get_pipeline().reindex()
