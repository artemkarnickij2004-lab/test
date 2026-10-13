# RAG Knowledge Assistant

> 🇷🇺 [Русская версия](README.ru.md)

A production-minded **Retrieval-Augmented Generation** demo: a chat assistant that answers questions over a document knowledge base with **hybrid retrieval (dense vectors + BM25)**, **clickable citations**, **offline quality evaluation** and a clean web UI. Ships with a fictional company's HR handbook (Russian + English) to demonstrate **cross-lingual retrieval**.

Built as a portfolio piece: the emphasis is not on "yet another LangChain wrapper", but on measurable retrieval quality, honest trade-offs and reproducible experiments.

## Features

- **Hybrid retrieval** — dense embeddings (E5 multilingual) + sparse BM25, fused with **Reciprocal Rank Fusion (RRF)**
  - …with two deliberate, measured improvements: **relative-score BM25 candidate filtering** and a **top-1 per-retriever guarantee** (see *Design decisions*)
- **Citations** — every answer references numbered sources; the UI shows each retrieved chunk with its RRF score and dense/sparse ranks
- **Cross-lingual search** — ask in Russian, retrieve from English documents (and vice versa)
- **Runs with or without an LLM key** — any OpenAI-compatible API (OpenAI, Groq, OpenRouter, Ollama…). Without a key it degrades gracefully to an extractive *retrieval-only* mode
- **Offline evaluation** — `python -m eval.evaluate` computes Recall@k / MRR for three search modes on a labeled set; no LLM needed, fully reproducible
- **Upload your own docs** — `.md`, `.txt`, `.pdf` via the UI or API
- **FastAPI backend + zero-dependency frontend** — a single self-contained HTML page (no CDN, works offline)
- **Tests, Docker, compose** — `pytest`, one-command container build with a pre-warmed embedding model

## Architecture

```
 documents (.md/.txt/.pdf)
        │
        ▼
 structure-aware chunking ─────────────► 500–1100 chars, overlap 200,
 (recursive splitter,                     markdown-heading titles as metadata
  paragraph → sentence → word)
        │
        ▼
 E5 embeddings (prefix "passage: ")          BM25 index (stopword-filtered,
 embedding: intfloat/multilingual-e5-base    relative-score candidate filter)
        │                                            │
        ▼                                            ▼
 NumPy vector store (exact cosine)        rank_bm25 (Okapi)
        └───────────────┬────────────────────────────┘
                        ▼
        RRF fusion  +  relative BM25 threshold  +  top-1 guarantee
                        ▼
              top-k chunks (k = 2…8)
                        ▼
   ┌── LLM key set ──► answer generated strictly from context,
   │                   citations [n] after each fact
   └── no key ───────► extractive answer: sentences most similar
                       to the question, with citations
```

## Quick start

```bash
git clone <repo> && cd rag-portfolio
python -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU build
pip install -r requirements.txt

# optional: generated answers (any OpenAI-compatible API)
cp .env.example .env   # then set LLM_API_KEY

uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
git clone <repo>
cd rag-portfolio
python -m venv .venv
.venv\Scripts\Activate.ps1      # CMD instead: .venv\Scripts\activate.bat
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

copy .env.example .env          # optional: set LLM_API_KEY

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If PowerShell blocks venv activation: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`.
If `python` is not found — install from python.org with "Add Python to PATH" checked, or use `py -m venv .venv`.
</details>

On the first run the app indexes the bundled knowledge base automatically (~15 s on CPU). Without `LLM_API_KEY` it works in **retrieval-only** mode.

<details>
<summary><b>No web server: console mode (CLI)</b></summary>

If you don't need the web UI, you can chat with the RAG system right in the terminal — no LLM key required either:

```bash
python -m scripts.cli
# commands inside the chat: /mode hybrid|vector|bm25, /k N, /exit
```

To see retrieval quality on the labeled set, run `python -m eval.evaluate --mode hybrid`.
</details>

### Docker

```bash
docker compose up --build        # or: docker build -t rag-demo . && docker run -p 8000:8000 rag-demo
LLM_API_KEY=sk-... docker compose up --build   # with LLM answers
```

## Quality evaluation

Retrieval quality is measured on 16 labeled questions (`eval/questions.jsonl`), each annotated with the expected source document — so **no LLM is required** for evaluation and results are deterministic:

```bash
python -m eval.evaluate --mode hybrid    # or: vector | bm25
```

Measured on this repo's corpus (CPU, `multilingual-e5-base`):

