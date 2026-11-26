import time

import psycopg2

from pipeline.config import DATABASE_URL, SQL_DIR


def connect(retries: int = 10, delay: float = 2.0):
    """Bazaya qoşulur. Docker-də Postgres gec qalxa bilər, ona görə bir neçə dəfə cəhd edir."""
    for attempt in range(1, retries + 1):
        try:
            return psycopg2.connect(DATABASE_URL)
        except psycopg2.OperationalError:
            if attempt == retries:
                raise
            time.sleep(delay)


def create_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))


def drop_schema(conn) -> None:
    """Bütün cədvəlləri silir (yalnız --reset ilə, təmiz başlanğıc üçün)."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS fact_orders, rejected_orders, dim_customer, "
                    "dim_product, dim_date CASCADE")
    conn.commit()
