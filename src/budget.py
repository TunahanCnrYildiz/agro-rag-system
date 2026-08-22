"""Budget inputs, arithmetic, and the framing that keeps a figure an estimate.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from values the user typed
into a form. The route does not call the LLM at all.

NOTHING IS READ OUT OF THE QUESTION. The previous attempt inferred which number
in a sentence belonged to which slot; its review found five wrong money figures.
That inference is gone: values arrive from labelled fields.

THE UNIT IS A SELECTION, NOT AN INFERENCE. A form alone does not fix this. A
farmer who harvested 2 tons from 5 donum holds "2 ton" in mind, not "400 kg/da",
and would type 2000 into a per-dekar field - five times too high, and silent.
So the form asks for the TOTAL harvest with a kg/ton selector and derives the
per-dekar figure itself. Area and price get the same treatment.

This module imports nothing from src/engine.py: with no text parsing there is
nothing to normalise, so it is values in, text out.
"""
from __future__ import annotations

import re

# A complete Turkish number token, with BOTH boundaries anchored. The pattern is
# inherited from the reviewed extraction module: it refuses "1.5" and "1.2.3"
# outright rather than re-parsing them from the middle, which is how a scanning
# regex turns "250.000" into "000".
_NUM_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)$")


def parse_tr_number(text: str) -> float | None:
    """Read one FIELD's contents. Never a sentence - that is the point."""
    token = (text or "").strip()
    if not _NUM_RE.match(token):
        return None
    return float(token.replace(".", "").replace(",", "."))


def format_tr(value: float, decimals: int) -> str:
    """Turkish number formatting: thousands dot, decimal comma.

    Written out rather than delegated to a locale library, which needs the
    locale to be installed on the host and fails differently per platform.
    """
    rounded = round(value, decimals)
    # Derive sign from rounded value, not raw value: values that round to
    # zero display as "0" not "-0", since -0.0 < 0 is False in Python
    sign = "-" if rounded < 0 else ""
    rounded = abs(rounded)
    whole = int(rounded)
    groups = f"{whole:,}".replace(",", ".")
    if decimals <= 0:
        return f"{sign}{groups}"
    frac = round((rounded - whole) * (10 ** decimals))
    return f"{sign}{groups},{frac:0{decimals}d}"


from dataclasses import dataclass


@dataclass(frozen=True)
class UnitOption:
    id: str
    label: str
    factor: float          # multiply by this to reach the canonical unit
    # A per-area unit needs the area before it means anything. Kept a property
    # of the UNIT rather than a second field, so the conversion stays one line
    # and a new per-area unit needs no new branch.
    per_area: bool = False


@dataclass(frozen=True)
class FieldSpec:
    id: str
    label: str
    required: bool
    min_value: float
    min_exclusive: bool
    units: tuple[UnitOption, ...]


# The single source of truth. The form the client draws and the validation the
# server runs are both derived from this tuple; deriving them separately is how
# a client stops marking a field required while the server keeps rejecting it.
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("area", "Alan", True, 0.0, True,
              (UnitOption("donum", "dönüm", 1.0),
               UnitOption("hektar", "hektar", 10.0))),
    # "Toplam" would be wrong under kg/dekar, so the label is neutral across all
    # three units. The per-dekar unit exists because TUIK publishes yields that
    # way and P2b prefills them; a farmer stating their own harvest still picks
    # kg or ton and states a total, exactly as in P1.
    FieldSpec("yield_total", "Ürün miktarı", True, 0.0, False,
              (UnitOption("kg", "kg", 1.0),
               UnitOption("ton", "ton", 1000.0),
               UnitOption("kg_da", "kg/dekar", 1.0, per_area=True))),
    FieldSpec("price", "Fiyat", True, 0.0, False,
              (UnitOption("tl_kg", "TL/kg", 1.0),
               UnitOption("tl_ton", "TL/ton", 0.001))),
    # Cost has no second plausible unit, so it carries one option rather than a
    # selector. Optional: without it we compute no margin figure, though the
    # answer still invites the user to supply one.
    FieldSpec("cost", "Masraf", False, 0.0, False,
              (UnitOption("tl", "TL", 1.0),)),
)

