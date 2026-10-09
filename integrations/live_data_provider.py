"""Live external-data provider adapter.

Truthful status of this project (verified Oct 2026):
- Zomato's current developer platform is a partner-only POS Integration API
  (registered restaurants/vendors, credentials, webhooks for their own orders).
- There is NO public or otherwise authorized API available to this project
  for pulling live delivery/order records, and no credentials are configured.
- Therefore this project runs in HISTORICAL mode on data/zomato_cleaned.csv.

This module provides the adapter skeleton so a future authorized provider can
be plugged in without touching the historical loader:
- providers register via PROVIDERS and are selected with LIVE_DATA_PROVIDER,
- secrets come only from environment variables (never source code),
- fetches use timeouts, honor a refresh interval (rate-limit friendly),
  cache the last good payload, and always report source/freshness metadata,
- nothing here invents live orders, GPS positions, times, or customers.
"""
import os
import time

PROVIDERS = {}
_cache = {"payload": None, "at": 0.0, "provider": None}


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


@register("none")
def _no_provider(_cfg):
    return {"available": False,
            "reason": "No live-data provider is configured. Zomato's POS "
                      "Integration API is partner-only; this deployment has no "
                      "partner credentials, so live delivery records cannot be "
                      "fetched. The dashboard uses the historical dataset."}


def provider_status(df=None):
    """Return honest live-data status. Never raises, never fakes data."""
    name = (_env("LIVE_DATA_PROVIDER", "none") or "none").lower()
    interval = 300
    try:
        interval = max(60, int(_env("LIVE_REFRESH_SECONDS", "300")))
    except Exception:
        pass
    base = {"provider": name,
            "available": False,
            "mode": "historical",
            "historical_source": "allenborochin/zomato_delivery_EDA :: zomato_cleaned.csv",
            "historical_rows": int(len(df)) if df is not None else 0,
            "live_records": 0,
            "last_refresh": None,
            "refresh_interval_seconds": interval}
    fn = PROVIDERS.get(name)
    if fn is None:
        base["reason"] = f"Unknown provider {name!r}. Set LIVE_DATA_PROVIDER to a registered provider or 'none'."
        return base
    if name == "none":
        base.update(_no_provider({}))
        return base
    # Configured provider: reuse cache inside the refresh interval, else fetch
    # with a hard timeout so a provider failure can never break analytics.
    now = time.time()
    if _cache["payload"] is not None and _cache["provider"] == name and now - _cache["at"] < interval:
        out = dict(base)
        out.update(_cache["payload"])
        return out
    cfg = {"api_key_present": bool(_env("LIVE_API_KEY")),
           "base_url": _env("LIVE_API_BASE_URL"),
           "timeout_seconds": 15}
    if not cfg["api_key_present"] or not cfg["base_url"]:
        base["reason"] = (f"Provider {name!r} is selected but LIVE_API_KEY or "
                          "LIVE_API_BASE_URL is not set. Live feed unavailable.")
        return base
    try:
        payload = fn(cfg) or {}
        if not isinstance(payload, dict) or "records" not in payload:
            raise ValueError("provider returned an unexpected payload")
        _cache.update({"payload": payload, "at": now, "provider": name})
        out = dict(base)
        out.update(payload)
        out["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
        return out
    except Exception as e:
        base["reason"] = f"Live provider {name!r} failed ({type(e).__name__}: {e}). Showing historical data."
        if _cache["payload"] is not None and _cache["provider"] == name:
            out = dict(base)
            out.update(_cache["payload"])
            out["stale_cache"] = True
            return out
        return base
