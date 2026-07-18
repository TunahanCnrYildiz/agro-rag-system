# Plan: guard the embedding model against the store

Spec: `../specs/2026-07-17-embedding-model-guard-design.md` (Approved). TDD.
The spec's "Testing" section IS the test list; this plan sequences it and pins the
current anchors (line numbers drifted after the 2026-07-18 year/era work):
- `get_vector_store` → `src/ingest.py:51`
- ingest() driver store-open → `src/ingest.py:359`; `--reset` delete/reopen → 361-367
- `engine._get_retriever_store` → `src/engine.py:191`; engine's config import → `src/engine.py:20`
- `fetch_dergipark.py:317-318` (read path, unchanged behaviour)

## Task 1 — RED: exception + `_check_embedding_model` (tests/test_ingest.py)
Per the spec's three-row table (equal→silent, None→warn, else→raise):
- `test_check_embedding_model_match_silent`: equal recorded/configured → returns None, no raise.
- `test_check_embedding_model_mismatch_raises`: different → raises
  `ing.EmbeddingModelMismatchError`; message contains BOTH model names.
- `test_check_embedding_model_none_warns` (capsys): `None` recorded → returns
  normally AND prints a warning naming the configured model.
- `test_check_embedding_model_error_names_reset`: the raised message contains
  `--reset`.
Reference `ing.EmbeddingModelMismatchError` and `ing._check_embedding_model` via
the module alias so the file still imports. Run `pytest -q tests/test_ingest.py
-k embedding_model` → all fail (AttributeError).

## Task 2 — GREEN: define the exception + the pure check
- `src/config.py`: `class EmbeddingModelMismatchError(RuntimeError): ...` (owns
  `embedding_model`, already imported at engine top level, no heavy deps — spec's
  reasoning).
- `src/ingest.py`: re-export it in the config import block (`from .config import
  ... EmbeddingModelMismatchError`) so `ing.EmbeddingModelMismatchError` resolves;
  add `_check_embedding_model(recorded: str | None, configured: str) -> None` with
  the table behaviour. Warning + error strings carry the model name(s) and the
  `--reset` remedy verbatim from the spec.
Run the Task-1 tests → green.

## Task 3 — RED: `get_vector_store` behaviour (tests/test_ingest.py)
Monkeypatch `ing.Chroma` (it's imported lazily inside `get_vector_store` — patch
`langchain_chroma.Chroma` or inject a fake via monkeypatching the symbol the
function looks up) with a fake whose `_collection.metadata` is settable:
- `test_get_vector_store_passes_collection_metadata`: the fake records the
  `collection_metadata` kwarg; assert it equals
  `{"embedding_model": settings.embedding_model}`.
- `test_get_vector_store_verifies_by_default`: fake reports a DIFFERENT recorded
  model → `get_vector_store()` raises `EmbeddingModelMismatchError`.
- `test_get_vector_store_verify_false_skips`: same mismatched fake +
  `get_vector_store(verify_model=False)` → returns the store, no raise.
Run → fail (current `get_vector_store` takes no arg, passes no metadata, never checks).

## Task 4 — GREEN: `get_vector_store(verify_model: bool = True)` (ingest.py:51)
- Add the `verify_model` param.
- Always pass `collection_metadata={"embedding_model": settings.embedding_model}`
  to `Chroma(...)` (no-op on an existing collection — spec's chromadb 1.5.9 probe).
- When `verify_model`: read `store._collection.metadata` (or `{}`),
  `_check_embedding_model(meta.get("embedding_model"), settings.embedding_model)`.
Run full `pytest -q tests/test_ingest.py` → green.

## Task 5 — GREEN: wire the ingest() driver (ingest.py:359-367)
- `store = get_vector_store(verify_model=not reset)` at 359 — without this,
  `--reset` (the one fix for a mismatch) can't run: the guard would raise on the
  pre-delete open.
- The post-delete reopen at 367 keeps the default (`verify_model=True`): a fresh
  collection is stamped at creation, so it verifies clean.
No new test beyond Task 3/4 (the driver just chooses the flag); a manual `python
-m src.ingest --reset`-path reasoning note in the commit suffices.

## Task 6 — RED→GREEN: engine read path (tests/test_engine.py + engine.py)
- RED: `test_get_retriever_store_reraises_mismatch` — `cache_clear()` first (it's
  `lru_cache`d), monkeypatch the lazily-imported `get_vector_store` to raise
  `EmbeddingModelMismatchError`, assert it PROPAGATES (not swallowed to None).
  `test_get_retriever_store_none_on_generic_error` — a generic Exception still
  returns `None`. First fails (current code catches everything → None).
- GREEN: add `EmbeddingModelMismatchError` to engine's config import (engine.py:20
  — MODULE level, so the `except` name is bound even if the lazy `ingest` import
  fails; this is the spec's NameError-trap fix). In `_get_retriever_store` add,
  BEFORE the broad handler:
  ```python
  except EmbeddingModelMismatchError:
      raise
  except Exception as exc:
      print(f"[engine] vector store unavailable: {exc}")
      return None
  ```
Run full `pytest -q` → green (suite 153 + new).

## Task 7 — VERIFY (behaviour on the real store)
- `pytest -q` green.
- **Expected on the LIVE store: a WARNING, not a failure.** The current collection
  has no recorded metadata (spec measured `metadata=None`), so
  `_check_embedding_model(None, "bge-m3")` warns and returns. Observe it once:
  `python -m src.ingest` (no `--reset`) opens the store, prints the
  "no recorded embedding model … re-ingest with --reset to stamp it" warning, then
  skips all already-ingested files. Retrieval still works.
- `python -m evals.run_eval --fast` → still 33/33 (the guard is a no-op on the
  matching config; retrieval unchanged).
- **Do NOT auto-stamp the live store.** Spec rejects backfilling the configured
  model into metadata (it launders a guess into a recorded fact). The store gains
  a real stamp only on an intentional `--reset` re-ingest (expensive: re-embeds
  76,798 chunks) — leave that to the user's judgement; the warning is the correct
  interim state.

## Commit shape (batched, English, no co-author)
1. config exception + `_check_embedding_model` + tests (Tasks 1-2).
2. `get_vector_store` verify + ingest() wiring + tests (Tasks 3-5).
3. engine read-path re-raise + tests (Task 6).
Do NOT push unless asked. No store mutation (guard is read-only on metadata).