_FIELDS_BY_ID = {f.id: f for f in FIELDS}


@dataclass(frozen=True)
class Value:
    amount: float
    source: str            # "user" | "norm" | "empty"
    # Where the norm came from, for the framing sentence. Only ever set on a
    # value the server itself confirmed against its own lookup.
    note: str | None = None


@dataclass(frozen=True)
class BudgetInputs:
    """Canonical units throughout: dekar, kg, TL/kg, TL."""
    area_da: Value
    yield_kg: Value
    price_tl_kg: Value
    cost_tl: Value | None
    # Which crop the farmer picked - an explicit client selection, never
    # inferred. It is not part of FIELDS: form_spec() emits it as a bare id
    # (the top-level "crop" key, and each row's own "id" under "crops"), the
    # client echoes it back in the payload, and _verify() keys on it to find
    # the one CropNorm row a "norm" claim could possibly be confirmed against.
    # Being client-supplied, it is untrusted exactly like every other field
    # here: _verify() looks it up in the table rather than believing it, so an
    # unknown or mismatched id simply means no row is found and every "norm"
    # claim on that submission downgrades to "user". render() prints the
    # matching row's label (crop_label) when one was found, and this raw id
    # otherwise.
    crop: str | None = None
    # The crop's display label ("Fındık"), from the CropNorm row _verify already
    # looked up. None when no table resolved the crop - render() then falls
    # back to the raw id rather than printing nothing.
    crop_label: str | None = None


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str


