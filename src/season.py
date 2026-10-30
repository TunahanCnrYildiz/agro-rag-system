"""The season calendar (Hüseyin's PDF p5): a crop's development stages, dated
from the farmer's own planting date, with each stage's relative water use.

EVERY FIGURE HERE IS PUBLISHED - decided 2026-10-30, a representative
calendar with an engineer warning, each line from a cited source and none from
our own agronomy. The stage lengths are FAO-56 Table 11, the water-use
coefficients FAO-56 Table 12 (data/crop_stages.json); data/crop_stage_map.json
says which published row is about which of our crops. The only arithmetic is
adding published day counts to the farmer's date, and it is done here, never
by a model.

WHICH ROW. Table 11 lists several climates per crop. Only rows published for
the Mediterranean or Europe are read (a few name a Mediterranean country -
"Spain", "Egypt" - instead), and only rows whose four stages add up to the
published total: the page carries a handful of typos ("2705" days for olives,
an Idaho sweet corn row 10 days short), and a calendar built from one would be
wrong in a way no reader could see. Among the rest, the row whose planting
month is nearest the farmer's is used - and if none is within a month, there is
NO calendar: the published durations belong to a season the farmer is not
planting in, and saying so beats stretching them over another.

Nothing here imports src/engine.py.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

from src.config import DATA_DIR

_STAGES_JSON = DATA_DIR / "crop_stages.json"
_MAP_JSON = DATA_DIR / "crop_stage_map.json"

_REGION = re.compile(r"medit|europe|spain|egypt", re.I)
# A row may name a latitude band instead of a climate - FAO-56 has one, spring
# "Barley/Oats/Wheat, 35-45 °L". It counts only when the band holds ALL of
# Türkiye, from southern Hatay to Sinop: arithmetic, unlike "Mid Latitudes",
# which FAO-56 never defines and which is therefore never read.
_BAND = re.compile(r"(\d+)\s*-\s*(\d+)\s*°\s*L(?![A-Za-z])")
TURKIYE_LATITUDE = (35.8, 42.1)


def _region_ok(region: str) -> bool:
    """A published region these farmers are in: the Mediterranean or Europe,
    or a latitude band that contains Türkiye whole."""
    if _REGION.search(region or ""):
        return True
    band = _BAND.search(region or "")
    if band is None:
        return False
    south, north = float(band.group(1)), float(band.group(2))
    return south <= TURKIYE_LATITUDE[0] and TURKIYE_LATITUDE[1] <= north

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_TR_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
              "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

STAGE_NAMES = ("Başlangıç", "Gelişme", "Orta dönem", "Son dönem")

DISCLAIMER = (
    "Bu takvim yayımlanmış kaynaklardan derlenmiş temsili bir programdır; "
    "iklim, çeşit ve tarlanızın koşulları süreleri değiştirir. Tarlanıza özel "
    "kesin bilgi için bir ziraat mühendisine danışın."
)
KC_EXPLAINED = (
    "Kc, bitkinin su tüketiminin kısa biçilmiş referans çim yüzeyine oranıdır; "
    "1'in üstü referanstan fazla su tükettiği anlamına gelir."
)
NO_FERTILIZATION_YET = (
    "Gübreleme: bu ürün için üreticinin ürün sayfalarında yayımlanmış bir "
    "uygulama zamanı yok. Dönemlere göre gübreleme için bana ayrıca sorabilirsiniz."
)
FERTILIZATION_HEAD = (
    "**Gübreleme** · üreticinin ürün sayfalarında yayımladığı uygulama zamanları:"
)
FERTILIZATION_DOSES = (
    "Dozlar ürün sayfalarında yazıyor; \"{product} dekara ne kadar?\" diye sorarsanız "
    "alanınıza göre hesaplarım."
)
_TIMING_JSON = DATA_DIR / "product_timing.json"

# THE WEATHER RULES ARE THE COMPANY'S OWN, published in its Akademi article
# "Toprağa Ne Zaman Gübre Atılır?" - quoted, and a test checks the quotes
# against the scraped article. Its thresholds, not ours: any rain, and 30 °C.
# The PDF's "yağış varsa sulama ertelenir" has no published source here, so
# rain is reported in millimetres and irrigation is not advised on.
WEATHER_SOURCE_URL = ("https://www.ekolojiktarim.com.tr/2025/09/25/"
                      "topraga-ne-zaman-gubre-atilir-dogru-zamanlama-rehberi/")
RAIN_RULE_QUOTE = "yağmur öncesi gübre uygulaması kayıplara neden olur"
RAIN_RULE = (
    "Yağış bekleniyor. Akademi'ye göre \"yağmur öncesi gübre uygulaması kayıplara "
    "neden olur\"; uygulama yağmur sonrasına bırakılır."
)
HEAT_RULE_QUOTE = "30°C üzeri sıcaklıklarda yaprak uygulaması yapılmamalıdır"
HEAT_RULE = (
    "Sıcaklığın 30 °C'yi aşması bekleniyor. Akademi'ye göre \"30°C üzeri "
    "sıcaklıklarda yaprak uygulaması yapılmamalıdır\"; serin saatler tercih edilir."
)


@lru_cache(maxsize=1)
def _load() -> tuple[dict, dict]:
    """(stages file, crop map), or two empty dicts. A broken file costs the
    calendar, never the answer - the norms modules' rule."""
    try:
        stages = json.loads(_STAGES_JSON.read_text(encoding="utf-8"))
        mapping = json.loads(_MAP_JSON.read_text(encoding="utf-8"))
        if not isinstance(stages, dict) or not isinstance(mapping, dict):
            return {}, {}
        return stages, mapping
    except Exception:  # noqa: BLE001
        return {}, {}


