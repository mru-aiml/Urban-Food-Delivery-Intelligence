"""Hotspots, recommendations, data-quality helpers."""
import pandas as pd
import numpy as np


def hotspots(df, top_n=30):
    out = {"has_geo": False, "points": [], "areas": []}
    lat = "Delivery_location_latitude" if "Delivery_location_latitude" in df.columns else None
    lon = "Delivery_location_longitude" if "Delivery_location_longitude" in df.columns else None
    # engineered frame may keep original names too
    if lat is None:
        for c in df.columns:
            if "delivery_location_lat" in c.lower():
                lat = c
    if lon is None:
        for c in df.columns:
            if "delivery_location_lon" in c.lower():
                lon = c
    dt = "_dtime" if "_dtime" in df.columns else None
    if lat and lon and dt:
        d = df[[lat, lon, dt, "_is_delayed" if "_is_delayed" in df.columns else dt]].dropna()
        # aggregate into grid cells to keep payload small
        d = d.copy()
        d["_la"] = (d[lat] // 0.05 * 0.05).round(3)
        d["_lo"] = (d[lon] // 0.05 * 0.05).round(3)
        g = d.groupby(["_la", "_lo"]).agg(orders=(dt, "count"),
                                          avg_time=(dt, "mean"),
                                          delay_rate=("_is_delayed" if "_is_delayed" in df.columns else dt, "mean"))
        g = g.sort_values("orders", ascending=False).head(top_n)
        pts = []
        for (la, lo), r in g.iterrows():
            dr = float(r["delay_rate"])
            color = "green" if dr < 0.35 else ("yellow" if dr < 0.6 else "red")
            pts.append({"lat": float(la), "lon": float(lo), "orders": int(r["orders"]),
                        "avg_time": round(float(r["avg_time"]), 2),
                        "delay_rate": round(dr * 100, 2), "color": color})
        out["has_geo"] = True
        out["points"] = pts
    # area/city fallback (always provided)
    if "_city" in df.columns and dt:
        g = df.groupby("_city").agg(orders=(dt, "count"), avg_time=(dt, "mean"),
                                    delay_rate=("_is_delayed", "mean") if "_is_delayed" in df.columns else (dt, "mean"),
                                    avg_dist=("_dist", "mean") if "_dist" in df.columns else (dt, "mean"),
                                    avg_rating=("_rating", "mean") if "_rating" in df.columns else (dt, "mean"))
        areas = []
        for city, r in g.iterrows():
            dr = float(r["delay_rate"]) if "_is_delayed" in df.columns else 0
            areas.append({"label": str(city), "orders": int(r["orders"]),
                          "avg_time": round(float(r["avg_time"]), 2),
                          "delay_rate": round(dr * 100, 2),
                          "avg_distance": round(float(r["avg_dist"]), 2),
                          "avg_rating": round(float(r["avg_rating"]), 2)})
        out["areas"] = sorted(areas, key=lambda x: x["delay_rate"], reverse=True)
    return out


def recommendations(df):
    recs = []
    dt = "_dtime" if "_dtime" in df.columns else None
    if not dt or not len(df):
        return recs
    if "_hour" in df.columns:
        g = df.dropna(subset=["_hour"]).groupby("_hour")["_is_delayed"].mean() if "_is_delayed" in df.columns else df.groupby("_hour")[dt].mean()
        peak = g.sort_values(ascending=False).head(3)
        if len(peak) and (peak.iloc[0] > (g.mean() * 1.1)):
            hrs = ", ".join(f"{int(h)}:00" for h in peak.index)
            recs.append({"problem": "Evening/peak-hour delivery delays",
                         "evidence": f"Delay rate peaks at {hrs} (up to {peak.iloc[0]*100:.1f}% delayed vs {g.mean()*100:.1f}% average).",
                         "action": "Increase rider capacity and pre-position riders in high-demand zones during these hours.",
                         "expected_impact": "Analytical estimate only — peak-hour late deliveries could fall if capacity matches demand."})
    if "_traffic" in df.columns and "_is_delayed" in df.columns:
        g = df.groupby("_traffic")["_is_delayed"].mean().sort_values(ascending=False)
        if len(g) and g.iloc[0] > 0.5:
            recs.append({"problem": f"High delays under '{g.index[0]}' traffic",
                         "evidence": f"{g.iloc[0]*100:.1f}% of orders delayed when traffic is '{g.index[0]}'.",
                         "action": "Extend promised delivery windows dynamically when traffic density is high/jam.",
                         "expected_impact": "Fewer SLA breaches; improved customer satisfaction (analytical recommendation)."})
    if "_dist" in df.columns and "_is_delayed" in df.columns:
        far = df[df["_dist"] > df["_dist"].quantile(0.8)]
        if len(far) > 20 and far["_is_delayed"].mean() > df["_is_delayed"].mean() * 1.2:
            recs.append({"problem": "Long-distance orders fail more often",
                         "evidence": f"Top-quintile distance orders: {far['_is_delayed'].mean()*100:.1f}% delayed vs {df['_is_delayed'].mean()*100:.1f}% overall.",
                         "action": "Assign long-distance orders to faster vehicles or split delivery zones.",
                         "expected_impact": "Potential reduction in long-haul late deliveries."})
    if "_vehicle" in df.columns and dt:
        g = df.groupby("_vehicle")[dt].mean().sort_values()
        if len(g) >= 2 and (g.iloc[-1] - g.iloc[0]) > 3:
            recs.append({"problem": f"Vehicle gap: {g.index[-1]} slower than {g.index[0]}",
                         "evidence": f"{g.index[-1]} averages {g.iloc[-1]:.1f} min vs {g.index[0]} at {g.iloc[0]:.1f} min.",
                         "action": "Prefer faster vehicle types for peak/far orders; service slower fleet.",
                         "expected_impact": "Lower average delivery time on reassigned orders."})
    if "_weather" in df.columns and "_is_delayed" in df.columns:
        g = df.groupby("_weather")["_is_delayed"].mean().sort_values(ascending=False)
        if len(g) and g.iloc[0] > 0.5:
            recs.append({"problem": f"Weather-linked delays ({g.index[0]})",
                         "evidence": f"{g.iloc[0]*100:.1f}% delayed in {g.index[0]} conditions.",
                         "action": "Add weather buffer to ETAs and alert customers proactively.",
                         "expected_impact": "Fewer surprise delays; better ratings."})
    if not recs:
        recs.append({"problem": "No dominant risk pattern",
                     "evidence": "Delay rates are evenly spread across dimensions.",
                     "action": "Maintain current operations; monitor SLA trends weekly.",
                     "expected_impact": "Stable performance."})
    return recs


def data_quality(df_raw, df_clean):
    total_cells = df_raw.shape[0] * df_raw.shape[1]
    missing = int(df_raw.isna().sum().sum())
    completeness = round((1 - missing / total_cells) * 100, 2) if total_cells else 0
    dup = int(df_raw.duplicated().sum())
    uniqueness = round((1 - dup / len(df_raw)) * 100, 2) if len(df_raw) else 0
    # validity: numerics in sane ranges
    valid_checks = 0
    valid_ok = 0
    for c in df_raw.columns:
        s = pd.to_numeric(df_raw[c], errors="coerce")
        if s.notna().sum() > len(df_raw) * 0.3:
            valid_checks += int(s.notna().sum())
            valid_ok += int(((s > 0) & (s < 1000)).sum())
    validity = round(valid_ok / valid_checks * 100, 2) if valid_checks else 100.0
    consistency = round((completeness + uniqueness) / 2, 2)
    score = round((completeness * 0.35 + uniqueness * 0.25 + validity * 0.25 + consistency * 0.15), 2)
    return {
        "score": score,
        "dimensions": {"completeness": completeness, "uniqueness": uniqueness,
                       "validity": validity, "consistency": consistency},
        "missing_by_column": {c: int(df_raw[c].isna().sum()) for c in df_raw.columns},
        "missing_total": missing,
        "duplicate_rows": dup,
        "unique_records": int(len(df_raw) - dup),
        "raw_rows": int(len(df_raw)), "clean_rows": int(len(df_clean)),
        "dtypes": {c: str(t) for c, t in df_raw.dtypes.items()},
    }
