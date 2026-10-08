"""Association rule mining with mlxtend (Apriori). Uses real categorical columns."""
import pandas as pd


def _bin_delay(v, thr=35):
    try:
        return "Delayed" if float(v) > thr else "OnTime"
    except Exception:
        return "Unknown"


def mine_rules(df, min_support=0.05, min_confidence=0.4, max_len=3):
    from mlxtend.frequent_patterns import apriori, association_rules
    import config
    # pick available categorical cols
    cols = []
    for logical in ["_weather", "_traffic", "_vehicle", "_order_type", "_city", "_festival", "_delay_band"]:
        if logical in df.columns:
            cols.append(logical)
    if "_is_delayed" in df.columns and "_delay_band" not in cols and "_delay_band" in df.columns:
        pass
    if len(cols) < 2:
        return {"rules": [], "message": "Not enough categorical columns for mining."}
    d = df[cols].copy()
    for c in cols:
        d[c] = d[c].fillna("Unknown").astype(str).str.strip().str.replace(" ", "_")
    # one-hot
    basket = pd.get_dummies(d, prefix=cols)
    # drop rare columns to bound size
    if basket.shape[1] > 120:
        keep = basket.mean().sort_values(ascending=False).head(120).index
        basket = basket[keep]
    try:
        freq = apriori(basket, min_support=min_support, use_colnames=True, max_len=max_len)
    except Exception as e:
        return {"rules": [], "message": f"Apriori failed: {e}"}
    if freq.empty:
        return {"rules": [], "message": "No frequent itemsets at this support. Lower minimum support."}
    try:
        rules = association_rules(freq, metric="confidence", min_threshold=min_confidence)
    except Exception as e:
        return {"rules": [], "message": f"Rule generation failed: {e}"}
    if rules.empty:
        return {"rules": [], "message": "No rules at this confidence. Lower minimum confidence."}
    rules = rules.sort_values("lift", ascending=False).head(40)
    out = []
    for _, r in rules.iterrows():
        ant = sorted(list(r["antecedents"]))
        con = sorted(list(r["consequents"]))
        out.append({
            "pattern": f"{' + '.join(ant)} → {' + '.join(con)}",
            "antecedent": ant, "consequent": con,
            "support": round(float(r["support"]), 4),
            "confidence": round(float(r["confidence"]), 4),
            "lift": round(float(r["lift"]), 4),
        })
    return {"rules": out, "count": len(out),
            "params": {"min_support": min_support, "min_confidence": min_confidence}}