@lru_cache(maxsize=1)
def _load_timing() -> tuple[list[dict], dict, dict]:
    """(timing rows, TÜİK groups, product name -> page URL); empty on any
    failure - a broken file costs the fertilization rows, never the calendar."""
    try:
        from src.config import PRODUCTS_JSON
        timing = json.loads(_TIMING_JSON.read_text(encoding="utf-8"))
        products = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
        links = {p["product_name"]: p.get("source_url", "") for p in products
                 if isinstance(p, dict) and p.get("product_name")}
        rows = [r for r in timing.get("rows", []) if isinstance(r, dict)]
        return rows, timing.get("tuik_groups", {}), links
    except Exception:  # noqa: BLE001
        return [], {}, {}


@dataclass(frozen=True)
class Application:
    """One product application the manufacturer's page times."""
    product: str
    link: str
    when: str
    first: date | None   # only when the page counts from planting


def applications(crop_id: str, planting: date) -> tuple[Application, ...]:
    """Every published application row that names this crop, or names TÜİK's
    group it belongs to. Dated from `planting` only where the page itself
    counts from planting."""
    rows, groups, links = _load_timing()
    out = []
    for row in rows:
        crops = row.get("crops") or groups.get(row.get("tuik_group", ""), [])
        if crop_id not in crops:
            continue
        days = row.get("after_planting_days")
        first = planting + timedelta(days=days) if isinstance(days, int) else None
        out.append(Application(row["product"], links.get(row["product"], ""),
                               row["when"], first))
    return tuple(out)


def available_crops() -> tuple[str, ...]:
    """Our crop ids the map names a Table 11 crop for."""
    _, mapping = _load()
    return tuple(cid for cid, entry in mapping.items()
                 if isinstance(entry, dict) and _variants(entry))


