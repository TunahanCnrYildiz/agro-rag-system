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
   - **The volume is ALL of `data/`, not just the store - and it must carry the
     tracked JSON files too.** `.dockerignore` keeps `data/` out of the image
     and `docker-compose.yml` mounts `./data:/app/data`, so at runtime every
     file under `data/` comes from the host. The app reads tracked files from
     there: `crop_norms.json`, `world_norms.json`, `crop_fao_map.json`,
     `country_aliases.json`, `product_doses.json`, `fertplan_table.json`. A
     volume holding only the store starts fine and **raises nothing** - measured
     2026-10-28 with those files deleted: `extract_country("Fransa'dayım")`
     returns `None`, `norms.lookup` returns `None`, and a French grower is asked
     for his Turkish province. The TÜİK figures, the FAOSTAT world layer, country
     recognition and the dose card are all silently off. The simplest way to
     keep them is for the host's `./data` to be the repo checkout's own `data/`,
     so `git pull` updates the JSON files beside the store.
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
4. **Mobile build:** set `EXPO_PUBLIC_API_BASE` to the hosted URL **in the EAS
   build env** - `mobile-app/eas.json`, which already carries
   `https://poc.runiksoft.com` for the current host - and rebuild.
   **Never in `mobile-app/.env`.** Expo reads `EXPO_PUBLIC_*` at BUNDLE time, so
   whatever that file holds is baked into the next APK: a local or LAN base left
   there ships to real phones and the app cannot reach the backend, with nothing
   in the build to say so. For a one-off local run, set it in the shell for that
   command only. After building, check the extracted
   `assets/index.android.bundle` for the hosted host AND for the absence of any
   local one - checking only that the right one is present can pass for the
   wrong reason, since `src/api.ts`'s committed fallback is a LAN IP.
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
It also predates the whole FAOSTAT world layer (`world_norms.json`, country
recognition from the conversation, a foreign grower's country figures in the
answer) and the server-side history budget - all landed in September and
October 2026.
Redeploying brings all of that at once, plus four config defaults that moved
underneath the features and won't announce themselves. Every one of the data
features needs its JSON file on the volume - see step 1 of the checklist above.

**Four defaults that changed underneath the features:**

1. **`max_tokens`: 2048 → 3072 — this one needs a decision, not just a
   redeploy.** `src/config.py` raised the reply budget from 2048 to 3072, and
   the number is measured, not preference.
   **Re-measured 2026-10-28** after the country lines grew the crop_choice
   block: the worst prompt assembled from real parts, each at its observed
   maximum (the longest block, a retrieved context at the k × chunk_size cap,
   a full 3,000-character history), is 4,517 tokens - **but that left out the
   mobile profile turn, which rides on top of the 3,000** (item 4). Measured
   2026-10-29 on the same assembly: a typical 98-char profile adds 35 tokens
   (4,552), one at 386 of its 400-char cap adds 158 (**4,675; 4,675 + 3,072 =
   7,747, so the hosted model needs a context window of at least ~7,800
   tokens**). On the LOCAL model's 8,192 that leaves 445 spare - about the
   2026-08-13 floor (4,681, 439 spare), which stays the conservative figure.
   This repository does not know what `OPENROUTER_MODEL` names, so confirming
   the hosted model's window is on you — it is not an assertion this file can
   make for you.
   **What an overshoot does, measured on LM Studio only:** a prompt that fits
   but leaves less than `max_tokens` of room gets its ANSWER cut at the window
   edge (`finish_reason: length`); a prompt larger than that is accepted with
   HTTP 200 and its MIDDLE silently dropped. A canary at the top of the system
   prompt survived that cut, so on LM Studio it is old turns that go, not the
   system instructions — an earlier revision of this item said the opposite,
   without having measured it. **The hosted server's overshoot behaviour is
   unmeasured**; it may reject, or cut from the start.
   Three values move together and none may be raised without re-measuring
   this: `max_tokens`, `history_budget_chars` (item 4) and `SEND_BUDGET_CHARS`
   in `mobile-app/src/chatStore.ts`.
2. `vector_store_url` and `vector_store_sha256` now carry real defaults, so a
   container starting on an empty volume downloads the real archive instead of
   falling back to the fetch-and-ingest path. An improvement, and still a
   behaviour change worth knowing about before it happens.
3. `rate_limit_per_minute` defaults to 60. Nothing needs setting;
   `RATE_LIMIT_PER_MINUTE=0` disables it.
4. **`history_budget_chars` defaults to 3000 — the server now bounds the
   conversation the model sees.** Until 2026-10-28 that bound lived in the mobile
   client alone; the web widget sends `history.slice()`, its whole conversation,
   and the server appended every turn. Measured on LM Studio, +290 prompt tokens
   per web exchange: at 7 exchanges prompt + `max_tokens` passed the window, at
   11 the answer was cut, from 16 the server silently dropped the middle of the
   prompt. Now the newest whole turns that fit 3,000 characters reach the model,
   by the mobile client's own rule, so a web prompt no longer grows with the
   chat: on one question it measured flat at or under 4,050 tokens from 0 to 40
   exchanges, and the bound for any question is item 1's 4,517.
   **A behaviour change worth knowing:** in a long web conversation the model no
   longer sees old turns. Routing, retrieval and location are still read off the
   FULL history, so a province or country the user stated long ago is still
   found. **Mobile passes through unchanged, because its profile turn is
   exempt.** The app sends the profile ("Adım …, …'dayım, … yetiştiriyorum")
   first, ahead of a conversation it has already trimmed to 3,000, so a long
   mobile chat is over this budget by exactly that turn. The first revision of
   this budget counted it like any turn and dropped it - the oldest - first:
   measured 2026-10-29 at 7 exchanges, the province survived (it is read off
   the full history) but the name and crops left the model's view. That
   revision never reached production. The exemption covers only a leading user
   turn ending in the app's own closing sentence, up to 400 characters; a
   longer one is budgeted like any other.

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
4. **The data files are on the volume** — this is the check nothing else makes,
   because their absence raises no error (see step 1):
   `docker compose exec api ls /app/data` must list `crop_norms.json`,
   `world_norms.json`, `crop_fao_map.json`, `country_aliases.json`,
   `product_doses.json` and `fertplan_table.json` beside `vector_store`. Then
   one behavioural check: ask "Fransa'dayım, bu yıl buğday mı ekmeliyim?" — the
   answer must name France's FAOSTAT figures, not ask for a Turkish province.

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
