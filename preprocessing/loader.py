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
    """Download the CSV with stdlib urllib and cache it at dest. Returns path or None."""
    import urllib.request
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = dest + ".part"
    for url in _candidate_urls():
        try:
            print(f"[loader] downloading {url}")
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
                    os.replace(tmp, dest)
                    print(f"[loader] cached dataset -> {dest}")
                    return dest
                print(f"[loader] rejected {url}: unexpected header: {header[:120]!r}")
        except Exception as e:
            print(f"[loader] download failed for {url}: {e}")
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
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
