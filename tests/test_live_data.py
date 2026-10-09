"""Tests for live-data fetching (mocked provider, no network).

Covers: success normalization, malformed responses, timeouts, provider
rate limits, request rate limiting, unknown areas. A real end-to-end fetch
is verified separately against the deployed Render service.
Run: pytest tests/test_live_data.py
"""
import io
import json
import urllib.error

import app as A
from integrations import live_data_provider as lp


def _reset():
    lp._cache.clear()
    lp._last_attempt.clear()
    lp._mirror_cooldown.clear()


_GOOD = {"elements": [
    {"type": "node", "id": 1, "lat": 12.97, "lon": 77.60,
     "tags": {"amenity": "restaurant", "name": "Koshy's", "cuisine": "indian"}},
    {"type": "node", "id": 2, "lat": 12.98, "lon": 77.61,
     "tags": {"amenity": "fast_food"}},
    {"type": "node", "id": 3, "tags": {"amenity": "restaurant", "name": "NoCoords"}},
]}


def _patch_http(monkeypatch, body=None, exc=None, status=200):
    def fake(req, timeout=None):
        if exc is not None:
            raise exc
        return status, body
    monkeypatch.setattr(lp, "_http_open", fake)


def test_fetch_success_normalizes(monkeypatch):
    _reset()
    _patch_http(monkeypatch, json.dumps(_GOOD).encode())
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 200 and out["available"] is True
    assert out["record_count"] == 2 and len(out["records"]) == 2
    r0 = out["records"][0]
    assert r0["name"] == "Koshy's" and r0["lat"] == 12.97
    assert "delivery" not in out["data_type"] or "not delivery" in out["data_type"]
    assert out["fetched_at"] and out["cached"] is False


def test_fetch_empty_elements_is_honest(monkeypatch):
    _reset()
    _patch_http(monkeypatch, json.dumps({"elements": []}).encode())
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 200 and out["records"] == [] and out["record_count"] == 0


def test_fetch_malformed_json(monkeypatch):
    _reset()
    _patch_http(monkeypatch, b"<html>not json</html>")
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 502 and out["available"] is False
    assert out.get("records") is None
    assert isinstance(out.get("attempts"), list) and len(out["attempts"]) == 2
    assert all("invalid_response" in a["outcome"] for a in out["attempts"])


def test_fetch_timeout(monkeypatch):
    _reset()
    monkeypatch.setattr(lp, "RETRY_BACKOFF_SECONDS", 0)
    _patch_http(monkeypatch, exc=TimeoutError("timed out"))
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 502 and out["available"] is False


def test_fetch_provider_rate_limit(monkeypatch):
    _reset()
    err = urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, io.BytesIO(b""))
    _patch_http(monkeypatch, exc=err)
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 429 and out["available"] is False
    assert out["retry_after_seconds"] == 60


def test_fetch_retry_after_header(monkeypatch):
    _reset()
    err = urllib.error.HTTPError("http://x", 429, "Too Many Requests",
                                 {"Retry-After": "120"}, io.BytesIO(b""))
    _patch_http(monkeypatch, exc=err)
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 429 and out["retry_after_seconds"] == 120


def test_retry_transient_500_then_success(monkeypatch):
    _reset()
    monkeypatch.setattr(lp, "RETRY_BACKOFF_SECONDS", 0)
    calls = []
    err = urllib.error.HTTPError("http://x", 500, "Internal Error", {}, io.BytesIO(b"e"))

    def fake(req, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise err
        return 200, json.dumps(_GOOD).encode()

    monkeypatch.setattr(lp, "_http_open", fake)
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 200 and out["available"] is True and len(calls) == 2
    assert out["record_count"] == 2


def test_no_retry_on_invalid_response(monkeypatch):
    _reset()
    calls = []

    def fake(req, timeout=None):
        calls.append(1)
        return 200, b"<html>not json</html>"

    monkeypatch.setattr(lp, "_http_open", fake)
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
    assert status == 502
    assert len(calls) == len(lp.OVERPASS_URLS)  # once per mirror, no retries


def test_mirror_cooldown_skips_failing_mirrors(monkeypatch):
    _reset()
    calls = []

    def fake(req, timeout=None):
        calls.append(1)
        return 200, json.dumps(_GOOD).encode()

    monkeypatch.setattr(lp, "_http_open", fake)
    import time as _time
    for url in lp.OVERPASS_URLS:
        lp._mirror_cooldown[url] = _time.time()
    out, status = lp.fetch_live("bengaluru-mg-road", _now=1100.0)
    assert status == 502 and len(calls) == 0
    assert "cooling down" in out["reason"]
    assert all("cooling down" in a["outcome"] for a in out["attempts"])


def test_request_rate_limit(monkeypatch):
    _reset()
    calls = []

    def fake(req, timeout=None):
        calls.append(1)
        return 200, json.dumps(_GOOD).encode()

    monkeypatch.setattr(lp, "_http_open", fake)
    try:
        out1, s1 = lp.fetch_live("bengaluru-mg-road", _now=1000.0)
        assert s1 == 200 and len(calls) == 1
        out2, s2 = lp.fetch_live("bengaluru-mg-road", _now=1001.0)
        # fresh cache (TTL 15 min) is served without a new upstream call
        assert s2 == 200 and out2["cached"] is True and len(calls) == 1
        lp._cache.clear()
        out3, s3 = lp.fetch_live("bengaluru-mg-road", _now=1002.0)
        assert s3 == 429 and out3["retry_after_seconds"] > 0 and len(calls) == 1
    finally:
        _reset()


def test_ipv4_connection_uses_hostname_for_tls():
    import http.client
    assert issubclass(lp._IPv4HTTPSConnection, http.client.HTTPSConnection)


def test_unknown_area_rejected():
    _reset()
    out, status = lp.fetch_live("antarctica", _now=1000.0)
    assert status == 400 and out["available"] is False


def test_post_unknown_area_is_400():
    _reset()
    c = A.app.test_client()
    r = c.post("/api/live-fetch", json={"area": "antarctica"})
    assert r.status_code == 400


def test_post_success_end_to_end_mocked(monkeypatch):
    _reset()
    _patch_http(monkeypatch, json.dumps(_GOOD).encode())
    c = A.app.test_client()
    r = c.post("/api/live-fetch", json={"area": "mumbai-andheri-west"})
    assert r.status_code == 200
    j = json.loads(r.get_data(as_text=True))
    assert j["available"] is True and j["record_count"] == 2
    assert j["area"] == "mumbai-andheri-west" and j["fetched_at"]
