-- Urban Food Delivery Intelligence — Star Schema (MySQL)
-- Run: mysql -u root -p < database/schema.sql
CREATE DATABASE IF NOT EXISTS urban_food_dw CHARACTER SET utf8mb4;
USE urban_food_dw;

CREATE TABLE IF NOT EXISTS DIM_TIME (
  time_id INT AUTO_INCREMENT PRIMARY KEY,
  order_date DATE NULL,
  order_year INT NULL,
  order_month INT NULL,
  order_day INT NULL,
  order_hour INT NULL,
  weekday VARCHAR(16) NULL,
  is_weekend TINYINT DEFAULT 0,
  is_peak_hour TINYINT DEFAULT 0,
  UNIQUE KEY uq_dim_time (order_date, order_hour),
  INDEX idx_year_month (order_year, order_month)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS DIM_LOCATION (
  location_id INT AUTO_INCREMENT PRIMARY KEY,
  city VARCHAR(64) NULL,
  area VARCHAR(64) NULL,
  rest_lat DOUBLE NULL,
  rest_lon DOUBLE NULL,
  del_lat DOUBLE NULL,
  del_lon DOUBLE NULL,
  INDEX idx_city (city)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS DIM_VEHICLE (
  vehicle_id INT AUTO_INCREMENT PRIMARY KEY,
  vehicle_type VARCHAR(64) NULL,
  vehicle_condition INT NULL,
  UNIQUE KEY uq_vehicle (vehicle_type, vehicle_condition)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS DIM_WEATHER (
  weather_id INT AUTO_INCREMENT PRIMARY KEY,
  weather VARCHAR(64) NULL,
  traffic VARCHAR(64) NULL,
  festival VARCHAR(16) NULL,
  UNIQUE KEY uq_weather (weather, traffic, festival)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS DIM_ORDER_CTX (
  order_ctx_id INT AUTO_INCREMENT PRIMARY KEY,
  order_type VARCHAR(64) NULL,
  category VARCHAR(64) NULL,
  multiple_deliveries INT NULL,
  UNIQUE KEY uq_ctx (order_type, category, multiple_deliveries)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS DIM_CUSTOMER (
  customer_id_key INT AUTO_INCREMENT PRIMARY KEY,
  delivery_person_id VARCHAR(64) NULL,
  delivery_person_age DOUBLE NULL,
  delivery_person_rating DOUBLE NULL,
  INDEX idx_dp (delivery_person_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS FACT_DELIVERY (
  fact_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_code VARCHAR(64) NULL,
  time_id INT NULL,
  location_id INT NULL,
  vehicle_id INT NULL,
  weather_id INT NULL,
  order_ctx_id INT NULL,
  customer_id_key INT NULL,
  distance_km DOUBLE NULL,
  delivery_time_min DOUBLE NULL,
  delivery_speed_kmph DOUBLE NULL,
  is_delayed TINYINT DEFAULT 0,
  speed_label VARCHAR(16) NULL,
  FOREIGN KEY (time_id) REFERENCES DIM_TIME(time_id),
  FOREIGN KEY (location_id) REFERENCES DIM_LOCATION(location_id),
  FOREIGN KEY (vehicle_id) REFERENCES DIM_VEHICLE(vehicle_id),
  FOREIGN KEY (weather_id) REFERENCES DIM_WEATHER(weather_id),
  FOREIGN KEY (order_ctx_id) REFERENCES DIM_ORDER_CTX(order_ctx_id),
  FOREIGN KEY (customer_id_key) REFERENCES DIM_CUSTOMER(customer_id_key),
  INDEX idx_time (time_id),
  INDEX idx_loc (location_id),
  INDEX idx_delay (is_delayed),
  INDEX idx_order_code (order_code)
) ENGINE=InnoDB;
