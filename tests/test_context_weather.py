"""Weather lookup. The network is ALWAYS stubbed - a test that reaches Open-Meteo
would be slow, flaky, and would fail in CI."""

import src.context.weather as weather


def _stub(monkeypatch, geo=None, fc=None, boom=None, fc_boom=None):
    def fake_get(url, params=None, timeout=None):
        if boom:
            raise boom
        if fc_boom and "geocoding" not in url:
            raise fc_boom
        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self_inner): return geo if "geocoding" in url else fc
        return R()
    monkeypatch.setattr(weather.requests, "get", fake_get)
    weather.cache_clear()


GEO = {"results": [{"latitude": 38.6, "longitude": 27.4}]}
FC = {"daily": {"precipitation_sum": [0.0, 12.4, 0.0],
                "temperature_2m_min": [11.0, 10.2, 9.4],
                "temperature_2m_max": [30.1, 24.0, 26.5]}}


def test_returns_a_phrase_naming_rain_and_temperature(monkeypatch):
    _stub(monkeypatch, geo=GEO, fc=FC)
    out = weather.forecast("Manisa")
    assert out is not None
    assert "12" in out          # the rain figure reaches the phrase
    assert "30" in out or "9" in out


def test_network_failure_returns_none_and_does_not_raise(monkeypatch):
    _stub(monkeypatch, boom=TimeoutError("timed out"))
    assert weather.forecast("Manisa") is None


def test_forecast_request_failure_after_successful_geocode_returns_none(monkeypatch):
    _stub(monkeypatch, geo=GEO, fc_boom=TimeoutError("timed out"))
    assert weather.forecast("Manisa") is None


def test_malformed_forecast_payload_returns_none_and_does_not_raise(monkeypatch):
    _stub(monkeypatch, geo=GEO, fc={"daily": {
        "precipitation_sum": ["N/A"],
        "temperature_2m_min": ["N/A"],
        "temperature_2m_max": ["N/A"],
    }})
    assert weather.forecast("Manisa") is None


def test_unknown_province_returns_none(monkeypatch):
    _stub(monkeypatch, geo={"results": []}, fc=FC)
    assert weather.forecast("Atlantis") is None


def test_second_call_for_the_same_province_does_not_hit_the_network(monkeypatch):
    calls = {"n": 0}
    def counting_get(url, params=None, timeout=None):
        calls["n"] += 1
        class R:
            def raise_for_status(self): pass
            def json(self_inner): return GEO if "geocoding" in url else FC
        return R()
    monkeypatch.setattr(weather.requests, "get", counting_get)
    weather.cache_clear()
    weather.forecast("Manisa")
    first = calls["n"]
    weather.forecast("Manisa")
    assert calls["n"] == first


# --------------------------------------------------------------------------- #
# Only successes are cached
# --------------------------------------------------------------------------- #
def test_a_transient_failure_is_not_cached(monkeypatch):
    """One 2 s timeout must cost one lookup, not the feature.

    The old lru_cache memoised None, so a single blip - most likely on the first
    request in a cold container - disabled weather for that province until the
    process restarted, with no retry and no expiry.
    """
    calls = {"n": 0}

    def flaky_get(url, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] <= 1:                      # only the very first call fails
            raise TimeoutError("timed out")

        class R:
            def raise_for_status(self): pass
            def json(self_inner): return GEO if "geocoding" in url else FC
        return R()

    monkeypatch.setattr(weather.requests, "get", flaky_get)
    weather.cache_clear()

    assert weather.forecast("Manisa") is None    # the blip
    assert weather.forecast("Manisa") is not None  # recovers on the next answer


def test_an_unknown_province_is_retried_rather_than_remembered(monkeypatch):
    state = {"empty": True}

    def get(url, params=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self_inner):
                if "geocoding" in url:
                    return {"results": []} if state["empty"] else GEO
                return FC
        return R()

    monkeypatch.setattr(weather.requests, "get", get)
    weather.cache_clear()

    assert weather.forecast("Manisa") is None
    state["empty"] = False
    assert weather.forecast("Manisa") is not None


# --------------------------------------------------------------------------- #
# The cache is keyed by date
# --------------------------------------------------------------------------- #
def test_a_new_day_refetches(monkeypatch):
    """The container runs for weeks. A fortnight-old "önümüzdeki hafta" is wrong
    advice, not stale advice - spec §5.4 asks for the date key."""
    from datetime import date

    calls = {"n": 0}

    def counting_get(url, params=None, timeout=None):
        calls["n"] += 1

        class R:
            def raise_for_status(self): pass
            def json(self_inner): return GEO if "geocoding" in url else FC
        return R()

    monkeypatch.setattr(weather.requests, "get", counting_get)
    weather.cache_clear()

    weather.forecast("Manisa", date(2026, 8, 11))
    after_first = calls["n"]
    weather.forecast("Manisa", date(2026, 8, 11))
    assert calls["n"] == after_first              # same day: cached

    weather.forecast("Manisa", date(2026, 8, 12))
    assert calls["n"] > after_first               # next day: refetched


def test_yesterdays_entries_do_not_accumulate(monkeypatch):
    """Bounded by the 81 provinces, not by 81 x days-since-boot."""
    from datetime import date

    def get(url, params=None, timeout=None):
        class R:
            def raise_for_status(self): pass
            def json(self_inner): return GEO if "geocoding" in url else FC
        return R()

    monkeypatch.setattr(weather.requests, "get", get)
    weather.cache_clear()

    weather.forecast("Manisa", date(2026, 8, 11))
    weather.forecast("Aydın", date(2026, 8, 11))
    assert len(weather._FORECAST_CACHE) == 2

    weather.forecast("Manisa", date(2026, 8, 12))
    assert all(k[1] == date(2026, 8, 12) for k in weather._FORECAST_CACHE)
