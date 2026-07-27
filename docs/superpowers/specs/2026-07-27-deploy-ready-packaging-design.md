# Deploy-ready packaging — design

**Date:** 2026-07-27
**Status:** Approved design, pending implementation plan.
**Goal:** Make the system *deploy-ready* — remove the local-machine dependency and
reduce "go live" to filling in env vars + one deploy, **without launching anything now**
and **without changing local behavior**. Local (LM Studio + LAN) stays the default; hosted
is opt-in via env, exactly like the existing `chat_provider` switch.

Non-goals: provisioning a real host, choosing a vendor, buying GPUs, re-indexing the
corpus, or making the system publicly reachable. Those are the actual-launch step and stay
deferred (see `docs/roadmap-deployment.md` phases 2–3).

## Context / current state

- **Chat is already provider-portable** (`chat_provider = local | openrouter`, `src/engine.py`
  `ChatProfile`). The hosted-chat half of "go live" is done.
- **Embeddings are config-swappable in principle but not deploy-clean.** `get_embeddings()`
  (`src/ingest.py:46`) reads `lm_studio_base_url` / `lm_studio_api_key` / `embedding_model`.
  Any OpenAI-compatible bge-m3 endpoint works by setting those — but two problems block a
  clean hosted deploy:
  1. **Model-guard false-trip.** The store is stamped with the *string value* of
     `embedding_model` and `_check_embedding_model()` (`src/ingest.py:58`) compares that
     string. A hosted provider names bge-m3 differently (`BAAI/bge-m3` vs the local
     `text-embedding-bge-m3`), so pointing at hosted bge-m3 would raise
     `EmbeddingModelMismatchError` for the *same underlying model*. (Today the live store is
     unstamped → `recorded is None` → warns, not raises; but any future re-ingest stamps it
     and arms the trap.)
  2. **Naming abuse.** Using `lm_studio_base_url` / `lm_studio_api_key` for a hosted
     embedding provider is confusing and error-prone in a prod config that already has a
     third distinct endpoint (openrouter chat).
- **Mobile backend URL is already env-driven** — `api.ts:15` reads
  `process.env.EXPO_PUBLIC_API_BASE ?? "http://192.168.1.103:8000"` (single source, no other
  hardcoded backend URL). Gaps are packaging/docs only: no `mobile-app/.env.example`, the
  `eas.json` build profiles inject no `env`, and `mobile-app/README.md:17` still says to edit
  `src/api.ts` (stale).
- **CORS is already env-driven** (`cors_allow_origins`, default `*`). No code change needed
  to narrow it; only a safety reminder + docs.
- **Store size** ~1.4 GB, gitignored — needs a persistent disk on any host (already noted in
  the roadmap).

## Piece 1 — Embedding provider readiness (core)

Decouple the store's **logical embedding identity** from the **API model-id** so switching
to a hosted bge-m3 endpoint is a clean config swap with no re-index and no false guard trip.

**Config changes (`src/config.py`, `Settings`):**
- New `embedding_identity: str = Field(default="bge-m3")` — the *stable logical name* used
  ONLY to stamp the collection and in the guard comparison. Never sent to any API.
- New `embedding_base_url: str = Field(default="")` and `embedding_api_key: str = Field(default="")`
  — dedicated embedding endpoint/key. When empty, they fall back to `lm_studio_base_url` /
  `lm_studio_api_key` respectively (backward-compatible: existing `.env` untouched).
- `embedding_model` unchanged — still the API model-id sent to the endpoint.
- A resolver (property or small helper) returns the effective embedding base_url/api_key
  with the fallback applied, so callers don't repeat the `or lm_studio_*` logic.

**Ingest changes (`src/ingest.py`):**
- `get_embeddings()` builds `OpenAIEmbeddings` from the resolved embedding base_url/api_key
  (fallback-aware) + `embedding_model`. Behavior when the new vars are empty is byte-identical
  to today.
- `get_vector_store()` stamps `collection_metadata={"embedding_model": settings.embedding_identity}`
  (was `settings.embedding_model`).
- `_check_embedding_model()` compares against `settings.embedding_identity`. Semantics
  preserved: `recorded == identity` → silent; `recorded is None` → warn (unchanged, protects
  the current unstamped live store); genuine mismatch → raise.

> **Stamp-key note:** the metadata *key* stays `"embedding_model"` (what the current live
> store would use once stamped, and what existing tests read); only the *value* becomes the
> logical identity. This avoids a metadata-key migration.

