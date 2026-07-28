# Expand the corpus_fact panel, round 4 — design

**Date:** 2026-07-21
**Status:** design (approved in brainstorming)
**Extends:** round 3 (`2026-07-20-expand-corpus-fact-panel-round3-design.md`), which
itself extends the corpus-dependence map (`2026-07-18-corpus-dependence-map-design.md`).
Round 3's rules BIND this round; only what is listed under §2 as changed is new.

## 1. Purpose & success criteria

Grow the eval's retrieval guard: panel **18 → 22** `corpus_fact` cases
(corpus-carried **17 → 21**). Pure DATA authoring on existing machinery — **no code
change**; `pytest -q` stays **180**.

**Success =**
- Up to **15 candidates** mined and validated in both directions.
- Target **+4 corpus-carried** cases in `evals/eval_set.py`.
- Every shipped case clears §2's diversity rules and records a live-measured
  `corpus_class`.
- `python -m evals.run_eval --faithfulness --repeat 4` exits 0 — no recorded
  corpus-carried case regresses.
- Dropped candidates recorded in-file; candidates rejected before running recorded in a
  committed slate.

**Expected yield is LOWER than round 3's, stated up front so a shortfall is not
misread as failure.** Round 3 shipped 4 from 10 mined (~40%). The easy Zone-1 vein is
partly exhausted: five local-cultivar candidates have already been tried and dropped
for four different reasons — walnut (retrieval-broken), apricot (corpus-harmful),
cherry (answer-side), avocado (model-carried), Akça pear (retrieval-broken). **+4 is a
target, not a commitment. If the budget runs out at 2, ship 2 and record why.**

**Explicit non-goals:** hitting +4 by loosening an assertion; adding corpus data;
touching the prompt or retrieval code; inventing a new claim shape to dodge a cap.

**What this still does NOT mean:** the panel is a drift GUARD and a scoreboard over
self-selected cases, not a coverage meter. "21/22 corpus-carried" would mean "21 of the
22 cases we built to need the corpus do" — never "the corpus answers 95% of user
questions."

## 2. Rules

### Inherited unchanged from round 3

Assertion frozen before the first run. Broadening legitimate ONLY as an alternate
NOTATION of the same value — the test is *same value, or different claim?*
Answer-naturalness test applied before running. `context_any` source-specific, not a
query echo (bare cultivar name allowed for local-cultivar cases, the deveci precedent).
Validation in both directions. A normal read of exactly 2/4 escalates to `--repeat 8`.
**A red case is a map finding to DROP, never to tune green.**

### Now standard, earned in round 3

- **`--faithfulness` alone cannot validate a case.** It classifies on `answer_any`
  grounding only and never reads `context_any` (`run_eval.py:323-325`), so a case can
  read a textbook `4/4 vs 0/4` while retrieval never surfaced the source — the grounding
  firing on a list-echo off a methods roster. **Every case must also pass a normal
  `run_eval --only <id>` with `ret=True ctx=True`.**
- **Every `context_any` anchor must be verified UNIQUE to its source before the case
  runs**, checked **case-insensitively** (`_matches` is case-insensitive; a source
  sentence beginning "En düşük…" reads as zero hits under a naive scan). ANY-semantics
  means one non-unique anchor makes a green `ctx` prove nothing.

### CHANGED this round — the crop cap is now absolute

Round 3's crop rule was *"new, or represented at most once → at most one further case
each **this round**"*. Repeated verbatim each round, that raises the ceiling by one
every round and rebuilds the very concentration it exists to prevent.

**New rule: no crop may exceed 2 cases panel-wide, ever.** Round-independent and
countable. Pear stays grandfathered at 6 — existing cases are valid guards and are not
removed — but **no new pear case may be added.**

Note this is IDENTICAL in effect to round 3's rule for round 4 (every non-pear crop
sits at 1, so both allow +1). The difference bites from round 5 onward, which is why
fixing it now costs nothing.

**Why the cap is 2 and not tighter:** the crop axis matters LESS than the source axis.
The correlation that makes a guard weak is a shared DOCUMENT — same retrieval path,
same chunk family, cases go red together. Two apple cases from two different papers do
not fail together. A cap of 2 prevents monoculture without making mining needlessly hard.

### Round-4 starting position

