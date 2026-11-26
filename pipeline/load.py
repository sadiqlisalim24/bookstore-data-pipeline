"""Təmizlənmiş məlumatların PostgreSQL-ə yüklənməsi.

Hər yerdə INSERT ... ON CONFLICT (upsert) istifadə olunur: sətir varsa yenilənir,
yoxdursa əlavə olunur. Buna görə skripti neçə dəfə işə salsaq da, məlumat ikiləşmir.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import pandas as pd
from psycopg2.extras import execute_values

from pipeline import cleaning
from pipeline.config import (BASE_ORDERS_FILE, CUSTOMERS_FILE, DATA_DIR,
                             PRODUCTS_FILE)
from pipeline.db import create_schema

log = logging.getLogger(__name__)


def read_csv(path: Path) -> pd.DataFrame:
    # Hər şeyi mətn kimi oxuyuruq, tipləri cleaning.py özü çevirir.
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def _rows(df: pd.DataFrame) -> list[tuple]:
    return [tuple(None if pd.isna(v) else v for v in row)
            for row in df.itertuples(index=False, name=None)]


def upsert_customers(cur, df: pd.DataFrame) -> None:
    execute_values(cur, """
        INSERT INTO dim_customer (customer_id, full_name, city, signup_date, email, is_known)
        VALUES %s
        ON CONFLICT (customer_id) DO UPDATE SET
            full_name = EXCLUDED.full_name, city = EXCLUDED.city,
            signup_date = EXCLUDED.signup_date, email = EXCLUDED.email,
            is_known = TRUE, updated_at = now()
        WHERE (dim_customer.full_name, dim_customer.city, dim_customer.signup_date,
               dim_customer.email, dim_customer.is_known)
              IS DISTINCT FROM
              (EXCLUDED.full_name, EXCLUDED.city, EXCLUDED.signup_date, EXCLUDED.email, TRUE)
    """, [r + (True,) for r in _rows(df)])


def upsert_products(cur, df: pd.DataFrame) -> None:
    execute_values(cur, """
        INSERT INTO dim_product (product_id, title, category, list_price, is_known)
        VALUES %s
        ON CONFLICT (product_id) DO UPDATE SET
            title = EXCLUDED.title, category = EXCLUDED.category,
            list_price = EXCLUDED.list_price, is_known = TRUE, updated_at = now()
        WHERE (dim_product.title, dim_product.category, dim_product.list_price, dim_product.is_known)
              IS DISTINCT FROM (EXCLUDED.title, EXCLUDED.category, EXCLUDED.list_price, TRUE)
    """, _rows(df))


def add_unknown_members(cur, orders: pd.DataFrame) -> None:
    """Sifarişdə olan, amma kataloqda olmayan məhsul/müştəri üçün 'naməlum' sətir yaradır.

    Belə sifarişi atmırıq (gəliri itirməmək üçün), amma is_known = FALSE ilə işarələyirik.
    DO NOTHING: real məlumat artıq varsa, ona toxunmuruq.
    """
    products = sorted(orders["product_id"].unique())
    execute_values(cur, """
        INSERT INTO dim_product (product_id, title, category, list_price, is_known)
        VALUES %s ON CONFLICT (product_id) DO NOTHING
    """, [(p, f"Naməlum məhsul ({p})", "Naməlum", None, False) for p in products])

    customers = sorted(orders["customer_id"].dropna().unique())
    if customers:
        execute_values(cur, """
            INSERT INTO dim_customer (customer_id, full_name, city, is_known)
            VALUES %s ON CONFLICT (customer_id) DO NOTHING
        """, [(c, None, "Naməlum", False) for c in customers])


def upsert_dates(cur, orders: pd.DataFrame) -> None:
    start, end = orders["order_ts"].min().date(), orders["order_ts"].max().date()
    rows, day = [], start
    while day <= end:
        rows.append((int(day.strftime("%Y%m%d")), day, day.year, (day.month - 1) // 3 + 1,
                     day.month, day.strftime("%Y-%m"), day.day, day.isoweekday(),
                     day.isoweekday() >= 6))
        day += timedelta(days=1)
    execute_values(cur, """
        INSERT INTO dim_date (date_key, full_date, year, quarter, month, year_month,
                              day, iso_weekday, is_weekend)
        VALUES %s ON CONFLICT (date_key) DO NOTHING
    """, rows)


def upsert_orders(cur, orders: pd.DataFrame) -> tuple[int, int]:
    """Sifarişləri yükləyir. (yeni, yenilənmiş) sayını qaytarır.

    Mövcud sifariş yalnız iki şərtlə yenilənir:
      1) nəsə həqiqətən dəyişibsə (status və s.);
      2) gələn fayl köhnə fayldan "yeni"dirsə (fayl adları tarixlə adlanır və
         əlifba sırası = xronoloji sıra). Beləliklə köhnə fayl təkrar yüklənəndə
         yeni statusu geri qaytarmır.
    RETURNING (xmax = 0) Postgres-də sətrin yeni əlavə olunduğunu (TRUE)
    və ya yeniləndiyini (FALSE) göstərir.
    """
    df = orders.assign(date_key=orders["order_ts"].dt.strftime("%Y%m%d").astype(int))
    cols = ["order_id", "order_ts", "date_key", "customer_id", "product_id",
            "quantity", "unit_price", "status", "source_file"]
    result = execute_values(cur, """
        INSERT INTO fact_orders (order_id, order_ts, date_key, customer_id, product_id,
                                 quantity, unit_price, status, source_file)
        VALUES %s
        ON CONFLICT (order_id) DO UPDATE SET
            order_ts = EXCLUDED.order_ts, date_key = EXCLUDED.date_key,
            customer_id = EXCLUDED.customer_id, product_id = EXCLUDED.product_id,
            quantity = EXCLUDED.quantity, unit_price = EXCLUDED.unit_price,
            status = EXCLUDED.status, source_file = EXCLUDED.source_file,
            updated_at = now()
        WHERE EXCLUDED.source_file >= fact_orders.source_file
          AND (fact_orders.order_ts, fact_orders.customer_id, fact_orders.product_id,
               fact_orders.quantity, fact_orders.unit_price, fact_orders.status)
              IS DISTINCT FROM
              (EXCLUDED.order_ts, EXCLUDED.customer_id, EXCLUDED.product_id,
               EXCLUDED.quantity, EXCLUDED.unit_price, EXCLUDED.status)
        RETURNING (xmax = 0)
    """, [tuple(r) for r in df[cols].astype(object).where(df[cols].notna(), None).values],
        fetch=True, page_size=1000)
    inserted = sum(1 for (is_new,) in result if is_new)
    return inserted, len(result) - inserted


def save_rejected(cur, rejected: pd.DataFrame) -> None:
    if rejected.empty:
        return
    cols = ["order_id", "source_file", "reason", "order_ts", "customer_id",
            "product_id", "quantity", "unit_price", "status"]
    execute_values(cur, f"""
        INSERT INTO rejected_orders ({", ".join(cols)}) VALUES %s
        ON CONFLICT (order_id, source_file) DO UPDATE SET reason = EXCLUDED.reason
    """, _rows(rejected[cols]))


def load_orders_file(conn, path: Path) -> None:
    raw = read_csv(path)
    orders, rejected = cleaning.clean_orders(raw, path.name)
    with conn.cursor() as cur:
        add_unknown_members(cur, orders)
        upsert_dates(cur, orders)
        inserted, updated = upsert_orders(cur, orders)
        save_rejected(cur, rejected)
    log.info("%s: oxundu %s, yeni %s, yeniləndi %s, rədd edildi %s",
             path.name, len(raw), inserted, updated, len(rejected))


def full_load(conn, data_dir: Path = DATA_DIR) -> None:
    """Əsas yükləmə: customers, products və avqust-oktyabr sifarişləri."""
    create_schema(conn)
    orders_raw = read_csv(data_dir / BASE_ORDERS_FILE)
    customers = cleaning.clean_customers(read_csv(data_dir / CUSTOMERS_FILE))
    products = cleaning.clean_products(read_csv(data_dir / PRODUCTS_FILE), orders_raw)
    with conn.cursor() as cur:
        upsert_customers(cur, customers)
        upsert_products(cur, products)
    log.info("Müştərilər: %s, məhsullar: %s", len(customers), len(products))
    load_orders_file(conn, data_dir / BASE_ORDERS_FILE)
    conn.commit()


def incremental_load(conn, path: Path) -> None:
    """Yeni sifariş faylını mövcud məlumatın üzərinə yükləyir."""
    create_schema(conn)
    load_orders_file(conn, path)
    conn.commit()