def _coerce(value: object) -> float | None:
    """Accept a JSON number as readily as the string a text input produces.

    bool is checked first because it is a subclass of int in Python: without
    the guard, True would silently become 1 dekar.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return parse_tr_number(value)
    return None


def _read(spec: FieldSpec, raw: dict, area_da: float | None
          ) -> tuple[Value | None, FieldError | None]:
    entry = raw.get(spec.id)
    if not isinstance(entry, dict) or entry.get("value") in (None, ""):
        if spec.required:
            return None, FieldError(spec.id, f"{spec.label} alanını doldurun.")
        return None, None

    amount = _coerce(entry.get("value"))
    if amount is None:
        return None, FieldError(
            spec.id, f"{spec.label} bir sayı olmalı. Ondalık için virgül kullanın.")

    unit = next((u for u in spec.units if u.id == entry.get("unit")), None)
    if unit is None:
        return None, FieldError(spec.id, f"{spec.label} için birimi seçin.")

    if spec.min_exclusive and amount <= spec.min_value:
        return None, FieldError(
            spec.id, f"{spec.label} sıfırdan büyük olmalı.")
    if not spec.min_exclusive and amount < spec.min_value:
        return None, FieldError(spec.id, f"{spec.label} negatif olamaz.")

    if unit.per_area:
        if area_da is None:
            # Refused, never multiplied by a guessed area and never zeroed.
            return None, FieldError(
                spec.id,
                f"{spec.label} için dekar başına değer girdiniz; "
                f"önce alanı doldurun.")
        amount = amount * area_da

    claimed = "norm" if entry.get("source") == "norm" else "user"
    return Value(amount * unit.factor, claimed), None


# Which submitted field each norm measure prefills, and how that cell is built.
_VERIFIED = (("yield_total", "yield_kg_da", "yield", None),
             ("price", "price_tl_kg", "price", 2))


def _verify(values: dict, raw: dict, crop: str | None, table) -> tuple[dict, object | None]:
    """Confirm or downgrade every "this came from a norm" claim.

    A field claiming a norm whose submitted text does not match what we served
    is the user's own figure wearing TUIK's name, and the framing would then
    attribute a farmer's number to a statistical agency. Comparison is on the
    served TEXT and unit rather than the parsed floats: it answers exactly the
    question being asked - is this the figure we sent? - and has no rounding
    tolerance to get wrong.

    "user" is never second-guessed in the other direction. A value the user
    typed is theirs even when it happens to equal the norm.

    Returns the matched CropNorm row (or None) alongside the values, so
    validate() can take the crop's display label from it without a second
    lookup.
    """
    row = None
    if crop is not None:
        row = next((r for r in (table or ()) if r.crop == crop), None)

    for field_id, measure, unit_key, decimals in _VERIFIED:
        value = values.get(field_id)
        if value is None or value.source != "norm":
            continue
        cell = (None if row is None
                else _norm_cell(getattr(row, measure), *_NORM_UNITS[unit_key], decimals,
                                 show_range=unit_key == "yield"))
        entry = raw.get(field_id) or {}
        if (cell is not None
                and entry.get("value") == cell["value"]
                and entry.get("unit") == cell["unit"]):
            values[field_id] = Value(value.amount, "norm", cell["note"])
        else:
            values[field_id] = Value(value.amount, "user")
    return values, row


def validate(raw: dict, table=None) -> tuple[BudgetInputs | None, list[FieldError]]:
    """Read every field, collect every error. Never raises.

    Reports ALL errors rather than the first, so a user fixing a form is not
    walked through them one round trip at a time.
    """
    raw = raw if isinstance(raw, dict) else {}
    values: dict[str, Value | None] = {}
    errors: list[FieldError] = []

    # The area is read before everything else because a per-area unit cannot be
    # converted without it. Reading it out of FIELDS order rather than relying
    # on the tuple happening to list it first: that order is a layout decision,
    # not a contract, and a reorder would silently break every per-area field.
    area_spec = _FIELDS_BY_ID["area"]
    area_value, area_error = _read(area_spec, raw, None)
    values[area_spec.id] = area_value
    if area_error is not None:
        errors.append(area_error)
    area_da = area_value.amount if area_value is not None else None

    for spec in FIELDS:
        if spec.id == area_spec.id:
            continue
        value, error = _read(spec, raw, area_da)
        values[spec.id] = value
        if error is not None:
            errors.append(error)

    if errors:
        return None, errors

    crop = raw.get("crop")
    crop = crop if isinstance(crop, str) and crop.strip() else None
    values, row = _verify(values, raw, crop, table)

    return BudgetInputs(
        area_da=values["area"],
        yield_kg=values["yield_total"],
        price_tl_kg=values["price"],
        cost_tl=values["cost"],
        crop=crop,
        crop_label=row.label if row is not None else None,
    ), []


# The unit each measure is published in, and how it is written when it appears
# inside a sentence rather than on a chip.
_NORM_UNITS = {"yield": ("kg_da", "kg/da"), "price": ("tl_kg", "TL/kg")}


def _norm_cell(norm, unit_id: str, unit_text: str, decimals: int | None,
               show_range: bool) -> dict | None:
    """One prefillable figure, finished for display.

    Everything the card shows for this figure is written HERE: the value in
    Turkish notation, the unit to select alongside it, where it came from, and
    (when `show_range`) the range of the years before it. The client renders
    strings and formats nothing - a second Turkish number formatter over there
    is a second place for a decimal comma to go wrong.

    `show_range` is False for price. Measured on the shipped data: the price
    prefill sits ABOVE its own five-year range for 95 of 103 Manisa price
    cells and 45 of 48 in Ordu - that is lira inflation, not an anomaly, so
    showing the range there would read as a false outlier warning on almost
    every ordinary crop. Yield keeps its range: a stale yield is a physical
    quantity that does not inflate, and that is where an outlier is real.
    """
    if norm is None:
        return None
    value = (_format_qty(norm.amount) if decimals is None
             else format_tr(norm.amount, decimals))
    recent = None
    if show_range and norm.recent_min is not None and norm.recent_max is not None:
        recent = (f"önceki 5 yıl: {_format_qty(norm.recent_min)}–"
                  f"{_format_qty(norm.recent_max)} {unit_text}")
    return {
        "value": value,
        # The unit travels WITH the value. Dropping 28,4 into a field still
        # reading "kg" would claim a whole orchard yielded 28 kilos.
        "unit": unit_id,
        "note": f"TÜİK {norm.year}, {norm.region}",
        "recent": recent,
    }


def _crop_rows(table, latest_year: int | None) -> list[dict]:
    """Every crop's figures, for a card that picks one of them client-side.

    A price cell is built ONLY when its year equals `latest_year`. Measured on
    Ordu: 61 crops carry a price, but only 25 are from the latest year and 29
    are older than 2023 - `Arpa (Diğer)` prefills 1,10 TL/kg from 2018, nine
    times too low. Lira is nominal, so a stale price is not a meaningful
    physical quantity the way a stale yield still is, and it silently
    inflates the revenue this form computes. `latest_year=None` (the cutoff is
    unknown) serves no price cell at all - absence, never a guess. Yield is
    untouched: it keeps prefilling from whatever year it last has a value.
    """
    rows = []
    for row in table:
        price = row.price_tl_kg
        if price is not None and (latest_year is None or price.year != latest_year):
            price = None
        rows.append({
            "id": row.crop,
            "label": row.label,
            "yield": _norm_cell(row.yield_kg_da, *_NORM_UNITS["yield"], None,
                                 show_range=True),
            "price": _norm_cell(price, *_NORM_UNITS["price"], 2, show_range=False),
        })
    return rows


def _echo(spec: FieldSpec, submitted: dict | None) -> dict:
    """What the user typed, given back verbatim, and the raw claim about
    where it came from.

    Verbatim matters for `value`: this is the value the error message is
    ABOUT, so reformatting it would show the user something other than what
    was rejected. A number that arrived as JSON becomes text, because that is
    what a text input holds and what parse_tr_number reads.

    `source` is the raw claim being echoed back - "norm" exactly when the
    submitted entry itself said "norm" - not a verdict re-derived by comparing
    the echoed value and unit to the crop's cell. That comparison used to be
    how the card marked a field "norm" on redisplay, and it upgraded a farmer's
    own typed figure to "norm" the moment it happened to equal the published
    one. _verify() still checks this claim at compute time, so a lying client
    is caught there, not here.
    """
    entry = (submitted or {}).get(spec.id)
    if not isinstance(entry, dict):
        return {"value": "", "unit": spec.units[0].id}
    value = entry.get("value")
    unit = entry.get("unit")
    return {
        "value": "" if value is None else str(value),
        # An unrecognised unit falls back to the first, or the card would render
        # with no chip selected and no way to tell why.
        "unit": unit if any(u.id == unit for u in spec.units) else spec.units[0].id,
        "source": "norm" if entry.get("source") == "norm" else "user",
    }


def form_spec(errors: list[FieldError], table=None, submitted=None,
              latest_year: int | None = None) -> dict:
    """Serialise FIELDS for the client, attaching each error to its own field.

    `table` is a province's worth of norms, from norms.province_table. When it
    is absent - no province resolved, or a broken data file - the output is
    byte-identical to P1's, because an already-deployed client reads this dict
    and an unexpected key is a wire change wearing an addition's clothes.

    `submitted` is the payload that failed validation. Echoing it back is not a
    nicety: the card seeds its state from `value`, so without it a single bad
    field wipes the whole form, the crop selection and its prefill included.

    `latest_year` is the norms dataset's most recent year (norms.latest_year());
    it decides which crops get a price cell at all - see _crop_rows. It is an
    int, not looked up here: this module imports nothing from src/norms.py.
    """
    # Coerce non-dict submitted to {} before use, as validate() does for raw.
    # submitted carries an untrusted payload that already failed validation, so
    # it must be defended at the same trust boundary as validate()'s raw param.
    submitted = submitted if isinstance(submitted, dict) else {}

    by_field = {e.field: e.message for e in errors}
    spec = {
        "fields": [
            {
                "id": f.id,
                "label": f.label,
                "required": f.required,
                "units": [{"id": u.id, "label": u.label} for u in f.units],
                "value": "",
                "source": "empty",
                "error": by_field.get(f.id),
            }
            for f in FIELDS
        ]
    }
    if submitted:
        for field in spec["fields"]:
            field.update(_echo(_FIELDS_BY_ID[field["id"]], submitted))
        crop = submitted.get("crop")
        if isinstance(crop, str) and crop.strip():
            spec["crop"] = crop
    if table:
        spec["crops"] = _crop_rows(table, latest_year)
    return spec


@dataclass(frozen=True)
class BudgetResult:
    yield_kg_da: float
    revenue_tl: float
    cost_tl: float | None
    margin_tl: float | None
    margin_pct: float | None


def compute(inputs: BudgetInputs) -> BudgetResult:
    """All arithmetic for this route lives here, in one place, on canonical units.

    validate() has already rejected a zero area, so the per-dekar division is
    safe; the revenue guard below is the one that is not implied by validation,
    because a zero harvest or a zero price is legitimate.
    """
    revenue = inputs.yield_kg.amount * inputs.price_tl_kg.amount
    cost = inputs.cost_tl.amount if inputs.cost_tl is not None else None
    margin = None if cost is None else revenue - cost
    pct = None if (margin is None or revenue <= 0) else margin / revenue * 100
    return BudgetResult(
        yield_kg_da=inputs.yield_kg.amount / inputs.area_da.amount,
        revenue_tl=revenue,
        cost_tl=cost,
        margin_tl=margin,
        margin_pct=pct,
    )


# Appended BY CODE, never asked of the model - the fertplan.FRAMING pattern.
# This sentence is the line between a calculation and a forecast.
FRAMING = (
    "Bu hesap bir tahmindir ve tamamen sizin girdiğiniz rakamlara dayanır; "
    "fiyat veya verim öngörüsü değildir."
)


def _norm_measures(inputs: BudgetInputs) -> list[tuple[str, Value]]:
    """Which measures came from a published norm, and under what Turkish label.

    The single place that decides whether any norm figure survived. render()
    and framing() both read this list rather than each re-checking .source, so
    the lead-in and the framing sentence can never disagree about it.
    """
    return [(label, value)
            for label, value in (("verim", inputs.yield_kg),
                                 ("fiyat", inputs.price_tl_kg))
            if value.source == "norm"]


# The second framing, for a calculation that used a published average. Both
# sentences are appended BY CODE and neither is ever asked of a model - the
# fertplan.FRAMING pattern. A provincial mean yield is a central tendency across
# every holding in the province; printed without this it invites being read as a
# forecast for one parcel.
def framing(inputs: BudgetInputs) -> str:
    """P1's sentence, or the one that names whose figures these are."""
    used = _norm_measures(inputs)
    if not used:
        return FRAMING

    plural = len(used) > 1
    which = " ve ".join(label for label, _ in used)
    noun = "rakamları" if plural else "rakamı"
    ortalama = "ortalamalarıdır" if plural else "ortalamasıdır"
    notes: list[str] = []
    for _, value in used:
        # Both measures normally share one note; printing it twice would read
        # as two different sources.
        if value.note and value.note not in notes:
            notes.append(value.note)
    source = " · ".join(notes)
    # The provenance (TÜİK, year, region) lives in the parenthetical only - the
    # sentence body says "yayımlanmış" (published) rather than naming TÜİK a
    # second time in the same sentence.
    return (
        f"Bu hesaptaki {which} {noun} sizin değil, yayımlanmış bölge "
        f"{ortalama} ({source}). Bölge ortalaması tek bir tarlanın verimi "
        f"veya sizin alacağınız fiyat için bir öngörü değildir; kendi "
        f"rakamınızı girerseniz hesap ona göre yapılır."
    )

