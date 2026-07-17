# Guard the Embedding Model Against the Store — Design

**Date:** 2026-07-17
**Status:** Approved (ready for plan + implementation)
**Files touched:** `src/config.py`, `src/ingest.py`, `src/engine.py`,
`tests/test_ingest.py`, `tests/test_engine.py`
**Follows:** `6deac09` — "Anchor .env to the project root so the CWD can't swap
the embedding model"

## Problem

Nothing verifies that `settings.embedding_model` matches the model the Chroma
collection was actually indexed with.

Today a mismatch is caught only by Chroma, and only when the **dimensions
differ**:

```
Collection expecting embedding with dimension of 1024, got 768
```

That is what `6deac09` chased down: a CWD-relative `.env` fell back to
`nomic-embed-text` (768) against a `bge-m3` (1024) store, and every retrieval
died. Loud, but incidental — the error came from a shape check, not from anyone
verifying the model.

**A wrong-but-same-dimension model produces no error at all.** Query vectors
land in a space they were never trained against, nearest-neighbour search
returns whatever is closest in that wrong space, and the model dutifully
answers from garbage context. Silent, and indistinguishable from a thin corpus
— the same misreading `6deac09` records ("read like a corpus problem, not a
config one").

Dimension collision is not exotic. 1024 alone covers `bge-m3`,
`bge-large-en-v1.5`, `mxbai-embed-large`, and `multilingual-e5-large`; 768 is
shared by most base-size models. Swapping models within a size class is exactly
the edit someone makes in `.env`.

## What we can and cannot know

**Measured 2026-07-17** against the live store:

```
$ python -c "...chromadb.PersistentClient(path='data/vector_store')..."
'botany_knowledge' None
```

The existing collection carries **no metadata**. The store that exists today
cannot be verified — nothing recorded what built it. The check can only start
recording from the next collection creation onward, which makes the legacy path
a design decision rather than an afterthought.

**Measured 2026-07-17**, chromadb 1.5.9 — does `get_or_create_collection`
overwrite metadata on an existing collection?

```python
col  = c.get_or_create_collection("probe_coll", metadata={"embedding_model": "MODEL-A"})
# created: {'embedding_model': 'MODEL-A'}
col2 = c2.get_or_create_collection("probe_coll", metadata={"embedding_model": "MODEL-B"})
# reopened with B -> {'embedding_model': 'MODEL-A'}
```

**It preserves the original and ignores the passed value.** This is what makes
the whole approach work: we can pass the configured model on every open and
still read back the value recorded at *creation* time. Were it otherwise, the
check would compare the config against an echo of itself and pass forever.

`langchain_chroma` routes `collection_metadata` straight into that call
(`Chroma.__ensure_collection` → `get_or_create_collection(metadata=...)`), so
the guarantee holds through the wrapper.

Reading recorded metadata is also preferred over **probing dimensions with a
live embedding call**: probing would add an LM Studio round-trip to every store
open, and dimension is the weaker signal anyway — it is precisely the
same-dimension case that this guard exists to catch.

## Design

### Where the exception lives

`EmbeddingModelMismatchError` is defined in **`src/config.py`** and re-exported
from `ingest.py`.

`config.py` owns `embedding_model`, is already imported at engine.py top level,
and pulls no heavy dependencies. But the deciding reason is a bug in the
obvious alternative. `engine._get_retriever_store` imports `ingest` lazily
*inside* its `try`:

```python
try:
    from .ingest import get_vector_store, EmbeddingModelMismatchError  # if THIS raises...
    return get_vector_store()
except EmbeddingModelMismatchError:   # ...the name is unbound -> NameError
    raise
```

An `except` clause resolves its name at exception time. If the lazy import
fails — the "langchain not installed" case the fallback exists to serve — the
handler raises `NameError` and masks the real error. Defining the exception
where engine already imports from removes the trap.

### The check

A pure helper in **`src/ingest.py`** does the deciding, so tests never construct
a Chroma client. Only the exception type lives in `config.py`; the logic sits
next to its caller:

```python
def _check_embedding_model(recorded: str | None, configured: str) -> None:
    """Raise on mismatch; warn when the store predates this check."""
```

| `recorded` | Behavior |
|---|---|
| equals `configured` | silent — the happy path |
| `None` | print a warning naming `configured`, return normally |
| anything else | `raise EmbeddingModelMismatchError` |

**`None` warns rather than fails** because an unstamped collection is *unknown*,
not *mismatched* — and the live store is unstamped today. Failing hard would
break a working setup until a full re-ingest. Backfilling the configured model
into the metadata was rejected for the opposite reason: it launders a guess into
a recorded fact, so a wrong `.env` today would permanently stamp the wrong model
and leave the guard worse than useless — it would then certify the mismatch as
correct.

The warning names the model and the remedy:

```
[ingest] WARNING: collection 'botany_knowledge' has no recorded embedding
model (created before this check). Configured: bge-m3. Cannot verify -
re-ingest with --reset to stamp it.
```

The raised error names both models and the remedy.

### `get_vector_store(verify_model: bool = True)`

Always passes `collection_metadata={"embedding_model": settings.embedding_model}`
— a no-op on an existing collection, per the probe above. When `verify_model`,
reads `store._collection.metadata` and hands it to `_check_embedding_model`.

`verify_model=False` exists for one caller, and without it the feature
deadlocks: `ingest()` opens the store at ingest.py:242 **before** deleting it at
:246, so a guard that raises on open would make `--reset` — the one command that
fixes a mismatch — impossible to run.

```python
store = get_vector_store(verify_model=not reset)
if reset:
    store.delete_collection()
    store = get_vector_store()   # fresh: stamped, and verified by default
```

Deleting through a raw `chromadb` client instead was rejected: it duplicates
client-construction knowledge that currently lives only in `get_vector_store`.

### Call sites

| Site | Behavior |
|---|---|
| `ingest.py:242` | `verify_model=not reset`; reopen after delete uses the default |
| `engine.py:191` | mismatch re-raised; every other failure still returns `None` |
| `fetch_dergipark.py:317` | default — a read path, fails like any other |

Plain `python -m src.ingest` against a mismatched store now raises instead of
poisoning the collection with vectors from a second model.

### The read path

`engine._get_retriever_store` catches all exceptions and returns `None`, which
would swallow the guard into a silent fallback. It gains one clause:

```python
except EmbeddingModelMismatchError:
    raise            # a config error, not "unavailable"
except Exception as exc:
    print(f"[engine] vector store unavailable: {exc}")
    return None
```

The `None` fallback exists for **nothing ingested yet** and **langchain not
installed** — states that are legitimately recoverable and where answering
without context is the right degradation. A model mismatch is neither: retrieval
is broken until a human edits `.env` or re-ingests, and no amount of retrying
fixes it. Falling back would mean serving confidently-worded, context-free
answers for as long as nobody reads the logs — the exact failure this project
has repeatedly fought (see the empty-answer-guard and `[NOPRODUCT]` specs).
Better a 500 that names the cause.

`_get_retriever_store` is `lru_cache`d, so the raise is not memoised as a `None`
and recurs per call until fixed.

## Testing

TDD — tests first, each failing before its implementation.

**`tests/test_ingest.py`**
- `_check_embedding_model` matching → returns silently
- `_check_embedding_model` mismatched → raises `EmbeddingModelMismatchError`,
  message names both models
- `_check_embedding_model(None, ...)` → returns, warns on stdout (capsys)
- error message includes the `--reset` remedy
- `get_vector_store` passes `collection_metadata` with the configured model
  (monkeypatched `Chroma`)
- `get_vector_store(verify_model=False)` skips the check on a mismatched store

**`tests/test_engine.py`**
- `_get_retriever_store` re-raises `EmbeddingModelMismatchError`
  (`cache_clear()` first — it is `lru_cache`d)
- `_get_retriever_store` still returns `None` on a generic exception

Existing fakes and `monkeypatch` stay the idiom; no test touches a real Chroma
client or LM Studio.

## Out of scope

- Startup-time validation in the API lifespan — larger surface than
  `ingest.py`/`engine.py`, and makes the store a hard boot dependency.
- Probing dimensions with a live embedding call.
- Recording chunk_size/overlap or other ingest params in metadata. Same class of
  bug, no evidence it has bitten, and each addition is another field to keep
  honest. YAGNI until it does.
