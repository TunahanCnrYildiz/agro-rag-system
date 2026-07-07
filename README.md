# Agro-Botany RAG & Product Linker System

A production-ready, Python RAG backend that powers a mobile-app chatbot and a
web widget for an ecological agriculture company
([ekolojiktarim.com.tr](https://www.ekolojiktarim.com.tr/)).

The AI acts as an **expert Agricultural Engineer (Ziraat Mühendisi)** focused
strictly on **organic plant nutrition, sustainable fertilization, soil health,
and botany education** — with hard safety guardrails and automatic language
matching.

---

## Architecture

```
User query ─▶ FastAPI /api/chat ─▶ RAG Engine
                                     ├─ Botany retrieval   (ChromaDB, local embeddings)
                                     ├─ Product matching   (scraped catalog JSON)
                                     └─ LM Studio chat      (Gemma, OpenAI-compatible)
                                           ▲
                                   Strict system prompt
                                   (persona + guardrails + language rule)
```

| Layer            | Choice                                             |
| ---------------- | -------------------------------------------------- |
| LLM provider     | LM Studio local server (`http://localhost:1234/v1`)|
| RAG framework    | LangChain                                          |
| Vector DB        | ChromaDB (persistent, local)                       |
| Backend API      | FastAPI + Uvicorn                                  |
| Doc processing   | pypdf + RecursiveCharacterTextSplitter (1000/200)  |
| Scraping         | requests + BeautifulSoup                           |

---

## Safety guardrails (enforced on every query)

- **No disease diagnosis.** Describes general symptom patterns only.
- **No chemical pesticides / medical treatments / illegal substances.**
- On such requests it **politely refuses and redirects** to professional
  in-field analysis — in the user's own language.
- **Advisory, non-prescriptive** tone ("bunun sebebi ... olabilir").
- **Language matching:** the full response is generated in the same language
  as the user's query.

Guardrails live in `src/config.py` (`SYSTEM_PROMPT`) and are injected into the
system message on every call in `src/engine.py`.

---

## Project layout

```
agro-rag-system/
├── data/vector_store/     # persistent ChromaDB files (generated)
├── docs/
│   ├── books/             # put botany PDFs / TXTs here
│   └── products/          # scraped products.json (generated)
├── src/
│   ├── config.py          # endpoints, models, paths, SYSTEM_PROMPT
│   ├── scraper.py         # crawl catalog (mock fallback)
│   ├── ingest.py          # chunk + embed books -> Chroma
│   ├── engine.py          # retrieval + product match + LM Studio
│   └── main.py            # FastAPI app
├── requirements.txt
└── README.md
```

---

## Quickstart

### 1. Install dependencies

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start LM Studio

In LM Studio, load a chat model (e.g. a local Gemma build) and an embedding
model, then start the **local server** on port `1234`. Set the exact model
names in a `.env` file (copy `.env.example`).

### 3. Build the product catalog

```bash
python -m src.scraper          # live crawl, mock fallback on failure
python -m src.scraper --mock   # force offline mock catalog
```

Writes `docs/products/products.json`.

### 4. Get botany documents

Either drop your own PDFs / TXTs into `docs/books/`, or bulk-download
open-access / public-domain botany books from the Internet Archive:

```bash
python -m src.fetch_books --max 50          # plant-nutrition focused, 50 books
python -m src.fetch_books --query "subject:(mycorrhiza)" --max 20
```

Only freely downloadable, non-restricted items are fetched (borrow-only / DRM
items are skipped), and each PDF is validated before it is kept.

### 5. Ingest botany documents

With documents in `docs/books/`:

```bash
python -m src.ingest           # incremental
python -m src.ingest --reset   # rebuild collection
```

Persists embeddings to `data/vector_store/`. (Requires LM Studio's embedding
model to be running.)

### 6. Run the API

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for the interactive Swagger UI.

---

## API

### `POST /api/chat`

Request:

```json
{
  "message": "Domates yapraklarım sararıyor, ne önerirsiniz?",
  "history": [{"role": "user", "content": "Merhaba"}],
  "stream": false
}
```

Unified response:

```json
{
  "answer": "Yaprak sararmasının sebebi azot eksikliği olabilir ...",
  "recommended_products": [
    {"title": "Solucan Gübresi (Vermikompost)", "link": "https://..."}
  ]
}
```

Set `"stream": true` to receive Server-Sent Events: a first `products` event,
then `token` events, then a `done` event.

### `GET /health`

Liveness probe.

---

## Execution log

- Project scaffolded with modular `src/` layout per spec.
- `scraper.py` includes a curated mock catalog so the full pipeline runs
  offline / when the live site rate-limits.
- `ingest.py` streams files page-by-page and flushes to Chroma in fixed
  batches to avoid loading hundreds of books into memory.
- `engine.py` combines botany retrieval + lexical product matching and injects
  the strict persona/guardrail prompt on every call.
- `main.py` exposes `/api/chat` (unified + streaming) with permissive CORS for
  mobile and web clients.