| Search mode      | Recall@1 | Recall@3 | Recall@5 | MRR   |
|------------------|---------:|---------:|---------:|------:|
| **hybrid**       | **0.94** | **1.00** | **1.00** | 0.96  |
| vector only      | 0.94     | **1.00** | **1.00** | **0.97** |
| BM25 only        | 0.69     | 0.75     | 0.75     | 0.72  |

Embedding model comparison (hybrid mode, same corpus):

| Embedding model               | Recall@1 | Recall@5 | MRR  |
|-------------------------------|---------:|---------:|-----:|
| `multilingual-e5-small`       | 0.81     | 0.94     | 0.86 |
| `multilingual-e5-base` (default) | **0.94** | **1.00** | **0.96** |

Two findings worth highlighting (they shaped the code):

1. **Naive RRF penalizes unique finds.** A document ranked #1 by dense search but missed by BM25 (cross-lingual query, zero lexical overlap) scored *lower* than a mid-ranked document found by both. Fix: the final list always retains each retriever's top-1 — hybrid Recall@5 went 0.94 → 1.00 without hurting other queries.
2. **BM25 needs stopword filtering and candidate thresholds.** Bare BM25 on Russian text ranks documents matching "на / и / сколько" above relevant ones, which then poisons the fusion. Stopword filtering + dropping sparse candidates below 0.35 × top-score cleaned this up.

In production I would add a cross-encoder reranking stage on top of the fused candidates — the retrieval layer here is structured to make that a ~20-line change (see *Roadmap*).

## Configuration

All settings are environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `LLM_API_KEY` | *(empty)* | Set → generated answers with citations; empty → extractive retrieval-only mode |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint (Ollama: `http://localhost:11434/v1`) |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model name |
| `EMBED_MODEL` | `intfloat/multilingual-e5-base` | Sentence-Transformers embedding model |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1100` / `200` | Chunking parameters (chars) |
| `TOP_K` / `CANDIDATES` | `4` / `12` | Returned chunks / per-retriever candidate pool |
| `RRF_K` | `60` | RRF smoothing constant |
| `SPARSE_REL_THRESHOLD` | `0.35` | Min BM25 score as a fraction of the best candidate |

## Project structure

```
rag-portfolio/
├── app/
│   ├── main.py          # FastAPI HTTP layer (chat / upload / reindex / status)
│   ├── pipeline.py      # RAG orchestration: ingest → index → answer (+extractive fallback)
│   ├── chunking.py      # structure-aware recursive splitter with overlap
│   ├── embeddings.py    # E5 embeddings (query/passage prefixes), cached singleton
│   ├── store.py         # NumPy vector store, exact cosine search, disk persistence
│   ├── retrieval.py     # BM25 + dense + RRF fusion, stopwords, thresholds
│   ├── llm.py           # OpenAI-compatible chat client + grounded prompt
│   └── config.py        # env-based settings
├── static/index.html    # self-contained chat UI (no external resources)
├── data/documents/      # demo knowledge base (RU + EN company handbook)
├── eval/                # labeled questions + Recall@k/MRR evaluation script
├── tests/               # chunking & fusion unit tests (no models needed)
├── Dockerfile / docker-compose.yml
└── requirements.txt
```

## Design decisions

- **NumPy instead of FAISS/Qdrant.** At demo scale (thousands of chunks) an exact brute-force cosine search is single-digit milliseconds and removes an entire service from the deployment. The storage is isolated behind a small interface (`VectorStore`), so swapping in Qdrant/pgvector is a change to one file — which I would do at ~100k+ chunks.
- **E5 models need `query:`/`passage:` prefixes.** Both are applied centrally in `embeddings.py`; forgetting them measurably degrades quality.
- **Structure-aware chunking > fixed-size slicing.** The splitter prefers paragraph, then sentence, then word boundaries, and prepends document titles into chunk metadata. Chunk quality is the single highest-leverage part of a RAG system.
- **Retrieval-only mode is a feature, not a limitation.** The demo is fully usable without any paid API, and the extractive fallback doubles as an honest "show me what the retriever found" debugging view.
- **Evaluation without an LLM.** Questions are labeled with their source document, so Retrieval metrics are cheap, deterministic and CI-friendly. LLM-based answer-quality scoring (e.g. RAGAS) is listed in the roadmap instead.

## Roadmap

- Cross-encoder reranker over fused candidates (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`)
- Swap `VectorStore` → Qdrant; incremental per-document reindexing
- Answer streaming (SSE), conversation memory with query rewriting
- RAGAS-based answer faithfulness metrics in CI
- Query expansion / HyDE for short ambiguous queries

## License

MIT
