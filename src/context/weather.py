"""Coming-week weather for a province, as a short phrase for the prompt.

Three figures are agronomically useful and the rest is noise: rain in the next
few days (fertiliser applied before heavy rain washes off), the low (frost), and
the high.

Open-Meteo needs no key for non-commercial use. IT DOES REQUIRE ONE FOR
COMMERCIAL USE, and this is a commercial product - budget a key before go-live.

Never raises. A weather lookup that can break an answer is worse than no weather.

ONLY SUCCESSES ARE CACHED. An `lru_cache` here would memoise `None`, so a single
transient 2 s timeout - most likely on the very first request in a cold container,
which is exactly when the network is least settled - would disable weather for that
province until the process restarted, with no retry and no expiry. A failure must
cost one lookup, not the feature.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import requests

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FC_URL = "https://api.open-meteo.com/v1/forecast"

# Short: this sits in the request path. Exceeding it costs the weather sentence,
# not the answer.
_TIMEOUT = 2.0

# Successes only, both of them. Nothing here is ever a negative result, so a
# failed lookup is simply retried next time.
#   coordinates: the 81 provinces do not move, so one lookup each, forever.
#   forecasts:   keyed by (province, day) - see forecast() for why the day matters.
@dataclass(frozen=True)
class Outlook:
    """The coming week, as the three figures the phrase is made of - so the
    season calendar can test them against a published rule without a second
    request and without parsing a sentence back into numbers."""
    rain_mm: float      # the week's total, to 0,1 mm
    t_min: int          # the week's lowest daily minimum, °C
    t_max: int          # the week's highest daily maximum, °C

    def phrase(self) -> str:
        return (f"önümüzdeki hafta toplam {self.rain_mm} mm yağış bekleniyor, "
                f"sıcaklık {self.t_min}-{self.t_max} °C aralığında")


_GEO_CACHE: dict[str, tuple[float, float]] = {}
_FORECAST_CACHE: dict[tuple[str, date], Outlook] = {}


def cache_clear() -> None:
    """Drop both caches. For tests; nothing in production needs it."""
    _GEO_CACHE.clear()
    _FORECAST_CACHE.clear()


def _geocode(province: str) -> tuple[float, float] | None:
    """Province name -> coordinates, or None. A miss is not cached."""
    hit = _GEO_CACHE.get(province)
    if hit is not None:
        return hit
    try:
        r = requests.get(_GEO_URL, timeout=_TIMEOUT, params={
            "name": province, "count": 1, "language": "tr", "country": "TR",
        })
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        coords = float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception:  # noqa: BLE001 - see module docstring
        return None
    _GEO_CACHE[province] = coords
    return coords


def forecast(province: str, today: date | None = None) -> str | None:
    """A Turkish phrase, or None when unavailable for any reason - outlook()'s
    figures, written out."""
    found = outlook(province, today)
    return found.phrase() if found is not None else None


def outlook(province: str, today: date | None = None) -> Outlook | None:
    """The coming week's figures, or None when unavailable for any reason.

    KEYED BY (province, day). An earlier version cached per province only, on the
    reasoning that "a forecast a few hours stale changes no advice" because the
    cache "lives only as long as the process" - but the process is a uvicorn
    container that runs for weeks. A fortnight-old "önümüzdeki hafta toplam 0.0 mm
    yağış bekleniyor" is wrong advice, not stale advice. Spec §5.4 asked for the
    date key; this restores it.

    The day is a parameter so the keying is testable without freezing the clock,
    matching how src/context/season.py takes its date.
    """
    day = today or date.today()
    hit = _FORECAST_CACHE.get((province, day))
    if hit is not None:
        return hit

    coords = _geocode(province)
    if coords is None:
        return None
    lat, lon = coords
    try:
        r = requests.get(_FC_URL, timeout=_TIMEOUT, params={
            "latitude": lat, "longitude": lon, "timezone": "Europe/Istanbul",
            "forecast_days": 7,
            "daily": "precipitation_sum,temperature_2m_min,temperature_2m_max",
        })
        r.raise_for_status()
        daily = (r.json() or {}).get("daily") or {}
        rain = [x for x in (daily.get("precipitation_sum") or []) if x is not None]
        tmin = [x for x in (daily.get("temperature_2m_min") or []) if x is not None]
        tmax = [x for x in (daily.get("temperature_2m_max") or []) if x is not None]
        if not (rain and tmin and tmax):
            return None
        found = Outlook(round(sum(rain), 1), round(min(tmin)), round(max(tmax)))
    except Exception:  # noqa: BLE001
        return None

    # Keep only today's entries, so the cache stays bounded by the 81 provinces
    # instead of growing by 81 every day the container stays up.
    for stale in [k for k in _FORECAST_CACHE if k[1] != day]:
        del _FORECAST_CACHE[stale]
    _FORECAST_CACHE[(province, day)] = found
    return found
