"""Build-time precomputation of algorithm-comparison results.

Runs once during `pip install`-adjacent build step (see render.yaml) so that
production requests are served instantly from cache instead of retraining on
a cold worker (which exceeds request timeouts on small instances).

Usage:  python -m mining.precompute_comparison

Always exits 0: a failed category only logs and leaves the runtime lazy
fallback (compute-on-first-request) in place. Writes
models/comparison_cache.json inside the image; never commits anything.
"""
import time
import traceback


def main():
    import app as app_module
    from mining import model_comparison as mc

    df = app_module.STATE.get("df")
    if df is None:
        print("[precompute] dataset not loaded; skipping:",
              app_module.STATE.get("load_error"), flush=True)
        return
    jobs = [("classification", lambda: mc.compare_classification(df)),
            ("clustering", lambda: mc.compare_clustering(df)),
            ("association", lambda: mc.compare_association(df)),
            ("anomaly", lambda: mc.compare_anomaly(df))]
    for name, fn in jobs:
        t0 = time.time()
        try:
            out = fn()
            print(f"[precompute] {name}: ok in {time.time() - t0:.1f}s "
                  f"(cached={out.get('cached')})", flush=True)
        except Exception as e:
            print(f"[precompute] {name}: FAILED {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()


if __name__ == "__main__":
    main()
