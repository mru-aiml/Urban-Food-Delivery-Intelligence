# CASE STUDY: Urban Food Delivery Intelligence System Using Data Warehousing and Data Mining

## 1. Introduction

The Urban Food Delivery Intelligence System is a web-based analytical project that studies
food-delivery operations using a real dataset of approximately **38,964 delivery records**
with **22 attributes**. Instead of being a food-ordering app, it is a decision-support
dashboard: it takes raw delivery records and turns them into charts, patterns and predictions.

The system helps analyse delivery time, distance, traffic conditions, weather, vehicle type,
city, delivery-person ratings and overall delivery patterns. It is built as a BTech
Data Warehousing and Data Mining (DWM) mini-project, so every concept in the syllabus —
ETL, data warehouse, OLAP, association rules, clustering, classification — is mapped to a
working module in the website.

## 2. Problem Statement

Food delivery platforms generate large amounts of operational data every day: order times,
rider details, traffic and weather conditions, distances and delivery durations. But raw
delivery records do not directly give useful managerial insights. A manager cannot look at
39,000 rows in a spreadsheet and answer questions like "when are delays worst?", "which
conditions cause late deliveries?" or "which orders are risky before dispatch?".

This system transforms raw delivery data into useful information for:

- operational analysis of day-to-day delivery performance;
- delivery performance and delay analysis across city, traffic, weather and vehicle;
- pattern discovery from historical orders;
- risk prediction for new or upcoming deliveries;
- decision support through dashboards, explanations and recommendations.

## 3. Objectives

1. Analyse food-delivery data from a real public dataset.
2. Build a data warehouse-oriented analytical structure (facts and dimensions).
3. Perform OLAP operations (roll-up, drill-down, slice, dice, pivot).
4. Discover hidden patterns using association rule mining.
5. Group delivery behaviour using K-Means clustering.
6. Predict delivery-delay risk with a classification model.
7. Detect unusual delivery behaviour with anomaly detection.
8. Provide visual dashboards for managers and analysts.
9. Explain possible factors associated with delays for any selected order.
10. Generate actionable recommendations from the observed evidence.

## 4. Dataset

- Dataset: `zomato_delivery_EDA`
- Source (Hugging Face): `allenborochin/zomato_delivery_EDA`
- File used: `zomato_cleaned.csv`
- Size: **38,964 rows × 22 columns**

Important fields actually present in the file:

`Delivery_person_ID`, `Delivery_person_Age`, `Delivery_person_Ratings`,
`Restaurant_latitude`, `Restaurant_longitude`, `Delivery_location_latitude`,
`Delivery_location_longitude`, `Order_Date`, `Time_Orderd`, `Time_Order_picked`,
`Weather_conditions`, `Road_traffic_density`, `Vehicle_condition`, `Type_of_order`,
`Type_of_vehicle`, `multiple_deliveries`, `Festival`, `City`, `Time_taken (min)`,
`distance_km`, `delivery_speed` (plus an `ID` column).

## 5. Technologies Used

- **Frontend:** HTML, CSS, JavaScript, Chart.js (charts), Leaflet (hotspot maps where
  coordinates exist, otherwise a city-table fallback).
- **Backend:** Python, Flask (REST APIs served to the dashboard).
- **Data processing:** Pandas, NumPy.
- **Data mining:** mlxtend (Apriori association rules), scikit-learn (K-Means,
  RandomForest classifier, IsolationForest anomaly detection, scalers).
- **Machine learning:** K-Means clustering, Random Forest / classification model for
  delay risk, Isolation Forest for anomalies.
- **Deployment:** Render (free Python web service with Gunicorn).
- **Dataset source:** Hugging Face (downloaded once over HTTPS, then cached locally).
- **Database:** MySQL support with DataFrame fallback — if no MySQL server is reachable,
  the application serves all analytics from its in-memory engineered DataFrame, so MySQL
  is optional and not required for the deployed application.

## 6. System Architecture

Data flows in one direction, from raw records to the dashboard:

