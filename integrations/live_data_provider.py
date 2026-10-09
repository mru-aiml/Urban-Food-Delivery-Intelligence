"""Live external-data provider adapter.

Verified status (Oct 2026):
- Zomato's developer platform is a partner-only POS Integration API
  (registered restaurants/vendors, credentials, webhooks for their own
  orders). There is NO public or otherwise authorized API available to this
  project for pulling live delivery/order records, and no such credentials
  exist here. Live DELIVERY data therefore cannot be fetched.
- What CAN be fetched without credentials: current restaurant listings from
  OpenStreetMap via the public Overpass API (usage policy respected:
  small bounded queries, explicit fetch only, server-side rate limit,
  response cache). This is live RESTAURANT data, never delivery events,
  and is always labelled as such.

Rules enforced here: secrets only from env (Overpass needs none), hard
timeouts, bounded response sizes, fixed area allowlist (no arbitrary
queries), validation of every field, per-area rate limiting + cache with
freshness metadata. Per-mirror attempts are logged server-side with HTTP
status and a short sanitized body snippet; transient failures (timeouts,
resets, HTTP 5xx) get one bounded retry with backoff, while HTTP 429,
refusals and invalid data never retry, and a failing mirror cools down
before it is tried again. Failures return honest errors; nothing is fabricated.
"""
import json
import os
import time
import http.client
import socket
import urllib.parse
import urllib.request

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "UrbanFoodDeliveryIntelligence/1.0 (educational DWM project)"
REQUEST_TIMEOUT_SECONDS = 25
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_RECORDS = 200
# Small fixed boxes (south, west, north, east). No arbitrary bboxes accepted.
AREAS = {
    "bengaluru-mg-road": {"label": "Bengaluru MG Road",
                          "bbox": (12.965, 77.595, 12.985, 77.615)},
    "mumbai-andheri-west": {"label": "Mumbai Andheri West",
                            "bbox": (19.110, 72.820, 19.135, 72.845)},
    "delhi-connaught-place": {"label": "Delhi Connaught Place",
                              "bbox": (28.625, 77.205, 28.645, 77.230)},
}
CACHE_TTL_SECONDS = 15 * 60
MIN_UPSTREAM_INTERVAL_SECONDS = 45
RETRY_BACKOFF_SECONDS = 2
MAX_ATTEMPTS_PER_MIRROR = 2  # 1 initial try + 1 retry (transient failures only)
MIRROR_COOLDOWN_SECONDS = 180  # skip a mirror that failed recently
_mirror_cooldown = {}  # url -> epoch of last failure


class ProviderRateLimited(Exception):
    """All mirrors answered HTTP 429: slow down, do not retry immediately."""

    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after


class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    """HTTPS that connects over IPv4 even when DNS prefers IPv6.

    Some containers resolve AAAA first but have no IPv6 route (ENETUNREACH);
    urllib tries only the first address. This resolves AF_INET explicitly
    while keeping SNI/certificate verification on the real hostname.
    """

    def connect(self):
        if getattr(self, "_tunnel_host", None):
            return super().connect()
        try:
            addrs = socket.getaddrinfo(self.host, self.port,
                                       socket.AF_INET, socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise OSError(f"No IPv4 address for {self.host}: {e}") from e
        if not addrs:
            raise OSError(f"No IPv4 address for {self.host}")
        err = None
        for _fam, _typ, _proto, _canon, sockaddr in addrs:
            try:
                self.sock = socket.create_connection(
                    sockaddr, timeout=self.timeout,
                    source_address=getattr(self, "source_address", None))
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                err = None
                break
            except OSError as e:
                err = e
        if err is not None:
            raise err
        server_hostname = getattr(self, "server_hostname", None) or self.host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_IPv4HTTPSConnection, req)


_opener = urllib.request.build_opener(_IPv4HTTPSHandler)


