"""Central configuration + flexible column mapping for Urban Food Delivery Intelligence."""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")

# Dataset source. Downloaded ONCE via plain HTTPS (stdlib urllib, no extra
# dependencies) and cached as data/zomato_cleaned.csv; later runs reuse the file.
HF_DATASET = os.getenv("HF_DATASET", "allenborochin/zomato_delivery_EDA")
HF_FILE = os.getenv("HF_FILE", "zomato_cleaned.csv")
LOCAL_CSV_CANDIDATES = [
    os.path.join(DATA_DIR, "zomato_cleaned.csv"),
    os.path.join(DATA_DIR, "zomato.csv"),
    os.path.join(DATA_DIR, "delivery.csv"),
]

# MySQL settings (never hardcode password — env only)
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "urban_food_dw")

# App settings
SLA_DEFAULT_MINUTES = float(os.getenv("SLA_DEFAULT", "40"))
DELAY_THRESHOLD_MINUTES = float(os.getenv("DELAY_THRESHOLD", "35"))
RANDOM_STATE = 42
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL", "600"))

# ---------------------------------------------------------------------------
# Flexible column mapping.
# Actual HF dataset columns (verified Oct 2026):
#   ID, Delivery_person_ID, Delivery_person_Age, Delivery_person_Ratings,
#   Restaurant_latitude, Restaurant_longitude, Delivery_location_latitude,
#   Delivery_location_longitude, Order_Date, Time_Orderd, Time_Order_picked,
#   Weather_conditions, Road_traffic_density, Vehicle_condition,
#   Type_of_order, Type_of_vehicle, multiple_deliveries, Festival, City,
#   Time_taken (min), distance_km, delivery_speed
#
# Canonical logical names -> list of possible physical columns (first match wins)
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    "order_id": ["ID", "Order_ID", "order_id", "id"],
    "delivery_person_id": ["Delivery_person_ID", "Delivery_person_Id"],
    "age": ["Delivery_person_Age", "Age"],
    "rating": ["Delivery_person_Ratings", "Rating", "Delivery_person_Rating"],
    "rest_lat": ["Restaurant_latitude"],
    "rest_lon": ["Restaurant_longitude"],
    "del_lat": ["Delivery_location_latitude"],
    "del_lon": ["Delivery_location_longitude"],
    "order_date": ["Order_Date", "order_date", "Date"],
    "time_ordered": ["Time_Orderd", "Time_Ordered", "time_ordered"],
    "time_picked": ["Time_Order_picked", "Time_Order_Picked"],
    "weather": ["Weather_conditions", "Weather", "weather"],
    "traffic": ["Road_traffic_density", "Traffic", "road_traffic"],
    "vehicle_condition": ["Vehicle_condition"],
    "order_type": ["Type_of_order", "Order_Type"],
    "vehicle": ["Type_of_vehicle", "Vehicle", "vehicle_type"],
    "multiple_deliveries": ["multiple_deliveries", "Multiple_deliveries"],
    "festival": ["Festival", "festival"],
    "city": ["City", "city"],
    "delivery_time": ["Time_taken (min)", "Time_taken", "Delivery_Time", "delivery_time"],
    "distance": ["distance_km", "Distance", "distance"],
    "speed_label": ["delivery_speed", "Delivery_Speed"],
    "prep_time": ["Preparation_Time", "prep_time", "Prep_Time"],
    "category": ["Category", "Food_Category"],
    "area": ["Area", "Zone", "Locality"],
    "customer_id": ["Customer_ID", "customer_id", "User_ID"],
}

CATEGORICAL_MINING_DEFAULTS = ["weather", "traffic", "vehicle", "order_type", "city", "festival"]
NUMERIC_CLUSTER_DEFAULTS = ["delivery_time", "distance", "rating", "age", "multiple_deliveries"]