**Rule 1 — banned sources (16), already in the panel:**
`dp_1399494`, `dp_21748`, `dp_1004550`, `dp_21747`, `dp_19393`, `dp_1292456`,
`dp_1797532`, `dp_19373`, `dp_1514564`, `dp_30474`, `dp_1559843`, `dp_19394`,
`dp_19531`, `dp_21713`, `dp_21735`, `dp_30475`.

**Rule 2 — crops.** Pear BANNED (6). At 1, each may take **one** more: apple,
persimmon, pomegranate, safflower, raspberry, chickpea, carob, grape, maize, wheat,
rangeland/forage. Any other crop may take up to 2. `disease_rhizoctonia_biocontrol` is
crop-free (a soil pathogen) and consumes no crop slot.

**Rule 3 — claim-shape cap of 3, panel-wide:**

| Claim shape | Now | New allowed |
|---|---|---|
| self-fertility verdict | 4 | **0** (already over; grandfathered) |
| **named plant material** (was: `resistant-cultivar list` 2 + `region-adapted cultivar rec.` 2 — ONE family, see below) | **5** | **0** (already over; **grandfathered**) |
| storage duration / condition | 2 | 1 |
| **input application rate** (was: `nitrogen dose`) | 2 | 1 |
| harvest timing | 1 | 2 |
| drying pretreatment | 1 | 2 |
| biocontrol-agent list | 1 | 2 |
| minimum-diameter threshold | 1 | 2 |
| bud load | 1 | 2 |
| sowing date | 1 | 2 |
| (any brand-new shape) | 0 | 3 |

**How a claim shape is defined — added 2026-07-21 after round 4's slate review found
the cap being evaded by relabelling.** A shape is defined by the **STRUCTURE of the
assertion** — a recommended value plus its unit; a named plant material; a duration; a
list of named agents — **not by the application context or the unit's denominator.**
Compost t/da, seed-treatment g/100 kg, pot fertilizer g/saksı and micronutrient ppm are
therefore **ONE shape** (an input application rate), the same bucket as `nitrogen dose`.
Likewise, "which rootstock is recommended for region X" is the same shape as "which
cultivar is recommended for region X" — a region-adapted plant-material recommendation.
**Slicing an existing shape finely enough to open a "new" bucket defeats the cap**, and
round 4's first slate did exactly that: 9 of its 10 rows claimed brand-new buckets, four
of which collapsed into the dose family under this definition.

This is the failure this spec predicted for the ROUND-3 rule and did not fully close:
"'same shape' is a judgment call, and a rule applied by judgment bends under mining
pressure." Making the cap a cap rather than a ban was right; leaving the LABELLING free
was the remaining gap.

#### `named plant material` is ONE family, and it is ALREADY OVER CAP — adjudicated 2026-07-21

**Added by the final whole-branch review, which found the amendment above still
being evaded in the very table it amends.** The table previously carried
`resistant-cultivar list` (2) and `region-adapted cultivar rec.` (2) as SEPARATE
buckets. They are not separate. Both assert **a named plant material** — the exact
structure the amendment lists as one of its four canonical shapes — and they differ
only in the **application context** that motivates the naming (disease resistance vs
regional adaptation). Splitting on application context is precisely the evasion the
amendment bans; the amendment banned it for the dose family and then left it
standing one row above.

The split also does not survive contact with the cases. `local_oltu_raspberry`'s
assertion is a **two-name LIST** ("hollanda boduru", "newburg") yet sat in the
"region-adapted" bucket, while the fireblight and chickpea lists sat in
"resistant-cultivar list". So the recorded split was never singular-vs-list either —
it was disease-resistance vs regional adaptation, i.e. application context, full stop.

**Ruling: `named plant material` is one family. It currently holds FIVE cases,
against a cap of 3:**

| # | case id | why it is named plant material |
|---|---|---|
| 1 | `disease_fireblight_resistant` | names resistant cultivars |
| 2 | `local_chickpea_blight_cultivars` | names resistant cultivars |
| 3 | `local_diyarbakir_safflower` | names a region-adapted cultivar |
| 4 | `local_oltu_raspberry` | names region-adapted cultivars (a two-name list) |
| 5 | `local_antalya_grapefruit_rootstock` | names a region-adapted rootstock — **shipped THIS round; this is the case that landed at the collapse point** |

**Grandfathered, exactly as `self-fertility verdict` (4 against a cap of 3) already
is. The five existing cases REMAIN VALID GUARDS and are not removed, retuned, or
renamed. But NO NEW named-plant-material case may be added — ever, in any round.**
A cap binds FORWARD; it does not delete guards that were measured and shipped
honestly under a labelling that was wrong. Deleting them would trade a real
retrieval guard for a bookkeeping tidy, which is the wrong direction.