```text
zomato_cleaned.csv (Hugging Face / local data/)
        |
        v
ETL / preprocessing (loader -> cleaner -> feature engineering)
        |
        v
Data warehouse-oriented layer (engineered DataFrame + optional MySQL star schema)
        |
        v
OLAP (roll-up, drill-down, slice, dice, pivot)
        |
        v
Data Mining / Machine Learning (rules, clusters, classifier, anomalies)
        |
        v
Flask APIs (/api/overview, /api/olap, /api/clusters, ...)
        |
        v
HTML / CSS / JavaScript dashboard (Chart.js + Leaflet)
```

## 7. ETL Process

- **Extract:** the backend loads `data/zomato_cleaned.csv`. If the file is missing, it is
  downloaded once from Hugging Face over plain HTTPS and cached; later runs reuse it.
  Column names are resolved through a flexible mapping (`config.COLUMN_MAP`), so the code
  adapts to the actual file instead of assuming names.
- **Transform:** whitespace and common null tokens are cleaned; duplicates removed;
  numeric columns coerced; impossible values flagged (e.g. delivery time ≤ 0 or > 180 min,
  distance ≤ 0 or > 100 km); order dates parsed; hour, weekday/weekend and peak-hour flags
  derived; delivery speed (km/h) computed from distance and time; delay flags and severity
  bands created from a 35-minute delay threshold; categorical fields normalised.
- **Load:** the cleaned and engineered data is loaded into the application's analytical
  layer (in-memory warehouse tables, plus an optional MySQL star schema), with ETL metrics
  (rows loaded, duplicates removed, invalid values flagged) recorded for the Data
  Warehouse page.

## 8. Data Warehouse

The project uses a **star schema**: one central fact table holding measurements, linked to
smaller dimension tables holding descriptive context.

- **FACT_DELIVERY** — grain: one row per delivered order. Facts (measures) such as
  distance, delivery time, speed and delay flag, plus foreign keys to each dimension.
- **DIM_TIME** — order date with Year → Month → Day → Hour hierarchy, weekday, weekend
  and peak-hour flags.
- **DIM_LOCATION** — city and area plus restaurant and delivery coordinates.
- **DIM_VEHICLE** — vehicle type and condition.
- **DIM_WEATHER** — weather, traffic density and festival context.
- **DIM_ORDER_CTX** — order type, category and multiple-delivery info.
- **DIM_CUSTOMER** — courier details (delivery-person id, age, rating) under a surrogate key.

Facts are the numbers we analyse (time, distance, delay); dimensions are the "by what"
we slice them (by city, by traffic, by hour). The schema browser works from the
application itself; a live MySQL server is optional because of the DataFrame fallback.

## 9. OLAP Operations

- **Roll-up (City → overall):** average delivery time per city rolled up to one overall average.
- **Drill-down (City → Traffic → Weather):** start from a city, break it down by traffic
  level, then further by weather within a traffic level.
- **Slice (Traffic = High):** fix one dimension value and view all metrics for it.
- **Dice (Traffic = High AND Weather = Cloudy):** fix values on two or more dimensions
  and analyse that sub-cube.
- **Pivot (City vs Traffic, average delivery time):** rotate the cube so cities form rows,
  traffic levels form columns, and each cell shows average delivery time.

## 10. Data Mining

### Association Rule Mining (Apriori, via mlxtend)

Each order is converted into items such as traffic level, weather, vehicle, city and delay
band. The algorithm reports rules with **support** (how often the pattern occurs),
**confidence** (how often the consequent follows the antecedent) and **lift** (how much
more likely than chance). Example pattern: "Jam traffic → delayed". Important: association
does **not** prove causation — the dashboard labels these as evidence, not proof.

### K-Means Clustering

Deliveries are grouped by operational characteristics (time, distance, rating, age,
multiple deliveries). Each cluster gets an automatic plain-English name (e.g.
long-distance deliveries, cited from its profile), so managers can see the main
"behaviour segments" in the data.

### Classification (delay prediction)

A RandomForest model learns to predict delay risk from distance, rating, hour, traffic,
weather, vehicle, city and related features, reporting accuracy, confusion matrix and
feature importances. The same model powers the Risk Predictor and the per-order explainer.