def plant_months(text: str) -> frozenset[int]:
    """Every month a published "Plant Date" names: "Apr/May", "Mar-May",
    "Apr; Sep/Oct", "Oct/Nov". A range takes every month inside it."""
    found: set[int] = set()
    for a, sep, b in re.findall(r"([A-Za-z]{3,})\.?\s*(-)?\s*([A-Za-z]{3,})?", text or ""):
        first = _MONTHS.get(a[:3].lower())
        last = _MONTHS.get(b[:3].lower()) if b else None
        if first and sep and last:
            month = first
            while True:
                found.add(month)
                if month == last:
                    break
                month = month % 12 + 1
        else:
            found.update(m for m in (first, last) if m)
    return frozenset(found)


def _days(row: dict) -> tuple[int, int, int, int] | None:
    """The four stage lengths, when they add up to the published total.

    The table writes some values as two readings - "25/30" days, a total of
    "115/130". A reading is used only when EXACTLY ONE combination of the
    readings adds up to a published total: bell pepper's "25/30" initial stage
    with 35 + 40 + 20 and a total of 125 can only be 30. Two combinations that
    both add up (spinach: 60 and 70) leave the row unused - the arithmetic
    cannot say which season was meant. "var.", "--" and the page's typos
    ("2705" days for olives) never add up and are never used.
    """
    try:
        options = [[int(v) for v in str(row[k]).split("/")]
                   for k in ("init", "dev", "mid", "late")]
        totals = {int(v) for v in str(row["total"]).split("/")}
    except (KeyError, TypeError, ValueError):
        return None
    matches = {(a, b, c, d) for a in options[0] for b in options[1]
               for c in options[2] for d in options[3] if a + b + c + d in totals}
    return next(iter(matches)) if len(matches) == 1 else None


def usable_rows(t11_crop: str) -> list[dict]:
    stages, _ = _load()
    return [row for row in stages.get("stages", [])
            if row.get("crop") == t11_crop and _region_ok(row.get("region") or "")
            and _days(row) is not None and plant_months(row.get("plant", ""))]


def _month_gap(a: int, b: int) -> int:
    gap = abs(a - b) % 12
    return min(gap, 12 - gap)


@dataclass(frozen=True)
class Stage:
    name: str
    start: date
    end: date            # the stage's last day
    days: int
    water: str           # the Kc line, published values only


@dataclass(frozen=True)
class SeasonCalendar:
    label: str
    planting: date       # a tree's season START, an annual's planting
    stages: tuple[Stage, ...]
    row: dict            # the Table 11 row the durations came from
    kc: dict | None      # the Table 12 row, or the range a "t12_range" names
    note: str | None
    applications: tuple[Application, ...] = ()
    kind: str = "annual"  # "annual" | "tree"


@dataclass(frozen=True)
class NoCalendar:
    label: str
    reason: str


def _variants(entry: dict) -> list[tuple[str, object]]:
    """(Table 11 crop, Table 12 spec) pairs for a map entry. Most crops have one;
    a crop FAO-56 publishes as several rows with their own coefficients - banana
    in its first and second year - lists them under "variants", so each row
    keeps its own Kc."""
    if isinstance(entry.get("variants"), list):
        return [(v.get("t11"), v.get("t12")) for v in entry["variants"]
                if isinstance(v, dict) and v.get("t11")]
    if entry.get("t11"):
        return [(entry["t11"], entry.get("t12_range") and {"range": entry["t12_range"]}
                 or entry.get("t12"))]
    return []


_KC = re.compile(r"\d\.\d{1,2}")


def _kc_value(text: object) -> str | None:
    """A published Kc - "1.15", or a range "0.70-0.90" - or None. Table 12
    prints some footnote marks unmarked, so walnut's "0.65" reads "0.6518":
    a value with more than two decimals is not one the table published."""
    if not isinstance(text, str):
        return None
    parts = text.strip().split("-")
    return text.strip() if parts and all(_KC.fullmatch(x) for x in parts) else None


