"""Delivery intelligence: filtered metrics + chart breakdowns + performance summary."""
import pandas as pd
import numpy as np


def apply_filters(df, f):
    d = df.copy()
    m = {
        "city": "_city", "weather": "_weather", "traffic": "_traffic",
        "vehicle": "_vehicle", "order_type": "_order_type", "status": "_delay_band",
    }
    for k, col in m.items():
        v = (f or {}).get(k)
        if v and col in d.columns:
            if isinstance(v, list):
                d = d[d[col].isin(v)]
            elif str(v).lower() not in ("all", ""):
                d = d[d[col] == v]
    # date range
    try:
        if (f or {}).get("from") and "_order_date_parsed" in d.columns:
            d = d[pd.to_datetime(d["_order_date_parsed"], errors="coerce") >= pd.to_datetime(f["from"])]
        if (f or {}).get("to") and "_order_date_parsed" in d.columns:
            d = d[pd.to_datetime(d["_order_date_parsed"], errors="coerce") <= pd.to_datetime(f["to"])]
    except Exception:
        pass
    return d


def delivery_metrics(df):
    dt = "_dtime" if "_dtime" in df.columns else None
    ds = "_dist" if "_dist" in df.columns else None
    return {
        "count": int(len(df)),
        "avg_delivery_time": round(float(df[dt].mean()), 2) if dt and len(df) else None,
        "avg_distance": round(float(df[ds].mean()), 2) if ds and len(df) else None,
        "avg_speed": round(float(df["_speed_kmph"].replace([np.inf, -np.inf], np.nan).mean()), 2) if "_speed_kmph" in df.columns and len(df) else None,
        "delay_rate": round(float(df["_is_delayed"].mean() * 100), 2) if "_is_delayed" in df.columns and len(df) else None,
        "on_time_rate": round(float((1 - df["_is_delayed"].mean()) * 100), 2) if "_is_delayed" in df.columns and len(df) else None,
        "avg_rating": round(float(df["_rating"].mean()), 2) if "_rating" in df.columns and len(df) else None,
    }


def delivery_charts(df):
    dt = "_dtime" if "_dtime" in df.columns else None
    out = {}
    if dt and "_dist" in df.columns:
        s = df[["_dist", dt]].dropna().sample(min(800, len(df))) if len(df) > 800 else df[["_dist", dt]].dropna()
        out["time_vs_distance"] = [{"x": round(float(x), 2), "y": round(float(y), 2)} for x, y in zip(s["_dist"], s[dt])]
    else:
        out["time_vs_distance"] = []
    for key, col in [("time_by_traffic", "_traffic"), ("time_by_weather", "_weather"),
                     ("time_by_vehicle", "_vehicle"), ("time_by_city", "_city"),
                     ("time_by_hour", "_hour"), ("time_by_order_type", "_order_type")]:
        if dt and col in df.columns:
            g = df.dropna(subset=[col]).groupby(col)[dt].mean().sort_values()
            out[key] = [{"label": str(k), "value": round(float(v), 2)} for k, v in g.items()]
        else:
            out[key] = []
    return out


def performance_summary(df):
    dt = "_dtime" if "_dtime" in df.columns else None
    s = {}
    if not dt or not len(df):
        return s
    for label, col in [("traffic", "_traffic"), ("weather", "_weather"),
                       ("vehicle", "_vehicle"), ("city", "_city")]:
        if col in df.columns:
            g = df.dropna(subset=[col]).groupby(col)[dt].mean().sort_values()
            if len(g):
                s[f"best_{label}"] = {"label": str(g.index[0]), "avg": round(float(g.iloc[0]), 2)}
                s[f"worst_{label}"] = {"label": str(g.index[-1]), "avg": round(float(g.iloc[-1]), 2)}
    if "_hour" in df.columns:
        g = df.dropna(subset=["_hour"]).groupby("_hour")[dt].mean().sort_values(ascending=False)
        if len(g):
            s["peak_delay_hour"] = {"label": f"{int(g.index[0])}:00", "avg": round(float(g.iloc[0]), 2)}
    if "_dist" in df.columns:
        try:
            far = df.nlargest(5, "_dist")[[c for c in ["_oid", "_dist", dt, "_city", "_traffic"] if c in df.columns]]
            s["longest_deliveries"] = far.round(2).to_dict("records")
        except Exception:
            pass
    return s


def filter_options(df):
    opts = {}
    for key, col in [("cities", "_city"), ("weather", "_weather"), ("traffic", "_traffic"),
                     ("vehicles", "_vehicle"), ("order_types", "_order_type")]:
        opts[key] = sorted([str(x) for x in df[col].dropna().unique()]) if col in df.columns else []
    return opts
