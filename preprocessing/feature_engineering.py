"""Feature engineering: derived DWM attributes (hour, speed, delay flags, SLA bands)."""
import numpy as np
import pandas as pd
import config
from preprocessing.loader import logical_map


def _parse_hour(val):
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    # handles "21:55", "22:10", also float-like "0.458333333" (fraction of day — treat as unavailable)
    try:
        if ":" in s:
            h = int(s.split(":")[0])
            if 0 <= h <= 23:
                return h
        f = float(s)
        if 0 <= f < 1:  # fraction of day
            return int(f * 24)
        if 0 <= f <= 23:
            return int(f)
    except Exception:
        return np.nan
    return np.nan


def engineer(df_clean):
    mp = logical_map(df_clean)
    df = df_clean.copy()

    def col(logical):
        c = mp.get(logical)
        return c if (c and c in df.columns) else None

    c_time = col("time_ordered")
    c_date = "_order_date_parsed" if "_order_date_parsed" in df.columns else col("order_date")
    c_dt = col("delivery_time")
    c_ds = col("distance")

    df["_hour"] = df[c_time].apply(_parse_hour) if c_time else np.nan
    if c_date and c_date in df.columns:
        d = pd.to_datetime(df[c_date], errors="coerce")
        df["_year"] = d.dt.year
        df["_month"] = d.dt.month
        df["_day"] = d.dt.day
        df["_weekday"] = d.dt.day_name()
        df["_is_weekend"] = d.dt.weekday.ge(5).astype(int)
    else:
        for k in ["_year", "_month", "_day", "_weekday", "_is_weekend"]:
            df[k] = np.nan
    df["_is_peak"] = df["_hour"].apply(lambda h: 1 if pd.notna(h) and h in [12, 13, 19, 20, 21] else 0)

    # speed km/h
    if c_dt and c_ds:
        df["_speed_kmph"] = df[c_ds] / (df[c_dt] / 60.0)
        df["_speed_kmph"] = df["_speed_kmph"].replace([np.inf, -np.inf], np.nan)
    else:
        df["_speed_kmph"] = np.nan

    # delay flag (project threshold)
    thr = config.DELAY_THRESHOLD_MINUTES
    if c_dt:
        df["_is_delayed"] = (df[c_dt] > thr).astype(int)
    else:
        df["_is_delayed"] = 0
    # delay severity
    def sev(t):
        if pd.isna(t):
            return "unknown"
        if t <= 25:
            return "on-time"
        if t <= thr:
            return "at-risk"
        if t <= 45:
            return "delayed"
        return "severely-delayed"
    df["_delay_band"] = df[c_dt].apply(sev) if c_dt else "unknown"

    # canonical renamed helpers (for analytics code readability)
    rename = {}
    for logical, canon in [("weather", "_weather"), ("traffic", "_traffic"),
                           ("vehicle", "_vehicle"), ("order_type", "_order_type"),
                           ("city", "_city"), ("festival", "_festival"),
                           ("multiple_deliveries", "_multi"),
                           ("delivery_time", "_dtime"), ("distance", "_dist"),
                           ("rating", "_rating"), ("order_id", "_oid")]:
        c = col(logical)
        if c:
            rename[c] = canon
    # avoid collision: only rename if canon not already a col
    rename = {k: v for k, v in rename.items() if v not in df.columns}
    df = df.rename(columns=rename)
    mp2 = logical_map(df_clean)
    return df, {"threshold": thr, "mapping": mp2,
                "features": ["_hour", "_year", "_month", "_day", "_weekday",
                             "_speed_kmph", "_is_delayed", "_delay_band", "_is_peak"]}
