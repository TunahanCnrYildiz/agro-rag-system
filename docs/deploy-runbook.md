# Deploy Runbook (local → hosted)

A short, ordered checklist for the actual go-live step. Strategy/tradeoffs live
in `roadmap-deployment.md`; this file is the "what to do" once you decide to
deploy. Nothing here changes local dev — local stays the default.

## Prerequisites
- A host: Fly.io / Render / Railway / a VPS. Platform TLS provides HTTPS.
- An OpenRouter account + key (hosted chat).
- A hosted bge-m3 embedding endpoint (e.g. DeepInfra `BAAI/bge-m3`) + key,
  **or** keep embeddings on a reachable LM Studio. Embeddings must stay bge-m3
  or the store needs a full re-ingest.

## Steps
1. **Persistent disk for the store.** `data/vector_store` (~1.4 GB) is gitignored.
   Attach a persistent volume and copy or re-ingest the store onto it. The
   container mounts it (see `docker-compose.yml` / your host's volume config).
2. **Backend env (host secret store, never committed):**
   - `CHAT_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...`, `OPENROUTER_MODEL=...`
   - `EMBEDDING_BASE_URL=...`, `EMBEDDING_API_KEY=...`, `EMBEDDING_MODEL=BAAI/bge-m3`,
     `EMBEDDING_IDENTITY=bge-m3`
   - **Migration note — this bites real stores, it is not hypothetical.** A Chroma
     store stamped under the older guard recorded the API model-id (e.g.
     `text-embedding-bge-m3`), not the logical `bge-m3`. The guard now compares
     against `EMBEDDING_IDENTITY`, so such a store raises
     `EmbeddingModelMismatchError` on open and **every retrieval fails** — backend,
     eval and app alike. The maintainer's own store hit exactly this (measured
     2026-07-28); the earlier claim that the live store was unstamped was wrong.
     The vectors are fine — only the label differs — so **re-stamp, never
     re-ingest**:

     ```python
     # one-time, from the repo root; touches metadata only, not the 81k vectors
     from langchain_chroma import Chroma
     from src.config import settings, VECTOR_STORE_DIR
     from src.ingest import get_embeddings
     store = Chroma(collection_name=settings.collection_name,
                    embedding_function=get_embeddings(),
                    persist_directory=str(VECTOR_STORE_DIR))
     store._collection.modify(metadata={"embedding_model": settings.embedding_identity})
     ```

     Then confirm `get_vector_store()` opens with no override. Setting
     `EMBEDDING_IDENTITY` to the old stamped value also works, but drags the
     LM Studio model-id into every later hosted config — prefer re-stamping.
     Note the guard deliberately does NOT auto-migrate: silently rewriting a
     mismatched stamp would defeat the very swap it exists to catch.
   - `CORS_ALLOW_ORIGINS=https://your-site.example` (narrow it — the backend logs
     a warning while it is `*`).
3. **Deploy the backend** (Docker image builds from the repo `Dockerfile`).
   Confirm `GET /health` returns the expected provider + model.
4. **Mobile build:** set `EXPO_PUBLIC_API_BASE` to the hosted URL (EAS build env
   or `mobile-app/.env`) and rebuild. See `mobile-app/.env.example`.
5. **Web widget:** point its backend URL at the hosted API.
6. **Verify quality held:** run `python -m evals.run_eval` against the hosted
   config before announcing the deploy.

## Redeploying an existing host
The checklist above is for the first deploy. `poc.runiksoft.com` is already
running one — a build dated 2026-08-04 — and its `openapi.json` still carries
only `message`, `history` and `stream` on `ChatRequest`. The budget, dose and
compare cards stay dormant no matter which client talks to it, because the
running backend has never heard of them.

What that build predates: the three cards themselves, the `/api/chat` rate
limit, and the crop-norms data layer in its entirety — `data/crop_norms.json`
does not exist in it. The file was created on 2026-08-19, fifteen days after
that build, and thirteen commits have rewritten it since.
Redeploying brings all of that at once, plus three config defaults that moved
underneath the features and won't announce themselves.

**Three defaults that changed underneath the features:**

1. **`max_tokens`: 2048 → 3072 — this one needs a decision, not just a
   redeploy.** `src/config.py` raised the reply budget from 2048 to 3072, and
   the number is measured, not preference: the crop_choice question is the
   longest context block at 3,452 prompt tokens on its own, 4,681 once the
   mobile client's full history budget rides along, and 4,681 + 3,072 = 7,753
   of 8,192, so 439 tokens spare. That headroom was measured against the LOCAL
   model's 8,192-token window. This repository does not know what
   `OPENROUTER_MODEL` names, so confirming the hosted model's window is on you
   — it is not an assertion this file can make for you. If that window is
   smaller, the failure does not look like the old one: instead of an ANSWER
   visibly cut mid-sentence, the PROMPT is silently truncated and drops the
   system instructions first.
   `SEND_BUDGET_CHARS` in `mobile-app/src/chatStore.ts` is the other half of
   this number and cannot move independently of `max_tokens`.
2. `vector_store_url` and `vector_store_sha256` now carry real defaults, so a
   container starting on an empty volume downloads the real archive instead of
   falling back to the fetch-and-ingest path. An improvement, and still a
   behaviour change worth knowing about before it happens.
3. `rate_limit_per_minute` defaults to 60. Nothing needs setting;
   `RATE_LIMIT_PER_MINUTE=0` disables it.

**Note on `--proxy-headers` — not a step.** `docker-entrypoint.sh` starts the
backend as `exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"` —
no `--proxy-headers`. Adding that flag does **not** change the current rate
limit: `SlidingWindowLimit.allow()` takes no arguments at all, so the limiter
has no client address to key on regardless of what uvicorn trusts upstream of
it. The flag would only make a future per-IP limit *possible*, and only
alongside a trusted-proxy list, because `X-Forwarded-For` is set by the client
and an attacker can just rotate it. On its own the flag is worth nothing —
don't add it expecting today's behaviour to improve.

CORS narrowing is unchanged: step 2 of the checklist above already covers it,
and it is deliberately not repeated here — a second copy is a second thing to
go stale.

**Verify, in this order:**
1. `GET /health` — confirm provider and model.
2. `GET /openapi.json` — the check that actually separates the new build from
   the old. Confirm `ChatRequest` carries all six of `budget`, `compare`,
   `dose`, `history`, `message`, `stream`, and that the schemas include
   `BudgetPayload`, `ComparePayload` and `DosePayload`.
3. The startup log line: `[main] rate limit: 60 requests/minute on
   /api/chat, counted globally rather than per caller. Set
   RATE_LIMIT_PER_MINUTE=0 to disable.`

**What this does not do.** The rate limit lives on `main`, not in production,
so the live endpoint stays open to unlimited requests until this redeploy
happens. An API key or shared secret was considered and rejected for this
architecture, so nobody has to raise it again: `web-widget/widget/agro-chat-widget.js`
is a single `<script>` embedded on a public site, so any secret it carries
sits in page source, and the mobile app's copy ships inside an APK — such a
secret filters automated scanners and nothing else. Worth having one day, but
it is not authentication and must not be described as that.

## Rollback
- Local dev is unaffected at all times. To revert a host to local-style behavior,
  clear the hosted env vars (chat falls back to `local`, embeddings to LM Studio).
