"""Warehouse layer: MySQL star-schema load with graceful fallback to in-memory.
If MySQL is unreachable, analytics continue from the engineered DataFrame."""
import pandas as pd
import config


def mysql_conn(db=True):
    import mysql.connector
    kw = dict(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
              user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    if db:
        kw["database"] = config.MYSQL_DB
    return mysql.connector.connect(**kw)


def warehouse_available():
    try:
        c = mysql_conn()
        c.close()
        return True, "connected"
    except Exception as e:
        return False, str(e)


def star_schema_view():
    """Return schema description for the visual explorer (works w/o live DB)."""
    return {
        "tables": [
            {"name": "FACT_DELIVERY", "type": "fact",
             "columns": ["fact_id PK", "order_code", "time_id FK", "location_id FK",
                         "vehicle_id FK", "weather_id FK", "order_ctx_id FK",
                         "customer_id_key FK", "distance_km", "delivery_time_min",
                         "delivery_speed_kmph", "is_delayed", "speed_label"],
             "description": "Grain: one row per delivered order. All measures + foreign keys."},
            {"name": "DIM_TIME", "type": "dimension",
             "columns": ["time_id PK", "order_date", "order_year", "order_month",
                         "order_day", "order_hour", "weekday", "is_weekend", "is_peak_hour"],
             "description": "Time hierarchy: Year → Month → Day → Hour (roll-up / drill-down)."},
            {"name": "DIM_LOCATION", "type": "dimension",
             "columns": ["location_id PK", "city", "area", "rest_lat", "rest_lon", "del_lat", "del_lon"],
             "description": "Location hierarchy: City → Area + geo coordinates for hotspots."},
            {"name": "DIM_VEHICLE", "type": "dimension",
             "columns": ["vehicle_id PK", "vehicle_type", "vehicle_condition"],
             "description": "Delivery dimension: vehicle type + condition."},
            {"name": "DIM_WEATHER", "type": "dimension",
             "columns": ["weather_id PK", "weather", "traffic", "festival"],
             "description": "Delivery context: weather × traffic density × festival."},
            {"name": "DIM_ORDER_CTX", "type": "dimension",
             "columns": ["order_ctx_id PK", "order_type", "category", "multiple_deliveries"],
             "description": "Order context: type / category / batched deliveries."},
            {"name": "DIM_CUSTOMER", "type": "dimension",
             "columns": ["customer_id_key PK", "delivery_person_id", "delivery_person_age", "delivery_person_rating"],
             "description": "Courier dimension (surrogate key)."},
        ],
        "relationships": [
            "DIM_TIME 1—N FACT_DELIVERY", "DIM_LOCATION 1—N FACT_DELIVERY",
            "DIM_VEHICLE 1—N FACT_DELIVERY", "DIM_WEATHER 1—N FACT_DELIVERY",
            "DIM_ORDER_CTX 1—N FACT_DELIVERY", "DIM_CUSTOMER 1—N FACT_DELIVERY",
        ]
    }
