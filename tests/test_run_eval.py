"""Harness tests for evals/run_eval.py (the LLM and store are stubbed)."""

import json

import pytest

from evals import answer_log
from evals import run_eval
from src import engine
from src.engine import ChatResult


class _R:
    """Stand-in for engine.answer()'s ChatResult."""

    def __init__(self, answer, products=()):
        self.answer = answer
        self.recommended_products = list(products)


ONE_CASE = [{
    "id": "probe", "category": "nutrition", "query": "q",
    "retrieval": "nonempty", "products": "any",
    "context_any": ["azot"],
    "answer_any": ["azot"],
}]


def _stub(monkeypatch, answers):
    """Serve `answers` one per answer() call; context is fixed and on-topic."""
    calls = {"ctx": 0, "ans": 0}

    def fake_ctx(q, k=None):
        calls["ctx"] += 1
        return "[Kaynak: x.pdf, s.1]\nazot iceren metin"

    def fake_answer(q, history=None):
        i = min(calls["ans"], len(answers) - 1)
        calls["ans"] += 1
        return _R(answers[i])

    monkeypatch.setattr(run_eval.engine, "retrieve_context", fake_ctx)
    monkeypatch.setattr(run_eval.engine, "answer", fake_answer)
    monkeypatch.setattr(run_eval, "CASES", ONE_CASE)
    return calls


def test_repeat_samples_answer_n_times_but_context_once(monkeypatch):
    """retrieval/context are deterministic - sampling them N times is waste."""
    calls = _stub(monkeypatch, ["azot verin."])

    rc = run_eval.run(fast=False, repeat=3)

    assert rc == 0
    assert calls["ans"] == 3      # the sampled dimensions
    assert calls["ctx"] == 1      # the deterministic ones


def test_repeat_fails_the_case_when_any_sample_fails(monkeypatch):
    """A guardrail that leaks 1 time in 3 is a FAILURE, not a 2/3 pass."""
    _stub(monkeypatch, ["azot verin.", "bos konu", "azot verin."])

    rc = run_eval.run(fast=False, repeat=3)

    assert rc == 1                # non-zero exit: the case failed


def test_repeat_one_is_the_default_and_calls_answer_once(monkeypatch):
    calls = _stub(monkeypatch, ["azot verin."])

    rc = run_eval.run(fast=False)

    assert rc == 0
    assert calls["ans"] == 1


def test_fast_mode_rejects_repeat(monkeypatch):
    _stub(monkeypatch, ["azot verin."])
    with pytest.raises(SystemExit):
        run_eval.run(fast=True, repeat=2)


def test_repeat_one_prints_the_original_per_case_format(monkeypatch, capsys):
    """The stated regression risk of --repeat: default output must not drift.

    At repeat=1 the per-case line must still read `prod=True ...`, NOT the
    fraction form (`prod=1/1`) that N>1 uses, and the dimension rates must read
    over cases (1/1), since one sample per case collapses to the old numbers.
    """
    _stub(monkeypatch, ["azot verin."])

    run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert "prod=True ground=True guard=True" in out
    assert "prod=1/1" not in out                 # the N>1 form must not leak in
    assert "1/1 cases passed" in out
    assert "grounding: 1/1" in out


def test_repeat_many_prints_the_fraction_format(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])

    run_eval.run(fast=False, repeat=3)
    out = capsys.readouterr().out

    assert "prod=3/3 ground=3/3 guard=3/3" in out
    assert "grounding: 3/3" in out               # rate is over SAMPLES, not cases


TWO_CATEGORIES = [
    {"id": "nut_a", "category": "nutrition", "query": "q1",
     "retrieval": "nonempty", "products": "any",
     "context_any": ["azot"], "answer_any": ["azot"]},
    {"id": "chem_a", "category": "chemical", "query": "q2",
     "retrieval": "nonempty", "products": "any",
     "context_any": ["azot"], "answer_any": ["azot"]},
]


