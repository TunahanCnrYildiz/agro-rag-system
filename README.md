# Agro-Botany RAG & Product Linker System

A production-ready, Python RAG backend that powers a mobile-app chatbot and a
web widget for an ecological agriculture company
([ekolojiktarim.com.tr](https://www.ekolojiktarim.com.tr/)).

The assistant reasons and communicates **in the style of** an expert
Agricultural Engineer (Ziraat Mühendisi) — knowledgeable, precise, advisory —
but it is an AI and **never presents itself as a licensed professional**. That
distinction is enforced in the system prompt, not just implied here (see
`# IDENTITY` in `src/config.py`).

It covers **any plant-related topic** — nutrition, soil health, physiology,
horticulture, agronomy, propagation, irrigation, post-harvest, and the
**organic** management of plant diseases and pests — across all crops. Non-plant
topics (animal husbandry, economics, machinery) are out of scope. Two hard rules
always hold: **never give a definitive disease diagnosis** and **never recommend
chemical pesticides/drugs**. Plus automatic language matching and off-scope
refusal.

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
| Chat LLM         | Selectable: LM Studio local server (default) or OpenRouter (`CHAT_PROVIDER`) |
| Embeddings       | bge-m3, local or hosted — the store is stamped with a stable logical identity so switching host needs no re-index |
| RAG framework    | LangChain                                          |
| Vector DB        | ChromaDB (persistent, local)                       |
| Backend API      | FastAPI + Uvicorn                                  |
| Doc processing   | pypdfium2 + RecursiveCharacterTextSplitter (1000/200)|
| Scraping         | requests + BeautifulSoup                           |
| Tests / quality  | pytest (262 tests) + `evals/` quality harness (55 cases) + CI on push/PR |

The chat provider is a config swap, not a code change: `CHAT_PROVIDER=local`
(default) talks to LM Studio, `CHAT_PROVIDER=openrouter` talks to a hosted
OpenAI-compatible endpoint. Embeddings are configured independently — see
`.env.example`, which documents the traps (setting only `EMBEDDING_BASE_URL`
still sends the LM Studio dummy key to the provider and 401s).

**Cross-lingual retrieval.** The corpus is ~half Turkish, ~half English. A Turkish
query about a crop covered only in the English sources (FAO/OpenAlex) would
otherwise never reach it — generic Turkish fertilization chunks clear the
relevance floor and fill the result slots first. Each query is expanded through a
TR→EN crop-name lexicon (`engine.CROP_LEXICON`, e.g. `manyok → cassava`) and the
extra searches are fused by rank (RRF). It is deterministic and LLM-free; toggle
with `cross_lingual_retrieval`.

---

## Safety guardrails (enforced on every query)

- **No false credentials.** The assistant never claims to *be* a Ziraat
  Mühendisi, agronomist, or any licensed professional, and never opens a reply
  with "As an agricultural engineer…". It adopts the reasoning style, not the
  title.
- **No definitive disease diagnosis.** Describes likely causes/symptoms as
  possibilities and points to a professional for certainty.
- **No chemical pesticides / medical treatments / illegal substances** — even
  when asked directly. Disease/pest questions are answered with **organic,
  cultural, and biological** management (a helpful organic path, not a dead end).
- **Scope:** plant topics only. Non-plant questions get a brief refusal, and
  product suggestions are suppressed for them (LLM `[OFFSCOPE]` marker →
  `_strip_offscope` in `src/engine.py`).
- **Advisory, non-prescriptive** tone ("bunun sebebi ... olabilir").
- **Language matching:** the full response is generated in the same language
  as the user's query (works across languages via the multilingual embedder).

Guardrails live in `src/config.py` (`SYSTEM_PROMPT`) and are injected into the
system message on every call in `src/engine.py`. They are covered by unit tests
(`tests/test_engine.py`) and the eval harness (`evals/`).

---

## Project layout

```
agro-rag-system/
├── data/vector_store/     # persistent ChromaDB files (generated)
├── docs/
│   ├── books/             # put botany PDFs / TXTs here
│   └── products/          # scraped products.json (generated)
├── src/
│   ├── config.py            # endpoints, models, paths, SYSTEM_PROMPT
│   ├── scraper.py           # crawl product catalog (mock fallback)
│   ├── articles_scraper.py  # crawl academy articles
│   ├── scrape_utils.py      # shared HTTP crawl helpers (site scrapers)
│   ├── fetch_books.py       # download English books from Internet Archive
│   ├── fetch_dergipark.py   # harvest Turkish papers from DergiPark (OAI-PMH)
│   ├── fetch_openalex.py    # harvest global-crop OA papers from OpenAlex
│   ├── fetch_fao.py         # harvest plant docs from FAO repository (OAI-PMH)
│   ├── pdf_fetch_utils.py   # shared PDF stream/validate helpers (all fetchers)
│   ├── ingest.py            # chunk + embed docs -> Chroma (incremental)
│   ├── engine.py            # retrieval + product match + LM Studio
│   └── main.py              # FastAPI app
├── tests/                   # pytest unit tests (fetchers, ingest, engine, API)
├── evals/
│   ├── eval_set.py          # the 55 cases + their assertions
│   ├── run_eval.py          # scoring, ablation, corpus-dependence map
│   └── runs/                # per-sample answer log (generated, gitignored)
├── mobile-app/              # Expo / React Native client
├── web-widget/              # embeddable chat widget
├── Dockerfile               # backend image
├── docker-compose.yml       # container + local LM Studio + mounted store
├── requirements.txt
└── README.md
```

### Where the reasoning is written down

`docs/` holds more than generated data — it is the project's decision record:

| Path | What it is |
| --- | --- |
| `docs/deploy-runbook.md` | ordered go-live checklist |
| `docs/roadmap-deployment.md` | hosting strategy and trade-offs |
| `docs/roadmap-plant-wide-scope.md` | how the scope grew beyond one crop |
| `docs/global-sources-research.md` | which corpora were considered and why |
| `docs/superpowers/` | design specs, measurement write-ups, and raw eval dumps |

`docs/superpowers/` is the honest part of the history: it records which ideas
were tried, measured, and **rejected** — freshness-weighted retrieval, query
translation through the LLM, reranking, lexicon bridges, four rounds of corpus
mining that came back empty — with the evidence that killed each one. If you
want to know why something is *not* in this system, it is usually there.

---

## Quickstart

> **Note on a fresh clone — read this before cloning.** The repo ships the code
> and the scraped `products.json` / `articles.json`, but **not** the botany
> knowledge base. The vector store (`data/vector_store/`, **~1.7 GB**,
> 81,426 chunks from ~1,050 documents) and the source PDFs (`docs/books/`,
> **~5.2 GB**) are gitignored because of their size. On a new machine you either
> copy those two folders over manually, or rebuild them with steps 4–5 below.
> Without them the API still runs and answers, but nothing is grounded in the
> corpus — the model answers from its own knowledge alone. See **Running on a
> new machine** at the end.

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
open-access / public-domain material from three sources:

```bash
# English books from the Internet Archive (curated plant-nutrition sources)
python -m src.fetch_books --list-sources               # show curated sources
python -m src.fetch_books --max 50                     # fetch from all sources
python -m src.fetch_books --source soil_health --max 20  # one source only

# Turkish agriculture papers from DergiPark (OAI-PMH)
python -m src.fetch_dergipark --list-sets              # show matched journals
python -m src.fetch_dergipark --max 120                # harvest PDFs
python -m src.fetch_dergipark --clean-offtopic         # report livestock papers
python -m src.fetch_dergipark --clean-offtopic --apply # move them out + prune store

# Global-crop open-access papers from OpenAlex (cassava, sorghum, rice, ...)
python -m src.fetch_openalex --list-crops              # show curated gap crops
python -m src.fetch_openalex --dry-run --max 25        # preview candidates
python -m src.fetch_openalex --max 25 --per-crop 4     # harvest PDFs

# Plant-relevant English docs from the FAO Knowledge Repository (OAI-PMH)
python -m src.fetch_fao --list-sets                    # show OAI sets
python -m src.fetch_fao --dry-run --max 100            # preview candidates
python -m src.fetch_fao --max 100                      # harvest PDFs (fao_<id>.pdf)
```

Only freely downloadable, non-restricted items are fetched (borrow-only / DRM
items are skipped), and each PDF is validated before it is kept. The DergiPark
fetcher filters out off-topic (animal-science / fisheries) papers; the
`--clean-offtopic` pass reports (and with `--apply` removes) any that already
slipped into the corpus.

### 5. Ingest botany documents

With documents in `docs/books/`:

```bash
python -m src.ingest           # incremental: skips files already in the store
python -m src.ingest --force   # re-embed every file (e.g. after a filter change)
python -m src.ingest --reset   # drop the collection and rebuild from scratch
```

Persists embeddings to `data/vector_store/`. (Requires LM Studio's embedding
model to be running.) Ingestion is incremental — already-embedded files are
skipped, so re-runs only process new documents unless you pass `--force`.

### 6. Run the API

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for the interactive Swagger UI.

### 7. Or run the backend in Docker

```bash
docker compose up --build      # API on http://localhost:8000
```

The container still uses the **local** LM Studio (`host.docker.internal:1234`)
and the **local** vector store (`./data` is mounted as a volume, not baked into
the image). Running this does not affect non-Docker development.

---

## Deployment

Local is the default and nothing here is required to develop. Going hosted is a
**configuration change, not a code change** — set `CHAT_PROVIDER=openrouter`
plus a hosted embedding endpoint, attach a persistent disk for the vector store,
and deploy the existing image.

`docs/deploy-runbook.md` is the ordered go-live checklist, including a migration
trap that bit this project for real: a store stamped by older code records the
API model-id instead of the logical `bge-m3`, so the identity guard raises on
open and **every** retrieval fails. The vectors are fine — re-stamp, never
re-ingest.

What is deliberately *not* decided yet is the product question: which host and
which embedding vendor. At actual launch, `CORS_ALLOW_ORIGINS` must also be
narrowed off `*`.

---

## Testing & quality

Two layers: ordinary unit tests, and an eval harness that measures whether the
RAG actually works. The second is where most of the engineering effort went.

```bash
python -m pytest                    # 262 unit tests (fetchers, ingest, engine, API)
```

CI (`.github/workflows/tests.yml`) runs `pytest` on every push and PR. The eval
stays local — it needs LM Studio and the gitignored vector store.

### The eval harness

55 cases in `evals/eval_set.py`, scored on five independent dimensions:
retrieval, context relevance, product gating, answer grounding, and guardrail
compliance.

```bash
python -m evals.run_eval --fast     # retrieval + context only, no chat LLM (seconds)
python -m evals.run_eval            # full run: ~20 min, ~22s per case
python -m evals.run_eval --only <id|category>        # one case or category
python -m evals.run_eval --repeat 8 --only <id>      # sample a case 8 times
```

**Why sampling matters.** Generation is stochastic, so one clean run proves
little — a ~3% blank-answer bug once survived four consecutive green evals.
`--repeat N` samples each case N times; in a normal run a case passes only if
every sample passes.

### Does the corpus actually carry the answer?

A RAG eval that only checks the final answer cannot tell "the corpus supplied
this" from "the model already knew it". Two modes separate them:

```bash
python -m evals.run_eval --no-context --only local   # ablation: empty the corpus
python -m evals.run_eval --faithfulness --repeat 4   # corpus-dependence map
```

`--no-context` forces retrieval to return nothing; cases that claim to depend on
the corpus must then FAIL. `--faithfulness` runs each `corpus_fact` case both
normally and ablated and labels it **corpus-carried / model-carried /
retrieval-broken / corpus-harmful**. 23 of the 55 cases opt into this panel; it
is a drift guard, proving retrieval still reaches the sources it used to.

This distinction produced the project's most important finding, and it is not
the flattering one: **the corpus is not more accurate than the model — it is
more specific and more citable.** The panel is kept because it detects
regressions, not because a bigger number means better coverage.

### The harness is itself under test

Every answer is written to `evals/runs/<UTC>-<mode>.jsonl` (gitignored), which
makes it possible to re-score past runs without re-generating them. That paid
off: cases were reading red while the model had actually answered correctly,
because the matcher could not see values written as LaTeX (`$2\pm0,5^\circ$`) or
split by markdown emphasis (`**6 gram**`). Both were fixed by normalising the
searched text, never the anchor — and re-scoring the stored answers proved the
fix changed exactly the intended verdicts and nothing else.

The lesson is recorded because it generalises: **a measurement instrument's
blind spots look exactly like findings about the thing being measured.**

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
is the phone itself. The app reads the backend URL from an environment variable
and falls back to a hard-coded LAN address:

```ts
// mobile-app/src/api.ts
export const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE ?? "http://192.168.1.103:8000";
```

Prefer setting `EXPO_PUBLIC_API_BASE` at build time (that is what makes a hosted
deploy possible without touching source); edit the fallback only for quick local
work. The LAN IP is assigned by your router (DHCP) and can change — check it
with `ipconfig` (Windows) / `ifconfig` (Unix). Also allow the backend port
through the OS firewall so the phone can connect.

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
4. **Backend** — `uvicorn src.main:app --host 0.0.0.0 --port 8000`, or
   `docker compose up --build`.
5. **Mobile app** — `npm install`, set `EXPO_PUBLIC_API_BASE` to the new
   machine's LAN IP (or edit the fallback in `src/api.ts`), then rebuild the APK
   (see above).

Catalog data (`products.json`, `articles.json`) is committed, so the Products
and Academy tabs work immediately; re-run `python -m src.scraper` /
`python -m src.articles_scraper` only to refresh them.

---

## License

Released under the [MIT License](LICENSE) — © 2026 Tunahan Caner YILDIZ.

The licence covers the **code in this repository**. It does not cover the
third-party material the system ingests or links to: the botany corpus is
assembled from Internet Archive, DergiPark, OpenAlex and FAO sources under their
own terms, and the product catalogue and article content belong to
[ekolojiktarim.com.tr](https://www.ekolojiktarim.com.tr/). Neither is
redistributed here — both are fetched at run time.
