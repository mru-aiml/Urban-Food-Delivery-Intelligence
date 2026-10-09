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
freshness metadata. Failures return honest errors; nothing is fabricated.
"""
import json
import os
import time
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
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
            f"({s},{w},{n},{e});out body;")


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
    """Real HTTP fetch. Returns payload dict or raises with a clear error."""
    if area not in AREAS:
        raise ValueError(f"Unknown area {area!r}.")
    body = urllib.parse.urlencode(
        {"data": _overpass_query(AREAS[area]["bbox"])}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL, data=body,
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
    except Exception as e:
        raise ConnectionError(
            f"Overpass request failed ({type(e).__name__}: {e}).") from e
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
    except Exception as e:
        return {**base, "available": False, "area": area,
                "reason": f"Live fetch failed ({type(e).__name__}: {e}). "
                          "Historical analytics are unaffected."}, 502
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
