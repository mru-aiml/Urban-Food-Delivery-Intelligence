"""Algorithm comparison experiments — all metrics computed, cached, never hardcoded.

Compares the algorithms already implemented in this project on identical
data/splits, reusing their exact feature/target definitions:
- classification: LogisticRegression / DecisionTree / RandomForest /
  GradientBoosting on the production delay target (same split + seed),
- clustering: KMeans / Agglomerative / DBSCAN on the same scaled features,
- association: Apriori vs FPGrowth on the same transaction basket,
- anomaly: IsolationForest vs LocalOutlierFactor on the same features.

Results are cached in memory and on disk (models/comparison_cache.json),
keyed by dataset fingerprint + parameters, so experiments never rerun on
every page load. The production models are untouched.
"""
import json
import os
import time

import numpy as np
import pandas as pd

import config

CACHE_PATH = os.path.join(config.MODELS_DIR, "comparison_cache.json")
_MEM = {}
_SEED = int(getattr(config, "RANDOM_STATE", 42))
# Bump when experiment code/config changes so stale cached results are not reused.
CODE_VERSION = 3


def _key(base):
    return f"{base}:v{CODE_VERSION}"


def _r(x, nd=4):
    try:
        v = float(x)
    except Exception:
        return None
    if v != v or v in (float("inf"), float("-inf")):  # NaN / Infinity
        return None
    return round(v, nd)


def _dataset_key(df):
    try:
        import hashlib
        for cand in getattr(config, "LOCAL_CSV_CANDIDATES", []):
            if os.path.exists(cand):
                h = hashlib.md5()
                with open(cand, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 256), b""):
                        h.update(chunk)
                return f"{h.hexdigest()}:{df.shape[0]}x{df.shape[1]}"
    except Exception:
        pass
    return f"shape:{df.shape[0]}x{df.shape[1]}:{','.join(map(str, df.columns))}"


def _cached(key, dkey):
    hit = _MEM.get((key, dkey))
    if hit is not None:
        return dict(hit, cached=True)
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                blob = json.load(fh)
            hit = (blob.get("entries") or {}).get(f"{key}::{dkey}")
            if hit is not None:
                _MEM[(key, dkey)] = hit
                return dict(hit, cached=True)
    except Exception:
        pass
    return None


def _store(key, dkey, payload):
    _MEM[(key, dkey)] = payload
    try:
        os.makedirs(config.MODELS_DIR, exist_ok=True)
        blob = {"entries": {}}
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as fh:
                blob = json.load(fh)
            if not isinstance(blob.get("entries"), dict):
                blob["entries"] = {}
        blob["entries"][f"{key}::{dkey}"] = payload
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(blob, fh)
    except Exception:
        pass


# ---------------------------------------------------------------- classification
def compare_classification(df):
    key, dkey = _key("classification"), _dataset_key(df)
    hit = _cached(key, dkey)
    if hit is not None:
        return hit
    from mining.classification import _build_xy
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
    from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                                 f1_score, roc_auc_score, confusion_matrix)
    X, y, cols, err = _build_xy(df)
    if err:
        return {"error": err}
    # Identical split/target for every candidate (fair comparison, no leakage:
    # preprocessing below is fit on the training split only).
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.2, random_state=_SEED, stratify=y)
    balance = {"delayed_pct": _r(float(np.mean(yte)) * 100, 2),
               "n_train": int(len(Xtr)), "n_test": int(len(Xte))}
    cands = [
        ("Logistic Regression",
         make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=_SEED)),
         {"solver": "lbfgs", "max_iter": 1000, "scaled": True}),
        ("Decision Tree", DecisionTreeClassifier(random_state=_SEED),
         {"max_depth": None}),
        ("Random Forest", RandomForestClassifier(n_estimators=100, random_state=_SEED, n_jobs=2),
         {"n_estimators": 100, "n_jobs": 2}),
        # HistGradientBoosting (binned, early-stopping): same gradient-boosting
        # family, far leaner than exact greedy GB, which exceeds free-tier
        # worker memory on Render. Exact class reported honestly.
        ("Gradient Boosting", HistGradientBoostingClassifier(random_state=_SEED),
         {"class": "HistGradientBoostingClassifier", "early_stopping": True}),
    ]
    models = []
    for name, clf, params in cands:
        t0 = time.time()
        try:
            clf.fit(Xtr, ytr)
            train_s = round(time.time() - t0, 2)
        except Exception as e:
            models.append({"name": name, "error": f"{type(e).__name__}: {e}"})
            continue
        t1 = time.time()
        try:
            pred = clf.predict(Xte)
            proba = clf.predict_proba(Xte)[:, 1] if hasattr(clf, "predict_proba") else None
            predict_s = round(time.time() - t1, 3)
        except Exception as e:
            models.append({"name": name, "error": f"predict failed: {e}",
                           "train_time_s": train_s})
            continue
        try:
            auc = _r(roc_auc_score(yte, proba)) if proba is not None else None
        except Exception:
            auc = None
        models.append({"name": name, "params": params,
                       "accuracy": _r(accuracy_score(yte, pred)),
                       "precision": _r(precision_score(yte, pred, zero_division=0)),
                       "recall": _r(recall_score(yte, pred, zero_division=0)),
                       "f1": _r(f1_score(yte, pred, zero_division=0)),
                       "roc_auc": auc,
                       "train_time_s": train_s, "predict_time_s": predict_s,
                       "confusion_matrix": confusion_matrix(yte, pred).tolist()})
    payload = {"category": "classification",
               "target": "_is_delayed (>35 min delivery time)",
               "split": "stratified 80/20",
               "random_state": _SEED,
               "class_balance_test": balance,
               "features": len(cols),
               "models": models,
               "note": "Comparison experiments on this dataset/split; the production "
                       "predictor still uses its own trained RandomForest and is unchanged.",
               "dataset_key": dkey}
    _store(key, dkey, payload)
    return dict(payload, cached=False)


