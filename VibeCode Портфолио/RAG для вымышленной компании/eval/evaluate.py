"""Офлайн-оценка качества retrieval на размеченном наборе вопросов.

Метрики:
  * Recall@k — доля вопросов, где нужный документ попал в top-k;
  * MRR     — среднее 1/ранг первого релевантного результата.

Запуск из корня проекта:
    python -m eval.evaluate --mode hybrid
    python -m eval.evaluate --mode vector
    python -m eval.evaluate --mode bm25

Разметка — явно проставленный expected_doc, поэтому LLM для оценки не нужен:
скрипт работает полностью локально и воспроизводимо.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.pipeline import RAGPipeline

QUESTIONS_FILE = Path(__file__).parent / "questions.jsonl"
K_VALUES = (1, 3, 5)


def evaluate(pipeline: RAGPipeline, questions: list[dict], mode: str, candidates: int = 12) -> dict:
    hits_at = {k: 0 for k in K_VALUES}
    rr_sum = 0.0
    rows: list[tuple[int | None, str]] = []

    for item in questions:
        hits = pipeline.retriever.search(
            item["question"], top_k=max(K_VALUES), mode=mode, candidates=candidates
        )
        first_rank = next(
            (rank for rank, h in enumerate(hits, start=1) if h.chunk.doc_id == item["expected_doc"]),
            None,
        )
        for k in K_VALUES:
            if first_rank is not None and first_rank <= k:
                hits_at[k] += 1
        rr_sum += 1.0 / first_rank if first_rank else 0.0
        rows.append((first_rank, item["question"]))

    n = len(questions)
    return {
        "mode": mode,
        "n": n,
        "recall": {k: hits_at[k] / n for k in K_VALUES},
        "mrr": rr_sum / n,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "vector", "bm25"])
    parser.add_argument("--file", type=Path, default=QUESTIONS_FILE)
    parser.add_argument("--show-misses", action="store_true", help="показать только вопросы-промахи")
    args = parser.parse_args()

    questions = [json.loads(line) for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip()]

    pipeline = RAGPipeline()
    if len(pipeline.store) == 0:
        pipeline.reindex()

    result = evaluate(pipeline, questions, mode=args.mode)

    print(f"\n=== Retrieval evaluation · mode={result['mode']} · n={result['n']} ===")
    for rank, question in result["rows"]:
        if args.show_misses and rank is not None:
            continue
        marker = f"rank {rank}" if rank else "MISS "
        print(f"  [{marker:>7}] {question}")
    recall = "  ".join(f"Recall@{k} = {v:.3f}" for k, v in result["recall"].items())
    print(f"\n  {recall}   MRR = {result['mrr']:.3f}\n")


if __name__ == "__main__":
    main()
