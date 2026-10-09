"""Urban Food Delivery Intelligence — Flask backend.
Run: python app.py  (Windows, http://127.0.0.1:5000)
DWM flow: RAW -> ETL -> WAREHOUSE -> OLAP -> MINING -> PREDICTION -> INSIGHTS.
"""
import os, time, traceback
from datetime import datetime
from functools import lru_cache
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import config

app = Flask(__name__)
CORS(app)
STARTED = datetime.now().isoformat()

# ---------------------------------------------------------------- diagnostics
def _git_sha_fallback():
    """Best-effort local git SHA (Render containers may not ship .git)."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        head = os.path.join(here, ".git", "HEAD")
        if not os.path.exists(head):
            return "unknown"
        with open(head, "r", encoding="utf-8", errors="replace") as fh:
            ref = fh.read().strip()
        if ref.startswith("ref:"):
            refpath = os.path.join(here, ".git", *ref.split()[1].split("/"))
            if os.path.exists(refpath):
                with open(refpath, "r", encoding="utf-8", errors="replace") as fh:
                    return fh.read().strip() or "unknown"
            packed = os.path.join(here, ".git", "packed-refs")
            if os.path.exists(packed):
                want = ref.split()[1]
                with open(packed, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        parts = line.strip().split()
                        if len(parts) == 2 and parts[1] == want:
                            return parts[0]
            return "unknown"
        return ref or "unknown"
    except Exception:
        return "unknown"


def build_fingerprint():
    """Non-sensitive build/runtime fingerprint for deployment verification."""
    sha = (os.environ.get("RENDER_GIT_COMMIT") or "").strip() or _git_sha_fallback()
    try:
        pyv = __import__("sys").version.split()[0]
    except Exception:
        pyv = "unknown"
    try:
        npv = np.__version__
    except Exception:
        npv = "unknown"
    try:
        pdv = pd.__version__
    except Exception:
        pdv = "unknown"
    try:
        import analytics.overview as _ov
        ovmod = os.path.abspath(getattr(_ov, "__file__", "unknown"))
    except Exception as e:
        ovmod = f"import-failed: {type(e).__name__}: {e}"
    return {"commit": (sha[:12] if sha != "unknown" else "unknown"),
            "python": pyv, "numpy": npv, "pandas": pdv,
            "app_file": os.path.abspath(__file__), "overview_module": ovmod}

# ---------------------------------------------------------------- state
STATE = {"raw": None, "clean": None, "df": None, "raw_profile": None,
         "etl": None, "features_meta": None, "load_error": None,
         "last_processed": None, "demo_mode": False}


def boot():
    print("[BOOT] starting dataset load ...", flush=True)
    try:
        import pandas as _pd, numpy as _np, sys as _sys
        print(f"[BOOT] env python={_sys.version.split()[0]} pandas={_pd.__version__} numpy={_np.__version__}", flush=True)
        from preprocessing.loader import load_raw
        from preprocessing.cleaner import clean, profile_raw
        from preprocessing.feature_engineering import engineer
        raw, _raw_meta = load_raw()
        print(f"[BOOT] raw loaded: rows={len(raw)} cols={len(raw.columns)}", flush=True)
        STATE["raw_profile"] = profile_raw(raw)
        STATE["raw"] = raw
        cdf, etl = clean(raw)
        STATE["clean"] = cdf
        STATE["etl"] = etl
        edf, fmeta = engineer(cdf)
        STATE["df"] = edf
        STATE["features_meta"] = fmeta
        STATE["last_processed"] = datetime.now().isoformat()
        print(f"[BOOT] OK rows={len(edf)} cols={len(edf.columns)}", flush=True)
        print(f"[BOOT] columns: {list(edf.columns)}", flush=True)
    except Exception as e:
        STATE["load_error"] = f"{type(e).__name__}: {e}"
        print(f"[BOOT] FAILED: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()


boot()

def need_df():
    if STATE["df"] is None:
        print(f"[OVERVIEW ERROR] dataset not loaded: {STATE.get('load_error')}", flush=True)
        return jsonify({"error": "Dataset not loaded", "detail": STATE.get("load_error")}), 500
    return None

def safe(fn):
    try:
        return fn()
    except Exception as e:
        print(f"[API ERROR] {type(e).__name__}: {e}", flush=True)
        app.logger.exception("[API ERROR] traceback (server-side only)")
        return jsonify({"error": str(e)}), 500

# ---------------------------------------------------------------- health/meta
@app.get("/api/health")
def health():
    from database.warehouse import warehouse_available
    ok, msg = warehouse_available()
    df = STATE["df"]
    return jsonify({"status": "ok", "started": STARTED,
                    "rows": len(df) if df is not None else 0,
                    "columns": len(df.columns) if df is not None else 0,
                    "dataset_loaded": df is not None,
                    "load_error": STATE.get("load_error"),
                    "build": build_fingerprint(),
                    "mysql": {"available": ok, "detail": msg},
                    "demo_mode": STATE["demo_mode"]})

@app.get("/api/dataset-info")
def dataset_info():
    if STATE["raw"] is None:
        return jsonify({"error": STATE.get("load_error") or "not loaded"}), 500
    p = STATE["raw_profile"]
    return jsonify({"rows": p["rows"], "columns": p["columns"], "column_names": p["column_names"],
                    "dtypes": p["dtypes"], "missing_by_column": p["missing_by_column"],
                    "missing_total": p["missing_total"], "duplicate_rows": p["duplicate_rows"],
                    "unique_counts": p["unique_counts"],
                    "column_mapping": (STATE["etl"] or {}).get("column_mapping", {}),
                    "etl": STATE["etl"], "last_processed": STATE["last_processed"]})

@app.get("/api/data-quality")
def data_quality():
    err = need_df()
    if err: return err
    def go():
        from analytics.hotspots import data_quality as dq
        return jsonify(dq(STATE["raw"], STATE["clean"]))
    return safe(go)

@app.get("/api/warehouse/schema")
def wh_schema():
    def go():
        from database.warehouse import star_schema_view, warehouse_available
        ok, msg = warehouse_available()
        return jsonify({**star_schema_view(), "mysql": {"available": ok, "detail": msg},
                        "etl": STATE["etl"], "last_processed": STATE["last_processed"]})
    return safe(go)

# ---------------------------------------------------------------- overview
@app.get("/api/overview")
def overview():
    print("[OVERVIEW] request received", flush=True)
    err = need_df()
    if err: return err
    def go():
        import json as _json
        from analytics.overview import overview_stats, overview_charts, live_insights
        df = STATE["df"]
        print(f"[OVERVIEW] dataframe rows: {len(df)}", flush=True)
        print(f"[OVERVIEW] dataframe columns: {len(df.columns)}", flush=True)
        try:
            print("[OVERVIEW] calculating KPIs", flush=True)
            kpis = overview_stats(df)
            print("[OVERVIEW] KPIs complete", flush=True)
        except Exception:
            app.logger.exception("[OVERVIEW] failed at stage: KPIs")
            raise
        try:
            print("[OVERVIEW] calculating charts", flush=True)
            charts = overview_charts(df)
            for _ck, _cs in charts.items():
                print(f"[OVERVIEW DEBUG] {_ck}: rows={len(_cs)}", flush=True)
            print("[OVERVIEW] charts complete", flush=True)
        except Exception:
            app.logger.exception("[OVERVIEW] failed at stage: charts")
            raise
        try:
            print("[OVERVIEW] calculating insights", flush=True)
            insights = live_insights(df)
            print("[OVERVIEW] insights complete", flush=True)
        except Exception:
            app.logger.exception("[OVERVIEW] failed at stage: insights")
            raise
        payload = {"kpis": kpis, "charts": charts,
                   "insights": insights, "last_processed": STATE["last_processed"]}
        print("[OVERVIEW] serializing response", flush=True)
        try:
            _json.dumps(payload, allow_nan=False)
        except Exception as je:
            print(f"[OVERVIEW ERROR] response not strictly JSON-serializable: {je}", flush=True)
            app.logger.exception("[OVERVIEW] failed at stage: serialization")
            raise
        print("[OVERVIEW] response ready", flush=True)
        print("[OVERVIEW] serialization complete", flush=True)
        return jsonify(payload)
    return safe(go)

# ---------------------------------------------------------------- delivery
@app.get("/api/delivery-analytics")
def delivery():
    err = need_df()
    if err: return err
    def go():
        from analytics.delivery import apply_filters, delivery_metrics, delivery_charts, performance_summary, filter_options
        f = {k: request.args.get(k) for k in ["city", "weather", "traffic", "vehicle", "order_type", "status", "from", "to"] if request.args.get(k)}
        df = apply_filters(STATE["df"], f)
        return jsonify({"filters": f, "metrics": delivery_metrics(df), "charts": delivery_charts(df),
                        "summary": performance_summary(df), "options": filter_options(STATE["df"])})
    return safe(go)

# ---------------------------------------------------------------- orders + SLA
def _sla(df, sla):
    dt = "_dtime" if "_dtime" in df.columns else None
    if not dt: return df
    d = df.copy()
    d["_sla_band"] = pd.cut(d[dt], bins=[-1, sla - 10, sla, 999],
                            labels=["On Target", "At Risk", "SLA Breached"])
    return d

@app.get("/api/orders")
def orders():
    err = need_df()
    if err: return err
    def go():
        try: sla = float(request.args.get("sla", config.SLA_DEFAULT_MINUTES))
        except Exception: sla = config.SLA_DEFAULT_MINUTES
        page = max(1, int(request.args.get("page", 1)))
        size = min(200, max(5, int(request.args.get("size", 25))))
        q = (request.args.get("q") or "").strip().lower()
        band = request.args.get("band")
        sort = request.args.get("sort", "")
        d = _sla(STATE["df"], sla)
        if q:
            mask = pd.Series([False]*len(d))
            for c in d.columns:
                try: mask = mask | d[c].astype(str).str.lower().str.contains(q, na=False)
                except Exception: pass
            d = d[mask]
        if band and "_sla_band" in d.columns and band != "all":
            d = d[d["_sla_band"] == band]
        if sort and sort.lstrip("-") in d.columns:
            d = d.sort_values(sort.lstrip("-"), ascending=not sort.startswith("-"))
        total = len(d)
        cols = [c for c in ["_oid", "_order_date_parsed", "_hour", "_city", "_weather",
                            "_traffic", "_vehicle", "_order_type", "_dist", "_dtime",
                            "_rating", "_delay_band", "_sla_band", "_speed_kmph"] if c in d.columns]
        page_df = d.iloc[(page-1)*size: page*size][cols]
        rows = page_df.astype(object).where(pd.notna(page_df), None).to_dict("records")
        # json-safe
        clean_rows = [{k: (float(v) if isinstance(v, (np.floating,)) else (int(v) if isinstance(v, (np.integer,)) else (str(v) if not isinstance(v,(str,int,float,bool,type(None))) else v))) for k,v in r.items()} for r in rows]
        # sla summary
        sla_summary = {}
        if "_sla_band" in d.columns:
            vc = d["_sla_band"].value_counts()
            for k in ["On Target", "At Risk", "SLA Breached"]:
                sla_summary[k] = {"count": int(vc.get(k, 0)), "pct": round(float(vc.get(k,0))/len(d)*100,2) if len(d) else 0}
        return jsonify({"page": page, "size": size, "total": total,
                        "pages": (total+size-1)//size, "rows": clean_rows,
                        "columns": cols, "sla": sla, "sla_summary": sla_summary,
                        "dtypes": {c: str(STATE["df"][c].dtype) if c in STATE["df"].columns else "" for c in cols}})
    return safe(go)

@app.get("/api/orders/<order_id>")
def order_one(order_id):
    err = need_df()
    if err: return err
    def go():
        df = STATE["df"]
        col = "_oid" if "_oid" in df.columns else None
        r = None
        if col:
            m = df[df[col].astype(str) == str(order_id)]
            if len(m): r = m.iloc[0]
        if r is None:
            try:
                r = df.iloc[int(order_id)]
            except Exception:
                return jsonify({"error": "Order not found"}), 404
        out = {}
        for k, v in r.items():
            if isinstance(v, (np.floating,)): out[k] = float(v)
            elif isinstance(v, (np.integer,)): out[k] = int(v)
            elif pd.isna(v): out[k] = None
            elif hasattr(v, "isoformat"):
                try: out[k] = v.isoformat()
                except Exception: out[k] = str(v)
            else: out[k] = v
        return jsonify(out)
    return safe(go)

@app.get("/api/orders/<order_id>/explanation")
def explain(order_id):
    err = need_df()
    if err: return err
    def go():
        from mining.classification import load_classifier
        df = STATE["df"]
        col = "_oid" if "_oid" in df.columns else None
        r = None
        if col:
            m = df[df[col].astype(str) == str(order_id)]
            if len(m): r = m.iloc[0]
        if r is None:
            try: r = df.iloc[int(order_id)]
            except Exception: return jsonify({"error": "Order not found"}), 404
        thr = float((STATE["features_meta"] or {}).get("threshold", 35))
        dt = float(r["_dtime"]) if "_dtime" in r and pd.notna(r["_dtime"]) else None
        delayed = bool(dt and dt > thr)
        # contribution: compare value vs peer means (traffic/weather/vehicle/distance/hour)
        factors = []
        def peer_gap(colname, val):
            try:
                if colname not in df.columns or pd.isna(val): return 0
                g = df.groupby(colname)["_dtime"].mean()
                return float(g.get(val, df["_dtime"].mean()) - df["_dtime"].mean())
            except Exception: return 0
        gaps = {}
        if "_traffic" in df.columns: gaps["Traffic"] = peer_gap("_traffic", r.get("_traffic"))
        if "_weather" in df.columns: gaps["Weather"] = peer_gap("_weather", r.get("_weather"))
        if "_vehicle" in df.columns: gaps["Vehicle"] = peer_gap("_vehicle", r.get("_vehicle"))
        if "_city" in df.columns: gaps["City"] = peer_gap("_city", r.get("_city"))
        if "_dist" in df.columns and pd.notna(r.get("_dist")):
            gaps["Distance"] = max(0.0, (float(r["_dist"]) - float(df["_dist"].mean())) * 1.2)
        if "_hour" in df.columns and pd.notna(r.get("_hour")):
            gaps["Time of day"] = peer_gap("_hour", r.get("_hour"))
        pos = {k: max(0, v) for k, v in gaps.items()}
        tot = sum(pos.values())
        if tot > 0:
            factors = [{"feature": k, "pct": round(v/tot*100, 1)} for k, v in sorted(pos.items(), key=lambda x: -x[1])]
        else:
            factors = [{"feature": "No dominant factor", "pct": 100.0}]
        # model check
        clf, meta = load_classifier()
        model_delay_prob = None
        if clf is not None and meta is not None:
            try:
                feats_num = [c for c in ["_dist","_rating","_hour","_multi","_speed_kmph","_is_peak","_is_weekend"] if c in df.columns]
                feats_cat = [c for c in ["_weather","_traffic","_vehicle","_order_type","_city","_festival"] if c in df.columns]
                row = pd.DataFrame([{c: r.get(c) for c in feats_num+feats_cat}])
                X = pd.get_dummies(row, drop_first=False)
                for c in meta["columns"]:
                    if c not in X.columns: X[c] = 0
                X = X[meta["columns"]]
                model_delay_prob = round(float(clf.predict_proba(X)[0][1])*100, 1)
            except Exception: pass
        # recommendation
        top = factors[0]["feature"] if factors else ""
        action_map = {"Traffic": "Avoid peak-traffic dispatch; extend ETA and choose faster vehicle.",
                      "Distance": "Assign long-distance orders to motorcycles/scooters in good condition or split zones.",
                      "Weather": "Add weather buffer to promised time; notify customer proactively.",
                      "Vehicle": "Prefer better-conditioned vehicles for similar orders.",
                      "City": "Pre-position riders in this city zone during similar hours.",
                      "Time of day": "Shift capacity toward this hour window."}
        return jsonify({"order_id": str(order_id), "delivery_time": dt, "threshold": thr,
                        "delayed": delayed,
                        "details": {k: (None if pd.isna(v) else (float(v) if isinstance(v,(np.floating,)) else (int(v) if isinstance(v,(np.integer,)) else str(v)))) for k, v in dict(r).items()},
                        "factors": factors, "label": "Contributing factors / model evidence (association, not proven causation).",
                        "model_delay_probability": model_delay_prob,
                        "recommended_action": action_map.get(top, "Review dispatch timing and vehicle assignment.")})
    return safe(go)

# ---------------------------------------------------------------- OLAP
@app.get("/api/olap")
def olap_meta():
    err = need_df()
    if err: return err
    def go():
        from analytics.olap import available_dims, EXPLANATIONS, METRICS
        return jsonify({"dimensions": available_dims(STATE["df"]),
                        "metrics": list(METRICS.keys()), "explanations": EXPLANATIONS,
                        "time_hierarchy": ["_year","_month","_day","_hour"]})
    return safe(go)

@app.post("/api/olap")
def olap_run():
    err = need_df()
    if err: return err
    def go():
        from analytics.olap import run_olap
        b = request.get_json(force=True, silent=True) or {}
        return jsonify(run_olap(STATE["df"], op=b.get("op","roll-up"),
                                dimension=b.get("dimension","_hour"),
                                rows=b.get("rows","_vehicle"), columns=b.get("columns","_weather"),
                                metric=b.get("metric","avg_time"), filters=b.get("filters",{})))
    return safe(go)

# ---------------------------------------------------------------- mining
@app.get("/api/association-rules")
def assoc_get():
    err = need_df()
    if err: return err
    def go():
        from mining.association_rules import mine_rules
        return jsonify(mine_rules(STATE["df"]))
    return safe(go)

@app.post("/api/association-rules")
def assoc_post():
    err = need_df()
    if err: return err
    def go():
        from mining.association_rules import mine_rules
        b = request.get_json(force=True, silent=True) or {}
        return jsonify(mine_rules(STATE["df"], min_support=float(b.get("min_support",0.05)),
                                  min_confidence=float(b.get("min_confidence",0.4))))
    return safe(go)

@app.get("/api/clusters")
def clusters_get():
    err = need_df()
    if err: return err
    def go():
        from mining.clustering import run_kmeans
        return jsonify(run_kmeans(STATE["df"], k=int(request.args.get("k",4))))
    return safe(go)

@app.post("/api/clusters")
def clusters_post():
    err = need_df()
    if err: return err
    def go():
        from mining.clustering import run_kmeans
        b = request.get_json(force=True, silent=True) or {}
        return jsonify(run_kmeans(STATE["df"], k=int(b.get("k",4))))
    return safe(go)

@app.get("/api/classification")
def classification():
    err = need_df()
    if err: return err
    def go():
        from mining.classification import train_or_load_classifier
        return jsonify(train_or_load_classifier(STATE["df"]))
    return safe(go)

@app.get("/api/anomalies")
def anomalies():
    err = need_df()
    if err: return err
    def go():
        from mining.classification import detect_anomalies
        return jsonify(detect_anomalies(STATE["df"], limit=int(request.args.get("limit",60))))
    return safe(go)

@app.get("/api/algorithm-comparison")
def algorithm_comparison():
    err = need_df()
    if err: return err
    def go():
        from mining import model_comparison as mc
        cat = (request.args.get("category") or "classification").strip().lower()
        if cat == "classification":
            return jsonify(mc.compare_classification(STATE["df"]))
        if cat == "clustering":
            return jsonify(mc.compare_clustering(STATE["df"]))
        if cat == "association":
            return jsonify(mc.compare_association(STATE["df"]))
        if cat in ("anomaly", "anomalies", "anomaly-detection"):
            return jsonify(mc.compare_anomaly(STATE["df"]))
        return jsonify({"error": "Unknown category. Use classification, clustering, association or anomaly."}), 400
    return safe(go)

# ---------------------------------------------------------------- predict / what-if
def _predict_row(payload):
    from mining.classification import load_classifier
    clf, meta = load_classifier()
    if clf is None:
        from mining.classification import train_or_load_classifier
        train_or_load_classifier(STATE["df"])
        clf, meta = load_classifier()
    if clf is None: return None, None, "Model unavailable"
    df = STATE["df"]
    feats_num = [c for c in ["_dist","_rating","_hour","_multi","_speed_kmph","_is_peak","_is_weekend"] if c in df.columns]
    feats_cat = [c for c in ["_weather","_traffic","_vehicle","_order_type","_city","_festival"] if c in df.columns]
    row = {}
    key_map = {"distance":"_dist","rating":"_rating","hour":"_hour","multiple_deliveries":"_multi",
               "weather":"_weather","traffic":"_traffic","vehicle":"_vehicle","order_type":"_order_type",
               "city":"_city","festival":"_festival"}
    for k, v in (payload or {}).items():
        canon = key_map.get(k, k)
        if canon in feats_num+feats_cat: row[canon] = v
    # defaults = medians/modes
    for c in feats_num:
        if c not in row or row[c] in (None,""):
            row[c] = float(df[c].median()) if c in df.columns else 0
    for c in feats_cat:
        if c not in row or row[c] in (None,""):
            row[c] = str(df[c].mode().iloc[0]) if c in df.columns and len(df[c].mode()) else "Unknown"
    # derived
    if "_speed_kmph" in feats_num and ("_speed_kmph" not in payload):
        try: row["_speed_kmph"] = float(row.get("_dist",5)) / (30/60)
        except Exception: pass
    if "_is_peak" in feats_num:
        try: row["_is_peak"] = 1 if int(float(row.get("_hour",12))) in [12,13,19,20,21] else 0
        except Exception: row["_is_peak"] = 0
    X = pd.get_dummies(pd.DataFrame([row]), drop_first=False)
    for c in meta["columns"]:
        if c not in X.columns: X[c] = 0
    X = X[meta["columns"]]
    prob = float(clf.predict_proba(X)[0][1])
    # expected time: peer mean adjusted
    exp_time = float(df["_dtime"].mean())
    try:
        if "_traffic" in df.columns and row.get("_traffic") in df["_traffic"].values:
            exp_time = float(df[df["_traffic"]==row["_traffic"]]["_dtime"].mean())
        if "_dist" in row:
            exp_time += max(0, (float(row["_dist"])-float(df["_dist"].mean()))*1.1)
    except Exception: pass
    # feature contribution from importances mapped back to base feature
    imps = {f["feature"]: f["importance"] for f in meta.get("importances",[])}
    agg = {}
    for col, v in imps.items():
        base = col.split("_")[0]
        # map dummy prefix: e.g. _traffic_Jam -> Traffic
        label = col
        for canon, pretty in [("_traffic","Traffic"),("_weather","Weather"),("_dist","Distance"),
                              ("_vehicle","Vehicle"),("_multi","Multiple Orders"),("_hour","Hour"),
                              ("_city","City"),("_order_type","Order Type"),("_rating","Rating")]:
            if col.startswith(canon): label = pretty; break
        agg[label] = agg.get(label,0)+v
    tot = sum(agg.values()) or 1
    why = [{"feature":k,"pct":round(v/tot*100,1)} for k,v in sorted(agg.items(),key=lambda x:-x[1])[:6]]
    return prob, round(exp_time,1), why

@app.post("/api/predict-delay")
def predict():
    err = need_df()
    if err: return err
    def go():
        b = request.get_json(force=True, silent=True) or {}
        prob, exp_time, why = _predict_row(b)
        if prob is None: return jsonify({"error": why}), 500
        level = "LOW" if prob < 0.35 else ("MEDIUM" if prob < 0.65 else "HIGH")
        return jsonify({"risk": level, "probability": round(prob*100,1),
                        "expected_time": exp_time, "why": why,
                        "note": "Model evidence (RandomForest feature importance), not causal proof."})
    return safe(go)

@app.post("/api/what-if")
def whatif():
    err = need_df()
    if err: return err
    def go():
        b = request.get_json(force=True, silent=True) or {}
        cur, sim = b.get("current",{}), b.get("simulated",{})
        p1,e1,w1 = _predict_row(cur); p2,e2,w2 = _predict_row(sim)
        if p1 is None or p2 is None: return jsonify({"error":"model unavailable"}),500
        return jsonify({"current": {"prob": round(p1*100,1),"time": e1},
                        "simulated": {"prob": round(p2*100,1),"time": e2},
                        "improvement": {"minutes": round(e2-e1,1) if e1 and e2 else None,
                                        "pp": round((p2-p1)*100,1)}})
    return safe(go)

# ---------------------------------------------------------------- hotspots / recs
@app.get("/api/hotspots")
def hot():
    err = need_df()
    if err: return err
    def go():
        from analytics.hotspots import hotspots
        return jsonify(hotspots(STATE["df"]))
    return safe(go)

@app.get("/api/recommendations")
def recs():
    err = need_df()
    if err: return err
    def go():
        from analytics.hotspots import recommendations
        return jsonify({"recommendations": recommendations(STATE["df"])})
    return safe(go)

@app.get("/api/live-status")
def live_status():
    def go():
        from integrations.live_data_provider import provider_status
        return jsonify(provider_status(STATE["df"]))
    return safe(go)

@app.post("/api/demo-mode")
def demo():
    b = request.get_json(force=True, silent=True) or {}
    STATE["demo_mode"] = bool(b.get("enabled", not STATE["demo_mode"]))
    return jsonify({"demo_mode": STATE["demo_mode"],
                    "note": "Demo mode uses precomputed backend results for fast presentation (no fabricated numbers)."})

@app.get("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    # Render provides PORT; FLASK_PORT remains the local-dev override.
    port = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", "5000")))
    print("\nUrban Food Delivery Intelligence", flush=True)
    if STATE["df"] is not None:
        print(f"Dataset loaded successfully", flush=True)
        print(f"Rows: {len(STATE['df'])}", flush=True)
        print(f"Columns: {len(STATE['raw'].columns) if STATE['raw'] is not None else len(STATE['df'].columns)}", flush=True)
    else:
        print(f"ERROR: dataset failed to load: {STATE.get('load_error')}", flush=True)
    print(f"Server starting on 0.0.0.0:{port} ...\n", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
