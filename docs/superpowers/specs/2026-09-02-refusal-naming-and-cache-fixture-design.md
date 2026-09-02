# A refusal names a density that was never computed, and a cache stays clean by accident

Design, 2026-09-02. Two small, unrelated repairs taken in one round because neither earns a
round of its own and both sit in the same file family.

---

## A. `province_median_density_above_ceiling` is wrong for 191 of its 275 entries

The zero-area round (`85b2623`) put a year of zero recorded orchard into
`_province_area_never_orchard`'s median as `_UNBOUNDED_DENSITY`. The gate then refuses the
province and records:

```json
{"crop": "İncir (Yaş)", "province": "Düzce", "year": 0,
 "reason": "province_median_density_above_ceiling"}
```

Düzce's ten judged years are ten zero-area years. **No density was ever computed for it.** The
entry names a measurement that did not happen — the defect class this project already holds
comments to, applied to the committed record a reader is meant to trust.

### The shape, measured

The 275 province-level refusals in the shipped file split four ways:

| shape | entries | is the current name true? |
|---|---|---|
| all members finite, median above 444 | 63 | **yes** |
| every member unbounded — no density ever computed | 132 | no |
| mixed, the median itself unbounded | 59 | no |
| mixed, median finite and above 444 | 21 | **yes** |

### The cut is the median, not the members

An earlier reading of this defect put it at 132 — the entries with no finite member at all.
That is the wrong line. **The rule tests one thing, `statistics.median(densities) >
_MAX_TREES_PER_DA`, so the honest question is what sits at the middle.** Where the median is
unbounded, no density is at the middle and the name misdescribes it, whether or not the
province also recorded some real orchard years. İncir (Yaş)/Kırklareli has ten judged years,
six of them zero: four real densities exist, and none of them is what the verdict rests on.

So 191 entries take a new reason and 84 keep the existing one.

### The name

**`province_median_year_records_no_orchard`.**

The median year records no compact orchard area — parallel in grammar to the reason it sits
beside, so the record reads as one family, and stating what the gate found rather than what a
reader might infer from it.

**One qualification, added after review rather than claimed away.** For 14 of the 191 the
judged years are even in number and split exactly in half — five zero against five real in
twelve of them, four against four in Zerdali/Batman and Vişne/Batman. There
is then no single median year: there are two, and one of them records a real orchard. The
median is still unbounded — `statistics.median` averages the middle pair and an unbounded
member absorbs — so those provinces belong on this side of the cut, but the name's singular
"median year" is imprecise for them.

It is kept anyway. One of the two middle years does record no orchard, so the name is imprecise
rather than false, and it is strictly better than the old name, which was flatly false there —
the median is not a density. A further rename would cost another full rebuild of the data file
for a marginal gain. Recorded here so it is a decision rather than an oversight.

### What it costs

**No served figure changes.** The province is refused either way and its whole derived half
goes; only the reason string differs. The `crops` block of `data/crop_norms.json` must come out
byte-identical, and that is the property the tests assert rather than a hope. `meta` changes,
so the file is regenerated.

---

## B. `tests/test_norms.py`'s cache hygiene holds by accident

`norms._load` is `@lru_cache(maxsize=1)`. The file's `_write` helper repoints `norms._PATH` at a
temp file and clears the cache **on the way in and not on the way out**:

```python
def _write(tmp_path, monkeypatch, payload):
    """Point norms at a temporary file and clear its cache."""
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    return path
```

`monkeypatch` restores `_PATH` at teardown; the cache is not restored with it. A fixture table
of one or two crops therefore survives into whatever runs next.

### It does not leak today, and the reason is the finding

Measured: after `tests/test_norms.py` the cache holds the real 246 crops. What keeps it clean is
`test_the_shipped_file_keeps_the_two_tomatoes_apart`, which calls `norms._load.cache_clear()`
**for its own purposes** and happens to be defined after the last `_write` test. A test about
tomatoes is protecting the file.

Reorder the file, or add one `_write` test below it, and the protection is gone. The danger is
not hypothetical: `tests/test_shipped_norms.py` exists as a separate file precisely because a
real-data test sitting among fixture tests *"would silently read the fixture and pass
vacuously"* — its own words. The same trap is live inside `test_norms.py`, defused by an
accident of ordering.