def _http_open(req, timeout):
    """Single indirection for HTTP(S) fetches (patchable in tests)."""
    with _opener.open(req, timeout=timeout) as resp:
        return resp.status, resp.read(MAX_RESPONSE_BYTES + 1)

PROVIDERS = {}
_cache = {}       # area -> {"payload": ..., "at": epoch}
_last_attempt = {}  # area -> epoch of last upstream attempt


def register(name):
    def deco(fn):
        PROVIDERS[name] = fn
        return fn
    return deco


def _env(name, default=""):
    try:
        return (os.environ.get(name, default) or default).strip()
    except Exception:
        return default


def _overpass_query(bbox):
    s, w, n, e = bbox
    return ('[out:json][timeout:25];'
            'node["amenity"~"^(restaurant|fast_food)$"]'
            f"({s},{w},{n},{e});out body {MAX_RECORDS};")


def _normalize(elements):
    records = []
    for el in elements:
        try:
            if not isinstance(el, dict) or el.get("type") != "node":
                continue
            lat, lon = float(el["lat"]), float(el["lon"])
            tags = el.get("tags") or {}
            if not isinstance(tags, dict):
                tags = {}
            addr = tags.get("addr:full") or " ".join(
                str(tags.get(k, "")).strip() for k in
                ("addr:housenumber", "addr:street", "addr:suburb",
                 "addr:city", "addr:postcode") if tags.get(k))
            records.append({
                "id": f"node/{el.get('id')}",
                "name": str(tags.get("name") or "Unnamed"),
                "category": str(tags.get("amenity") or ""),
                "cuisine": str(tags.get("cuisine") or ""),
                "opening_hours": str(tags.get("opening_hours") or ""),
                "address": addr.strip(),
                "lat": lat, "lon": lon,
            })
            if len(records) >= MAX_RECORDS:
                break
        except Exception:
            continue
    return records


@register("osm_overpass")
def _fetch_overpass(_cfg, area):
    """Real HTTP fetch, trying public mirrors in order. Raises with reasons."""
    now = time.time()
    if area not in AREAS:
        raise ValueError(f"Unknown area {area!r}.")
    body = urllib.parse.urlencode(
        {"data": _overpass_query(AREAS[area]["bbox"])}).encode("utf-8")
    attempts = []
    rate_limited = []
    for url in OVERPASS_URLS:
        host = urllib.parse.urlparse(url).hostname or url
        if now - _mirror_cooldown.get(url, 0) < MIRROR_COOLDOWN_SECONDS:
            attempts.append({"mirror": host, "outcome": "skipped: cooling down"})
            continue
        outcome, failed_at = None, now
        for attempt in range(1, MAX_ATTEMPTS_PER_MIRROR + 1):
            req = urllib.request.Request(
                url, data=body,
                headers={"User-Agent": USER_AGENT,
                         "Content-Type": "application/x-www-form-urlencoded"})
            try:
                status, raw = _http_open(req, REQUEST_TIMEOUT_SECONDS)
            except urllib.error.HTTPError as e:
                snippet = ""
                try:
                    snippet = _snippet(e.read(2048))
                except Exception:
                    pass
                if e.code == 429:
                    rate_limited.append(_parse_retry_after(
                        getattr(e, "headers", None)) or 60)
                    outcome = "http_429 rate-limited (no retry)"
                    _log_attempt(host, attempt, status=429, err="HTTPError 429",
                                 snippet=snippet)
                    break
                if 500 <= e.code < 600 and attempt < MAX_ATTEMPTS_PER_MIRROR:
                    _log_attempt(host, attempt, status=e.code,
                                 err=f"HTTPError {e.code}, retrying",
                                 snippet=snippet)
                    time.sleep(RETRY_BACKOFF_SECONDS)
                    continue
                outcome = f"http_{e.code}"
                _log_attempt(host, attempt, status=e.code,
                             err=f"HTTPError {e.code}", snippet=snippet)
                break
            except Exception as e:
                outcome = f"{type(e).__name__}: {str(e)[:100]}"
                _log_attempt(host, attempt, err=f"{type(e).__name__}: {e}")
                if _is_transient(e) and attempt < MAX_ATTEMPTS_PER_MIRROR:
                    time.sleep(RETRY_BACKOFF_SECONDS)
                    outcome = None
                    continue
                break
            _log_attempt(host, attempt, status=status, nbytes=len(raw))
            if status == 429:
                rate_limited.append(60)
                outcome = "http_429 rate-limited (no retry)"
                break
            if status != 200:
                outcome = f"http_{status}"
                break
            try:
                payload = _parse_overpass(raw, url, area)
            except Exception as e:
                outcome = f"invalid_response: {type(e).__name__}"
                _log_attempt(host, attempt, status=status,
                             err=f"{type(e).__name__}: {e}")
                break
            _mirror_cooldown.pop(url, None)
            return payload
        attempts.append({"mirror": host, "outcome": outcome or "failed"})
        _mirror_cooldown[url] = failed_at
    tried = [a for a in attempts if "cooling down" not in (a.get("outcome") or "")]
    if rate_limited and tried and all(
            (a.get("outcome") or "").startswith("http_429") for a in tried):
        err = ProviderRateLimited(
            "Overpass rate limit reached on all mirrors. Please retry shortly.",
            max(rate_limited))
        err._attempts = attempts
        raise err
    if not tried:
        err = ConnectionError("All Overpass mirrors are cooling down after recent "
                              "failures. Please retry shortly.")
        err._attempts = attempts
        raise err
    err = ConnectionError("All Overpass mirrors failed ("
                          + " | ".join(f"{a['mirror']}: {a['outcome']}" for a in tried)
                          + ").")
    err._attempts = attempts
    raise err


