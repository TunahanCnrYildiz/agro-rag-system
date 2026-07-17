# FAO Breadth Depth-Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether the four thin corpus topics (pollination, grafting, greenhouse, post-harvest) are actually too thin to answer a real question, and harvest FAO content only where the measurement says content is missing.

**Architecture:** A throwaway scratch script calls `engine.retrieve_context()` with four pre-registered depth queries and counts how many pre-registered concept groups appear in the retrieved context (n-of-m, n=3 of m=6). The harness is not touched. Red probes get a corpus scan to separate "content absent" (harvest) from "content present but unretrieved" (a retrieval matter). Only probes that go red→green after a harvest earn a permanent eval case.

**Tech Stack:** Python 3.14, existing `src.engine` (Chroma + bge-m3 via LM Studio), `src.fetch_fao`, `evals/run_eval.py`.

**Spec:** `docs/superpowers/specs/2026-07-17-fao-breadth-depth-probe-design.md`

## Global Constraints

- **Pre-registration is binding.** The queries, concept groups, and `n=3` threshold in Task 1 are fixed by this committed plan. Do NOT edit them after seeing a result. If a term list looks wrong once results are in, that is a finding to record, not a value to tune (spec: "Pre-registration"; handoff item 22(a)).
- **Depth is asserted on retrieved CONTEXT only, never on the answer.** The model answers these questions from parametric knowledge; an answer-layer check would be vacuous (spec: "Depth cannot be asserted at the answer layer").
- **A red probe is not a harvest signal.** Every red probe goes through Task 3's corpus scan before any download (spec: "A red probe is not a harvest signal"; handoff item 5).
- **All four green ends the work item.** That is an accepted outcome, agreed in advance. Tasks 4-5 do not run.
- **Probes live in the scratchpad, not in the repo.** `context_min` enters `run_eval.py` only in Task 5, only if a probe earns it (spec: "Where the probes live").
- Scratch dir: `C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\ccc07c00-4104-4eb6-ad47-33de74db10c6\scratchpad`
- Repo root: `D:\Claude Projects\Agro-Botany RAG & Product Linker System`
- Needs LM Studio serving **bge-m3** at `:1234` (embeddings only; no chat model needed).
- Commit style: short, English, no `Co-Authored-By` trailer.

---

### Task 1: Probe script with a self-checked counter

**Files:**
- Create: `<scratch>/probe_depth.py`

**Interfaces:**
- Consumes: `engine.retrieve_context(query: str, k: int | None = None) -> str` (`src/engine.py:324`).
- Produces: `PROBES: list[dict]` (keys: `id`, `query`, `groups`), `count_groups(ctx: str, groups: list[list[str]]) -> tuple[int, list[str], list[str]]` returning (hits, hit_ids, missed_ids), and `THRESHOLD = 3`.