**Migration:** none forced. Local behavior identical; the live unstamped store keeps working
(warns). On the next voluntary re-ingest it stamps `bge-m3`, and from then on the guard gives
real protection while still allowing any provider that serves bge-m3.

**Tests (`tests/test_ingest.py` + `tests/test_config.py`):**
- Guard: `identity == recorded` → no raise; `recorded is None` → warns, no raise; genuine
  mismatch (`recorded="bge-m3"`, `identity="nomic"`) → raises.
- Hosted-style config: `embedding_model="BAAI/bge-m3"` with `embedding_identity="bge-m3"`
  against a store stamped `bge-m3` → passes (the exact bug this piece fixes).
- Fallback: empty `embedding_base_url`/`embedding_api_key` resolve to the `lm_studio_*`
  values; set values win.

## Piece 2 — Mobile backend URL → env (packaging + docs)

No `api.ts` logic change (already env-driven and single-source). Close the packaging gaps:
- **Add `mobile-app/.env.example`** documenting `EXPO_PUBLIC_API_BASE=` with the LAN-dev
  example and a hosted example (commented).
- **Fix `mobile-app/README.md`** — replace the stale "set `API_BASE` in `src/api.ts`"
  instruction with setting `EXPO_PUBLIC_API_BASE` (env / `mobile-app/.env`), keeping the LAN
  / emulator IP guidance.
- **Add an `env` block to `eas.json`** `preview` and `production` profiles carrying
  `EXPO_PUBLIC_API_BASE`. The real hosted URL is unknown now, so use a clear placeholder
  (e.g. `"https://REPLACE-WITH-HOSTED-BACKEND"`) and document in the runbook that it is set
  at build time. Local `expo start` is unaffected (reads the fallback / `mobile-app/.env`).

## Piece 3 — Deploy runbook + CORS

- **New `docs/deploy-runbook.md`** — a concise, ordered runbook for the actual go-live step
  (distinct from the strategic `roadmap-deployment.md`):
  1. Pick a host (Fly.io / Render / Railway / VPS) — platform TLS gives HTTPS.
  2. Attach a persistent disk for `data/vector_store` (~1.4 GB, not in git); copy or
     re-ingest onto it.
  3. Prod env: `CHAT_PROVIDER=openrouter` + `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`;
     embeddings → hosted bge-m3 via `EMBEDDING_BASE_URL`/`EMBEDDING_API_KEY`/`EMBEDDING_MODEL`
     with `EMBEDDING_IDENTITY=bge-m3`; `CORS_ALLOW_ORIGINS` narrowed to the widget/site
     origin(s).
  4. Set the mobile build's `EXPO_PUBLIC_API_BASE` to the hosted URL and rebuild.
  5. Secrets live in the host's env/secret store, never committed.
  6. After deploy, run `python -m evals.run_eval` against the hosted config to confirm
     quality held.
- **Extend `.env.example`** with the new embedding vars (`EMBEDDING_BASE_URL`,
  `EMBEDDING_API_KEY`, `EMBEDDING_IDENTITY`) and a commented prod block showing a hosted
  bge-m3 + openrouter + narrowed-CORS configuration.
- **CORS safety log (`src/main.py`)** — at startup, if `settings.cors_origins_list == ["*"]`,
  emit one WARNING line ("CORS is open to all origins — fine for local/dev, narrow
  CORS_ALLOW_ORIGINS before a public deploy"). Log only; no behavior change; fires once.

## Verification

- `pytest -q` green including the new guard/config tests (currently 228 → +new).
- Local defaults unchanged ⇒ `python -m evals.run_eval` unchanged and the local run path is
  byte-identical (all new settings default to empty/`bge-m3`/`*`).
- Manual: with `EMBEDDING_BASE_URL`/`EMBEDDING_API_KEY`/`EMBEDDING_MODEL` set to a hosted
  bge-m3 endpoint and `EMBEDDING_IDENTITY=bge-m3`, the backend starts and answers without a
  guard error (documented as a runbook check, not automated — no live hosted account now).

## Risks / decisions

- **Guard weakening?** No — identity comparison still catches a real model change; you only
  keep `embedding_identity=bge-m3` while the vectors are genuinely bge-m3. The failure mode
  moved from "false trip on the same model" to "correct on the same model."
- **Placeholder in `eas.json`** — a committed placeholder URL must be obviously non-functional
  (`REPLACE-WITH-...`) so a build never silently ships pointing at nothing real.
- **No re-index** is in scope; if a future decision picks a non-bge-m3 hosted embedder, that
  is a separate re-ingest project (roadmap phase 3, option C).
