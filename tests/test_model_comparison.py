"""Regression tests for algorithm comparison + live-data status.

All metrics must be computed from the real dataset (no hardcoded scores).
Run: pytest tests/test_model_comparison.py
"""
import app as A
from mining import model_comparison as mc


def _df():
    assert A.STATE["df"] is not None
    return A.STATE["df"]


def test_classification_comparison_real():
    r = mc.compare_classification(_df())
    assert r["category"] == "classification"
    names = [m["name"] for m in r["models"]]
    assert names == ["Logistic Regression", "Decision Tree", "Random Forest", "Gradient Boosting"]
    for m in r["models"]:
        for k in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            assert isinstance(m[k], float) and 0.0 <= m[k] <= 1.0, (m["name"], k)
        assert m["train_time_s"] >= 0 and m["predict_time_s"] >= 0
        assert len(m["confusion_matrix"]) == 2
    assert r["class_balance_test"]["n_train"] + r["class_balance_test"]["n_test"] > 30000


def test_clustering_comparison_real():
    r = mc.compare_clustering(_df())
    assert [a["name"] for a in r["algorithms"]] == ["K-Means", "Agglomerative", "DBSCAN (eps=0.8)"]
    for a in r["algorithms"]:
        assert a["n_clusters"] >= 1 and a["runtime_s"] >= 0
        if a.get("silhouette") is not None:
            assert -1.0 <= a["silhouette"] <= 1.0


def test_association_comparison_real():
    r = mc.compare_association(_df())
    assert [a["name"] for a in r["algorithms"]] == ["Apriori", "FPGrowth"]
    for a in r["algorithms"]:
        assert a["n_rules"] > 0
        assert a["avg_confidence"] > 0 and a["avg_lift"] > 0


def test_anomaly_comparison_real():
    r = mc.compare_anomaly(_df())
    assert [d["name"] for d in r["detectors"]] == ["Isolation Forest", "Local Outlier Factor"]
    for d in r["detectors"]:
        assert d["n_anomalies"] > 0 and 0.0 < d["anomaly_pct"] < 100.0


def test_live_status_honest_without_credentials():
    from integrations import live_data_provider as lp
    lp._cache.clear()
    lp._last_attempt.clear()
    c = A.app.test_client()
    r = c.get("/api/live-status")
    assert r.status_code == 200
    import json
    j = json.loads(r.get_data(as_text=True))
    assert j["available"] is False and j["mode"] == "historical"
    assert j["historical_rows"] == 38964
    body = r.get_data(as_text=True).lower()
    assert "historical" in body
    assert "password" not in body and "api_key" not in body