# ---------------------------------------------------------------- clustering
CLUSTER_SAMPLE_N = 4000


def _cluster_frame(df, n=CLUSTER_SAMPLE_N):
    from mining.clustering import _features
    from sklearn.preprocessing import StandardScaler
    feats = _features(df)
    if len(feats) < 2:
        return None, None, "Not enough numeric columns for clustering."
    d = df[feats].copy()
    for c in feats:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna()
    if len(d) < 50:
        return None, None, "Not enough rows for clustering comparison."
    if len(d) > n:
        d = d.sample(n=n, random_state=_SEED)
    scaler = StandardScaler()
    X = scaler.fit_transform(d.values)
    return X, feats, None


def compare_clustering(df, k=4):
    key, dkey = _key(f"clustering:k={k}"), _dataset_key(df)
    hit = _cached(key, dkey)
    if hit is not None:
        return hit
    from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN
    from sklearn.metrics import (silhouette_score, davies_bouldin_score,
                                 calinski_harabasz_score)
    X, feats, err = _cluster_frame(df)
    if err:
        return {"error": err}
    cands = [("K-Means", lambda: KMeans(n_clusters=k, random_state=_SEED, n_init=10).fit_predict(X)),
             ("Agglomerative", lambda: AgglomerativeClustering(n_clusters=k).fit_predict(X)),
             ("DBSCAN (eps=0.8)", lambda: DBSCAN(eps=0.8, min_samples=10).fit_predict(X))]
    algos = []
    for name, run in cands:
        t0 = time.time()
        try:
            labels = np.asarray(run())
            run_s = round(time.time() - t0, 2)
        except Exception as e:
            algos.append({"name": name, "error": f"{type(e).__name__}: {e}"})
            continue
        n_clu = int(len(set(labels.tolist()) - {-1}))
        noise = float(np.mean(labels == -1)) if -1 in labels else 0.0
        row = {"name": name, "n_clusters": n_clu,
               "noise_pct": _r(noise * 100, 2), "runtime_s": run_s,
               "n_points": int(len(labels))}
        if n_clu >= 2 and n_clu < len(labels):
            try:
                mask = labels != -1
                Xm, lm = (X[mask], labels[mask]) if noise > 0 else (X, labels)
                if len(set(lm.tolist())) >= 2:
                    row["silhouette"] = _r(silhouette_score(Xm, lm))
                    row["davies_bouldin"] = _r(davies_bouldin_score(Xm, lm))
                    row["calinski_harabasz"] = _r(calinski_harabasz_score(Xm, lm), 2)
                else:
                    row["metric_note"] = "Only one non-noise cluster: structure metrics undefined."
            except Exception as e:
                row["metric_note"] = f"Metrics unavailable ({type(e).__name__})."
        else:
            row["metric_note"] = "Fewer than two valid clusters: structure metrics undefined."
        algos.append(row)
    payload = {"category": "clustering", "k": k,
               "features": feats, "sample_n": int(len(X)), "random_state": _SEED,
               "algorithms": algos,
               "note": "Metrics assess cluster structure on a random sample, not "
                       "business success. Production K-Means output is unchanged.",
               "dataset_key": dkey}
    _store(key, dkey, payload)
    return dict(payload, cached=False)


# ---------------------------------------------------------------- association
ASSOC_SAMPLE_N = 10000  # mlxtend FPGrowth is quadratic-ish; a shared documented
# sample keeps both miners on identical footing and well inside timeouts.


def _basket(df):
    cols = [c for c in ["_weather", "_traffic", "_vehicle", "_order_type",
                        "_city", "_festival", "_delay_band"] if c in df.columns]
    if len(cols) < 2:
        return None, "Not enough categorical columns for mining."
    d = df[cols].copy()
    for c in cols:
        d[c] = d[c].fillna("Unknown").astype(str).str.strip().str.replace(" ", "_")
    basket = pd.get_dummies(d, prefix=cols)
    if basket.shape[1] > 120:
        keep = basket.mean().sort_values(ascending=False).head(120).index
        basket = basket[keep]
    return basket, None