The same shape already leaked once for real, in `tests/test_build_crop_norms.py`, and was fixed
there during P4 with a trailing `cache_clear()` and a comment saying why.

### The fix: copy the shape that already works

`tests/test_crop_compare.py` solves this correctly:

```python
@pytest.fixture(autouse=True)
def table(tmp_path, monkeypatch):
    ...
    norms._load.cache_clear()
    crop_compare._families.cache_clear()
    yield
    norms._load.cache_clear()
    crop_compare._families.cache_clear()
```

`tests/test_norms.py` gains an autouse fixture that clears `norms._load` after every test.
`_write` keeps its clear on the way in. `norms._load` is the module's only cache — checked, one
`@lru_cache` in the file — so nothing else needs clearing.

**Two** manual `norms._load.cache_clear()` calls then become redundant and are removed — in
`test_the_shipped_file_still_carries_provincial_yields` and in
`test_the_shipped_file_keeps_the_two_tomatoes_apart`. Both are real-data tests defending
themselves by hand against the fixture tests above them, and between them they are what has
kept the file honest. With the fixture in place each of them is preceded by a teardown that
just cleared, so the clear inside them buys nothing, and leaving a redundant clear that reads
as load-bearing is its own small untruth — the next person to touch those tests would not know
whether it may go.

Note the limit of what the fixture provides, since the round has already written one sentence
overreaching it: clearing after every test guarantees that nothing this file caches escapes
into what runs later, and that each test after the first starts clean. The first test in the
file is covered by `_write`'s own clear on entry, not by the fixture.

Removing them is also what makes the fixture testable: with the manual clears gone, deleting
the fixture's own clear must turn both of those tests red. That is the mutation below. Three
further redundant clears were found during review and removed too, so the measured count is
**four** red tests, not two.

`tests/test_shipped_norms.py` keeps its manual clear. That file documents it as an instrument
check — *"PROVE THE INSTRUMENT BEFORE TRUSTING IT"* — which is a different job from hygiene,
and it is out of scope here.

---

## Testing

**A**, in `tests/test_build_crop_norms.py`:
- a province whose judged years are all zero-area is recorded as
  `province_median_year_records_no_orchard`
- a province with real densities either side of the middle, mixed with zero years so the median
  lands unbounded, gets the same reason — this is the 59-entry shape and the one the 132 cut
  would have missed
- a province refused on finite densities alone keeps `province_median_density_above_ceiling`
- a province with zero years whose median is nevertheless finite and above 444 also keeps it —
  the boundary between the two names, in the direction that is easy to get wrong

**B**, in `tests/test_norms.py`: the fixture is pinned by MUTATION, not by a test that asserts
its existence. Removing the clear after `yield` must turn something red. If nothing goes red,
the fixture pins nothing and the round has bought a comment rather than a guarantee — that
outcome must be reported, not papered over.

`data/crop_norms.json` is regenerated. `test_the_shipped_file_is_what_the_builder_produces`
rebuilds and compares, so the file cannot lag the code. Expected afterwards: **66.610 served
cells, unchanged**, 1.714 refusal entries, unchanged, with 191 of them under the new reason and
84 under the old.

## As built

All of the above held: 66.610 served, the `crops` block byte-identical to main's, 1.714 entries
split 191 / 84, suite 1036.

Two figures in `_province_area_never_orchard`'s own docstring were found stale during review and
corrected in passing — the rule reaches **275 of 2.024** (crop, province) pairs, not 165 of
1.917, and removes **110** served cells, not 14. Both went wrong when the previous round put
zero-area years into this median; neither was introduced here.

The review found four false sentences from this round: two written by the round itself, one
written while repairing those, and one — a claim that a mutation turns *two* tests red when it
turns four — written in the commit titled "Say what the cache fixture proves, not what it
guarantees". That last one was stale rather than careless: it was true when measured, and an
earlier commit in the same push removed three redundant clears, which left two more tests
leaning on the fixture. Nobody re-ran the mutation after its surface changed.

That makes seven consecutive false sentences on this file across two rounds. Every one was
prose, none was code, and every one survived a careful READ and died on the first MEASUREMENT.
Recorded as a standing lesson rather than a per-round surprise.