def _kc_row(t12) -> dict | None:
    """The Table 12 row a spec names, or - for {"range": [crops]} - the range
    of every row of those crops: citrus is published as six rows by ground
    cover and canopy, and without asking which, the range is what is known."""
    stages, _ = _load()
    rows = stages.get("kc", [])
    if isinstance(t12, dict) and isinstance(t12.get("range"), list):
        picked = [r for r in rows if r.get("crop") in t12["range"]]
        out = {"crop": ", ".join(t12["range"]), "variant": None, "range": True}
        for key in ("kc_ini", "kc_mid", "kc_end"):
            values = [float(v) for v in (_kc_value(r.get(key)) for r in picked)
                      if v is not None and "-" not in v]
            if not values:
                return None
            out[key] = f"{min(values):.2f}-{max(values):.2f}"
        return out
    if not isinstance(t12, list) or len(t12) != 2:
        return None
    crop, variant = t12
    return next((r for r in rows if r.get("crop") == crop and r.get("variant") == variant),
                None)


def _num(text: str) -> str:
    """A published Kc as Turkish notation: "1.15" -> "1,15", "0.70-0.90" ->
    "0,70-0,90". Only the decimal mark changes."""
    return (text or "").replace(".", ",")


def _water_lines(kc: dict | None) -> tuple[str, str, str, str]:
    """The four stages' water lines. The rising-then-falling reading ("artıyor",
    "en yüksek", "azalıyor") is printed only when the published values say so -
    mid above the start and the end below mid; a range, or a crop whose
    mid-season is not its peak, gets the values alone."""
    values = None if kc is None else tuple(_kc_value(kc.get(k))
                                           for k in ("kc_ini", "kc_mid", "kc_end"))
    if values is None or None in values:
        missing = "su ihtiyacı için yayımlanmış katsayı yok"
        return (missing,) * 4
    ini, mid, end = (_num(v) for v in values)
    lo_hi = [tuple(float(x) for x in v.split("-")) for v in values]
    # Every reading of a published range must agree: the start's highest below
    # mid-season's lowest, and the end's highest below it too. Tomato's end
    # "0.70-0.90" sits wholly under its 1.15; citrus's ranges overlap and get
    # no reading at all.
    if max(lo_hi[0]) < min(lo_hi[1]) and max(lo_hi[2]) < min(lo_hi[1]):
        return (f"su ihtiyacı düşük (Kc {ini})",
                f"su ihtiyacı artıyor (Kc {ini} → {mid})",
                f"su ihtiyacı en yüksek (Kc {mid})",
                f"su ihtiyacı azalıyor (Kc {mid} → {end})")
    return (f"su ihtiyacı (Kc {ini})", f"su ihtiyacı (Kc {ini} → {mid})",
            f"su ihtiyacı (Kc {mid})", f"su ihtiyacı (Kc {mid} → {end})")


def build(crop_id: str, label: str, planting: date) -> SeasonCalendar | NoCalendar:
    """The calendar for one crop from one date - an annual's planting, a tree's
    season start - or the reason there is none."""
    _, mapping = _load()
    entry = mapping.get(crop_id)
    pairs = _variants(entry) if isinstance(entry, dict) else []
    if not pairs:
        return NoCalendar(label, "FAO-56 bu ürün için gelişim dönemi süresi "
                                 "yayımlamıyor, bu yüzden takvim çıkaramıyorum.")
    tree = entry.get("kind") == "tree"
    rows = [(row, t12) for t11, t12 in pairs for row in usable_rows(t11)]
    if not rows:
        return NoCalendar(label, "FAO-56'da bu ürün için Türkiye'ye uyan (Akdeniz, "
                                 "Avrupa ya da Türkiye'yi kapsayan bir enlem aralığı "
                                 "için yayımlanmış), tutarlı bir gelişim dönemi satırı "
                                 "yok, bu yüzden takvim çıkaramıyorum.")
    gap, row, t12 = min(((min(_month_gap(planting.month, m)
                              for m in plant_months(r["plant"])), r, t12)
                         for r, t12 in rows), key=lambda triple: triple[0])
    if gap > 1:
        published = sorted({m for r, _ in rows for m in plant_months(r["plant"])})
        months = ", ".join(_TR_MONTHS[m - 1] for m in published)
        asked = _TR_MONTHS[planting.month - 1]
        what, of = (("sezon başlangıcına", "başlangıcı") if tree else ("ekimine", "ekimi"))
        return NoCalendar(label, (
            f"FAO-56 bu ürün için Türkiye'ye uyan satırlarda yalnızca {months} {what} ait "
            f"süreleri yayımlıyor; {asked} {of} için yayımlanmış bir süre olmadığından "
            f"takvim çıkaramıyorum."))
    days = _days(row)
    kc = _kc_row(t12)
    water = _water_lines(kc)
    stages, start = [], planting
    for name, length, water_line in zip(STAGE_NAMES, days, water):
        end = start + timedelta(days=length - 1)
        stages.append(Stage(name, start, end, length, water_line))
        start = end + timedelta(days=1)
    # A variant's own note - "these days are shared by barley, oats and wheat" -
    # belongs to its row, and is printed only when that row is the one used.
    variant_note = next((v.get("note") for v in entry.get("variants", [])
                         if isinstance(v, dict) and v.get("t11") == row.get("crop")
                         and v.get("note")), None)
    return SeasonCalendar(label, planting, tuple(stages), row, kc,
                          variant_note or entry.get("note"),
                          applications(crop_id, planting), "tree" if tree else "annual")


