# Deploy-ready Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the system deploy-ready — hosted embeddings become a clean config swap (no re-index, no false guard trip), the mobile backend URL is packaged for env override, and a runbook + CORS reminder cover the actual go-live — all without changing local behavior.

**Architecture:** Mirror the existing `chat_provider` portability pattern for embeddings by separating the store's *logical identity* from the API *model-id*, with dedicated embedding endpoint/key settings that fall back to the `lm_studio_*` values. Everything defaults to today's local behavior; hosted is opt-in via env. Mobile and CORS changes are packaging/docs plus one startup log.

**Tech Stack:** Python 3.12, pydantic-settings, FastAPI, langchain-openai/langchain-chroma, pytest; Expo/React Native (TypeScript) for the mobile app.

## Global Constraints

- **No re-index in scope.** The bge-m3 store must stay valid; never change `embedding_model`'s *dimension* assumptions.
- **Local behavior byte-identical when new vars are unset.** Defaults: `embedding_identity="bge-m3"`, `embedding_base_url=""`, `embedding_api_key=""`, `cors_allow_origins="*"`.
- **Backward compatibility:** an existing local `.env` (with only `lm_studio_*` + `embedding_model`) must keep working unchanged.
- **Guard semantics preserved:** `recorded == identity` → silent; `recorded is None` → warn; genuine mismatch → raise.
- **Stamp metadata KEY stays `"embedding_model"`**; only its VALUE becomes the logical identity (avoids a metadata-key migration; existing tests read that key).
- **Commit style:** short, natural, English messages; no `Co-Authored-By` trailer.
- **Run everything from the repo root** (config reads a root-anchored `.env`).
- **eas.json placeholder URL must be obviously non-functional** (`REPLACE-WITH-...`).

---

### Task 1: Embedding provider settings + resolver

**Files:**
- Modify: `src/config.py` (add fields + resolver properties to `Settings`, after the chat-provider block ending at line 83)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings.embedding_identity: str` (default `"bge-m3"`), `Settings.embedding_base_url: str` (default `""`), `Settings.embedding_api_key: str` (default `""`), and properties `Settings.effective_embedding_base_url -> str`, `Settings.effective_embedding_api_key -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_embedding_identity_defaults_to_bge_m3():
    """Asserted on the FIELD DEFAULT (same reasoning as the chat_provider test):
    the real .env is gitignored, so an instance-level assert would be env-dependent."""
    assert Settings.model_fields["embedding_identity"].default == "bge-m3"


def test_embedding_endpoint_falls_back_to_lm_studio_when_unset():
    s = Settings(embedding_base_url="", embedding_api_key="")
    assert s.effective_embedding_base_url == s.lm_studio_base_url
    assert s.effective_embedding_api_key == s.lm_studio_api_key


def test_embedding_endpoint_override_wins():
    s = Settings(embedding_base_url="https://hosted.example/v1",
                 embedding_api_key="secret-key")
    assert s.effective_embedding_base_url == "https://hosted.example/v1"
    assert s.effective_embedding_api_key == "secret-key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -k embedding -v`