**Why a self-check on a throwaway script:** handoff item 22(b) — "measurement is only as good as the harness". Two probes lied on 2026-07-16 (one built messages with `products=[]`, so its 20% was not production's). Before trusting this counter, prove it counts: a synthetic deep context must score ≥3 and a synthetic shallow one must score <3. Without that, a green result could be a bug in the counter.

- [ ] **Step 1: Write the script with its self-check**

Create `<scratch>/probe_depth.py`:

```python
"""Depth probes for the four thin corpus topics (spec 2026-07-17).

Asks: does the RETRIEVED CONTEXT for a real, specific question contain several
of the terms a source that actually teaches the topic would use, or just a
passing mention? n-of-m over concept groups; a group hits if ANY of its
alternatives appears. Context layer only - the chat model answers these from its
own knowledge, so an answer-layer check would prove nothing about the corpus.

Terms and threshold are PRE-REGISTERED in the committed plan. Do not tune.

    python probe_depth.py --self-check   # prove the counter counts, run this first
    python probe_depth.py                # measure against the live store

Needs LM Studio serving bge-m3.
"""

from __future__ import annotations

import argparse
import sys

REPO = r"D:\Claude Projects\Agro-Botany RAG & Product Linker System"
sys.path.insert(0, REPO)

THRESHOLD = 3

# Each group is one CONCEPT; it hits if any alternative appears in the context.
# Listed in both languages because the corpus is TR+EN and the topic, not the
# language, is what we are asserting (same stance as eval_set's context_any).
PROBES = [
    {
        "id": "pollination_hand",
        "query": "Kabakta elle tozlama nasıl yapılır, erkek ve dişi çiçek nasıl ayırt edilir?",
        "groups": [
            ["erkek çiçek", "male flower", "staminate", "erkek organ"],
            ["dişi çiçek", "female flower", "pistillate", "dişi organ"],
            ["anter", "anther", "başçık", "stamen", "etamin"],
            ["stigma", "tepecik", "dişicik", "pistil"],
            ["elle tozlama", "hand pollination", "el ile tozla", "yapay tozla",
             "artificial pollination"],
            ["meyve tutumu", "fruit set", "sabah saat", "anthesis", "çiçek açma"],
        ],
    },
    {
        "id": "grafting_methods",
        "query": "Meyve ağacında kalem aşısı ile göz aşısı arasındaki fark nedir, hangi mevsimde yapılır?",
        "groups": [
            ["kambiyum", "cambium"],
            ["kalem", "scion"],
            ["anaç", "rootstock"],
            ["göz aşısı", "bud graft", "budding", "kalem aşısı", "whip",
             "cleft", "yarma aşı", "dilcikli"],
            ["kaynaş", "kallus", "callus", "graft union", "aşı yeri"],
            ["dinlenme", "dormant", "ilkbahar", "spring", "öz su", "sap flow"],
        ],
    },
    {
        "id": "greenhouse_climate",
        "query": "Serada nem ve sıcaklık kontrolü nasıl yapılır, havalandırma neye göre ayarlanır?",
        "groups": [
            ["bağıl nem", "relative humidity", "nispi nem"],
            ["buhar basınç", "vapour pressure", "vapor pressure", "vpd",
             "yoğuşma", "condensation"],
            ["tepe pencere", "ridge vent", "yan havaland", "side vent",
             "roof vent", "cebri havaland", "forced ventilation"],
            ["sıcaklık ayar", "setpoint", "set point", "gündüz sıcaklık",
             "gece sıcaklık", "day temperature", "night temperature"],
            ["gölgeleme", "shading", "thermal screen", "perde"],
            ["hava değişim", "air exchange", "air change", "hava sirkülasyon",
             "circulation"],
        ],
    },
    {
        "id": "postharvest_apple",
        "query": "Elmada hasat sonrası soğuk depolamada çürümeyi önlemek için ne yapılır?",
        "groups": [
            ["ön soğutma", "precooling", "pre-cooling", "hızlı soğutma"],
            ["etilen", "ethylene", "1-mcp"],
            ["kontrollü atmosfer", "controlled atmosphere", "modified atmosphere",
             "değiştirilmiş atmosfer"],
            ["bağıl nem", "relative humidity", "nispi nem"],
            ["çürüklük", "penicillium", "botrytis", "mavi küf", "gri küf",
             "blue mold", "gray mold", "grey mould", "acı benek", "bitter pit"],
            ["soğuk zarar", "chilling injury", "depolama sıcaklığ",
             "storage temperature"],
        ],
    },
]


def count_groups(ctx: str, groups: list[list[str]]) -> tuple[int, list[str], list[str]]:
    """(hits, hit_labels, missed_labels). A group hits if any alternative is a
    case-insensitive substring of the context. The label is the group's first
    alternative."""
    c = ctx.lower()
    hit, missed = [], []
    for g in groups:
        if any(alt.lower() in c for alt in g):
            hit.append(g[0])
        else:
            missed.append(g[0])
    return len(hit), hit, missed


def self_check() -> int:
    """Prove the counter counts before trusting any result against the store."""
    groups = PROBES[0]["groups"]

    deep = ("Kabakta erkek çiçek sabah açar; polenin anter üzerinden alınıp "
            "dişi çiçek üzerindeki stigma'ya sürülmesiyle elle tozlama yapılır.")
    shallow = ("Bahçenizde arıların tozlaşmayı sağlaması için kimyasal "
               "kullanımından kaçının. Sulama haftada bir yapılmalıdır.")
    empty = ""

    n_deep, _, _ = count_groups(deep, groups)
    n_shallow, _, _ = count_groups(shallow, groups)
    n_empty, _, _ = count_groups(empty, groups)

    ok = True
    for label, got, want in (("deep", n_deep, ">=3"),
                             ("shallow", n_shallow, "<3"),
                             ("empty", n_empty, "==0")):
        passed = (got >= 3 if want == ">=3"
                  else got == 0 if want == "==0" else got < 3)
        ok &= passed
        print(f"  self-check {label:<8} hits={got}  want {want}  "
              f"{'OK' if passed else 'FAIL'}")
    print("\nself-check:", "PASS" if ok else "FAIL - do not trust the probes")
    return 0 if ok else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description="Depth probes for thin corpus topics.")
    p.add_argument("--self-check", action="store_true",
                   help="Verify the counting logic on synthetic contexts and exit.")
    args = p.parse_args()

    if args.self_check:
        return self_check()

    from src import engine

    print(f"threshold: {THRESHOLD} of 6 concept groups\n")
    reds = []
    for probe in PROBES:
        ctx = engine.retrieve_context(probe["query"])
        n, hit, missed = count_groups(ctx, probe["groups"])
        verdict = "GREEN" if n >= THRESHOLD else "RED"
        if verdict == "RED":
            reds.append(probe["id"])
        print(f"{probe['id']:<22} {verdict}  {n}/6  ctx={len(ctx)} chars")
        print(f"    hit:    {', '.join(hit) or '-'}")
        print(f"    missed: {', '.join(missed) or '-'}\n")

    print(f"RED: {', '.join(reds) if reds else 'none - all four green'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the self-check and verify it passes**

```bash
cd "C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\ccc07c00-4104-4eb6-ad47-33de74db10c6\scratchpad"
python probe_depth.py --self-check
```

Expected output — all three lines OK, ending `self-check: PASS`:

```
  self-check deep     hits=5  want >=3  OK
  self-check shallow  hits=0  want <3   OK
  self-check empty    hits=0  want ==0  OK

self-check: PASS
```

The exact `hits=` numbers for `deep` may differ; what must hold is deep ≥3, shallow <3, empty ==0. If the shallow context scores ≥3, the groups are too loose to distinguish depth from a passing mention — STOP and report, do not proceed to Step 3 and do not silently tighten the pre-registered groups.

- [ ] **Step 3: Commit the plan's pre-registration**

Nothing to commit from the scratchpad (deliberately — the script is throwaway). The pre-registration lives in this committed plan file. Confirm it is committed before Task 2 runs:

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
git log --oneline -1 -- docs/superpowers/plans/2026-07-17-fao-breadth-depth-probe.md
```

Expected: a commit hash and message. If empty, the plan is uncommitted and the measurement is not pre-registered — commit it first.

---

### Task 2: Measure against the live store

**Files:**
- Run only: `<scratch>/probe_depth.py`

**Interfaces:**
- Consumes: Task 1's `PROBES`, `count_groups`, `THRESHOLD`.
- Produces: the RED list that Task 3 consumes.

- [ ] **Step 1: Confirm LM Studio is serving the embedding model**

```bash
curl -s http://localhost:1234/v1/models
```

Expected: JSON listing models, including a `bge-m3` entry. If this fails, start LM Studio and load bge-m3 — the probes measure retrieval and cannot run without it.

- [ ] **Step 2: Run the probes**

```bash
cd "C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\ccc07c00-4104-4eb6-ad47-33de74db10c6\scratchpad"
python probe_depth.py
```

Expected: four lines, each GREEN or RED with an n/6 score, and a final `RED:` summary. Runtime ~1 minute (four embedding calls plus vector search; no chat model).

- [ ] **Step 3: Record the raw result verbatim**

Paste the full output into the session and into the handoff note draft. Record it BEFORE interpreting it — including the `missed:` lists, which say what the corpus did not surface.

- [ ] **Step 4: Branch**

- **All four GREEN** → the thin topics cost us nothing. Skip to Task 6; Tasks 3-5 do not run. This closes handoff item 1.
- **Any RED** → continue to Task 3 for each red probe. Do NOT download anything yet.

---

### Task 3: Disambiguate each red probe (content absent vs unretrieved)

**Files:**
- Create: `<scratch>/scan_corpus.py`

**Interfaces:**
- Consumes: Task 2's RED list; `engine._get_retriever_store() -> Chroma | None` (`src/engine.py:191`), the langchain Chroma object from `ingest.get_vector_store()`. Its `.get(limit, offset, include)` is the paginated read.
- Produces: a per-red-probe verdict: `absent` (Task 4 harvests) or `present` (no harvest; record and stop).

**Why:** handoff item 5. "The corpus lacks bordeaux/sigatoka content" was obvious and wrong — 281 chunks existed; Turkish queries scored them below the 0.36 floor. A red probe alone cannot tell a content gap from a retrieval gap, and only one of those is fixed by downloading PDFs.

- [ ] **Step 1: Write the scanner**

Paginate — handoff item 19 records that fetching 93k chunks at once fails with "too many SQL variables".

Create `<scratch>/scan_corpus.py`:

```python
"""Does the corpus CONTAIN a topic's vocabulary at all, independent of whether
retrieval surfaces it? Direct scan of every chunk, no embeddings (spec
2026-07-17, disambiguation step; handoff item 5).

    python scan_corpus.py "erkek çiçek" "male flower" "hand pollination"
"""

from __future__ import annotations

import sys
from collections import Counter

REPO = r"D:\Claude Projects\Agro-Botany RAG & Product Linker System"
sys.path.insert(0, REPO)

PAGE = 5000


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    terms = [t.lower() for t in sys.argv[1:]]
    if not terms:
        print("usage: python scan_corpus.py TERM [TERM ...]")
        return 1

    from src import engine

    # Private, but this is a throwaway diagnostic. It returns the langchain
    # Chroma object from ingest.get_vector_store(), or None if the store is
    # unavailable - in which case every count below would be a misleading 0.
    store = engine._get_retriever_store()
    if store is None:
        print("vector store unavailable - a 0 here would be a lie, not a finding")
        return 1

    counts = Counter()
    sources = {t: Counter() for t in terms}
    total = offset = 0
    while True:
        page = store.get(limit=PAGE, offset=offset,
                         include=["documents", "metadatas"])
        docs = page.get("documents") or []
        metas = page.get("metadatas") or []
        if not docs:
            break
        for doc, meta in zip(docs, metas):
            d = (doc or "").lower()
            for t in terms:
                if t in d:
                    counts[t] += 1
                    src = (meta or {}).get("source", "?")
                    sources[t][src] += 1
        total += len(docs)
        offset += len(docs)

    print(f"scanned {total} chunks\n")
    for t in terms:
        print(f"{t!r}: {counts[t]} chunk(s)")
        for src, n in sources[t].most_common(5):
            print(f"    {n:>4}  {src}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the scanner finds a term that is certainly present**

Sanity-check the instrument before trusting a zero from it (item 22(b) again — a scanner that silently returns 0 for everything would "prove" every gap):

```bash
cd "C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\ccc07c00-4104-4eb6-ad47-33de74db10c6\scratchpad"
python scan_corpus.py "azot" "nitrogen"
```

Expected: `scanned ~9xxxx chunks` and thousands of hits for both terms, with `dp_`/`fao_`/`oa_` sources listed. If either returns 0, the scanner is broken — fix it before scanning anything else.

- [ ] **Step 3: Scan each red probe's missed groups**

For each RED probe, run the scanner over the alternatives of the groups it MISSED. Example, if `pollination_hand` came back red having missed the male/female-flower and hand-pollination groups:

```bash
python scan_corpus.py "erkek çiçek" "male flower" "staminate" "dişi çiçek" "female flower" "elle tozlama" "hand pollination"
```

- [ ] **Step 4: Assign a verdict per red probe**

- **Near-zero chunks across the missed groups** → `absent`. The corpus genuinely lacks it; Task 4 harvests this topic.
- **Substantial chunks exist** → `present`. This is a retrieval matter (the item-5 pattern), and FAO downloads are the wrong treatment. No harvest for this topic; record the chunk counts and the top sources in the handoff. Also note whether the hits are Turkish-only or English-only — that detail is what would inform any later retrieval work.
- **Content present ONLY under words the probe did not list** → the term list was the problem, not the corpus. Record it as a probe-design finding; no harvest.

If every red probe resolves to `present`, skip Task 4 and Task 5 and go to Task 6.

---

### Task 4: Harvest only the topics judged `absent`

**Files:**
- Run only: `src/fetch_fao.py`, `src/ingest.py`
- Modify: none — `fetch_fao.py` already takes `--set` (`src/fetch_fao.py:264`).

**Interfaces:**
- Consumes: Task 3's `absent` verdicts.
- Produces: new `fao_*.pdf` files in `docs/books/` and new chunks in the store; Task 5 re-runs the probes against them.

**Runs only if Task 3 returned at least one `absent`.**

- [ ] **Step 1: Preview what the Technical documents set offers**

`col_20.500.14283_3` is the set handoff item 1 names. Preview before downloading — the FAO filters run at ~55-60% precision (spec `2026-07-15-fao-fetcher-design.md`), so read the titles:

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m src.fetch_fao --set col_20.500.14283_3 --dry-run --max 60
```

Expected: a numbered list of `fao_id  title`. Read it and judge: do these titles plausibly carry the `absent` topics? If the set is clearly irrelevant to them, say so and stop — a harvest that cannot fix the measured gap is not justified by this plan, and the honest outcome is "FAO does not have it" recorded in Task 6.

- [ ] **Step 2: Harvest**

```bash
python -m src.fetch_fao --set col_20.500.14283_3 --max 60
```

Expected: `[fao] DONE. downloaded N paper(s)`. Existing files are skipped (`= already have ...`) and previously pruned ids are skipped — the fetcher is incremental.

- [ ] **Step 3: Ingest**

```bash
python -m src.ingest
```

Expected: new files chunked and added; already-ingested files auto-skipped. Watch the zero-chunk report at the end (added in handoff item 8) — any image-only PDF listed there contributes nothing and should be moved to `docs/books/_offtopic/`.

- [ ] **Step 4: Re-run the probes on the pre-registered terms**

```bash
cd "C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\ccc07c00-4104-4eb6-ad47-33de74db10c6\scratchpad"
python probe_depth.py
```

Expected: the previously-red `absent` probes now score ≥3. Same terms, same threshold — no edits.

- Probe went **red → green**: the harvest worked. It earns an eval case in Task 5.
- Probe **still red**: the harvest did not fix it. It does NOT get an eval case (spec: only probes that go green are promoted). Record it in Task 6 as "measured, FAO does not have it" so item 1 is not re-opened on the same hunch.

- [ ] **Step 5: Confirm no regression, then commit**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m evals.run_eval
```

Expected: `31/31` on every dimension, exactly as before the harvest. A drop means the new chunks are displacing good context — investigate before committing anything.

The corpus itself is gitignored, so there may be nothing to commit here (handoff item 7 hit the same: "Corpus only - nothing to commit"). If `_offtopic` quarantine or a filter change was needed, commit that:

```bash
git add -A
git commit -m "Harvest FAO technical docs for the measured-thin topics"
```

---

### Task 5: Promote the rescued probes into the eval

**Files:**
- Modify: `evals/run_eval.py` (add `_context_min_ok`, wire into the `context` dimension)
- Modify: `evals/eval_set.py` (document `context_min`; add the promoted case(s))
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Consumes: Task 4's red→green probes (their queries, groups, threshold).
- Produces: `context_min` as an eval_set field: `{"terms": list[list[str]], "n": int}`; `_context_min_ok(case: dict, ctx: str) -> bool`.

**Runs only if at least one probe went red→green in Task 4.** If none did, `context_min` has no user and must not be added — that is the dead-code outcome the spec exists to avoid.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_run_eval.py`:

```python
def test_context_min_requires_n_of_m_groups():
    case = {"context_min": {"terms": [["erkek çiçek", "male flower"],
                                      ["stigma"],
                                      ["anter", "anther"]],
                            "n": 2}}
    assert run_eval._context_min_ok(case, "erkek çiçek ve stigma anlatılır")
    assert not run_eval._context_min_ok(case, "sadece erkek çiçek geçer")


def test_context_min_absent_field_passes():
    assert run_eval._context_min_ok({}, "anything")


def test_context_min_group_hits_on_any_alternative():
    case = {"context_min": {"terms": [["erkek çiçek", "male flower"]], "n": 1}}
    assert run_eval._context_min_ok(case, "the MALE FLOWER opens at dawn")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m pytest tests/test_run_eval.py -k context_min -v
```

Expected: FAIL — `AttributeError: module 'evals.run_eval' has no attribute '_context_min_ok'`.

- [ ] **Step 3: Implement it**

In `evals/run_eval.py`, beside `_context_ok` (line 35):

```python
def _context_min_ok(case: dict, ctx: str) -> bool:
    """The retrieved context must cover at least n of m CONCEPT groups.

    context_any asserts the topic was retrieved at all; this asserts the corpus
    goes DEEP on it - a source that teaches a topic uses several of its specific
    terms together, one that mentions it in passing uses one. A group hits if any
    of its alternatives appears, so the check has teeth without being brittle
    about synonyms. Context layer by design: the chat model answers these from
    parametric knowledge, so an answer-layer depth check would pass without any
    corpus support at all.
    """
    spec = case.get("context_min")
    if not spec:
        return True
    c = ctx.lower()
    hits = sum(1 for group in spec["terms"]
               if any(alt.lower() in c for alt in group))
    return hits >= spec["n"]
```

Wire it into the `context` dimension in `run()` (line ~101-102):

```python
               "retrieval": _retrieval_ok(c, ctx),
               "context": _context_ok(c, ctx) and _context_min_ok(c, ctx)}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_run_eval.py -k context_min -v
```

Expected: 3 passed.

- [ ] **Step 5: Add the promoted case(s) to `eval_set.py`**

For each red→green probe, add a case using its EXACT pre-registered query, groups, and threshold from Task 1. Example for `pollination_hand` — copy the real groups from the script, do not paraphrase them:

```python
    {"id": "pollination_hand", "category": "horticulture",
     "query": "Kabakta elle tozlama nasıl yapılır, erkek ve dişi çiçek nasıl ayırt edilir?",
     "retrieval": "nonempty", "products": "none",
     "context_min": {"n": 3, "terms": [
         ["erkek çiçek", "male flower", "staminate", "erkek organ"],
         ["dişi çiçek", "female flower", "pistillate", "dişi organ"],
         ["anter", "anther", "başçık", "stamen", "etamin"],
         ["stigma", "tepecik", "dişicik", "pistil"],
         ["elle tozlama", "hand pollination", "el ile tozla", "yapay tozla",
          "artificial pollination"],
         ["meyve tutumu", "fruit set", "sabah saat", "anthesis", "çiçek açma"]]},
     "answer_any": ["tozla", "polen", "çiçek", "erkek", "dişi"]},
```

`products: "none"` follows eval_set's stated stance — the catalog is 48 fertilizers and none of them answers a pollination question (`eval_set.py:24-42`).

Document the field in the `eval_set.py` docstring, after the `context_any` entry (line ~23):

```
- context_min: {"n": int, "terms": [[alt, alt, ...], ...]}; the RETRIEVED CONTEXT
             must cover at least n of the m concept groups (a group hits if any
             alternative appears). Where context_any asserts the topic was
             retrieved, this asserts the corpus is DEEP enough to teach it:
             a real source uses several of a topic's specific terms together.
             Terms are PRE-REGISTERED (plan 2026-07-17) and were measured red
             before the harvest that fixed them - do not tune them to taste.
             Context layer by design: these questions are answerable from the
             model's own knowledge, so an answer_any depth check would pass with
             an empty corpus.
```

- [ ] **Step 6: Prove the new case guards something**

A promoted case must be shown red against the pre-harvest state, or it is decoration. The harvest already happened, so demonstrate it the way item 12 demonstrated the cross-lingual cases (by flipping a control): temporarily raise `n` above 6 in the case, confirm the case goes red, then restore it.

```bash
python -m evals.run_eval --fast --only pollination_hand
```

Expected: with `n` restored, the case passes on the `context` dimension. With `n: 7`, it fails — proving the dimension is live and reading this case's terms.

- [ ] **Step 7: Run the full suite and the full eval**

```bash
python -m pytest -q
python -m evals.run_eval
```

Expected: suite all green (no failures; don't assert a count — commit `f2881bd` removed the hardcoded counts precisely because they go stale), eval green on every dimension with the new case(s) included.

- [ ] **Step 8: Commit**

```bash
git add evals/run_eval.py evals/eval_set.py tests/test_run_eval.py
git commit -m "Add context_min: assert the corpus goes deep, not just on-topic"
```

---

### Task 6: Record the finding and close handoff item 1

**Files:**
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`

**Runs in every branch, including all-four-green.** The measurement is the deliverable; an unrecorded measurement gets re-litigated on the same hunch six weeks later, which is the failure mode the "DO NOT RE-CHASE" lists exist to prevent.

- [ ] **Step 1: Rewrite handoff item 1 with what was measured**

Replace the "More FAO breadth (optional)" item with the outcome. Include, verbatim from Task 2's output: each probe's n/6 score and its missed groups; for every red, Task 3's chunk counts and verdict; for every harvest, what it changed.

If all four came back green, say so plainly and close the item — e.g.:

```
1. **FAO breadth: MEASURED, no harvest needed (2026-07-17)** - spec
   `docs/superpowers/specs/2026-07-17-fao-breadth-depth-probe-design.md` + plan.
   The item-3 audit called 4 topics thin by CHUNK SHARE (pollination 0.5%,
   pruning/grafting 1.9%, greenhouse 2.3%, post-harvest) - a volume metric, not a
   quality one. Pre-registered depth probes (n-of-m specific terms over the
   RETRIEVED CONTEXT, n=3 of 6) scored: <paste scores>. Thin != failing.
   **DO NOT RE-CHASE** on chunk share alone; re-open only with a real question
   the assistant answers badly.
   Why the context layer: an answer-layer probe is vacuous here - gemma answers
   hand-pollination from parametric knowledge with an empty corpus.
```

- [ ] **Step 2: Verify the handoff still matches reality**

Check that the numbers quoted in the rewritten item match the actual run output — not the plan's illustrative examples. Any figure in a handoff note that nobody re-derived is a figure that quietly goes stale (item 22(a)).

- [ ] **Step 3: Commit**

Memory files live outside the repo and are not committed. If the harvest changed anything tracked, that was already committed in Task 4/5. Confirm the tree is clean:

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
git status --short
```

Expected: clean, or only the pre-existing untracked `docs/books/_offtopic/`.