Note what this costs round 5, stated so it is not rediscovered as a surprise: the
"local cultivar recommendation" vein — round 3's and round 4's most productive
source of candidates — is now **CLOSED**. Round 5 must mine other shapes, and the
only headroom left is in the four buckets round 4 opened (training-system choice,
sowing-implement choice, irrigation level, graft-material state) and in genuinely
new shapes.

`local_antalya_grapefruit_rootstock` is recorded as the case that landed at the
collapse point: it shipped as the last member of the merged family before the
family was recognised as over cap. It is not a rule violation by the author — the
family did not exist as one bucket when it was mined — and it is not being
unshipped. It is the boundary marker.

### Do NOT re-mine these — already measured and dropped

Re-trying them burns budget on known answers: Şebin walnut (`dp_1089365`),
Hacıhaliloğlu apricot (`dp_1217921`), 0900 Ziraat cherry (`dp_1154776`), Antalya
avocado (`dp_19510`), Akça pear (`dp_19393`), guar bean row spacing (`dp_257760`),
vetch phosphorus (`dp_30458`), Ege durum wheat (`dp_21741`), pea sowing date
(`dp_21712`). Plus every source listed in round 3's committed slate
(`docs/superpowers/2026-07-20-round3-candidate-slate.md`, §"Rejected at slate time").

## 3. Mining → validation pipeline

**Mining (budget 15).** Scan for sources clearing rules 1-3 that carry a concrete
finding **in the paper's own conclusion/recommendation sentence**. Round 3's approach
works and is reused: a conclusion-marker + concrete-value filter, then **read the text
of every shortlisted source**. Round 3 found 237 sources passing a naive filter, and the
binding constraint was assertion QUALITY, not supply — most were results-table ranges
that fail the answer-naturalness test. Never shortlist on a match count alone: `amasya`'s
hits were a province in a beetle survey, `gemlik`'s were olive-oil authenticity.

- **A mine-time REJECTION is a collision signal, not a deletion. Added 2026-07-21
  after round 4's final review.** Rejecting a source removes it from the candidate
  pool; it does NOT remove it from the vector store, so it remains fully
  retrievable and can still take a shipped case's retrieval path. **Before ranking
  the surviving rows, re-check each one against the rejection list for a source
  sharing its CROP and its INPUT/intervention, and record the collision in the row
  or de-rank it.** This is a read-only slate-time check, done in the same pass as
  anchor uniqueness, and it costs no model time. Round 4 paid for skipping it: it
  rejected `dp_19431` (sunflower + humic acid, Ankara) as multi-valued, then ranked
  `dp_19600` (sunflower + humic acid, Ankara) **RANK 1 with no collision note**.
  That row measured retrieval-broken with all four retrieved chunks from
  `dp_19431`. A contributing cause was a one-word error in the rejection list —
  `dp_19431` was recorded as "aspir" (safflower) rather than sunflower, which made
  the two rows look unrelated. **Crop labels in a rejection list are load-bearing**,
  because the next round's collision check reads them.

### STANDING RULE — verify every anchor against the STORED CHUNK TEXT, never against the PDF

**Added 2026-07-21 after round 4's first slate review. This is the round's most
transferable lesson and it binds every future round.**

An anchor must be confirmed present **as a contiguous run in the vector store**,
queried programmatically, before it is written into a slate. A PDF reader, a
copy-paste of the paper, or the source quote in a slate row is **NOT evidence that
an anchor matches.** The store's text is the product of PDF extraction, and it
differs from what the paper looks like.

**Round 4's first slate had TEN of its twenty anchors dead on arrival** — rows 1,
2, 6 and 9 had ZERO working anchors, so `ctx` could never have gone green for
them. Every one had been read off the PDF and looked perfect. Three defect classes,
all invisible in a PDF reader:

1. **Line breaks mid-phrase.** Extraction preserves the paper's line wrapping, so
   the store holds `toprağa zarar \nvermeden`, `kentsel \nkatı atık`,
   `ekimden önce \nayçiçeği`, `çıkış oranı\nindeksi`. `_matches` does **no
   whitespace normalization** — it is `re.escape(term)` against raw chunk text — so
   a space in the anchor cannot match a newline in the store. This killed 8 of the
   10. Any anchor longer than a few words is likely to straddle a line break
   somewhere; the longer the anchor, the likelier it is dead.
