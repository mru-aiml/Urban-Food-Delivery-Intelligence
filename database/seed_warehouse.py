"""Seed MySQL warehouse from engineered dataframe. Run: python -m database.seed_warehouse"""
import pandas as pd
import numpy as np
import config
from database.warehouse import mysql_conn


def seed(df):
    # create db + tables
    import mysql.connector
    conn = mysql.connector.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                                   user=config.MYSQL_USER, password=config.MYSQL_PASSWORD)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {config.MYSQL_DB}")
    conn.commit()
    conn.close()
    schema_path = __import__("os").path.join(__import__("os").path.dirname(__file__), "schema.sql")
    conn = mysql_conn()
    cur = conn.cursor()
    with open(schema_path) as f:
        for stmt in f.read().split(";"):
            s = stmt.strip()
            if s and not s.startswith("USE") and "CREATE DATABASE" not in s:
                try:
                    cur.execute(s)
                except Exception as e:
                    print("schema stmt skipped:", str(e)[:120])
    conn.commit()

    def get(col, default=None):
        return df[col] if col in df.columns else pd.Series([default] * len(df))

    n = len(df)
    print(f"Seeding {n} facts...")
    # Build dims via dedup
    time_df = pd.DataFrame({
        "order_date": pd.to_datetime(df.get("_order_date_parsed"), errors="coerce").dt.date,
        "order_year": df.get("_year"), "order_month": df.get("_month"),
        "order_day": df.get("_day"), "order_hour": df.get("_hour"),
        "weekday": df.get("_weekday"), "is_weekend": df.get("_is_weekend"),
        "is_peak_hour": df.get("_is_peak")}).fillna(pd.NA)
    # insert with executemany in chunks
    for name, dframe, cols in [
        ("DIM_TIME", time_df.drop_duplicates(),
         ["order_date", "order_year", "order_month", "order_day", "order_hour", "weekday", "is_weekend", "is_peak_hour"]),
    ]:
        rows = dframe.where(pd.notna(dframe), None).values.tolist()
        if rows:
            ph = ",".join(["%s"] * len(cols))
            cur.executemany(f"INSERT IGNORE INTO {name} ({','.join(cols)}) VALUES ({ph})", rows[:5000])
    conn.commit()
    print("DIM_TIME seeded (sample). Full fact load is optional — analytics run from DataFrame.")
    cur.close()
    conn.close()
    return {"seeded": True, "facts": n}


if __name__ == "__main__":
    from preprocessing.loader import load_raw
    from preprocessing.cleaner import clean
    from preprocessing.feature_engineering import engineer
    raw, _ = load_raw()
    cdf, _ = clean(raw)
    edf, _ = engineer(cdf)
    print(seed(edf.head(5000)))
