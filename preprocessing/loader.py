"""Flexible dataset loader: inspects actual columns, never assumes names.

Local-first strategy (no huggingface_hub / datasets dependency):
  1. Use data/zomato_cleaned.csv (or any *.csv in data/) if present.
  2. Otherwise download ONCE via plain HTTPS (stdlib urllib) and cache it to
     data/zomato_cleaned.csv. All later runs reuse the local file.
"""
import os
import glob
import pandas as pd
import config


def resolve_column(df, logical):
    """Return actual physical column for a logical name, or None."""
    for cand in config.COLUMN_MAP.get(logical, []):
        if cand in df.columns:
            return cand
        # case-insensitive fallback
        for c in df.columns:
            if c.strip().lower() == cand.strip().lower():
                return c
    return None


def logical_map(df):
    """Map every logical name -> physical column (or None if unavailable)."""
    return {k: resolve_column(df, k) for k in config.COLUMN_MAP}


def _try_local():
    for p in config.LOCAL_CSV_CANDIDATES:
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            return p
    found = sorted(glob.glob(os.path.join(config.DATA_DIR, "*.csv")))
    for p in found:
        if os.path.getsize(p) > 1000:
            return p
    return None


def _candidate_urls():
    base = f"https://huggingface.co/datasets/{config.HF_DATASET}/resolve/main/"
    files = [config.HF_FILE, "zomato_cleaned.csv", "zomato.csv"]
    urls = [base + fn for fn in dict.fromkeys(files)]  # de-duplicated, order kept
    return urls


def _download_once(dest):
    """Download the CSV with stdlib urllib and cache it at dest. Returns path or None.

    Multiprocess-safe (gunicorn --workers N) and multithread-safe: every
    downloader uses its OWN uniquely-named temp file and publishes atomically
    via os.replace, so concurrent workers can never interleave chunks into
    each other's file or read a half-written dest. If a sibling worker already
    published (or is still publishing) a valid file, reuse / wait for it.
    """
    import time
    import urllib.request
    import uuid
    os.makedirs(config.DATA_DIR, exist_ok=True)
    # Re-check: a sibling worker may have finished while this one was starting.
    if _try_local() is not None:
        return _try_local()
    # Unique per process AND thread: threads share a pid, so pid alone is not enough.
    tmp = f"{dest}.part-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    for url in _candidate_urls():
        try:
            print(f"[loader] downloading {url}", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "urban-food-intelligence/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    fh.write(chunk)
            if os.path.getsize(tmp) > 1000:
                # sanity check: must look like a CSV with expected columns
                with open(tmp, "r", encoding="utf-8", errors="replace") as fh:
                    header = fh.readline()
                if "," in header and ("Time_taken" in header or "delivery" in header.lower()
                                      or "Weather" in header or "City" in header):
                    # Prefer a file a sibling worker already published.
                    existing = _try_local()
                    if existing is not None and os.path.getsize(existing) > 1000:
                        print(f"[loader] reusing dataset published by sibling worker -> {existing}", flush=True)
                        try:
                            os.remove(tmp)
                        except OSError:
                            pass
                        return existing
                    try:
                        os.replace(tmp, dest)
                        print(f"[loader] cached dataset -> {dest} ({os.path.getsize(dest)} bytes)", flush=True)
                        return dest
                    except OSError as oe:
                        # Lost the publish race (or dest locked): a sibling is
                        # publishing; stop downloading and wait for their file below.
                        print(f"[loader] publish deferred ({type(oe).__name__}: {oe}); waiting for sibling file", flush=True)
                        break
                print(f"[loader] rejected {url}: unexpected header: {header[:120]!r}", flush=True)
        except Exception as e:
            print(f"[loader] download failed for {url}: {type(e).__name__}: {e}", flush=True)
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
    # Wait for a sibling worker that is still downloading/publishing (cold
    # start with multiple workers): poll for up to ~90s before giving up.
    for _ in range(90):
        local = _try_local()
        if local is not None:
            print(f"[loader] using dataset published by sibling worker -> {local}", flush=True)
            return local
        time.sleep(1)
    return None


def load_raw():
    """Load raw CSV. Returns (df, meta). Downloads+caches once if missing."""
    local = _try_local()
    if local is None:
        dest = os.path.join(config.DATA_DIR, "zomato_cleaned.csv")
        got = _download_once(dest)
        if got and os.path.exists(got):
            local = got
    if local is None or not os.path.exists(local):
        raise FileNotFoundError(
            "Dataset CSV not found and auto-download failed. "
            "Place zomato_cleaned.csv in data/ (see data/README.md).")
    df = pd.read_csv(local, encoding="utf-8", engine="python", on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]
    meta = {"source_path": local, "rows": int(df.shape[0]), "cols": int(df.shape[1]),
            "columns": list(df.columns)}
    return df, meta