def compare_association(df, min_support=0.05, min_confidence=0.4):
    key, dkey = _key(f"association:s={min_support}:c={min_confidence}"), _dataset_key(df)
    hit = _cached(key, dkey)
    if hit is not None:
        return hit
    from mlxtend.frequent_patterns import apriori, fpgrowth, association_rules
    if len(df) > ASSOC_SAMPLE_N:
        df = df.sample(n=ASSOC_SAMPLE_N, random_state=_SEED)
    basket, err = _basket(df)
    if err:
        return {"error": err}
    algos = []
    for name, fn in [("Apriori", apriori), ("FPGrowth", fpgrowth)]:
        t0 = time.time()
        try:
            freq = fn(basket, min_support=min_support, use_colnames=True, max_len=3)
            rules = association_rules(freq, metric="confidence", min_threshold=min_confidence)
            run_s = round(time.time() - t0, 2)
        except Exception as e:
            algos.append({"name": name, "error": f"{type(e).__name__}: {e}"})
            continue
        if rules.empty:
            algos.append({"name": name, "n_rules": 0, "runtime_s": run_s,
                          "note": "No rules at these thresholds."})
            continue
        top = rules.sort_values("lift", ascending=False).head(5)
        algos.append({"name": name, "n_rules": int(len(rules)),
                      "avg_support": _r(rules["support"].mean()),
                      "avg_confidence": _r(rules["confidence"].mean()),
                      "avg_lift": _r(rules["lift"].mean(), 2),
                      "runtime_s": run_s,
                      "top_rules": [f"{' + '.join(sorted(map(str, r['antecedents'])))} -> "
                                    f"{' + '.join(sorted(map(str, r['consequents'])))} "
                                    f"(lift {round(float(r['lift']), 2)})"
                                    for _, r in top.iterrows()]})
    payload = {"category": "association",
               "params": {"min_support": min_support, "min_confidence": min_confidence,
                          "max_len": 3, "transactions": int(len(basket)),
                          "items": int(basket.shape[1]),
                          "sample_n": ASSOC_SAMPLE_N, "random_state": _SEED},
               "algorithms": algos,
               "note": "Same basket, thresholds and sample for both miners "
                       "(production mining endpoint uses full data). Association "
                       "indicates a relationship, not causation.",
               "dataset_key": dkey}
    _store(key, dkey, payload)
    return dict(payload, cached=False)


# ---------------------------------------------------------------- anomaly
ANOMALY_SAMPLE_N = 5000


def compare_anomaly(df, contamination=0.02):
    key, dkey = _key(f"anomaly:c={contamination}"), _dataset_key(df)
    hit = _cached(key, dkey)
    if hit is not None:
        return hit
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor
    feats = [c for c in ["_dist", "_dtime", "_speed_kmph", "_rating"] if c in df.columns]
    if len(feats) < 2:
        return {"error": "Not enough numeric columns."}
    d = df[feats].copy()
    X = d.apply(pd.to_numeric, errors="coerce")
    X = X.fillna(X.median()).dropna()
    if len(X) > ANOMALY_SAMPLE_N:  # LOF is quadratic-ish: shared sample keeps it fair
        X = X.sample(n=ANOMALY_SAMPLE_N, random_state=_SEED)
    Xn = X.values
    out = []
    flags = {}
    for name, make in [("Isolation Forest",
                        lambda: IsolationForest(contamination=contamination,
                                              random_state=_SEED).fit_predict(Xn)),
                       ("Local Outlier Factor",
                        lambda: LocalOutlierFactor(n_neighbors=20,
                                                 contamination=contamination).fit_predict(Xn))]:
        t0 = time.time()
        try:
            pred = np.asarray(make())
            run_s = round(time.time() - t0, 2)
        except Exception as e:
            out.append({"name": name, "error": f"{type(e).__name__}: {e}"})
            continue
        mask = pred == -1
        flags[name] = set(np.nonzero(mask)[0].tolist())
        out.append({"name": name, "n_anomalies": int(mask.sum()),
                    "anomaly_pct": _r(float(mask.mean()) * 100, 2),
                    "runtime_s": run_s, "n_points": int(len(pred))})
    names = [a["name"] for a in out if "n_anomalies" in a]
    agreement = None
    if len(names) == 2:
        a, b = flags[names[0]], flags[names[1]]
        union = len(a | b)
        agreement = _r(len(a & b) / union, 3) if union else None
    payload = {"category": "anomaly", "features": feats,
               "contamination": contamination, "sample_n": int(len(Xn)),
               "random_state": _SEED, "detectors": out,
               "agreement_jaccard": agreement,
               "note": "No ground-truth anomaly labels exist, so accuracy cannot "
                       "be claimed; agreement measures overlap between detectors. "
                       "Production IsolationForest output is unchanged.",
               "dataset_key": dkey}
    _store(key, dkey, payload)
    return dict(payload, cached=False)