def _is_transient(exc):
    """Retry only transient network failures (never 429/refusals/bad data)."""
    import http.client as _hc
    return isinstance(exc, (TimeoutError, socket.timeout,
                            ConnectionResetError, BrokenPipeError,
                            _hc.RemoteDisconnected, _hc.IncompleteRead))


def _parse_retry_after(headers):
    try:
        if headers is None or not hasattr(headers, "get"):
            return None
        for key in ("Retry-After", "retry-after"):
            v = headers.get(key)
            if v is not None:
                return int(str(v).strip().split(",")[0])
    except Exception:
        pass
    return None


def _snippet(raw):
    try:
        txt = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    except Exception:
        return ""
    return "".join(ch if 32 <= ord(ch) < 127 else " " for ch in txt[:200]).strip()[:200]


def _log_attempt(host, attempt, status=None, nbytes=None, err=None, snippet=None):
    if err is None:
        print(f"[LIVE] {host} attempt {attempt} -> HTTP {status} ({nbytes} B)", flush=True)
    elif snippet:
        print(f"[LIVE] {host} attempt {attempt} FAILED {err} | body: {snippet}", flush=True)
    else:
        print(f"[LIVE] {host} attempt {attempt} FAILED {err}", flush=True)


def _parse_overpass(raw, url, area):
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Overpass response exceeded size limit.")
    try:
        doc = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        raise ValueError(f"Overpass returned invalid JSON ({e}).") from e
    if not isinstance(doc, dict) or not isinstance(doc.get("elements"), list):
        raise ValueError("Overpass returned an unexpected response shape.")
    records = _normalize(doc["elements"])
    now = time.time()
    return {"provider": "osm_overpass",
            "data_type": "live restaurant listings (OpenStreetMap) — not delivery orders",
            "source": "OpenStreetMap Overpass API",
            "mirror": url,
            "area": area, "area_label": AREAS[area]["label"],
            "records": records, "record_count": len(records),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))}


@register("none")
def _no_provider(_cfg, _area=None):
    return {"available": False,
            "reason": "No live-data provider is configured (LIVE_DATA_PROVIDER=none). "
                      "Zomato's POS Integration API is partner-only; this deployment has no "
                      "partner credentials, so live delivery records cannot be fetched. "
                      "The dashboard uses the historical dataset."}


