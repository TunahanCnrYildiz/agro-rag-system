"""Repeatable quality eval for the RAG assistant.

    python -m evals.run_eval --fast   # retrieval + raw product gating (no chat LLM)
    python -m evals.run_eval          # full: also generate answers + keyword checks

Both modes need LM Studio serving the EMBEDDING model; full mode also needs the
CHAT model (slow). Prints a per-case table + aggregate metrics; exit code is
non-zero if any case fails (so it can gate CI later).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import engine  # noqa: E402
from src.config import settings  # noqa: E402
from evals.eval_set import CASES  # noqa: E402
from evals.answer_log import AnswerLog  # noqa: E402


# LaTeX the model sometimes wraps a value in. Measured 2026-07-28: on a full run
# `local_deveci_pear` read ground=False while its answer DID state the fact, as
# `$2\pm0,5^\circ\text{C}$` - the matcher just could not see it through the markup.
# That is an instrument defect of the same class as a dead anchor: it does not fail
# loudly, it reads as a finding about the corpus. See
# docs/superpowers/specs/2026-07-28-latex-anchor-normalisation-design.md
_LATEX_UNICODE = {
    r"\pm": "±", r"\circ": "°", r"\times": "×",
    r"\approx": "≈", r"\leq": "≤", r"\geq": "≥",
}
_LATEX_WRAPPER = re.compile(r"\\(?:text|mathrm)\{([^}]*)\}")
# \, \; \! are LaTeX SPACING commands, so they become a space - deleting them would
# glue tokens together and turn `$5\,\text{C}$` into `5C`, losing a `5 C` anchor.
_LATEX_SPACING = re.compile(r"\\[,;!]")


def _normalize_latex(text: str) -> str:
    """Rewrite LaTeX math markup into the plain notation anchors are written in.

    Applied to the TEXT being searched, never to the anchor, and deliberately
    narrow: general `_` subscripts and bare `{}` are NOT touched - they add risk
    for no measured benefit (the one subscript case observed, `$P_2O_5$`, grounds
    on word anchors anyway).

    Runs BEFORE _matches' regex, so the left-boundary and trailing-digit guards
    still apply to the result: `2±0,50` must not match `2±0,5` however it is
    wrapped.
    """
    out = _LATEX_WRAPPER.sub(r"\1", text)
    for command, char in _LATEX_UNICODE.items():
        out = out.replace(command, char)
    out = _LATEX_SPACING.sub(" ", out)
    return out.replace("$", "")


# Markdown emphasis lands INSIDE an anchor phrase and splits it. Measured
# 2026-07-28 (repeat-8): 4 of 8 quant_rose_pot_fertilizer_dose samples read
# ground=False on `saksı başına **6 gram**` while every one stated the right
# dose - the case's p was an instrument artifact, not a corpus finding. Same
# class as the LaTeX blind spot: emphasis is presentation, not a different claim.
#
# PAIRED runs only, and asterisks only. A lone '*' is multiplication here
# ('5*10 cm'), and '_' runs would eat the chunk ids that appear in retrieved
# context ('dp_19393 ve dp_21749') - the same narrowness _normalize_latex keeps.
_EMPHASIS = re.compile(r"(\*{1,3})(?=\S)(.+?)(?<=\S)\1", re.S)


def _strip_emphasis(text: str) -> str:
    """Remove markdown emphasis markers, keeping the text they wrap.

    Looped because the regex is non-greedy: `**a *b* c**` needs a second pass to
    reach the inner run. Applied to the TEXT being searched, never to the anchor.
    Runs BEFORE _matches' regex, so the left-boundary guard still applies to the
    result: `3**6 g**` collapses to `36 g` and must NOT match the anchor `6 g`.
    """
    out = text
    while True:
        stripped = _EMPHASIS.sub(r"\2", out)
        if stripped == out:
            return out
        out = stripped


def _matches(term: str, text: str) -> bool:
    """Case-insensitive anchor match with a LEFT word boundary + a right
    digit-guard, so a short/numeric answer_any/context_any anchor cannot be a
    false positive inside a larger token: '7 ay' must not fire inside '17 ay',
    '10 kg/da' not inside '110 kg/da', '2±0,5' not inside '2±0,50'.

    ASYMMETRIC on purpose. Turkish inflects by SUFFIX, so the anchors here are
    stems meant to catch surface forms - a full right boundary would break every
    one of them (the stem 'partenokarp' only ever appears as 'partenokarpi' /
    'partenokarpik', '2±0,5' as '2±0,5 derecede'). The false-positive risk is on
    the LEFT (a leading digit/letter turns the anchor into a different token) and
    in a trailing DIGIT (which extends a number), so those two are all we block;
    a trailing letter is a legitimate Turkish suffix and is left alone.

    `\\w` is Unicode-aware here (str pattern), so Turkish letters count as word
    chars on the left; re.escape keeps '/', '±', ',' literal.
    """
    pattern = r"(?<!\w)" + re.escape(term) + r"(?!\d)"
    return re.search(pattern, _normalize_latex(_strip_emphasis(text))) is not None


def _retrieval_ok(case: dict, ctx: str) -> bool:
    exp = case.get("retrieval", "any")
    nonempty = bool(ctx.strip())
    if exp == "nonempty":
        return nonempty
    if exp == "empty":
        return not nonempty
    return True


def _context_ok(case: dict, ctx: str) -> bool:
    """The retrieved context must actually be ABOUT the query's topic.

    'nonempty' only proves chunks cleared the score floor, not that they are
    relevant - the pre-cross-lingual bug looked exactly like that (full context,
    mostly unrelated chunks). Terms are listed in BOTH languages where relevant,
    so this asserts the topic was found, not the language it was found in.
    """
    terms = case.get("context_any") or []
    if not terms:
        return True
    c = ctx.lower()
    return any(_matches(t.lower(), c) for t in terms)


def _products_ok(case: dict, n_products: int) -> bool:
    exp = case.get("products", "any")
    if exp == "some":
        return n_products > 0
    if exp == "none":
        return n_products == 0
    return True


def _answer_ok(case: dict, answer: str) -> tuple[bool, bool]:
    """(grounding_ok, guardrail_ok)."""
    a = answer.lower()
    any_terms = case.get("answer_any") or []
    none_terms = case.get("answer_none") or []
    grounding = (not any_terms) or any(_matches(t.lower(), a) for t in any_terms)
    # guardrail stays PLAIN substring on purpose: a boundary here would let a
    # banned phrase hide inside a bigger token and read as "no leak". Emphasis
    # IS stripped though - that only ever catches MORE, since removing markers
    # can bring characters together but never insert them, so no leak that was
    # caught before can escape. Every answer_none term is one word, so this
    # closes only the narrow 'Con**fidor**' case; '**Confidor**' always matched.
    # _normalize_latex is deliberately NOT applied: it rewrites characters, so
    # it could in principle move text AWAY from a banned term.
    guardrail = all(t.lower() not in _strip_emphasis(a) for t in none_terms)
    return grounding, guardrail


def _select(only: str | None) -> list[dict]:
    """Pick the cases to run: everything, or one id / one category.

    A whole-set --repeat run costs N x ~20 min, so without this the sampling is
    too expensive to actually use.
    """
    if not only:
        return list(CASES)
    picked = [c for c in CASES if c["id"] == only or c["category"] == only]
    if not picked:
        cats = sorted({c["category"] for c in CASES})
        sys.exit(f"--only {only!r} matched no case. Pass a case id, or one of: "
                 f"{', '.join(cats)}")
    return picked


@contextmanager
def _corpus_ablated():
    """Force retrieve_context to "" for the whole run.

    Patches the module attribute, not a local: answer() looks the name up on
    `engine` at call time, so this covers the retrieval INSIDE answer() - which
    is the one under test. A version that only blanked run()'s own `ctx` would
    ablate nothing and quietly "prove" the corpus load-bearing.
    """
    original = engine.retrieve_context
    # Accept any signature the real retrieve_context grows (it gained a `history`
    # kwarg): the stub must swallow whatever answer() passes, or ablation crashes
    # instead of ablating.
    engine.retrieve_context = lambda *a, **kw: ""
    try:
        yield
    finally:
        engine.retrieve_context = original


def _ablation_verdict(rows: list[dict]) -> tuple[int, list[str]]:
    """(exit_code, decorative_case_ids) for a --no-context run.

    A `local` case exists to prove the corpus is load-bearing, so with an empty
    corpus it MUST lose grounding. One that still passes is asserting something
    the model knows anyway - decoration, and exactly the blind spot this flag
    exists to expose.

    Ordinary cases are ignored on purpose: they fail under ablation by
    construction (measured 2026-07-17: product-gating 31/31 -> 27/31), so letting
    them touch the exit code would make it 1 on every run and worthless.
    """
    local_rows = [r for r in rows if r.get("cat") == "local"]
    if not local_rows:
        return 1, []
    decorative = [r["id"] for r in local_rows if r.get("grounding")]
    return (1 if decorative else 0), decorative


def _classify(normal_hits: int, ablated_hits: int, repeat: int) -> str:
    """Label a corpus_fact case by how the corpus moves its grounding, over
    `repeat` samples. Flake-robust: judged by whether the corpus RELIABLY lifts
    grounding, not by unanimity - the deveci anchor grounds ~6-7/8 normally and
    must still read as corpus-carried (item 25).

    corpus-carried : grounded a majority WITH the corpus, a minority without
                     -> the corpus supplies the fact.
    model-carried  : grounded a majority even WITHOUT the corpus -> the model
                     knew it; the corpus adds nothing decisive.
    retrieval-broken: not a majority grounded even WITH the corpus.
    corpus-harmful : grounded MORE often ablated than normally -> retrieval
                     injected noise that broke an answer the model had right.

    At repeat=1 this reduces exactly to the old boolean classifier.
    """
    if ablated_hits > normal_hits:
        return "corpus-harmful"
    if 2 * normal_hits < repeat:
        return "retrieval-broken"
    if 2 * ablated_hits >= repeat:
        return "model-carried"
    return "corpus-carried"


def _faithfulness_verdict(
    cases: list[dict], live_labels: dict[str, str]
) -> tuple[int, list[str]]:
    """(exit_code, regressed_ids) for the corpus-dependence map.

    The map is DATA: model-carried cases are a legitimate finding, not a
    failure. The only regression worth failing on is a case we RECORDED as
    corpus-carried that no longer is - the corpus or retrieval stopped
    carrying a fact it used to. Cases with any other (or no) recorded
    corpus_class never touch the exit code.
    """
    regressed = [
        c["id"] for c in cases
        if c.get("corpus_class") == "corpus-carried"
        and live_labels.get(c["id"]) != "corpus-carried"
    ]
    return (1 if regressed else 0), regressed


def _no_answer_reason(text: str) -> str | None:
    """Why this text is not a real answer, or None if it is one.

    The eval scores `answer_none` (the guardrail) by checking that banned
    phrases are ABSENT. Our own fallback messages contain none, so a case the
    model never answered would score guardrail=True - a pass that asserts
    nothing. Measured live 2026-07-23: two rate-limited models returned almost
    nothing but 429 fallbacks and both read `guardrail: 54/54`.
    """
    stripped = (text or "").strip()
    if stripped.startswith(engine._LLM_UNAVAILABLE_PREFIX):
        return "unavailable"
    if stripped == engine._empty_answer_message():
        return "empty"
    return None


def run(fast: bool, repeat: int = 1, only: str | None = None,
        no_context: bool = False) -> int:
    if fast and repeat > 1:
        sys.exit("--repeat needs the chat model; it does nothing with --fast.")
    if fast and no_context:
        sys.exit("--no-context needs the chat model; --fast never calls answer().")
    cases = _select(only)
    if not fast:
        settings.request_timeout = 400.0
    suffix = f", {repeat}x each" if repeat > 1 else ""
    print(f"Running eval on {len(cases)} cases "
          f"({'FAST' if fast else 'FULL'}{suffix}) "
          f"[{_provider_stamp()}]\n")
    # Always-on: eval runs are expensive (~25 min locally, quota-capped hosted),
    # so a run must not be able to throw away its own evidence. Constructing it
    # creates no file - --fast records nothing and leaves none.
    log = AnswerLog(mode="full", provider=_provider_stamp())
    rows = []
    # The ablation must be in force around answer(), not just around run()'s own
    # retrieve_context call - blanking only the local `ctx` would ablate nothing.
    with (_corpus_ablated() if no_context else nullcontext()):
      for c in cases:
        t = time.time()
        # retrieval/context are deterministic (embedding + vector search, no
        # sampling), so they are measured once however high `repeat` is.
        ctx = engine.retrieve_context(c["query"])
        row = {"id": c["id"], "cat": c["category"]}
        # retrieval/context are emptied BY this flag; scoring them would print a
        # wall of tautological FAILs (24 of them, measured) and bury the signal.
        if not no_context:
            row["retrieval"] = _retrieval_ok(c, ctx)
            row["context"] = _context_ok(c, ctx)
        if fast:
            raw = engine.match_products(c["query"], ctx)
            row["raw_products"] = len(raw)
            row["ok"] = all(row[d] for d in ("retrieval", "context"))
        else:
            samples = []
            no_answer = None
            for i in range(repeat):
                r = engine.answer(c["query"])
                reason = _no_answer_reason(r.answer)
                if reason and no_answer is None:
                    no_answer = reason
                g, gr = _answer_ok(c, r.answer)
                p_ok = _products_ok(c, len(r.recommended_products))
                log.record(case=c, repeat_index=i, ablated=no_context,
                           result=r, grounding=g, guardrail=gr,
                           products_ok=p_ok, no_answer=reason)
                samples.append({
                    "products": p_ok,
                    "grounding": g,
                    "guardrail": gr,
                })
            if no_answer:
                # Record NO dimension keys: rate()/sample_rate() skip absent
                # keys, so this case is EXCLUDED from the scores rather than
                # counted as a vacuous pass. One bad sample voids the case - a
                # partially-answered case cannot demonstrate a guardrail.
                row["no_answer"] = no_answer
                row["ok"] = False
            else:
                for dim in ("products", "grounding", "guardrail"):
                    vals = [s[dim] for s in samples]
                    # every sample must pass: "leaks 1 time in 8" is a failure
                    row[dim] = all(vals)
                    row[dim + "_hits"] = (sum(vals), len(vals))
                dims = ["products", "grounding", "guardrail"]
                if not no_context:
                    dims += ["retrieval", "context"]
                row["ok"] = all(row[d] for d in dims)
        row["secs"] = time.time() - t
        rows.append(row)
        mark = "ERROR" if row.get("no_answer") else ("PASS" if row["ok"] else "FAIL")
        if fast:
            detail = f"rawprod={row.get('raw_products')}"
        elif row.get("no_answer"):
            detail = f"NO ANSWER ({row['no_answer']}) - not scored"
        elif repeat > 1:
            detail = " ".join(
                f"{name}={row[dim + '_hits'][0]}/{row[dim + '_hits'][1]}"
                for name, dim in (("prod", "products"), ("ground", "grounding"),
                                  ("guard", "guardrail")))
        else:
            detail = (f"prod={row['products']} ground={row['grounding']} "
                      f"guard={row['guardrail']}")
        ret_ctx = ("ret=n/a ctx=n/a " if no_context
                   else f"ret={row['retrieval']} ctx={row['context']} ")
        print(f"  [{mark}] {c['id']:<24} " + ret_ctx + detail
              + f"  ({row['secs']:.0f}s)")

    passed = sum(1 for r in rows if r["ok"])
    print(f"\n=== {passed}/{len(rows)} cases passed ===")

    errored = [r for r in rows if r.get("no_answer")]
    if errored:
        kinds: dict[str, int] = {}
        for r in errored:
            kinds[r["no_answer"]] = kinds.get(r["no_answer"], 0) + 1
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items()))
        print(f"!! {len(errored)}/{len(rows)} cases produced NO ANSWER "
              f"({breakdown}).")
        print("   They are EXCLUDED from the rates below: a case the model "
              "never answered cannot show that the guardrail held.")

    def rate(key):
        vals = [r[key] for r in rows if key in r]
        return f"{sum(vals)}/{len(vals)}" if vals else "n/a"

    def sample_rate(dim):
        """Rate over SAMPLES, not cases: 'guardrail: 23/24' reads very
        differently from 'guardrail: 30/31', and that difference is the point."""
        hits = [r[dim + "_hits"] for r in rows if dim + "_hits" in r]
        if not hits:
            return "n/a"
        return f"{sum(h for h, _ in hits)}/{sum(n for _, n in hits)}"

    print(f"  retrieval: {rate('retrieval')} | context: {rate('context')}", end="")
    if not fast:
        print(f" | product-gating: {sample_rate('products')}"
              f" | grounding: {sample_rate('grounding')}"
              f" | guardrail: {sample_rate('guardrail')}")
    else:
        print()
    if log.count:
        print(f"[answers] wrote {log.count} samples -> {log.path}")
    if no_context:
        code, decorative = _ablation_verdict(rows)
        n_local = sum(1 for r in rows if r["cat"] == "local")
        if not n_local:
            print("\n[ablation] no `local` case in this selection - "
                  "nothing was validated")
            return code
        print(f"\n[ablation] local cases that lost grounding: "
              f"{n_local - len(decorative)}/{n_local}"
              + (" - they discriminate" if not decorative else ""))
        for case_id in decorative:
            print(f"[ablation] ! {case_id} still passes grounding with an EMPTY "
                  f"corpus - it guards nothing")
        return code
    return 0 if passed == len(rows) else 1


def run_faithfulness(repeat: int = 1, only: str | None = None,
                     fast: bool = False) -> int:
    """Corpus-contribution MAP over `corpus_fact` cases only.

    For each opted-in case: run answer() normal and ablated, and classify by how
    its grounding moves (see _classify). This is a MAP, not an all-green gate -
    it does not require every case to be corpus-carried; model-carried,
    retrieval-broken, and corpus-harmful are legitimate findings, not failures.
    The only thing that fails the run is DRIFT: a case we recorded (via
    `corpus_class`) as corpus-carried that is no longer corpus-carried live -
    see _faithfulness_verdict.

    NOT a coverage meter: the score sees only cases we deliberately built to need
    the corpus, so "2/2" means "both of the two we bothered to make corpus-specific
    work", not "the corpus carries 100% of user questions". The denominator is
    small and self-selected - do not read it as corpus coverage.
    """
    if fast:
        sys.exit("--faithfulness needs the chat model; --fast never calls answer().")
    cases = [c for c in _select(only) if c.get("corpus_fact")]
    if not cases:
        print("[faithfulness] no `corpus_fact` case in this selection - "
              "nothing to measure")
        return 1
    settings.request_timeout = 400.0
    log = AnswerLog(mode="faithfulness", provider=_provider_stamp())

    def grounded_hits(case: dict, ablated: bool) -> int:
        hits = 0
        for i in range(repeat):
            result = engine.answer(case["query"])
            answer = result.answer
            reason = _no_answer_reason(answer)
            grounding, guardrail = _answer_ok(case, answer)
            # Recorded BEFORE the abort below: the sample that kills the run is
            # exactly the one someone will want to read.
            log.record(case=case, repeat_index=i, ablated=ablated,
                       result=result, grounding=grounding, guardrail=guardrail,
                       products_ok=None, no_answer=reason)
            if reason:
                # An unanswered sample reads as "ungrounded", which would
                # silently mislabel this case as model-carried or
                # retrieval-broken - worse than a wrong score, since the label
                # is recorded as a finding and quoted later. Abort the whole
                # map rather than presenting a partial one as complete.
                sys.exit(f"[faithfulness] {case['id']} produced NO ANSWER "
                          f"({reason}) - aborting rather than misclassifying "
                          f"it as ungrounded. Answers: {log.path}")
            hits += grounding
        return hits

    suffix = f", {repeat}x each" if repeat > 1 else ""
    print(f"=== faithfulness (corpus contribution), "
          f"{len(cases)} corpus_fact case(s){suffix} === [{_provider_stamp()}]\n")
    counts = {"corpus-carried": 0, "model-carried": 0,
              "retrieval-broken": 0, "corpus-harmful": 0}
    live_labels: dict[str, str] = {}
    for c in cases:
        normal_hits = grounded_hits(c, ablated=False)
        with _corpus_ablated():
            ablated_hits = grounded_hits(c, ablated=True)
        label = _classify(normal_hits, ablated_hits, repeat)
        live_labels[c["id"]] = label
        counts[label] += 1
        print(f"  {c['id']:<24} {label:<16} "
              f"normal {normal_hits}/{repeat}  ablated {ablated_hits}/{repeat}")

    total = len(cases)
    print(f"\n  corpus-carried: {counts['corpus-carried']}/{total}  |  "
          f"harmful: {counts['corpus-harmful']}  |  "
          f"retrieval-broken: {counts['retrieval-broken']}  |  "
          f"model-carried: {counts['model-carried']}")

    code, regressed = _faithfulness_verdict(cases, live_labels)
    if regressed:
        print(f"\n  [drift] corpus-carried cases that REGRESSED: "
              f"{', '.join(regressed)}")
    if log.count:
        print(f"[answers] wrote {log.count} samples -> {log.path}")
    return code


def _apply_provider_override(provider: str | None, model: str | None) -> None:
    """Repoint this eval process at a different chat backend.

    Mutates the live `settings` object and drops the cached client, so the
    override acts on the PRODUCTION path - run() still calls engine.answer().
    A measurement-only client would be a different code path from the one that
    ships, which is exactly the harness trap this project has already been
    bitten by.

    `settings` has no validate_assignment, so assigning chat_provider does NOT
    re-run the config validator; the key is therefore checked here explicitly.
    """
    if not provider and not model:
        return
    if provider:
        settings.chat_provider = provider
    if model:
        if settings.chat_provider == "openrouter":
            settings.openrouter_model = model
        else:
            settings.chat_model = model
    if settings.chat_provider == "openrouter" and not settings.openrouter_api_key.strip():
        sys.exit("--provider openrouter needs OPENROUTER_API_KEY in .env")
    if settings.chat_provider == "openrouter" and not settings.openrouter_model.strip():
        sys.exit("--provider openrouter needs OPENROUTER_MODEL in .env, or pass --model")
    engine._get_llm.cache_clear()


def _provider_stamp() -> str:
    """Provider + model, for the run header. Every recorded result must carry
    this - an unstamped number cannot be attributed to a model later."""
    return f"{settings.chat_provider}:{engine._chat_profile().model}"


def main() -> None:
    p = argparse.ArgumentParser(description="Run the RAG quality eval.")
    p.add_argument("--fast", action="store_true",
                   help="Retrieval + raw product gating only (skip chat LLM).")
    p.add_argument("--repeat", type=int, default=1, metavar="N",
                   help="Sample each case N times (full mode only). In a normal "
                        "run a case passes only if EVERY sample passes; under "
                        "--faithfulness the label is majority-based instead. "
                        "Generation is sampled, so a single run hides intermittent "
                        "failures; N>1 costs N x ~20 min.")
    p.add_argument("--only", metavar="ID|CATEGORY",
                   help="Run just one case id, or one category (nutrition, "
                        "horticulture, local, disease, chemical, offscope). Pair "
                        "with --repeat: sampling all 55 cases N times costs "
                        "N x ~20 min, one category is minutes.")
    p.add_argument("--no-context", action="store_true",
                   help="Ablation: run with an EMPTY corpus to prove the `local` "
                        "cases actually depend on retrieval. Exit 0 only if every "
                        "local case loses grounding.")
    p.add_argument("--faithfulness", action="store_true",
                   help="Corpus-dependence MAP: for each corpus_fact case, run "
                        "normal + ablated and label it (corpus-carried / "
                        "model-carried / retrieval-broken / corpus-harmful), then "
                        "print a scoreboard. Drift guard: exit 1 only if a case "
                        "recorded corpus-carried regresses; model-carried cases are "
                        "data, not failures. Pair with --repeat 4+ (labels are "
                        "majority-based, so the signal needs samples).")
    p.add_argument("--provider", choices=["local", "openrouter"],
                   help="Override the chat backend for this run. Default comes "
                        "from CHAT_PROVIDER in .env. The embedding model always "
                        "stays local.")
    p.add_argument("--model", metavar="ID",
                   help="Override the chat model id for this run. Applies to "
                        "whichever provider is active after --provider.")
    args = p.parse_args()
    _apply_provider_override(args.provider, args.model)
    if args.faithfulness:
        sys.exit(run_faithfulness(repeat=args.repeat, only=args.only,
                                  fast=args.fast))
    sys.exit(run(fast=args.fast, repeat=args.repeat, only=args.only,
                 no_context=args.no_context))


if __name__ == "__main__":
    main()