# Written to stand alone: a deployed client that cannot draw the form shows only
# this, so it names the figures it needs instead of pointing at a widget. The
# wording also survives P2 - when norms arrive the fields come prefilled and the
# sentence still reads correctly.
ASK_FOR_NUMBERS = (
    "Hesaplayabilmem için birkaç rakama ihtiyacım var: ektiğiniz alan, aldığınız "
    "toplam ürün, ürünün satış fiyatı ve masrafınız. Bu rakamları verirseniz "
    "gelirinizi ve kâr marjınızı hesaplayabilirim."
)

# The failure mode of this route is silence, never a guess: there is no fallback
# to the model path, because an LLM answer about money is what this spec removes.
COMPUTE_FAILED = (
    "Hesaplamayı tamamlayamadım. Lütfen girdiğiniz değerleri kontrol edip "
    "tekrar deneyin."
)


def _format_qty(value: float) -> str:
    """Format a quantity for the restated line without rounding it away.

    The restated line exists so the user can check what the calculation was
    made from; it stands in for an upper bound on input values, so it has to
    echo what was typed rather than a rounded stand-in. format_tr(x, 0) would
    turn 2,5 into "2", silently disagreeing with the arithmetic underneath it,
    which still uses the true 2,5.
    """
    if value == int(value):
        return format_tr(value, 0)
    # 2,5 formats to "2,50" at two decimals, and a value that rounds to a
    # whole number at two decimals (e.g. 12.995052770448549) formats to
    # "13,00" - both are padding, not something the user typed, so strip
    # every trailing zero and then the now-bare comma. This branch only runs
    # when value != int(value), so format_tr(value, 2) always contains a
    # comma; rstrip("0") can only eat digits after it, never a whole
    # number's own trailing zeros (those go through the branch above).
    return format_tr(value, 2).rstrip("0").rstrip(",")


