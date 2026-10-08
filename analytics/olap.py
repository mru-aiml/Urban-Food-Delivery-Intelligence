"""OLAP engine: roll-up, drill-down, slice, dice, pivot — computed with pandas."""
import pandas as pd

EXPLANATIONS = {
    "roll-up": "ROLL-UP aggregates data to a higher level of a hierarchy (e.g. Hour → Day → Month), reducing detail.",
    "drill-down": "DRILL-DOWN navigates to a lower, more detailed level (e.g. Month → Day → Hour).",
    "slice": "SLICE fixes one dimension to a single value (e.g. Weather = 'Rain'), producing a sub-cube.",
    "dice": "DICE applies filters on two or more dimensions (e.g. City=Pune AND Traffic=High).",
    "pivot": "PIVOT rotates the cube: rows × columns for a chosen measure (e.g. Vehicle × Weather → avg time).",
}

TIME_LEVELS = ["_year", "_month", "_day", "_hour"]
METRICS = {"avg_time": ("_dtime", "mean"), "count": ("_dtime", "count"),
           "avg_distance": ("_dist", "mean"), "delay_rate": ("_is_delayed", "mean"),
           "avg_rating": ("_rating", "mean")}


def available_dims(df):
    dims = []
    for c in ["_year", "_month", "_day", "_hour", "_city", "_vehicle",
              "_weather", "_traffic", "_order_type", "_festival", "_weekday"]:
        if c in df.columns:
            dims.append(c)
    return dims


def run_olap(df, op="roll-up", dimension="_hour", rows="_vehicle",
             columns="_weather", metric="avg_time", filters=None):
    filters = filters or {}
    d = df.copy()
    for k, v in filters.items():
        if k in d.columns and v not in (None, "", "all"):
            d = d[d[k] == v]
    mcol, agg = METRICS.get(metric, ("_dtime", "mean"))
    if mcol not in d.columns:
        return {"error": f"Metric column {mcol} unavailable in dataset.", "operation": op}
    op = op.lower().replace("_", "-")
    try:
        if op == "pivot":
            if rows not in d.columns or columns not in d.columns:
                return {"error": "Pivot rows/columns unavailable.", "operation": op}
            t = pd.pivot_table(d, values=mcol, index=rows, columns=columns,
                               aggfunc=agg, fill_value=0)
            if agg == "mean":
                t = t.round(2)
            table = [{"row": str(i), **{str(c): (round(float(v), 2) if agg == "mean" else int(v)) for c, v in row.items()}} for i, row in t.to_dict("index").items()]
            chart = [{"label": str(i), "value": round(float(d[d[rows] == i][mcol].mean()), 2)} for i in t.index[:12]]
            return {"operation": op, "explanation": EXPLANATIONS[op], "dimensions": {"rows": rows, "columns": columns},
                    "metric": metric, "filters": filters, "table": table, "chart": chart}
        # roll-up / drill-down / slice / dice all produce grouped table + bar chart
        dim = dimension if dimension in d.columns else (available_dims(d)[0] if available_dims(d) else None)
        if not dim:
            return {"error": "No OLAP dimensions available.", "operation": op}
        if op == "roll-up":
            # move one level up the time hierarchy when possible
            if dim in TIME_LEVELS:
                i = TIME_LEVELS.index(dim)
                dim = TIME_LEVELS[max(0, i - 1)] if TIME_LEVELS[max(0, i - 1)] in d.columns else dim
        elif op == "drill-down":
            if dim in TIME_LEVELS:
                i = TIME_LEVELS.index(dim)
                dim = TIME_LEVELS[min(len(TIME_LEVELS) - 1, i + 1)] if TIME_LEVELS[min(len(TIME_LEVELS)-1, i+1)] in d.columns else dim
        g = d.dropna(subset=[dim]).groupby(dim)[mcol].agg(agg)
        if agg == "mean":
            g = g.round(2)
        table = [{"label": str(k), "value": (round(float(v), 2) if agg == "mean" else int(v))} for k, v in g.sort_values().items()]
        return {"operation": op, "explanation": EXPLANATIONS.get(op, ""),
                "dimensions": {"dimension": dim}, "metric": metric,
                "filters": filters, "table": table[:50], "chart": table[:30]}
    except Exception as e:
        return {"error": str(e), "operation": op}