Expected: FAIL — `AttributeError`/`KeyError` (fields and properties don't exist yet).

- [ ] **Step 3: Add the fields and resolver properties**

In `src/config.py`, insert after the chat-provider block (immediately before the `# --- Generation params ---` comment at line 85):

```python
    # --- Embedding provider (independent of chat_provider) --- #
    # The store is stamped with a STABLE LOGICAL identity, not the API model-id,
    # so a hosted bge-m3 endpoint (which names the model differently, e.g.
    # "BAAI/bge-m3") is a clean config swap and does NOT trip the model guard.
    # embedding_model (above) stays the id sent to the API; embedding_identity is
    # the store's identity used for stamping + guard comparison.
    embedding_identity: str = Field(default="bge-m3")
    # Dedicated embedding endpoint/key. Empty -> fall back to the lm_studio_*
    # values, so an existing local .env keeps working unchanged. A hosted deploy
    # sets these to the real embedding provider without overloading the
    # LM-Studio-named vars (which in prod point nowhere).
    embedding_base_url: str = Field(default="")
    embedding_api_key: str = Field(default="")

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url.strip() or self.lm_studio_base_url

    @property
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key.strip() or self.lm_studio_api_key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -k embedding -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "Add embedding identity + dedicated endpoint settings"
```

---

### Task 2: Ingest uses resolver + stamps logical identity

**Files:**
- Modify: `src/ingest.py` — `get_embeddings()` (lines 46-55) and `get_vector_store()` (lines 96-104)
- Test: `tests/test_ingest.py` (update one existing test, add two)

**Interfaces:**
- Consumes: `settings.effective_embedding_base_url`, `settings.effective_embedding_api_key`, `settings.embedding_identity`, `settings.embedding_model` (from Task 1).
- Produces: no signature changes — `get_embeddings()` and `get_vector_store(verify_model=True)` keep their shapes; only their internals change.

- [ ] **Step 1: Update the existing metadata test + write the new tests**

In `tests/test_ingest.py`, change `test_get_vector_store_passes_collection_metadata` (lines 269-274) to assert the logical identity:

```python
def test_get_vector_store_passes_collection_metadata(monkeypatch):
    _patch_chroma(monkeypatch, {"embedding_model": settings.embedding_identity})
    ing.get_vector_store()
    assert _FakeChroma.last_kwargs.get("collection_metadata") == {
        "embedding_model": settings.embedding_identity
    }
```

Then append two new tests at the end of the file:

```python
def test_get_vector_store_stamps_identity_not_model_id(monkeypatch):
    # embedding_model is the API id; the STAMP must be the logical identity.
    _patch_chroma(monkeypatch, {"embedding_model": settings.embedding_identity})
    monkeypatch.setattr(settings, "embedding_model", "some/api-model-id")
    ing.get_vector_store()
    assert _FakeChroma.last_kwargs.get("collection_metadata") == {
        "embedding_model": settings.embedding_identity
    }


def test_hosted_model_id_does_not_trip_guard(monkeypatch):
    # Store stamped with the logical identity ("bge-m3"); a hosted provider's
    # differently named model-id ("BAAI/bge-m3") must NOT raise, because the
    # guard compares identity, not the API id. This is the bug this task fixes.
    _patch_chroma(monkeypatch, {"embedding_model": "bge-m3"})
    monkeypatch.setattr(settings, "embedding_identity", "bge-m3")
    monkeypatch.setattr(settings, "embedding_model", "BAAI/bge-m3")
    ing.get_vector_store()  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ingest.py -k "vector_store or hosted_model_id" -v`
Expected: FAIL — the store still stamps `settings.embedding_model` (the nomic default), so the identity assertions and the guard mismatch fail.

- [ ] **Step 3: Point get_embeddings at the resolved endpoint**

In `src/ingest.py`, replace the body of `get_embeddings()` (lines 46-55):

```python
def get_embeddings() -> OpenAIEmbeddings:
    """Embeddings client for the configured embedding endpoint: LM Studio locally,
    or a hosted bge-m3 provider when embedding_base_url/api_key are set. The model
    stays bge-m3 either way (the store is stamped with the logical identity)."""
    return OpenAIEmbeddings(
        base_url=settings.effective_embedding_base_url,
        api_key=settings.effective_embedding_api_key,
        model=settings.embedding_model,
        # LM Studio embedding servers usually don't support batching well;
        # keep chunks modest and let our own batching drive throughput.
        check_embedding_ctx_length=False,
    )
```

- [ ] **Step 4: Stamp + verify the logical identity**

In `src/ingest.py`, `get_vector_store()`, change the two lines that reference `settings.embedding_model` (line 100 and line 104):

```python
        collection_metadata={"embedding_model": settings.embedding_identity},
    )
    if verify_model:
        recorded = (store._collection.metadata or {}).get("embedding_model")
        _check_embedding_model(recorded, settings.embedding_identity)
```

- [ ] **Step 5: Run the full ingest test module**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: PASS (all, including the updated + 2 new tests).

- [ ] **Step 6: Commit**

```bash
git add src/ingest.py tests/test_ingest.py
git commit -m "Stamp store with logical embedding identity; resolve embedding endpoint"
```

---

### Task 3: Mobile backend URL packaging

**Files:**
- Create: `mobile-app/.env.example`
- Modify: `mobile-app/README.md` (the "API endpoint" section, lines 15-23)
- Modify: `mobile-app/eas.json` (`build.preview` and `build.production` profiles)

**Interfaces:**
- Consumes: `EXPO_PUBLIC_API_BASE` — already read by `mobile-app/src/api.ts:15` (no code change).
- Produces: nothing other tasks depend on (packaging/docs).

- [ ] **Step 1: Create `mobile-app/.env.example`**

```bash
# Copy to mobile-app/.env (gitignored) or set in the shell / EAS build env.
# The mobile app reads this at bundle time via src/api.ts.

# Backend base URL the app calls.
#   Local physical device:  http://<your-machine-LAN-IP>:8000
#   Android emulator:        http://10.0.2.2:8000
#   Hosted:                  https://your-deployed-api.example
EXPO_PUBLIC_API_BASE=http://192.168.1.103:8000
```

- [ ] **Step 2: Fix the stale README instruction**

In `mobile-app/README.md`, replace the "API endpoint" section body (lines 17-23) with:

```markdown
Set `EXPO_PUBLIC_API_BASE` (in `mobile-app/.env` — see `.env.example` — or the
shell / EAS build env) to wherever the backend runs; `src/api.ts` reads it at
bundle time and falls back to a LAN IP only when it is unset. `127.0.0.1` only
works when the app and API share a machine (e.g. web preview); a physical device
or emulator needs a reachable address:

- Android emulator → `http://10.0.2.2:8000`
- Physical device → `http://<your-machine-LAN-IP>:8000`
- Production → your deployed API's public URL
```

- [ ] **Step 3: Inject `EXPO_PUBLIC_API_BASE` into the EAS build profiles**

In `mobile-app/eas.json`, add an `env` block to the `preview` and `production` profiles so a build bakes in the hosted URL. The real URL is unknown now — use an obvious placeholder:

```json
    "preview": {
      "distribution": "internal",
      "env": {
        "EXPO_PUBLIC_API_BASE": "https://REPLACE-WITH-HOSTED-BACKEND"
      },
      "android": {
        "buildType": "apk"
      },
      "ios": {
        "simulator": true
      }
    },
    "production": {
      "autoIncrement": true,
      "env": {
        "EXPO_PUBLIC_API_BASE": "https://REPLACE-WITH-HOSTED-BACKEND"
      },
      "android": {
        "buildType": "app-bundle"
      },
      "ios": {}
    }
```

- [ ] **Step 4: Verify JSON is valid**

Run: `python -c "import json; json.load(open('mobile-app/eas.json', encoding='utf-8')); print('eas.json OK')"`
Expected: prints `eas.json OK` (no JSON error).

- [ ] **Step 5: Commit**

```bash
git add mobile-app/.env.example mobile-app/README.md mobile-app/eas.json
git commit -m "Package mobile backend URL via EXPO_PUBLIC_API_BASE (env + EAS + docs)"
```

---

### Task 4: Deploy runbook, prod .env example, CORS warning

**Files:**
- Create: `docs/deploy-runbook.md`
- Modify: `.env.example` (add embedding vars + a commented prod block)
- Modify: `src/main.py` (add `_warn_if_open_cors` + call it after the CORS middleware, around line 94)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `settings.cors_origins_list` (existing), the embedding vars from Task 1.
- Produces: `main._warn_if_open_cors(origins: list[str]) -> None`.

- [ ] **Step 1: Write the failing CORS-warning tests**

Append to `tests/test_main.py`:

```python
def test_warn_if_open_cors_warns_on_wildcard(capsys):
    main._warn_if_open_cors(["*"])
    out = capsys.readouterr().out
    assert "WARNING" in out and "CORS" in out


def test_warn_if_open_cors_silent_when_narrowed(capsys):
    main._warn_if_open_cors(["https://example.com"])
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -k warn_if_open_cors -v`
Expected: FAIL — `AttributeError: module 'src.main' has no attribute '_warn_if_open_cors'`.

- [ ] **Step 3: Add the warning helper and call it**

In `src/main.py`, after the `app.add_middleware(...)` block (ends line 94), add:

```python


def _warn_if_open_cors(origins: list[str]) -> None:
    """One-time startup reminder when CORS is wide open. Fine for local/dev; a
    public deploy should narrow CORS_ALLOW_ORIGINS to the real site origins."""
    if origins == ["*"]:
        print(
            "[main] WARNING: CORS_ALLOW_ORIGINS='*' allows all origins - fine for "
            "local/dev, but narrow it before a public deploy."
        )


_warn_if_open_cors(settings.cors_origins_list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -k warn_if_open_cors -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Extend `.env.example` with the embedding vars + prod block**

In `.env.example`, replace the `# --- Chat provider ---` section (lines 29-37) with this expanded block:

```bash
# --- Chat provider ---------------------------------------------------------
# "local" (default) uses the LM Studio server above. "openrouter" uses a hosted
# OpenAI-compatible endpoint instead.
CHAT_PROVIDER=local
# Required only when CHAT_PROVIDER=openrouter. Never commit a real key.
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=
OPENROUTER_MODEL=

# --- Embedding provider ----------------------------------------------------
# The store is stamped with a STABLE logical identity, so a hosted bge-m3
# endpoint (named e.g. "BAAI/bge-m3") is a clean config swap with NO re-index.
# EMBEDDING_IDENTITY must stay "bge-m3" as long as the vectors are bge-m3.
EMBEDDING_IDENTITY=bge-m3
# Leave EMBEDDING_BASE_URL / EMBEDDING_API_KEY empty for local (falls back to the
# LM_STUDIO_* values above). For a hosted deploy, set them to the real provider.
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=

# --- Hosted-deploy example (uncomment + fill in for production) -------------
# CHAT_PROVIDER=openrouter
# OPENROUTER_API_KEY=sk-or-...
# OPENROUTER_MODEL=google/gemma-4-26b-a4b-it
# EMBEDDING_BASE_URL=https://api.deepinfra.com/v1/openai
# EMBEDDING_API_KEY=di-...
# EMBEDDING_MODEL=BAAI/bge-m3
# EMBEDDING_IDENTITY=bge-m3
# CORS_ALLOW_ORIGINS=https://your-site.example
```

- [ ] **Step 6: Write the deploy runbook**

Create `docs/deploy-runbook.md`:

```markdown
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
   - `CORS_ALLOW_ORIGINS=https://your-site.example` (narrow it — the backend logs
     a warning while it is `*`).
3. **Deploy the backend** (Docker image builds from the repo `Dockerfile`).
   Confirm `GET /health` returns the expected provider + model.
4. **Mobile build:** set `EXPO_PUBLIC_API_BASE` to the hosted URL (EAS build env
   or `mobile-app/.env`) and rebuild. See `mobile-app/.env.example`.
5. **Web widget:** point its backend URL at the hosted API.
6. **Verify quality held:** run `python -m evals.run_eval` against the hosted
   config before announcing the deploy.

## Rollback
- Local dev is unaffected at all times. To revert a host to local-style behavior,
  clear the hosted env vars (chat falls back to `local`, embeddings to LM Studio).
```

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — 228 prior + 5 new (3 config, 2 main) + 2 new ingest = 235 (the updated ingest test replaces one, nets +2). No failures.

- [ ] **Step 8: Commit**

```bash
git add src/main.py tests/test_main.py .env.example docs/deploy-runbook.md
git commit -m "Add deploy runbook, prod env example, and open-CORS startup warning"
```

---

## Self-Review

**Spec coverage:**
- Piece 1 (embedding identity + dedicated endpoint + guard/stamp) → Tasks 1 & 2. ✓
- Piece 2 (mobile `.env.example`, README fix, eas.json env) → Task 3. ✓
- Piece 3 (runbook, `.env.example` prod block, CORS warning) → Task 4. ✓
- Verification (pytest green, local unchanged) → Task 4 Step 7 + defaults preserved. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one intentional placeholder (`REPLACE-WITH-HOSTED-BACKEND`) is a required, obvious non-functional marker per the spec.

**Type consistency:** `embedding_identity` / `embedding_base_url` / `embedding_api_key` / `effective_embedding_base_url` / `effective_embedding_api_key` (Task 1) are used verbatim in Task 2. `_warn_if_open_cors(origins: list[str])` defined and called consistently in Task 4. Stamp metadata key stays `"embedding_model"` across Task 2 and its tests.

**Note on the test count:** Task 4 Step 7's "235" assumes the current baseline of 228 and that the updated ingest metadata test is an in-place replacement (not additive). If the observed number differs, reconcile by listing new test names rather than trusting the arithmetic.
```