# --------------------------------------------------------------------------- #
# The card
# --------------------------------------------------------------------------- #
# Written to stand alone: a client that cannot draw the card shows only this,
# so it names what the programme is built from instead of pointing at a widget.
ASK_FOR_INPUTS = (
    "Sezon programını iki bilgiyle çıkarırım: ürün ve ekim (dikim) tarihi - "
    "meyve ağaçlarında sezonun başladığı tarih. Gelişim dönemlerinin süreleri "
    "FAO'nun yayımladığı tablolardan gelir."
)
COMPUTE_FAILED = (
    "Sezon programını çıkaramadım. Lütfen seçimlerinizi kontrol edip tekrar deneyin."
)
DATE_ERROR = "Ekim (dikim) tarihini GG.AA.YYYY biçiminde yazın (örn. 15.04.2027)."
TREE_DATE_ERROR = "Sezon başlangıcını GG.AA.YYYY biçiminde yazın (örn. 01.02.2027)."


def crop_options() -> list[dict]:
    """The crops the card offers - those the map names a published stage row
    for - with the labels the rest of the product uses for them."""
    from src import norms
    labels = dict(norms.available_crops())
    _, mapping = _load()
    return sorted(({"id": cid, "label": labels.get(cid, cid),
                    "kind": mapping[cid].get("kind", "annual")}
                   for cid in available_crops()), key=lambda c: c["label"])