def fetch_live(area=None, _now=None):
    """Fetch live records for an area. Never fabricates data.

    Returns (payload_dict, http_status). Cached fresh results are returned
    without hitting the provider; attempts inside the rate-limit window get
    HTTP 429; provider failures get HTTP 502 with the reason.
    """
    now = _now if _now is not None else time.time()
    name = (_env("LIVE_DATA_PROVIDER", "osm_overpass") or "osm_overpass").lower()
    area = area or "bengaluru-mg-road"
    base = {"provider": name,
            "historical_source": "allenborochin/zomato_delivery_EDA :: zomato_cleaned.csv"}
    fn = PROVIDERS.get(name)
    if fn is None:
        return {**base, "available": False,
                "reason": f"Unknown provider {name!r}."}, 400
    if name == "none":
        out = dict(base)
        out.update(_no_provider({}))
        return out, 200
    if area not in AREAS:
        return {**base, "available": False,
                "reason": f"Unknown area {area!r}. Valid areas: {sorted(AREAS)}."}, 400
    hit = _cache.get(area)
    if hit is not None and now - hit["at"] < CACHE_TTL_SECONDS:
        out = dict(base)
        out.update(hit["payload"])
        out["available"] = True
        out["cached"] = True
        return out, 200
    last = _last_attempt.get(area, 0)
    if now - last < MIN_UPSTREAM_INTERVAL_SECONDS:
        return {**base, "available": False, "area": area,
                "reason": "Rate limit: a fetch was already attempted recently.",
                "retry_after_seconds": int(MIN_UPSTREAM_INTERVAL_SECONDS - (now - last))}, 429
    _last_attempt[area] = now
    try:
        payload = fn({}, area)
    except ProviderRateLimited as e:
        return {**base, "available": False, "area": area,
                "reason": f"Provider rate limit: {e} Historical analytics are unaffected.",
                "retry_after_seconds": int(e.retry_after or 60),
                "attempts": list(getattr(e, "_attempts", []))}, 429
    except Exception as e:
        return {**base, "available": False, "area": area,
                "reason": f"Live fetch failed ({type(e).__name__}: {e}). "
                          "Historical analytics are unaffected.",
                "attempts": list(getattr(e, "_attempts", []))}, 502
    _cache[area] = {"payload": payload, "at": now}
    out = dict(base)
    out.update(payload)
    out["available"] = True
    out["cached"] = False
    return out, 200


def provider_status(df=None):
    """Honest live-data status. Never raises, never fakes data."""
    name = (_env("LIVE_DATA_PROVIDER", "osm_overpass") or "osm_overpass").lower()
    base = {"provider": name,
            "available": False,
            "mode": "historical",
            "fetch_endpoint": "POST /api/live-fetch",
            "areas": [{"id": k, "label": v["label"]} for k, v in AREAS.items()],
            "historical_source": "allenborochin/zomato_delivery_EDA :: zomato_cleaned.csv",
            "historical_rows": int(len(df)) if df is not None else 0,
            "live_records": 0,
            "last_refresh": None}
    if name == "none":
        base.update(_no_provider({}))
        return base
    if name not in PROVIDERS:
        base["reason"] = f"Unknown provider {name!r}."
        return base
    fresh = [(a, c) for a, c in _cache.items()
             if time.time() - c["at"] < CACHE_TTL_SECONDS]
    if fresh:
        area, hit = fresh[0]
        out = dict(base)
        out.update({"available": True,
                    "mode": "historical+live",
                    "data_type": hit["payload"].get("data_type"),
                    "area": area,
                    "live_records": hit["payload"].get("record_count", 0),
                    "last_refresh": hit["payload"].get("fetched_at")})
        return out
    base["reason"] = ("Live restaurant listings are available on demand via "
                      "POST /api/live-fetch (OpenStreetMap Overpass API; no "
                      "credentials needed). Nothing has been fetched yet — "
                      "historical analytics remain the default source.")
    return base
