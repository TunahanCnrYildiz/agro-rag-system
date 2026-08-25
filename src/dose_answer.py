"""The product-dose route: the manufacturer's own per-dekar figure, times the
farmer's area, and nothing else.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from a figure the
manufacturer published and an area the user selected. The route does not call
the LLM at all.

NOTHING IS READ OUT OF THE QUESTION. "5 donumum var, ne kadar alirim?" has
exactly the shape P1 removed from the budget route - a number in a sentence
that must reach arithmetic - so it gets exactly the same treatment: labelled
fields, a unit that is a SELECTION, no inference.

THE METHOD IS AN ATTRIBUTE OF THE ANSWER, NOT AN INPUT. 37 of the 42 products
with a per-area dose publish it for drip irrigation only, so a method selector
would offer a choice in appearance only. Every figure that exists for the
product and group is printed, each labelled with the method the source
attached to it.

This module imports nothing from src/engine.py - the boundary src/norms.py,
src/budget.py and src/doses.py all keep.
"""
from __future__ import annotations

from dataclasses import dataclass

from src import doses
from src.budget import FieldError, UnitOption, coerce_number
from src.dose_parse import GROUP_KEYS

# The three groups the panels segment by, with the label the card prints. The
# ids come from the parser rather than being restated, so a group the data can
# carry and a button the farmer can press cannot drift apart.
_GROUP_LABELS = {"sebze": "Sebze", "meyve": "Meyve", "tarla": "Tarla bitkisi"}
GROUPS: tuple[tuple[str, str], ...] = tuple((key, _GROUP_LABELS[key])
                                            for key in GROUP_KEYS)
_GROUP_IDS = frozenset(GROUP_KEYS)

# P1's area control, unchanged, including the unit-as-selection rule.
AREA_UNITS: tuple[UnitOption, ...] = (UnitOption("donum", "dönüm", 1.0),
                                      UnitOption("hektar", "hektar", 10.0))

AREA_LABEL = "Alan"


@dataclass(frozen=True)
class DoseInputs:
    """Canonical throughout: dekar."""
    product: str
    group: str
    area_da: float


def _read_area(raw: dict) -> tuple[float | None, FieldError | None]:
    entry = raw.get("area")
    if not isinstance(entry, dict) or entry.get("value") in (None, ""):
        return None, FieldError("area", f"{AREA_LABEL} alanını doldurun.")
    amount = coerce_number(entry.get("value"))
    if amount is None:
        return None, FieldError(
            "area", f"{AREA_LABEL} bir sayı olmalı. Ondalık için virgül kullanın.")
    unit = next((u for u in AREA_UNITS if u.id == entry.get("unit")), None)
    if unit is None:
        return None, FieldError("area", f"{AREA_LABEL} için birimi seçin.")
    if amount <= 0:
        return None, FieldError("area", f"{AREA_LABEL} sıfırdan büyük olmalı.")
    return amount * unit.factor, None


def validate(raw: object) -> tuple[DoseInputs | None, list[FieldError]]:
    """Read every field, collect every error. Never raises.

    The product is checked against the table rather than believed, for the same
    reason budget._verify looks the crop up: it arrives from a client, and a
    name we hold no figure for must become a field error rather than an empty
    answer with no explanation.
    """
    raw = raw if isinstance(raw, dict) else {}
    errors: list[FieldError] = []

    product = raw.get("product")
    product = product.strip() if isinstance(product, str) else ""
    if not product:
        errors.append(FieldError("product", "Ürünü seçin."))
    elif product not in doses.available_products():
        errors.append(FieldError(
            "product",
            "Bu ürünün sayfasında dekara doz yayımlanmamış; elimde bir rakam yok."))

    group = raw.get("group")
    if not isinstance(group, str) or group not in _GROUP_IDS:
        errors.append(FieldError(
            "group", "Tarlanızın grubunu seçin: sebze, meyve veya tarla bitkisi."))

    area_da, area_error = _read_area(raw)
    if area_error is not None:
        errors.append(area_error)

    if errors:
        return None, errors
    return DoseInputs(product=product, group=group, area_da=area_da), []


def form_spec(errors: list[FieldError], submitted: object = None) -> dict:
    """Serialise the card for the client, attaching each error to its field.

    `submitted` is the payload that failed validation. Echoing it back is not a
    nicety: the card seeds its state from this dict, so without it a single bad
    field wipes the product and the group along with the area.

    `kind` is here so a client that grows a second card type can tell them
    apart. The dose form travels on its own SSE event and its own response key,
    so an already-deployed build never receives one at all - see src/engine.py.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    by_field = {e.field: e.message for e in errors}

    entry = submitted.get("area")
    entry = entry if isinstance(entry, dict) else {}
    value = entry.get("value")
    unit = entry.get("unit")

    product = submitted.get("product")
    group = submitted.get("group")
    return {
        "kind": "product_dose",
        "products": list(doses.available_products()),
        "groups": [{"id": key, "label": label} for key, label in GROUPS],
        "product": product if isinstance(product, str) else "",
        "group": group if isinstance(group, str) else "",
        "area": {
            "label": AREA_LABEL,
            # A number that arrived as JSON becomes text, because that is what
            # a text input holds and what the parser reads.
            "value": "" if value is None else str(value),
            # An unrecognised unit falls back to the first, or the card renders
            # with no chip selected and no way to tell why.
            "unit": unit if any(u.id == unit for u in AREA_UNITS) else AREA_UNITS[0].id,
            "units": [{"id": u.id, "label": u.label} for u in AREA_UNITS],
        },
        "errors": {"product": by_field.get("product"),
                   "group": by_field.get("group"),
                   "area": by_field.get("area")},
    }
