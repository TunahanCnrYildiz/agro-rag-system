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
    weather.forecast.cache_clear()
    weather._geocode.cache_clear()


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
    weather.forecast.cache_clear()
    weather._geocode.cache_clear()
    weather.forecast("Manisa")
    first = calls["n"]
    weather.forecast("Manisa")
    assert calls["n"] == first
