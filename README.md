# Agro-Botany RAG & Product Linker System

A production-ready, Python RAG backend that powers a mobile-app chatbot and a
web widget for an ecological agriculture company
([ekolojiktarim.com.tr](https://www.ekolojiktarim.com.tr/)).

The AI acts as an **expert Agricultural Engineer (Ziraat Mühendisi)** focused
strictly on **organic plant nutrition, sustainable fertilization, soil health,
and botany education** — with hard safety guardrails and automatic language
matching.

---

## Screenshots

The mobile app (Expo / React Native) mirrors the company site with Home,
Products, Academy, and AI Assistant tabs, all driven by live scraped data and
the RAG backend.

| Home | Products |
| --- | --- |
| ![Home](docs/screenshots/home.png) | ![Products](docs/screenshots/products.png) |

| Academy | AI Assistant |
| --- | --- |
| ![Academy](docs/screenshots/articles.png) | ![AI Assistant](docs/screenshots/chat.png) |

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

> **Note on a fresh clone:** the repo ships the code and the scraped
> `products.json` / `articles.json`, but **not** the botany knowledge base.
> The vector store (`data/vector_store/`, ~700 MB) and the source PDFs
> (`docs/books/`) are gitignored because of their size. On a new machine you
> either copy those two folders over manually, or rebuild them with steps 4–5
> below. Without them the API still runs, but the assistant has no botany
> knowledge to ground its answers. See **Running on a new machine** at the end.

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

## Mobile app

The `mobile-app/` folder is an Expo (React Native) app with Home, Products,
Academy, and Chat tabs. It talks to the same backend API.

```bash
cd mobile-app
npm install
npm run web        # browser preview
npx expo start     # dev server for Expo Go / device
```

**Point it at your backend.** A physical phone cannot reach `127.0.0.1` — that
is the phone itself. Set `API_BASE` in `mobile-app/src/api.ts` to the host
machine's LAN IP (both devices on the same Wi-Fi), e.g.:

```ts
export const API_BASE = "http://192.168.1.103:8000";
```

The IP is assigned by your router (DHCP) and can change; check it with
`ipconfig` (Windows) / `ifconfig` (Unix) and update it here. Also allow the
backend port through the OS firewall so the phone can connect.

**Build an installable APK.** Cloud build via EAS
(`eas build -p android --profile preview`), or a local Gradle build after
`npx expo prebuild -p android` → `./gradlew assembleRelease`. The self-contained
release APK lands in
`android/app/build/outputs/apk/release/app-release.apk`.

---

## Running on a new machine

A `git clone` alone is **not** a fully working system. Checklist:

1. **Python deps** — `pip install -r requirements.txt`.
2. **LM Studio** — install it, download a chat model (e.g. Gemma) and an
   embedding model (e.g. bge-m3), start the local server on port `1234`, and
   set the exact model ids in `.env` (copy `.env.example`).
3. **Knowledge base** — copy `data/vector_store/` and `docs/books/` from the
   original machine, **or** rebuild with `python -m src.fetch_books` +
   `python -m src.ingest`. (A rebuild is *similar* but not identical — the
   Internet Archive returns different books over time.)
4. **Backend** — `uvicorn src.main:app --host 0.0.0.0 --port 8000`.
5. **Mobile app** — `npm install`, set `API_BASE` to the new machine's LAN IP,
   then rebuild the APK (see above).

Catalog data (`products.json`, `articles.json`) is committed, so the Products
and Academy tabs work immediately; re-run `python -m src.scraper` /
`python -m src.articles_scraper` only to refresh them.