2. **Curly punctuation.** The store holds U+2019 (`’`), not ASCII `'`. An anchor
   typed with a straight apostrophe silently matches nothing.
3. **Replacement characters.** Extraction can emit U+FFFD where the PDF had a
   glyph it could not map — the store holds `gonca�çiçek sayısı` where the paper
   shows `gonca-çiçek sayısı`.

**This check belongs at slate time, not at validation time.** It costs one
read-only store query per anchor and no model time. Deferred to validation it
costs a full generation run to discover, and — worse — a dead anchor does not fail
loudly: it produces `ctx=False`, which reads as a *retrieval-broken finding about
the corpus* rather than as a typo in the slate. A round-3 candidate was nearly
recorded that way. **A dead anchor is a slate bug that disguises itself as map
data**, which is why it must be caught before it can contaminate the map.

Practical form of the check: for each anchor, scan the store's chunks with the
exact `_matches` semantics, case-insensitively and corpus-wide, and record the
hit count, the source, and the pages. That same query simultaneously satisfies the
uniqueness rule above, so the two checks are one query, not two. **If an anchor
returns zero chunks, do not shorten it by guesswork — read the stored chunk and
pick a run that exists in it.**

Note the rule is about `context_any`, which is matched against retrieved CHUNK
TEXT. `answer_any` is matched against the MODEL'S ANSWER, so an `answer_any` form
with zero corpus hits is legitimate — a model may use a notation the paper does
not. Slates should say so explicitly where it occurs, so a zero count is not later
mistaken for a dead anchor of the kind this rule exists to catch.

**Per-candidate validation, in this order — the order is deliberate:**

1. **Anchor uniqueness** (before any run, case-insensitive). Cheapest check, and round 3
   shipped an anchor that collided with a paper mining had explicitly REJECTED.
2. **Ablated direction.** A case that grounds with an EMPTY corpus is already dead,
   whatever it does normally — cheapest elimination.
3. **Normal direction**, `--faithfulness --repeat 4`; a normal read of exactly 2/4
   escalates to `--repeat 8` (bpmorettini read 2/4 and was real at 7/8; guar bean read
   2/4 and was 0/8).
4. **Normal-run `ret=True ctx=True`.** Round 3's durum-wheat candidate classified a
   textbook corpus-carried 4/4 vs 0/4 and would have shipped as a FALSE guard without
   this step.
5. **Confirm the finding in the source PDF** for anything shipped.

Only **corpus-carried** candidates ship. model-carried / retrieval-broken /
corpus-harmful results are map DATA, recorded as in-file drop-log comments with their
measured counts, so a future session does not re-chase them as data gaps.

## 4. Exit gates

1. `python -m evals.run_eval --faithfulness --repeat 4` — whole panel. **See the two-stage
   protocol below: a flag is not automatically a failure.**
2. `python -m evals.run_eval --no-context --only local` — exit 0.
3. `python -m pytest -q` — **180**, unchanged.
4. `git diff --stat main..HEAD` — only `evals/eval_set.py`, this spec, the plan, and the
   round-4 slate.

### STANDING RULE — the drift gate is TWO-STAGE

**Adopted 2026-07-21, after round 4's own gate run. This amends gate 1 above and binds every
future round.**

Run `--faithfulness --repeat 4` over the whole panel. **Every flagged case is then measured
ONCE at `--repeat 8`, and that verdict is FINAL in both directions** — a repeat-8 red is a
real regression and merge stops; a repeat-8 green clears the flag. There is no second
escalation. **"Re-run until it goes green" is forbidden**: that is tuning-to-green at the
gate level, the same defect as widening an assertion to rescue a red case.

**Why the gate needed this.** Round 4's run exited 1, flagging `local_deveci_pear` (1/4) and
`quant_rose_pot_fertilizer_dose` (1/4). Both then measured **6/8 with ablated 0/8** — no
regression existed. The branch had changed no code and no corpus, only appended independent
case dicts, so no existing case *could* regress because of it. A gate defined purely as
"repeat 4 exits 0" therefore fails while nothing is wrong, and will do so more often as the
panel grows and intermittent cases accumulate.

