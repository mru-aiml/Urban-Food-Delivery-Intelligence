"""ETL cleaning with full metrics (DWM: Extract -> Transform -> Clean -> Load)."""
import numpy as np
import pandas as pd
from datetime import datetime
from preprocessing.loader import logical_map


def profile_raw(df):
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing_by_column": {c: int(df[c].isna().sum()) for c in df.columns},
        "missing_total": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "unique_counts": {c: int(df[c].nunique(dropna=True)) for c in df.columns},
    }


def clean(df_raw):
    """Clean dataset. Returns (df_clean, etl_metrics). Never fabricates data."""
    t0 = datetime.now()
    metrics = {"started_at": t0.isoformat()}
    df = df_raw.copy()
    metrics["rows_loaded"] = int(df.shape[0])

    # strip whitespace on object cols, normalise common null tokens
    for c in df.select_dtypes(include="object").columns:
        df[c] = df[c].astype(str).str.strip()
        df[c] = df[c].replace({"nan": np.nan, "NaN": np.nan, "null": np.nan,
                               "NULL": np.nan, "None": np.nan, "": np.nan, "NaT": np.nan})
    # duplicates
    dup = int(df.duplicated().sum())
    metrics["duplicates_removed"] = dup
    df = df.drop_duplicates().reset_index(drop=True)

    mp = logical_map(df)
    # coerce numerics
    for logical in ["age", "rating", "rest_lat", "rest_lon", "del_lat", "del_lon",
                    "multiple_deliveries", "delivery_time", "distance", "vehicle_condition"]:
        col = mp.get(logical)
        if col and col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # parse dates / times
    od = mp.get("order_date")
    if od:
        df["_order_date_parsed"] = pd.to_datetime(df[od], errors="coerce", dayfirst=True)
    else:
        df["_order_date_parsed"] = pd.NaT

    invalid = 0
    # invalid: delivery_time <=0 or >180, distance <=0 or >100, age out of range
    dt = mp.get("delivery_time")
    if dt:
        bad = ((df[dt] <= 0) | (df[dt] > 180)).sum()
        invalid += int(bad)
        df.loc[(df[dt] <= 0) | (df[dt] > 180), dt] = np.nan
    ds = mp.get("distance")
    if ds:
        bad = ((df[ds] <= 0) | (df[ds] > 100)).sum()
        invalid += int(bad)
        df.loc[(df[ds] <= 0) | (df[ds] > 100), ds] = np.nan
    metrics["invalid_values_flagged"] = int(invalid)

    # drop rows with no delivery time AND no distance (unusable fact)
    before = len(df)
    keep_cols = [c for c in [mp.get("delivery_time"), mp.get("distance")] if c]
    if keep_cols:
        df = df.dropna(subset=keep_cols, how="all").reset_index(drop=True)
    metrics["rows_dropped_unusable"] = int(before - len(df))

    metrics["missing_total_after_strip"] = int(df.isna().sum().sum())
    metrics["columns_transformed"] = len(df.columns)
    metrics["final_usable_records"] = int(len(df))
    metrics["finished_at"] = datetime.now().isoformat()
    metrics["duration_seconds"] = round((datetime.now() - t0).total_seconds(), 2)
    metrics["column_mapping"] = {k: v for k, v in mp.items()}
    return df, metrics
