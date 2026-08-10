"""Coming-week weather for a province, as a short phrase for the prompt.

Three figures are agronomically useful and the rest is noise: rain in the next
few days (fertiliser applied before heavy rain washes off), the low (frost), and
the high.

Open-Meteo needs no key for non-commercial use. IT DOES REQUIRE ONE FOR
COMMERCIAL USE, and this is a commercial product - budget a key before go-live.

Never raises. A weather lookup that can break an answer is worse than no weather.
"""
from __future__ import annotations

from functools import lru_cache

import requests

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FC_URL = "https://api.open-meteo.com/v1/forecast"

# Short: this sits in the request path. Exceeding it costs the weather sentence,
# not the answer.
_TIMEOUT = 2.0


@lru_cache(maxsize=128)
def _geocode(province: str) -> tuple[float, float] | None:
    """Province name -> coordinates. Cached for the process lifetime; the 81
    provinces do not move, so one lookup each is the whole cost."""
    try:
        r = requests.get(_GEO_URL, timeout=_TIMEOUT, params={
            "name": province, "count": 1, "language": "tr", "country": "TR",
        })
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        return float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception:  # noqa: BLE001 - see module docstring
        return None


@lru_cache(maxsize=128)
def forecast(province: str) -> str | None:
    """A Turkish phrase, or None when unavailable for any reason.

    Cached per province. The cache is deliberately NOT keyed by date: it lives
    only as long as the process, and a forecast that is a few hours stale changes
    no fertilisation advice.
    """
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
        total_rain = round(sum(rain), 1)
        return (f"önümüzdeki hafta toplam {total_rain} mm yağış bekleniyor, "
                f"sıcaklık {round(min(tmin))}-{round(max(tmax))} °C aralığında")
    except Exception:  # noqa: BLE001
        return None
