"""Overview / executive dashboard calculations — all from real data."""
import pandas as pd
import numpy as np


def _pick(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def overview_stats(df):
    dt = _pick(df, "_dtime", "Time_taken (min)")
    ds = _pick(df, "_dist", "distance_km")
    rt = _pick(df, "_rating", "Delivery_person_Ratings")
    out = {}
    out["total_orders"] = int(len(df))
    out["total_records"] = int(len(df))
    out["avg_delivery_time"] = round(float(df[dt].mean()), 2) if dt else None
    out["median_delivery_time"] = round(float(df[dt].median()), 2) if dt else None
    out["avg_distance"] = round(float(df[ds].mean()), 2) if ds else None
    out["avg_rating"] = round(float(df[rt].mean()), 2) if rt else None
    if "_is_delayed" in df.columns:
        out["delayed_orders"] = int(df["_is_delayed"].sum())
        out["on_time_pct"] = round(float((1 - df["_is_delayed"].mean()) * 100), 2)
        out["delay_pct"] = round(float(df["_is_delayed"].mean() * 100), 2)
    else:
        out["delayed_orders"] = None
        out["on_time_pct"] = None
        out["delay_pct"] = None
    if "_speed_kmph" in df.columns:
        s = df["_speed_kmph"].replace([np.inf, -np.inf], np.nan).dropna()
        out["avg_speed"] = round(float(s.mean()), 2) if len(s) else None
    else:
        out["avg_speed"] = None
    return out


def _group_avg(df, dim, metric):
    if dim not in df.columns or metric not in df.columns:
        return []
    g = df.dropna(subset=[dim]).groupby(dim)[metric].agg(["mean", "count"]).reset_index()
    g.columns = ["label", "value", "count"]
    g["value"] = g["value"].round(2)
    return g.sort_values("value").to_dict("records")


def overview_charts(df, max_points=60):
    dt = _pick(df, "_dtime", "Time_taken (min)")
    out = {}
    # orders over time
    if "_order_date_parsed" in df.columns:
        d = pd.to_datetime(df["_order_date_parsed"], errors="coerce")
        s = d.dt.date.value_counts().sort_index()
        if len(s) > max_points:
            s = s.iloc[-max_points:]
        out["orders_over_time"] = [{"label": str(k), "value": int(v)} for k, v in s.items()]
    else:
        out["orders_over_time"] = []
    # avg delivery time by hour
    if "_hour" in df.columns and dt:
        g = df.dropna(subset=["_hour"]).groupby("_hour")[dt].mean().sort_index()
        out["time_by_hour"] = [{"label": f"{int(k)}:00", "value": round(float(v), 2)} for k, v in g.items()]
    else:
        out["time_by_hour"] = []
    # distribution histogram
    if dt:
        h, edges = np.histogram(df[dt].dropna(), bins=20)
        out["time_distribution"] = [{"label": f"{edges[i]:.0f}-{edges[i+1]:.0f}", "value": int(h[i])} for i in range(len(h))]
    else:
        out["time_distribution"] = []
    for key, col in [("by_weather", "_weather"), ("by_traffic", "_traffic"),
                     ("by_vehicle", "_vehicle"), ("by_city", "_city")]:
        if col in df.columns:
            s = df[col].fillna("Unknown").value_counts().head(12)
            out[key] = [{"label": str(k), "value": int(v)} for k, v in s.items()]
        else:
            out[key] = []
    # delay pct by traffic/weather
    if "_is_delayed" in df.columns:
        for key, col in [("delay_by_traffic", "_traffic"), ("delay_by_weather", "_weather"),
                         ("delay_by_vehicle", "_vehicle"), ("delay_by_city", "_city")]:
            if col in df.columns:
                g = df.groupby(col)["_is_delayed"].mean().sort_values(ascending=False).head(12)
                out[key] = [{"label": str(k), "value": round(float(v) * 100, 2)} for k, v in g.items()]
    if dt:
        for key, col in [("avg_time_by_traffic", "_traffic"), ("avg_time_by_weather", "_weather"),
                         ("avg_time_by_vehicle", "_vehicle"), ("avg_time_by_city", "_city")]:
            if col in df.columns:
                out[key] = _group_avg(df, col, dt)
    return out


def live_insights(df):
    """Generate 3-5 dynamic insights from actual data."""
    ins = []
    dt = _pick(df, "_dtime", "Time_taken (min)")
    if dt and "_hour" in df.columns:
        g = df.dropna(subset=["_hour"]).groupby("_hour")[dt].mean()
        if len(g):
            pk = int(g.idxmax())
            ins.append({"title": "Peak delivery pressure",
                        "text": f"Highest average delivery time occurs around {pk}:00 ({g.max():.1f} min avg). Consider extra capacity in this window.",
                        "severity": "warning"})
    if dt and "_traffic" in df.columns:
        g = df.dropna(subset=["_traffic"]).groupby("_traffic")[dt].mean().sort_values()
        if len(g) >= 2:
            ins.append({"title": "Traffic impact",
                        "text": f"'{g.index[-1]}' traffic averages {g.iloc[-1]:.1f} min vs '{g.index[0]}' at {g.iloc[0]:.1f} min — traffic level is strongly associated with slower deliveries.",
                        "severity": "info"})
    if dt and "_dist" in df.columns:
        c = df[["_dist", dt]].dropna().corr().iloc[0, 1] if len(df) > 10 else float("nan")
        if pd.notna(c):
            ins.append({"title": "Distance effect",
                        "text": f"Distance–delivery-time correlation is {c:.2f}. Long-distance orders show {'much ' if c > 0.4 else ''}higher delay probability.",
                        "severity": "info" if c < 0.5 else "warning"})
    if "_is_delayed" in df.columns and "_weather" in df.columns:
        g = df.groupby("_weather")["_is_delayed"].mean().sort_values(ascending=False)
        if len(g):
            ins.append({"title": "Weather risk",
                        "text": f"Highest delay rate under '{g.index[0]}' weather ({g.iloc[0]*100:.1f}% delayed). Route planning should account for this.",
                        "severity": "warning" if g.iloc[0] > 0.5 else "info"})
    if "_city" in df.columns and "_is_delayed" in df.columns:
        g = df.groupby("_city")["_is_delayed"].mean().sort_values(ascending=False)
        if len(g) >= 2:
            ins.append({"title": "City hotspot",
                        "text": f"'{g.index[0]}' has the highest delay rate ({g.iloc[0]*100:.1f}%) vs best '{g.index[-1]}' ({g.iloc[-1]*100:.1f}%).",
                        "severity": "info"})
    return ins[:5]