def parse_date(text: object) -> date | None:
    """"15.04.2027", "15/04/2027", "15-04-2027" or "2027-04-15"; None otherwise."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text)
    parts = (int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None
    if parts is None:
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        parts = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    if parts is None or not 2000 <= parts[0] <= 2100:
        return None
    try:
        return date(*parts)
    except ValueError:
        return None


def validate(raw: object) -> tuple[tuple[str, str, date] | None, dict]:
    """((crop id, label, planting date), {}) or (None, {field: message}).
    Never raises; every error at once, like the other cards."""
    raw = raw if isinstance(raw, dict) else {}
    listed = crop_options()
    options = {c["id"]: c["label"] for c in listed}
    trees = {c["id"] for c in listed if c.get("kind") == "tree"}
    errors: dict[str, str] = {}
    crop = raw.get("crop")
    if not isinstance(crop, str) or not crop.strip():
        errors["crop"] = "Ürünü seçin."
    elif crop not in options:
        errors["crop"] = "Bu ürün için yayımlanmış bir gelişim dönemi tablosu yok."
    planting = parse_date(raw.get("planting"))
    if planting is None:
        errors["planting"] = TREE_DATE_ERROR if crop in trees else DATE_ERROR
    if errors:
        return None, errors
    return (crop, options[crop], planting), {}


def form_spec(errors: dict | None = None, submitted: object = None,
              crop: str | None = None) -> dict:
    """The card. `crop` preselects one the question named; a rejected
    submission echoes back what the farmer had, so one bad field does not wipe
    the other."""
    submitted = submitted if isinstance(submitted, dict) else {}
    errors = errors or {}
    chosen = submitted.get("crop") if isinstance(submitted.get("crop"), str) else crop
    planting = submitted.get("planting")
    return {
        "kind": "season",
        "crops": crop_options(),
        "crop": chosen or "",
        "planting": planting if isinstance(planting, str) else "",
        "errors": {"crop": errors.get("crop"), "planting": errors.get("planting")},
    }


def _day(d: date) -> str:
    return f"{d.day} {_TR_MONTHS[d.month - 1]}"


def weather_lines(result: SeasonCalendar, today: date, province: str | None,
                  outlook) -> list[str]:
    """This week's forecast and the company's rules it triggers - only while
    the season is under way or a week from starting: a forecast says nothing
    about a planting months away. `outlook` is weather.Outlook or None."""
    if outlook is None or province is None:
        return []
    if not (result.planting - timedelta(days=7) <= today <= result.stages[-1].end):
        return []
    lines = [f"**Bu hafta** ({province}, Open-Meteo tahmini): {outlook.phrase()}."]
    if outlook.rain_mm > 0:
        lines.append(RAIN_RULE)
    if outlook.t_max > 30:
        lines.append(HEAT_RULE)
    if len(lines) > 1:
        lines.append(f"Kaynak: Ekolojik Tarım Akademi, \"Toprağa Ne Zaman Gübre "
                     f"Atılır?\" ({WEATHER_SOURCE_URL})")
    return lines


def render(result: SeasonCalendar | NoCalendar, weather: list[str] | None = None) -> str:
    """Code-written Turkish; the source and the warning are part of the text.
    `weather` is weather_lines()' output, placed after the programme."""
    if isinstance(result, NoCalendar):
        return f"**{result.label}**: {result.reason}\n\n{DISCLAIMER}"
    tree = result.kind == "tree"
    planted = f"{_day(result.planting)} {result.planting.year}"
    started = "sezon başlangıcı" if tree else "ekim/dikim"
    lines = [f"**{result.label}** için temsili sezon programı · {started}: {planted}", ""]
    for i, s in enumerate(result.stages, 1):
        lines.append(f"{i}. **{s.name}** · {_day(s.start)} – {_day(s.end)} "
                     f"({s.days} gün) · {s.water}")
    last = result.stages[-1].end
    closing = "Sezonun bitişi" if tree else "Son dönemin bitişi (hasat dönemi)"
    lines += ["", f"{closing}: {_day(last)} {last.year}", ""]
    region, plant = result.row.get("region", ""), result.row.get("plant", "")
    source = (f"Kaynak: FAO-56 (Allen vd., 1998), Tablo 11 - {result.row.get('crop')}, "
              f"{region}, {plant} {'başlangıcı' if tree else 'ekimi'}")
    source += " ve Tablo 12." if result.kc else "."
    lines.append(source)
    if result.note:
        lines.append(result.note)
    if result.kc:
        lines.append(KC_EXPLAINED)
    lines.append("")
    if result.applications:
        lines.append(FERTILIZATION_HEAD)
        for app in result.applications:
            line = f"- **{app.product}** · {app.when}"
            if app.first is not None:
                which = "dikim günü" if app.first == result.planting else "ilk uygulama"
                line += f" · {which}: {_day(app.first)} {app.first.year}"
            lines.append(line)
        lines.append(FERTILIZATION_DOSES.format(product=result.applications[0].product))
    else:
        lines.append(NO_FERTILIZATION_YET)
    if weather:
        lines += [""] + weather
    lines += ["", DISCLAIMER]
    return "\n".join(lines)
