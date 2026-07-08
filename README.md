# RAG Agent

A self-contained Retrieval-Augmented Generation agent: upload documents, ask
questions about them in a chat UI, and watch the system observe itself —
latency, token spend, cost, and answer quality — through built-in monitoring
and an LLM-judged eval harness.

Built as a demonstration of production-minded AI engineering practices, not
just a model call in a loop.

![status](https://img.shields.io/badge/status-demo--ready-brightgreen)

## What's inside

| Requirement                          | Where                                                          |
| ------------------------------------- | --------------------------------------------------------------- |
| Read files & answer questions         | `app/rag/` (loaders, chunking, vector search, generation)        |
| Q&A chat UI                           | `static/index.html` → **Chat** tab                               |
| File upload UI                        | **Documents** tab — PDF, DOCX, TXT, MD                            |
| Agent monitoring / observability       | SQLite trace log + **Monitoring** & **Traces** tabs (latency, tokens, cost, error rate, time series) |
| Evals                                 | `eval/` — gold Q&A set graded by an LLM judge, runnable from the **Eval** tab or CLI |
| Git-deployable                        | `Dockerfile`, `docker-compose.yml`, GitHub Actions CI            |

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Browser (static/*)              │
                    │   Chat · Documents · Monitoring · Traces · Eval │
                    └───────────────────────┬───────────────────────┘
                                            │ fetch() / REST (JSON)
                    ┌───────────────────────▼───────────────────────┐
                    │                 FastAPI (app/main.py)          │
                    │  routers: documents · query · metrics · eval   │
                    └──────┬───────────────────────┬─────────────────┘
                           │                        │
              ┌────────────▼───────────┐  ┌─────────▼─────────────┐
              │   RAG pipeline          │  │   Observability        │
              │   (app/rag/pipeline.py) │  │   (app/observability/) │
              │                         │  │                         │
              │ 1. load + chunk file    │  │ every query/eval call   │
              │ 2. embed + upsert       │  │ writes a trace row:     │
              │    (ChromaDB, local)    │  │ latency, tokens, cost,  │
              │ 3. retrieve top-k       │  │ error → SQLite          │
              │ 4. prompt + generate    │  └─────────┬─────────────┘
              │    (Gemini API)         │            │
              └────────────┬────────────┘  ┌─────────▼─────────────┐
                           │               │  metrics/summary,      │
                           │               │  metrics/timeseries,   │
                           │               │  metrics/traces        │
                           │               └─────────────────────────┘
              ┌────────────▼────────────┐
              │  ChromaDB (persistent,  │
              │  on-disk, built-in ONNX │
              │  embeddings — no extra  │
              │  API key required)      │
              └──────────────────────────┘
```

## Design decisions (and why)

- **Gemini for generation, ChromaDB's built-in embeddings for retrieval.**
  Gemini has a free API tier (via Google AI Studio), which makes this cheap
  to run and demo end-to-end. Retrieval still uses Chroma's bundled ONNX
  MiniLM embedding model rather than a separate embeddings API call —
  one less network dependency, and it keeps the vector store fully local.
- **SQLite over a hosted observability platform.** The goal is to show the
  *shape* of agent observability (structured traces, latency percentiles,
  token/cost accounting, an evals loop) without requiring the reviewer to
  sign up for LangSmith/Arize/etc. just to run a take-home. The trace
  schema (`app/db.py`) is the part that would port directly to a real
  tracing backend.
- **Hand-rolled chunker instead of a LangChain dependency.** At this scope,
  a recursive character splitter is ~40 lines and every line is inspectable
  — worth it for a project meant to demonstrate understanding of RAG
  internals rather than wrapping a framework.
- **No build step for the frontend.** Plain HTML/JS + Tailwind/Chart.js via
  CDN means `docker run` is the entire deploy story; no Node toolchain to
  install, version, or go stale.
- **LLM-as-judge eval, not string matching.** Answers are free text with
  citations, so exact-match scoring would mostly measure phrasing. The
  judge call uses Gemini's structured-output mode (`response_mime_type:
  application/json` + a JSON schema) so scores are always machine-parseable,
  not prose the model might phrase inconsistently.

## Quickstart

### Option A — Docker (recommended)

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)

docker compose up --build
```

Open http://localhost:8000.

### Option B — local Python

```bash
python -m venv .venv
. .venv/Scripts/Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # macOS/Linux

pip install -r requirements-dev.txt
cp .env.example .env   # set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)

uvicorn app.main:app --reload
```

Open http://localhost:8000.

### Option C — Render (public demo link)

`render.yaml` is a Render Blueprint spec for the free web-service tier:

1. On [Render](https://render.com), **New +** → **Blueprint** → connect this repo.
2. Render detects `render.yaml` and prompts for `GEMINI_API_KEY` (kept out of
   the repo, entered directly in Render's dashboard).
3. Deploy — you get a public `*.onrender.com` URL.

Free tier notes: the service sleeps after ~15 min idle (cold start ~30-60s on
the next request), and has no persistent disk, so uploaded documents and
trace history reset whenever the container restarts.

### Try it end-to-end

1. **Documents** tab → upload `sample_docs/employee_handbook.md` (or your own PDF/DOCX/TXT/MD).
2. **Chat** tab → ask "How many PTO days do employees get?"
3. **Monitoring** tab → see the query show up with latency/cost.
4. **Eval** tab → click **Run Eval** to grade the system against
   `eval/eval_set.json` (a 5-question gold set written against the sample
   handbook — seed it first via `python -m eval.seed_sample_docs`, or just
   upload it through the UI).

## Configuration

All settings are environment variables (see `.env.example`):

| Variable            | Default              | Notes                                             |
| -------------------- | --------------------- | -------------------------------------------------- |
| `GEMINI_API_KEY`     | —                     | required (free tier available)                     |
| `GEMINI_MODEL`       | `gemini-2.5-flash`    | `gemini-3.5-flash` also works but its free tier caps at 20 requests/day |
| `CHUNK_SIZE`         | `1000`                | characters per chunk                               |
| `CHUNK_OVERLAP`      | `150`                 | character overlap between chunks                   |
| `TOP_K`              | `4`                   | chunks retrieved per query                         |

## API reference

| Method   | Path                     | Purpose                                    |
| -------- | ------------------------ | ------------------------------------------- |
| `POST`   | `/api/documents/upload`  | upload + chunk + index a file               |
| `GET`    | `/api/documents`         | list indexed documents                      |
| `DELETE` | `/api/documents/{id}`    | remove a document and its chunks            |
| `POST`   | `/api/query`             | ask a question, get a cited answer          |
| `GET`    | `/api/metrics/summary`   | aggregate stats (latency, cost, error rate) |
| `GET`    | `/api/metrics/timeseries`| hourly query volume/latency for charts      |
| `GET`    | `/api/metrics/traces`    | paginated raw trace log                     |
| `POST`   | `/api/eval/run`          | run the eval set, save + return a report    |
| `GET`    | `/api/eval/latest`       | fetch the most recent eval report           |
| `GET`    | `/health`                | liveness check (used by Docker healthcheck) |

## Project structure

```
app/
  main.py                FastAPI app, router wiring
  config.py               env-driven settings
  db.py                   SQLite schema + connection helper
  models.py                Pydantic request/response models
  eval_runner.py          shared eval logic (used by API + CLI)
  rag/
    loaders.py             PDF/DOCX/TXT/MD -> plain text
    chunking.py             recursive character splitter
    vectorstore.py          ChromaDB wrapper (add/query/delete)
    pipeline.py              retrieve -> prompt -> generate -> trace
  observability/
    tracing.py               cost estimation + trace persistence
    metrics.py               summary stats, time series, trace listing
  routers/
    documents.py, query.py, metrics.py, eval.py
static/                   vanilla HTML/JS/CSS UI (no build step)
eval/
  eval_set.json            gold Q&A pairs
  run_eval.py               CLI entry point
  seed_sample_docs.py       ingest sample_docs/ without going through HTTP
sample_docs/              a fictitious employee handbook for demo/eval
tests/                     pytest unit tests (chunking, health, eval scoring shape)
```

## Testing

```bash
pytest -v
```

Tests avoid live API calls (no `GEMINI_API_KEY` needed) — they cover
chunking correctness and app wiring (`/health`, router registration). The
eval harness itself *does* call the Gemini API and is exercised manually /
in a real environment, not in CI, to avoid needing a secret in every PR.

## Limitations / what I'd do next with more time

- Retrieval is single-vector cosine/L2 search — no re-ranking, no hybrid
  BM25+vector, no query rewriting.
- Trace storage is SQLite on a local volume — fine for one instance, would
  move to Postgres + a real tracing backend (Langfuse/Arize/Honeycomb) for
  multi-instance deployments.
- No auth — this is a local/demo deployment, not multi-tenant.
- Eval set is small (5 cases) and tied to the sample doc; a production
  eval suite would grow with every reported failure mode.
