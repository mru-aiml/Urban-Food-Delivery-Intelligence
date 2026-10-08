"""K-Means clustering with scaling + auto-generated human-readable names."""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import joblib, os
import config


def _features(df):
    feats = [c for c in ["_dtime", "_dist", "_rating", "_speed_kmph", "_hour", "_multi"]
             if c in df.columns]
    return feats


def run_kmeans(df, k=4):
    from sklearn.preprocessing import StandardScaler
    feats = _features(df)
    if len(feats) < 2:
        return {"error": "Not enough numeric columns for clustering."}
    d = df[feats].copy()
    for c in feats:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.fillna(d.median())
    if len(d) < k * 5:
        return {"error": "Not enough rows for this K."}
    scaler = StandardScaler()
    X = scaler.fit_transform(d.values)
    km = KMeans(n_clusters=k, random_state=config.RANDOM_STATE, n_init=10)
    labels = km.fit_predict(X)
    df2 = df.copy()
    df2["_cluster"] = labels
    clusters = []
    for i in range(k):
        sub = df2[df2["_cluster"] == i]
        prof = {"id": int(i), "count": int(len(sub)),
                "pct": round(len(sub) / len(df2) * 100, 2)}
        if "_dtime" in sub.columns:
            prof["avg_time"] = round(float(sub["_dtime"].mean()), 2)
        if "_dist" in sub.columns:
            prof["avg_distance"] = round(float(sub["_dist"].mean()), 2)
        if "_rating" in sub.columns:
            prof["avg_rating"] = round(float(sub["_rating"].mean()), 2)
        if "_is_delayed" in sub.columns:
            prof["delay_rate"] = round(float(sub["_is_delayed"].mean() * 100), 2)
        prof["name"] = _name_cluster(prof, df2)
        clusters.append(prof)
    # scatter sample (distance vs time coloured by cluster)
    samp = df2.sample(min(600, len(df2))) if len(df2) > 600 else df2
    pts = []
    if "_dist" in samp.columns and "_dtime" in samp.columns:
        for _, r in samp.iterrows():
            pts.append({"x": round(float(r["_dist"]), 2), "y": round(float(r["_dtime"]), 2),
                        "c": int(r["_cluster"])})
    # persist
    try:
        os.makedirs(config.MODELS_DIR, exist_ok=True)
        joblib.dump(km, os.path.join(config.MODELS_DIR, "cluster_model.pkl"))
        joblib.dump(scaler, os.path.join(config.MODELS_DIR, "cluster_scaler.pkl"))
        joblib.dump(feats, os.path.join(config.MODELS_DIR, "cluster_features.pkl"))
    except Exception:
        pass
    return {"k": k, "features": feats, "clusters": clusters, "points": pts}


def _name_cluster(p, df2):
    t = p.get("avg_time", 0) or 0
    d = p.get("avg_distance", 0) or 0
    dr = p.get("delay_rate", 0) or 0
    overall_t = df2["_dtime"].mean() if "_dtime" in df2.columns else t
    overall_d = df2["_dist"].mean() if "_dist" in df2.columns else d
    if dr >= 65:
        return "High-Delay Deliveries"
    if d >= overall_d * 1.4:
        return "Long-Distance Deliveries"
    if t <= overall_t * 0.85 and d <= overall_d:
        return "Fast Short-Distance Deliveries"
    if t >= overall_t * 1.2:
        return "Slow Deliveries"
    if (p.get("avg_rating", 0) or 0) >= 4.7:
        return "Highly-Rated Deliveries"
    return f"Cluster {p['id']} · Balanced Profile"
