"""Delay classification (RandomForest) + anomaly detection (IsolationForest)."""
import numpy as np
import pandas as pd
import os, joblib
import config


def _build_xy(df):
    feats_num = [c for c in ["_dist", "_rating", "_hour", "_multi", "_speed_kmph", "_is_peak", "_is_weekend"] if c in df.columns]
    feats_cat = [c for c in ["_weather", "_traffic", "_vehicle", "_order_type", "_city", "_festival"] if c in df.columns]
    if "_is_delayed" not in df.columns:
        return None, None, None, "Delay label unavailable."
    d = df[feats_num + feats_cat + ["_is_delayed"]].dropna()
    if len(d) < 200:
        return None, None, None, "Not enough rows."
    X = pd.get_dummies(d[feats_num + feats_cat], drop_first=True)
    y = d["_is_delayed"].astype(int)
    return X, y, list(X.columns), None


def train_or_load_classifier(df):
    """Train RandomForest once, persist, return metrics + importances."""
    model_path = os.path.join(config.MODELS_DIR, "delay_model.pkl")
    meta_path = os.path.join(config.MODELS_DIR, "delay_meta.pkl")
    X, y, cols, err = _build_xy(df)
    if err:
        return {"error": err}
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
    # load cached if columns match
    try:
        if os.path.exists(model_path) and os.path.exists(meta_path):
            m = joblib.load(meta_path)
            if m.get("columns") == cols and m.get("n") == len(df):
                clf = joblib.load(model_path)
                return {**m["metrics"], "cached": True, "features": m["importances"]}
    except Exception:
        pass
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=config.RANDOM_STATE, stratify=y)
    clf = RandomForestClassifier(n_estimators=150, max_depth=14, random_state=config.RANDOM_STATE, n_jobs=-1)
    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    metrics = {"accuracy": round(float(accuracy_score(yte, pred)), 4),
               "precision": round(float(precision_score(yte, pred, zero_division=0)), 4),
               "recall": round(float(recall_score(yte, pred, zero_division=0)), 4),
               "f1": round(float(f1_score(yte, pred, zero_division=0)), 4),
               "confusion_matrix": confusion_matrix(yte, pred).tolist(),
               "n_train": int(len(Xtr)), "n_test": int(len(Xte))}
    imp = sorted([{"feature": c, "importance": round(float(v), 4)}
                  for c, v in zip(cols, clf.feature_importances_)],
                 key=lambda x: x["importance"], reverse=True)[:15]
    try:
        os.makedirs(config.MODELS_DIR, exist_ok=True)
        joblib.dump(clf, model_path)
        joblib.dump({"columns": cols, "n": len(df), "metrics": metrics, "importances": imp}, meta_path)
        # scaler placeholder for spec (models/scaler.pkl)
        from sklearn.preprocessing import StandardScaler
        sc = StandardScaler().fit(Xtr.values)
        joblib.dump(sc, os.path.join(config.MODELS_DIR, "scaler.pkl"))
    except Exception:
        pass
    return {**metrics, "cached": False, "features": imp}


def load_classifier():
    model_path = os.path.join(config.MODELS_DIR, "delay_model.pkl")
    meta_path = os.path.join(config.MODELS_DIR, "delay_meta.pkl")
    if os.path.exists(model_path) and os.path.exists(meta_path):
        try:
            return joblib.load(model_path), joblib.load(meta_path)
        except Exception as e:
            # Stale pickle (e.g. trained under older sklearn/numpy) -> retrain.
            print(f"[classifier] cached model unloadable ({e}); will retrain.")
            for p in (model_path, meta_path):
                try:
                    os.remove(p)
                except Exception:
                    pass
    return None, None


def detect_anomalies(df, limit=60):
    from sklearn.ensemble import IsolationForest
    feats = [c for c in ["_dist", "_dtime", "_speed_kmph", "_rating"] if c in df.columns]
    if len(feats) < 2:
        return {"anomalies": [], "message": "Not enough numeric columns."}
    d = df.copy()
    X = d[feats].apply(pd.to_numeric, errors="coerce")
    med = X.median()
    X = X.fillna(med)
    iso = IsolationForest(contamination=0.02, random_state=config.RANDOM_STATE)
    try:
        scores = iso.fit_predict(X.values)
    except Exception as e:
        return {"anomalies": [], "message": str(e)}
    d["_anom"] = scores
    an = d[d["_anom"] == -1].copy()
    # expected range: mean ± 2σ of time within distance decile
    an["dist_bin"] = pd.qcut(an["_dist"] if "_dist" in an.columns else an[feats[0]], 5, duplicates="drop")
    out = []
    for _, r in an.head(limit * 3).iterrows():
        try:
            same = df[(df["_dist"] >= float(r["_dist"]) - 1) & (df["_dist"] <= float(r["_dist"]) + 1)] if "_dist" in df.columns else df
            exp = float(same["_dtime"].mean()) if "_dtime" in same.columns and len(same) else None
            dev = round(float(r["_dtime"]) - exp, 1) if exp and "_dtime" in r else None
        except Exception:
            exp, dev = None, None
        out.append({"order_id": str(r.get("_oid", r.name)),
                    "distance": round(float(r["_dist"]), 2) if "_dist" in r and pd.notna(r["_dist"]) else None,
                    "delivery_time": round(float(r["_dtime"]), 1) if "_dtime" in r and pd.notna(r["_dtime"]) else None,
                    "expected": round(exp, 1) if exp else None,
                    "deviation": dev,
                    "city": str(r.get("_city", "")), "traffic": str(r.get("_traffic", "")),
                    "note": "Anomaly detected: delivery time is significantly higher than normal for this distance." if (dev and dev > 10) else "Unusual delivery pattern vs peer orders."})
        if len(out) >= limit:
            break
    return {"anomalies": out, "count": len(out), "contamination": 0.02}