> ### ⚠ CORRECTION 2026-07-29 — the numbers below are SUPERSEDED
>
> Everything from here to the end of this subsection was computed from `p` estimates that
> two INSTRUMENT DEFECTS had deflated: the matcher could not see a value stated in LaTeX
> (fixed `8048435`) or split by markdown emphasis (fixed `b09d334`). Re-measured at
> `--repeat 8` after both fixes, pooled with the answer log:
>
> | case | `p` used below | measured `k/n` | `p̂` |
> |---|---|---|---|
> | `quant_rose_pot_fertilizer_dose` | 0.625 | **19/19** | 1.000 |
> | `local_deveci_pear` | 0.750 | **19/19** | 1.000 |
> | `local_scarletspur_apple` | 0.750 | **19/19** | 1.000 |
> | `local_bpmorettini_pear` | 0.750 | **23/25** | 0.920 |
>
> Three of the four were artifacts. Only `local_bpmorettini_pear` is genuinely imperfect —
> and its `p̂` walked up as samples accumulated (`0.778 → 0.882 → 0.920`), so every earlier
> reading of it, including the 0.750 assumed below, was over-confident.
>
> **Panel-wide: 29.7% → 0.2% at repeat 4, and 21.1% → 0.0% at repeat 8** (point estimate,
> same structure — only known-flaky cases get `p<1`). At each measured case's one-sided 95%
> lower bound it is **7.2% / 2.7%**, so even the worst case is a quarter of the old point
> estimate. All counts are POOLED across runs, pre-committed before each run.
>
> **The two-stage protocol STANDS, but the reasoning below does NOT — do not re-quote it.**
> "The proportional threshold means repeat-8 barely helps" is false at clean `p`: repeat-8
> more than halves the panel figure. What actually justifies stopping at two stages is that
> repeat-4's absolute false alarm is already ~3.7%.
>
> Also: the `p = 0.875 / repeat 4` cell below reads 1.2%; the correct value is **0.7%**
> (1.2% is what `p = 0.85` gives). Verified against `_classify`'s actual flag condition,
> `2*normal < repeat`, i.e. `fa(n,p) = P(Bin(n,p) < n/2)`.
>
> The rose paragraph's diagnosis ("the source writes '3 ile 6 g/saksı', so the model reports
> the range") was a plausible corpus-level story fitted to a number the instrument produced.
> All 8 fresh samples named 6 g. **The rose drop trigger is void.** Details in the
> `handoff-next-steps` memory.

**Why NOT simply raise the whole-panel gate to `--repeat 8`** — measured, and it is the
expensive non-fix. `_classify`'s threshold is PROPORTIONAL (`normal ≥ n/2`), so extra samples
sharpen the estimate without moving the bar: they help a high-`p` case and barely touch a
borderline one.

| case `p` | false alarm at repeat 4 | at repeat 8 |
|---|---|---|
| 0.875 | 1.2% | 0.1% |
| 0.750 | 5.1% | 2.7% |
| 0.625 | 15.2% | **13.7%** |

Panel-wide that is **29.7% → 21.1% for double the runtime** (~80 min → ~160 min), and about
two-thirds of the remaining 21% comes from a single borderline case. The two-stage protocol
costs ~95 min and reached the identical conclusion.

**Recorded observation, not yet acted on:** `quant_rose_pot_fertilizer_dose` grounds at
`p ≈ 0.625` (pooled 10 of 16) against a clean ablated 0/8. Its corpus-dependence is real but
its own noise swamps its signal, and it cannot be repaired — the source writes "3 ile
6 g/saksı" in its verdict chunk, so the model sometimes reports the range, and widening
`answer_any` to accept that is a different claim. It stays for now; drop it only if its
pooled `p` keeps falling across future runs, never on a single bad read.

**Execution constraint:** shared working tree, **strictly sequential** subagents (or
inline), **exactly one eval process at a time**. Worktree isolation is impossible here —
a fresh worktree gets tracked files only, and both `data/vector_store/` and `.env` are
gitignored, so an isolated worktree cannot mine or run the eval at all.

**Ops:** run from the repo root (`config.py` reads a relative `.env`). LM Studio serving
bge-m3 + gemma at :1234, gemma's Max Concurrent Predictions = 1. `PYTHONIOENCODING=utf-8`
on every command — the Windows console is cp1252 and Turkish characters raise
`UnicodeEncodeError`.

**Durable record:** candidates rejected before running go into a committed slate
(`docs/superpowers/2026-07-21-round4-candidate-slate.md`), the way round 3's final review
required — otherwise shortlisted-but-unrun candidates leave no trace and get re-mined.