### Anomaly Detection (IsolationForest)

Orders whose time/distance pattern deviates strongly from peer orders are flagged as
anomalies for review (possible data issues or genuinely unusual trips).

## 11. Website Modules

- **Overview:** KPIs, 8 charts and auto-generated insights from the full dataset.
- **Delivery Intelligence:** filterable metrics, time-vs-distance scatter, performance
  summary and an SLA monitor with adjustable threshold.
- **OLAP Explorer:** interactive roll-up, drill-down, slice, dice and pivot on the cube.
- **Data Mining:** Apriori rules, K-Means clusters, classifier scores and anomalies.
- **Risk Predictor:** delay probability and expected time for a hypothetical order.
- **Why Was It Late?:** contributing factors and recommended action for a chosen order.
- **Hotspot Intelligence:** delay heatmap grid where coordinates exist, plus city table.
- **Smart Recommendations:** problem → evidence → action → impact cards from the data.
- **Data Warehouse:** star-schema visual plus ETL metrics.
- **Data Quality:** completeness, validity, consistency and uniqueness scores.
- **Dataset Explorer:** searchable, paginated order browser with SLA bands.
- **About Project:** concept summary mapping syllabus topics to modules.

## 12. Key Dashboard Results

Computed live from `zomato_cleaned.csv` (38,964 records) — not manually entered:

- Total Orders: **38,964**
- Average Delivery Time: **26.58 min**
- Average Distance: **9.77 km**
- Average Rating: **4.63**
- On-Time Rate: **81.91%**
- Delayed Orders: **7,048**
- Average Speed: **23.59 km/h**
- Median Delivery Time: **26 min**

These values are computed from the dataset on every load and are not manually entered.

## 13. Unique Features

1. **Why Was This Delivery Late?** — per-order factor breakdown with a suggested action.
2. **Delivery Risk Predictor** — delay probability before dispatch, plus what-if comparison.
3. **OLAP Explorer** — five real cube operations with viva-style explanations.
4. **Hidden Pattern Discovery** — Apriori rules with support, confidence and lift.
5. **Delivery Behaviour Clustering** — auto-named K-Means segments.
6. **Hotspot Intelligence** — geo grid heatmap with city fallback (never invents coordinates).
7. **Smart Recommendations** — evidence-linked actions, not generic tips.
8. **Data Quality monitoring** — dimension scores instead of blind trust in the CSV.
9. **Integrated DWM + ML dashboard** — warehouse, OLAP, mining and prediction in one app.

The system does not only show historical charts; it combines analytics and data mining
to support decisions.

## 14. Benefits

- **Delivery operations:** spot peak pressure hours and high-delay zones for rostering.
- **Restaurants:** realistic prep-plus-dispatch expectations in bad traffic/weather.
- **Delivery managers:** SLA tracking, hotspot lists and evidence-backed actions.
- **Business analysts:** sliceable cube and exportable patterns for reports.
- **Customers (indirectly):** better ETAs and proactive delay communication driven by the
  same delay factors the system measures.

Claims stay within what historical analysis can support; the system advises, it does not
control live dispatch.

## 15. Limitations

The public dataset does not contain actual customer identity, restaurant preparation time,
live traffic, live GPS tracking or real-time operational feeds. Timestamps are order-level
(not second-by-second tracking), and some columns need cleaning before use. Therefore the
system should be treated as an **analytical prototype** rather than a live production
food-delivery platform.

## 16. Future Scope

Real-time delivery tracking, live traffic APIs, restaurant preparation-time integration,
real customer/order history, a cloud data warehouse, real-time streaming, better
forecasting, a mobile application, real-time alerts and more advanced explainable AI.

## 17. Conclusion

This project shows how Data Warehousing, OLAP, Data Mining, Machine Learning and
visualisation can convert raw food-delivery records into useful operational insights.
Starting from ~39K real delivery rows, the system builds an ETL pipeline, a star-schema
warehouse layer, an OLAP cube, mining models and a dashboard that together answer what
happened, why it happened, what may happen next and what should be done about it.