def render(inputs: BudgetInputs, result: BudgetResult) -> str:
    """Code-written Turkish. Restates its inputs before stating its result."""
    crop_name = inputs.crop_label or inputs.crop
    crop = f" {crop_name} için" if crop_name else ""
    given = [
        f"**{_format_qty(inputs.area_da.amount)} dönüm**",
        f"toplam **{_format_qty(inputs.yield_kg.amount)} kg** "
        f"(dekara {_format_qty(result.yield_kg_da)} kg)",
        f"kilogram fiyatı **{format_tr(inputs.price_tl_kg.amount, 2)} TL**",
    ]
    if result.cost_tl is not None:
        given.append(f"masraf **{format_tr(result.cost_tl, 2)} TL**")

    # Same lead-in P1 always used, unless a norm figure is standing in for
    # something the user did not type - then "girdiğiniz" (what you entered)
    # would be the same falsehood the framing sentence exists to remove.
    lead_in = ("Şu değerlere göre" if _norm_measures(inputs)
               else "Girdiğiniz değerlere göre")
    lines = [f"{lead_in}{crop}: " + ", ".join(given) + ".", ""]

    if result.margin_tl is None:
        lines.append(f"Gelir **{format_tr(result.revenue_tl, 2)} TL**.")
        lines.append(
            "Masrafınızı da girerseniz kâr marjınızı da hesaplayabilirim.")
    else:
        pct = ("" if result.margin_pct is None
               else f" (kâr marjı %{format_tr(result.margin_pct, 0)})")
        lines.append(
            f"Gelir **{format_tr(result.revenue_tl, 2)} TL** · "
            f"Masraf **{format_tr(result.cost_tl, 2)} TL** · "
            f"**Marj {format_tr(result.margin_tl, 2)} TL**{pct}"
        )

    lines.extend(["", framing(inputs)])
    return "\n".join(lines)