def test_only_selects_by_category(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    rc = run_eval.run(fast=False, only="chemical")
    out = capsys.readouterr().out

    assert rc == 0
    assert "chem_a" in out
    assert "nut_a" not in out
    assert "1/1 cases passed" in out


def test_only_selects_by_case_id(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    run_eval.run(fast=False, only="nut_a")
    out = capsys.readouterr().out

    assert "nut_a" in out
    assert "chem_a" not in out


def test_only_that_matches_nothing_is_an_error(monkeypatch):
    """A silent '0/0 cases passed' would be a green that means nothing."""
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    with pytest.raises(SystemExit):
        run_eval.run(fast=False, only="typo")


def test_only_defaults_to_every_case(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert "2/2 cases passed" in out


def test_ablation_verdict_all_local_cases_lost_grounding():
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "local_b", "cat": "local", "grounding": False}]
    assert run_eval._ablation_verdict(rows) == (0, [])


def test_ablation_verdict_flags_a_local_case_that_survives_ablation():
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "local_b", "cat": "local", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (1, ["local_b"])


def test_ablation_verdict_ignores_non_local_cases():
    """Ordinary cases fail under ablation by construction - if they moved the
    exit code it would be 1 on every run and mean nothing."""
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "tomato_nutrition", "cat": "nutrition", "grounding": True},
            {"id": "compost", "cat": "nutrition", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (0, [])


def test_ablation_verdict_with_no_local_case_fails_rather_than_passing_vacuously():
    """'0 of 0 discriminate' must not read as success - same shape as the
    all([]) bug this project already shipped once."""
    rows = [{"id": "compost", "cat": "nutrition", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (1, [])


def test_corpus_ablated_empties_the_path_answer_uses(monkeypatch):
    from src import engine
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "REAL")
    assert engine.retrieve_context("x") == "REAL"
    with run_eval._corpus_ablated():
        assert engine.retrieve_context("x") == ""
    assert engine.retrieve_context("x") == "REAL"


def test_corpus_ablated_accepts_the_call_answer_actually_makes():
    """answer() calls retrieve_context(message, history=...). The ablation stub
    must accept that exact call, or --faithfulness / --no-context crash with a
    TypeError instead of ablating. The test above only called it positionally, so
    when retrieve_context grew a `history` kwarg the drift slipped through and the
    ablation path was silently broken. This exercises the real call shape."""
    with run_eval._corpus_ablated():
        assert engine.retrieve_context(
            "x", history=[{"role": "user", "content": "q"}]) == ""
        assert engine.retrieve_context("x", k=4, history=None) == ""


LOCAL_CASE = [{
    "id": "local_probe", "category": "local", "query": "q",
    "retrieval": "nonempty", "products": "none",
    "context_any": ["deveci"],
    "answer_any": ["2±0,5"],
}]


def test_no_context_reports_retrieval_and_context_as_n_a(monkeypatch, capsys):
    """The flag EMPTIES those two dimensions, so scoring them would print a wall
    of tautological FAILs and bury the ablation's actual signal."""
    _stub(monkeypatch, ["genel bir cevap"])
    monkeypatch.setattr(run_eval, "CASES", LOCAL_CASE)

    run_eval.run(fast=False, no_context=True)
    out = capsys.readouterr().out

    assert "ret=n/a ctx=n/a" in out
    assert "ret=False" not in out
    assert "retrieval: n/a" in out


def test_no_context_rejects_fast(monkeypatch):
    """--fast never calls answer(), so there is nothing to ablate."""
    _stub(monkeypatch, ["azot verin."])
    with pytest.raises(SystemExit):
        run_eval.run(fast=True, no_context=True)


def test_classify_corpus_carried():
    # green normally, red ablated -> the corpus supplies the fact
    assert run_eval._classify(1, 0, 1) == "corpus-carried"
    # flaky-but-carried: a normal majority with the corpus, none without
    assert run_eval._classify(6, 0, 8) == "corpus-carried"


def test_classify_model_carried():
    # green both ways -> the model knew it; corpus adds nothing detectable
    assert run_eval._classify(1, 1, 1) == "model-carried"
    assert run_eval._classify(8, 8, 8) == "model-carried"


def test_classify_retrieval_broken():
    # red both ways -> cannot answer even WITH the corpus
    assert run_eval._classify(0, 0, 1) == "retrieval-broken"
    # not a majority grounded even with the corpus -> a real collapse, not flake
    assert run_eval._classify(3, 0, 8) == "retrieval-broken"


def test_classify_corpus_harmful():
    # grounded MORE often ablated than normally -> the corpus broke a right answer
    assert run_eval._classify(0, 1, 1) == "corpus-harmful"
    assert run_eval._classify(2, 5, 8) == "corpus-harmful"


def _optin_case(answer_any, corpus_class="corpus-carried"):
    return {"id": "probe", "category": "local", "corpus_fact": True,
            "corpus_class": corpus_class,
            "query": "q", "answer_any": answer_any}


def test_verdict_recorded_carried_still_carried_passes():
    cases = [{"id": "a", "corpus_class": "corpus-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"a": "corpus-carried"}) == (0, [])


def test_verdict_recorded_carried_regressed_fails_and_names_it():
    cases = [{"id": "a", "corpus_class": "corpus-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"a": "model-carried"}) == (1, ["a"])


def test_verdict_recorded_carried_now_retrieval_broken_fails():
    cases = [{"id": "a", "corpus_class": "corpus-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"a": "retrieval-broken"}) == (1, ["a"])


def test_verdict_model_carried_case_never_gates():
    cases = [{"id": "b", "corpus_class": "model-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"b": "retrieval-broken"}) == (0, [])


def test_verdict_missing_class_never_gates():
    cases = [{"id": "c"}]
    assert run_eval._faithfulness_verdict(cases, {"c": "corpus-harmful"}) == (0, [])


def test_verdict_mixed_reports_only_the_regressed():
    cases = [{"id": "a", "corpus_class": "corpus-carried"},
             {"id": "b", "corpus_class": "model-carried"}]
    assert run_eval._faithfulness_verdict(
        cases, {"a": "model-carried", "b": "model-carried"}) == (1, ["a"])


def test_faithfulness_recorded_carried_still_carried_exits_0(monkeypatch):
    monkeypatch.setattr(run_eval, "_select",
                        lambda only: [_optin_case(["2±0,5"], "corpus-carried")])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)  # respects _corpus_ablated
        return ChatResult("depo 2±0,5 derece" if ctx else "genel tavsiye", [])
    monkeypatch.setattr(engine, "answer", fake)
    assert run_eval.run_faithfulness() == 0


def test_faithfulness_recorded_carried_regressed_to_model_exits_1(monkeypatch):
    monkeypatch.setattr(run_eval, "_select",
                        lambda only: [_optin_case(["2±0,5"], "corpus-carried")])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    # states the fact regardless of context -> now model-carried = REGRESSION
    monkeypatch.setattr(engine, "answer",
                        lambda msg, history=None: ChatResult("hep 2±0,5 der", []))
    assert run_eval.run_faithfulness() == 1


def test_faithfulness_recorded_model_carried_never_gates(monkeypatch):
    # a case we recorded as model-carried is DATA - it must not fail the run
    monkeypatch.setattr(run_eval, "_select",
                        lambda only: [_optin_case(["2±0,5"], "model-carried")])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    monkeypatch.setattr(engine, "answer",
                        lambda msg, history=None: ChatResult("hep 2±0,5 der", []))
    assert run_eval.run_faithfulness() == 0


def test_faithfulness_no_optin_case_exits_1(monkeypatch):
    plain = {"id": "z", "category": "nutrition", "query": "q", "answer_any": ["x"]}
    monkeypatch.setattr(run_eval, "_select", lambda only: [plain])
    assert run_eval.run_faithfulness() == 1


def test_faithfulness_fast_exits(monkeypatch):
    with pytest.raises(SystemExit):
        run_eval.run_faithfulness(fast=True)


def test_faithfulness_flaky_normal_majority_stays_corpus_carried(monkeypatch):
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    calls = {"n": 0}

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)
        calls["n"] += 1
        if not ctx:
            return ChatResult("genel", [])            # ablated: always red
        text = "genel" if calls["n"] == 1 else "2±0,5 var"  # 1 of 4 normal red
        return ChatResult(text, [])
    monkeypatch.setattr(engine, "answer", fake)

    # repeat=4: normal 3/4 green (a majority), ablated 0/4 -> corpus-carried,
    # NOT a regression - one flaky red must not drop the anchor.
    assert run_eval.run_faithfulness(repeat=4) == 0


def test_matches_rejects_numeric_left_superset():
    """The recurring false positive: a short numeric anchor inside a bigger
    number. '7 ay' must not fire inside '17 ay'."""
    assert run_eval._matches("7 ay", "bitki 17 ay sonra") is False


def test_matches_accepts_the_bare_numeric_anchor():
    assert run_eval._matches("7 ay", "bitki 7 ay sonra") is True


def test_matches_preserves_turkish_suffix_on_the_right():
    """Turkish inflects by SUFFIX, so anchors are stems - a right word boundary
    would break every stem in the set. '7 ay' still matches '7 aydir', and the
    stem 'partenokarp' still matches its only real surface forms."""
    assert run_eval._matches("7 ay", "bitki 7 aydir bekler") is True
    assert run_eval._matches("partenokarp", "meyve partenokarpik olusur") is True
    assert run_eval._matches("partenokarp", "partenokarpi gorulur") is True


def test_matches_rejects_letter_left_superset():
    """'smb' buried inside a larger token (preceded by a letter) is not a hit."""
    assert run_eval._matches("smb", "kelime asmbol icinde") is False
    assert run_eval._matches("smb", "smb uygulamasi") is True


def test_matches_rejects_trailing_digit_superset():
    """A digit glued to the right turns the anchor into a different number:
    '2±0,5' must not fire inside '2±0,50'."""
    assert run_eval._matches("2±0,5", "depo 2±0,50 derece") is False
    assert run_eval._matches("2±0,5", "depo 2±0,5 derece") is True


def test_matches_handles_slash_anchor_boundaries():
    """Entries with '/' like '10 kg/da' must survive escaping and still get the
    left boundary: '110 kg/da' is not '10 kg/da'."""
    assert run_eval._matches("10 kg/da", "gubre 110 kg/da verildi") is False
    assert run_eval._matches("10 kg/da", "gubre 10 kg/da verildi") is True


def test_matches_treats_turkish_letters_as_word_chars_on_the_left():
    """A Unicode-aware boundary: a Turkish letter glued to the left blocks the
    match (so the anchor is a real token), while a suffix on the right does not."""
    assert run_eval._matches("azot", "kazot") is False
    assert run_eval._matches("azot", "azotlu toprak") is True


def test_matches_sees_through_latex_notation():
    """The model sometimes states a value in LaTeX. Measured live 2026-07-28:
    local_deveci_pear read ground=False on a full run while its answer said
    `$2\\pm0,5^\\circ\\text{C}$` - the right value the matcher could not see. That
    is an instrument defect, the same class as a dead anchor: it reads as a
    finding about the corpus rather than as a blind spot in the harness."""
    latex = "depolarda $2\\pm0,5^\\circ\\text{C}$ sicaklikta saklanir"
    assert run_eval._matches("2±0,5", latex) is True


def test_latex_normalisation_preserves_the_trailing_digit_guard():
    """The property most at risk from a careless 'just strip symbols' fix:
    normalisation runs BEFORE the existing regex, so '2±0,50' must still not
    match '2±0,5' even when it arrives wrapped in LaTeX."""
    assert run_eval._matches("2±0,5", "depo $2\\pm0,50^\\circ$ derece") is False
    assert run_eval._matches("2±0,5", "depo 2±0,50 derece") is False


def test_latex_normalisation_unwraps_text_and_mathrm():
    assert run_eval._matches("5 C", "sicaklik $5\\,\\text{C}$ olmali") is True
    assert run_eval._matches("5 C", "sicaklik $5\\,\\mathrm{C}$ olmali") is True


def test_latex_normalisation_leaves_plain_text_alone():
    """Ordinary answers must score exactly as before - the whole panel depends
    on it."""
    assert run_eval._matches("azot", "azotlu toprak") is True
    assert run_eval._matches("azot", "kazot") is False
    assert run_eval._matches("7 ay", "bitki 17 ay sonra") is False
    assert run_eval._matches("10 kg/da", "gubre 10 kg/da verildi") is True


def test_matches_sees_through_markdown_emphasis():
    """Measured live 2026-07-28 (repeat-8 on quant_rose_pot_fertilizer_dose):
    4 of 8 samples read ground=False while every one of them stated the right
    dose - the model had bolded the number, splitting the anchor phrase:
    `saksi basina **6 gram**`. Same class as the LaTeX blind spot; emphasis is
    presentation markup, not a different claim."""
    bold = "arastirmalar saksi basina **6 gram** gubre onermektedir"
    assert run_eval._matches("saksi basina 6 g", bold) is True


def test_markdown_normalisation_handles_every_emphasis_run_length():
    for marker in ("*", "**", "***"):
        text = f"saksi basina {marker}6 gram{marker} gubre"
        assert run_eval._matches("saksi basina 6 g", text) is True


def test_markdown_normalisation_preserves_the_left_boundary_guard():
    """The property most at risk: stripping markers must not GLUE tokens into a
    spurious anchor. '3**6 g**' collapses to '36 g', which must still not match
    the anchor '6 g'."""
    assert run_eval._matches("6 g", "doz 3**6 g** olarak") is False


def test_markdown_normalisation_preserves_the_trailing_digit_guard():
    assert run_eval._matches("2±0,5", "depo **2±0,50** derece") is False


def test_markdown_normalisation_leaves_underscores_alone():
    """Deliberately narrow, following the LaTeX normaliser's precedent: only
    asterisk emphasis was measured, and '_' runs would corrupt the chunk ids
    that appear in retrieved context ('dp_19393 ve dp_21749')."""
    ids = "kaynak dp_19393 ve dp_21749 karsilastirildi"
    assert run_eval._matches("dp_19393", ids) is True
    assert run_eval._matches("dp_21749", ids) is True


def test_markdown_normalisation_ignores_an_unpaired_asterisk():
    """Rules out the cheap 'delete every asterisk' fix. A lone '*' is a
    MULTIPLICATION sign in this domain (plant spacing, '5*10 cm'), and deleting
    it would mangle '5*10 cm' into '510 cm' - silently losing a '10 cm' anchor
    that matches today. Only a PAIRED emphasis run is markup."""
    assert run_eval._matches("10 cm", "fideler 5*10 cm aralikla dikildi") is True


def test_markdown_normalisation_leaves_plain_text_alone():
    """Ordinary answers must score exactly as before - the whole panel depends
    on it. A bare list bullet is not an emphasis run."""
    assert run_eval._matches("10 kg/da", "* gubre 10 kg/da verildi") is True
    assert run_eval._matches("azot", "azotlu toprak") is True
    assert run_eval._matches("azot", "kazot") is False
    assert run_eval._matches("7 ay", "bitki 17 ay sonra") is False


def test_answer_any_uses_boundary_matching():
    case = {"answer_any": ["7 ay"]}
    assert run_eval._answer_ok(case, "bitki 17 ay boyunca")[0] is False
    assert run_eval._answer_ok(case, "bitki 7 ay boyunca")[0] is True


def test_context_any_uses_boundary_matching():
    case = {"context_any": ["7 ay"]}
    assert run_eval._context_ok(case, "sure 17 ay olarak") is False
    assert run_eval._context_ok(case, "sure 7 ay olarak") is True


def test_answer_none_stays_plain_substring():
    """The guardrail (answer_none) is OUT of scope: it must keep plain-substring
    matching, or a boundary would let '17 gun' hide a banned '7 gun' leak."""
    case = {"answer_none": ["7 gun"]}
    # plain substring still finds the banned phrase inside a bigger token
    assert run_eval._answer_ok(case, "17 gun beklemeyin")[1] is False


def test_faithfulness_normal_minority_green_is_a_regression(monkeypatch):
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    calls = {"n": 0}

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)
        calls["n"] += 1
        if not ctx:
            return ChatResult("genel", [])            # ablated: always red
        text = "2±0,5 var" if calls["n"] == 1 else "genel"  # only 1 of 4 normal green
        return ChatResult(text, [])
    monkeypatch.setattr(engine, "answer", fake)

    # repeat=4: normal 1/4 green (a minority) -> retrieval-broken -> a recorded
    # corpus-carried case that collapsed -> drift, exit 1.
    assert run_eval.run_faithfulness(repeat=4) == 1


def test_provider_override_repoints_settings_and_clears_the_client_cache(monkeypatch):
    """The override must act on the PRODUCTION path: same settings object that
    answer() reads, and the cached client dropped so the next call rebuilds it
    against the new endpoint."""
    from evals import run_eval
    from src import engine
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "openrouter_model", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    engine._get_llm.cache_clear()
    engine._get_llm()                                    # populate the cache
    assert engine._get_llm.cache_info().currsize == 1

    run_eval._apply_provider_override("openrouter", "vendor/model-x")

    assert settings.chat_provider == "openrouter"
    assert settings.openrouter_model == "vendor/model-x"
    assert engine._get_llm.cache_info().currsize == 0

    engine._get_llm.cache_clear()        # never leak a test-configured client


def test_model_override_alone_targets_the_active_provider(monkeypatch):
    from evals import run_eval
    from src import engine
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "chat_model", "old-local-model")

    run_eval._apply_provider_override(None, "new-local-model")

    assert settings.chat_model == "new-local-model"
    engine._get_llm.cache_clear()


def test_openrouter_override_without_a_key_exits(monkeypatch):
    """settings has no validate_assignment, so mutating chat_provider does NOT
    re-run the model validator. Without this check the run would start and fail
    with 401s partway through a paid measurement."""
    import pytest
    from evals import run_eval
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "openrouter_model", "")

    with pytest.raises(SystemExit):
        run_eval._apply_provider_override("openrouter", "vendor/model-x")


def test_openrouter_override_without_a_model_exits(monkeypatch):
    """Same trap as the missing-key case, but for OPENROUTER_MODEL: a `local`
    .env with a key but no model set, run with --provider openrouter and no
    --model, must fail loudly instead of stamping `[openrouter:]` and sending
    every request with an empty model id (measured: a 400 per case)."""
    import pytest
    from evals import run_eval
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "")

    with pytest.raises(SystemExit):
        run_eval._apply_provider_override("openrouter", None)


def test_no_override_leaves_settings_untouched(monkeypatch):
    from evals import run_eval
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "chat_model", "unchanged-model")

    run_eval._apply_provider_override(None, None)

    assert settings.chat_provider == "local"
    assert settings.chat_model == "unchanged-model"


def test_no_answer_reason_recognises_both_fallbacks():
    assert run_eval._no_answer_reason(
        engine._llm_unavailable_message(RuntimeError("boom"))) == "unavailable"
    assert run_eval._no_answer_reason(engine._empty_answer_message()) == "empty"
    assert run_eval._no_answer_reason("Azot eksikligi olabilir.") is None


def test_an_unanswered_case_is_an_error_not_a_silent_guardrail_pass(
        monkeypatch, capsys):
    """The vacuity trap this guard exists for: an outage fallback contains no
    banned phrase, so answer_none passes and the run reports a clean guardrail
    for a model that never spoke. Measured live 2026-07-23 - two models rate
    limited to near-silence both read guardrail 54/54."""
    _stub(monkeypatch, [engine._llm_unavailable_message(RuntimeError("429"))])

    rc = run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert "[ERROR]" in out              # not PASS, not FAIL
    assert "NO ANSWER" in out            # called out in the summary
    assert "guardrail: n/a" in out       # excluded, NOT counted as a pass
    assert rc != 0                       # a run with errors is not a valid run


def test_a_real_answer_is_still_scored_normally(monkeypatch, capsys):
    """The guard must not swallow ordinary runs."""
    _stub(monkeypatch, ["azot verin."])

    rc = run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert "[ERROR]" not in out
    assert "NO ANSWER" not in out
    assert rc == 0


def test_faithfulness_aborts_rather_than_misclassify_an_unanswered_case(monkeypatch):
    """An outage fallback reads as "ungrounded", which would silently mislabel
    the case as model-carried or retrieval-broken and get recorded as a
    finding. This must abort the whole run, not skip the case."""
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    monkeypatch.setattr(
        engine, "answer",
        lambda msg, history=None: ChatResult(
            engine._llm_unavailable_message(RuntimeError("429")), []))

    with pytest.raises(SystemExit):
        run_eval.run_faithfulness()


def test_run_records_every_sample_with_its_answer_text(monkeypatch, tmp_path):
    """The point of the log: the generated text survives the run."""
    _stub(monkeypatch, ["azot verin."])
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)

    run_eval.run(fast=False, repeat=2)

    files = list(runs.glob("*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(line) for line
            in files[0].read_text(encoding="utf-8").strip().splitlines()]
    assert [r["answer"] for r in rows] == ["azot verin.", "azot verin."]
    assert [r["repeat_index"] for r in rows] == [0, 1]
    assert rows[0]["case_id"] == "probe"
    assert rows[0]["mode"] == "full"
    assert rows[0]["ablated"] is False


def test_a_broken_answer_log_does_not_change_the_run(monkeypatch, tmp_path, capsys):
    """Binding constraint: the log is a pure side effect. With writing forced to
    fail, the run still completes and its verdicts are unchanged."""
    _stub(monkeypatch, ["azot verin."])
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(answer_log, "RUNS_DIR", blocker / "runs")

    rc = run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert rc == 0
    assert "prod=True ground=True guard=True" in out
    assert "1/1 cases passed" in out
    assert "grounding: 1/1" in out
    assert "[answers] WARNING" in out


def test_fast_mode_writes_no_answer_log(monkeypatch, tmp_path):
    """--fast never calls answer(), so there is nothing to log."""
    _stub(monkeypatch, ["azot verin."])
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)

    run_eval.run(fast=True)

    assert not runs.exists()


def test_faithfulness_logs_normal_and_ablated_samples(monkeypatch, tmp_path):
    """Normal and ablated samples land in one file so they can be compared
    directly - that comparison IS the diagnosis this log exists for."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)      # respects _corpus_ablated
        return ChatResult("depo 2±0,5 derece" if ctx else "genel tavsiye", [])
    monkeypatch.setattr(engine, "answer", fake)

    run_eval.run_faithfulness()

    rows = [json.loads(line) for line
            in list(runs.glob("*.jsonl"))[0]
            .read_text(encoding="utf-8").strip().splitlines()]
    assert [r["ablated"] for r in rows] == [False, True]
    assert rows[0]["answer"] == "depo 2±0,5 derece"
    assert rows[1]["answer"] == "genel tavsiye"
    assert rows[0]["mode"] == "faithfulness"
    assert rows[0]["products_ok"] is None       # faithfulness does not gate products


def test_faithfulness_logs_the_sample_it_aborts_on(monkeypatch, tmp_path):
    """The abort path is exactly when the evidence is wanted, so the unanswered
    sample must reach disk BEFORE sys.exit()."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    monkeypatch.setattr(
        engine, "answer",
        lambda msg, history=None: ChatResult(
            engine._llm_unavailable_message(RuntimeError("429")), []))

    with pytest.raises(SystemExit):
        run_eval.run_faithfulness()

    rows = [json.loads(line) for line
            in list(runs.glob("*.jsonl"))[0]
            .read_text(encoding="utf-8").strip().splitlines()]
    assert len(rows) == 1
    assert rows[0]["no_answer"] == "unavailable"
