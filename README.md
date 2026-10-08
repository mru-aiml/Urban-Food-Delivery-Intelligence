# Urban Food Delivery Intelligence System
A **Data Warehousing & Data Mining (DWM)** BI platform on the Zomato delivery dataset (~39K rows). Not a food-ordering site — an operations intelligence tool: *Don't just show what happened. Discover why, predict what may happen, recommend what to do.*

## Features
- Overview dashboard (8 KPIs, 8 charts, live insights from real data)
- Delivery Intelligence (filters, scatter, SLA monitor with adjustable threshold)
- OLAP Explorer (roll-up, drill-down, slice, dice, pivot + viva explanations)
- Data Mining Center (Apriori via mlxtend, K-Means with auto-names, RandomForest + confusion matrix, IsolationForest)
- Risk Predictor + What-If simulator (trained model, feature contributions)
- Why-Was-It-Late explainer (per-order evidence, "association not causation")
- Hotspot Intelligence (Leaflet grid heatmap when lat/lon exist + city table fallback — never invents coordinates)
- Smart Recommendations (Problem→Evidence→Action→Impact)
- Data Warehouse explorer (star schema visual, ETL metrics), Data Quality center (score), Dataset explorer (paginated)
- Demo mode toggle (precomputed backend results, no fabricated numbers)

## Tech
Flask, pandas, numpy, scikit-learn, mlxtend, joblib, MySQL (`mysql-connector-python`), Chart.js, Leaflet, vanilla JS.

## Dataset
`allenborochin/zomato_delivery_EDA` → `zomato_cleaned.csv` (~39K rows). Downloaded once via plain HTTPS and cached as `data/zomato_cleaned.csv` (no `huggingface_hub`/`datasets` needed). Column mapping in `config.COLUMN_MAP` adapts to actual names (`ID, Delivery_person_Age, Weather_conditions, Road_traffic_density, Type_of_vehicle, City, Time_taken (min), distance_km, ...`). If a requested field is absent the UI marks it unavailable — no fake stats.

## Setup (Windows)
```powershell
python -m venv .venv; .\.venv\Scripts\Activate
pip install -r requirements.txt
copy .env.example .env   # set MYSQL_PASSWORD if needed
# MySQL (optional — app runs offline without it):
mysql -u root -p -e "CREATE DATABASE urban_food_dw;"
mysql -u root -p urban_food_dw < database\schema.sql
python -m database.seed_warehouse   # optional
# Run
python app.py   # → http://127.0.0.1:5000
```
Without MySQL the app uses the engineered DataFrame directly and reports "MySQL offline" gracefully.

## API
`GET /api/health /api/overview /api/delivery-analytics /api/orders?page&size&q&band&sla /api/orders/<id> /api/orders/<id>/explanation /api/dataset-info /api/data-quality /api/warehouse/schema /api/olap(GET meta) POST /api/olap /api/association-rules(GET+POST) /api/clusters(GET+POST) /api/classification /api/anomalies /api/hotspots /api/recommendations POST /api/predict-delay /api/what-if /api/demo-mode`

## Deploying on Render
`render.yaml` defines a free Python web service (see file for details):
- Build: `pip install -r requirements.txt` (Python 3.13.7)
- Start: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- Health check: `/api/health`
- The app reads Render's `PORT` env var (falls back to `FLASK_PORT`/5000 locally) and binds `0.0.0.0` with `debug=False`.
- On first boot it downloads `zomato_cleaned.csv` once from Hugging Face and caches it as `data/zomato_cleaned.csv` (ephemeral on Render — re-downloads automatically when missing). No `huggingface_hub`/`datasets` packages required.
- MySQL is optional: without `MYSQL_*` env vars the app serves everything from its DataFrame warehouse fallback. Never commit `.env` (see `.env.example`).

## DWM concepts
ETL + quality metrics, star schema/surrogate keys, OLAP ops, support/confidence/lift, K-Means profiling, precision/recall/F1, anomaly detection, SLA/delay thresholds.


## Structure
See spec §4. `models/` holds `delay_model.pkl, cluster_model.pkl, scaler.pkl` (trained on first classification call).
