from datetime import date, datetime

import pandas as pd

from pipeline.cleaning import (DATE_FORMATS, TIMESTAMP_FORMATS, clean_customers,
                               clean_orders, clean_products, normalize_key,
                               parse_datetime, parse_price)


def test_parse_price_formats():
    assert parse_price("22 AZN") == 22.0
    assert parse_price("25,00") == 25.0
    assert parse_price("12.5 AZN") == 12.5
    assert parse_price("") is None
    assert parse_price("N/A") is None
    assert parse_price("inf") is None


def test_parse_dates_day_first():
    assert parse_datetime("14/03/2025", DATE_FORMATS) == datetime(2025, 3, 14)
    assert parse_datetime("19.06.2025", DATE_FORMATS) == datetime(2025, 6, 19)
    assert parse_datetime("2024-07-04", DATE_FORMATS) == datetime(2024, 7, 4)
    assert parse_datetime("05.10.2026 22:15", TIMESTAMP_FORMATS) == datetime(2026, 10, 5, 22, 15)
    assert parse_datetime("2026-10-28T03:29:40", TIMESTAMP_FORMATS) == datetime(2026, 10, 28, 3, 29, 40)
    assert parse_datetime("bad", DATE_FORMATS) is None


def test_normalize_key_handles_dotted_capital_i():
    assert normalize_key(" BƏDİİ ") == "bədii"


def test_clean_customers_dedup_and_city():
    raw = pd.DataFrame({
        "customer_id": ["C1", "C1", "C2"],
        "full_name": ["ELNUR HƏSƏNLI", "Elnur Həsənli", "Aysel"],
        "city": ["BAKU", " Bakı", "GANJA"],
        "signup_date": ["2024-04-13", "2024-04-13", "31.12.2024"],
        "email": ["a@example.com", "a@example.com", ""],
    })
    df = clean_customers(raw)
    assert list(df["customer_id"]) == ["C1", "C2"]
    assert df.loc[0, "full_name"] == "Elnur Həsənli"
    assert list(df["city"]) == ["Bakı", "Gəncə"]
    assert df.loc[1, "signup_date"] == date(2024, 12, 31)
    assert df.loc[1, "email"] is None


def test_clean_products_fills_missing_price_from_orders():
    raw = pd.DataFrame({"product_id": ["P1", "P2"], "title": ["A", "B"],
                        "category": ["biznes ", "IT"], "price": ["", "6 AZN"]})
    orders = pd.DataFrame({"product_id": ["P1", "P1", "P1"],
                           "unit_price": ["12.50", "12.50", "10.00"]})
    df = clean_products(raw, orders)
    assert list(df["category"]) == ["Biznes", "Texnologiya"]
    assert list(df["list_price"]) == [12.5, 6.0]


def test_clean_orders_rules():
    raw = pd.DataFrame({
        "order_id": ["O1", "O1", "O2", "O3"],
        "order_ts": ["2026-08-01 10:00:00", "2026-08-01 10:00:00", "01.09.2026 12:30", "2026-09-02T08:00:00"],
        "customer_id": ["C1", "C1", "", "C2"],
        "product_id": ["P1", "P1", "P2", "P3"],
        "quantity": ["1", "1", "2", "-1"],
        "unit_price": ["10.00", "10.00", "5.00", "5.00"],
        "status": ["COMPLETED", "COMPLETED", "Completed", "completed"],
    })
    clean, rejected = clean_orders(raw, "test.csv")
    assert list(clean["order_id"]) == ["O1", "O2"]
    assert set(clean["status"]) == {"completed"}
    assert clean.loc[1, "customer_id"] is None
    assert list(rejected["order_id"]) == ["O3"]
    assert rejected.loc[0, "reason"] == "non_positive_quantity"


def test_clean_orders_rejects_blank_ids_fractional_qty_and_bad_price():
    raw = pd.DataFrame({
        "order_id": ["", "", "O1", "O2", "O3"],
        "order_ts": ["2026-08-01 10:00:00"] * 5,
        "customer_id": ["C1"] * 5,
        "product_id": ["P1"] * 5,
        "quantity": ["1", "2", "2.5", "1", "2.0"],
        "unit_price": ["10.00", "20.00", "10.00", "N/A", "10.00"],
        "status": ["completed"] * 5,
    })
    clean, rejected = clean_orders(raw, "test.csv")
    assert list(clean["order_id"]) == ["O3"]
    assert clean.loc[0, "quantity"] == 2
    reasons = dict(zip(rejected["source_row"], rejected["reason"]))
    assert reasons == {2: "missing_order_id", 3: "missing_order_id",
                       4: "invalid_quantity", 5: "invalid_price"}


def test_clean_orders_keeps_last_row_for_repeated_order():
    raw = pd.DataFrame({
        "order_id": ["O1", "O1", "O1"],
        "order_ts": ["2026-08-01 10:00:00"] * 3,
        "customer_id": ["C1"] * 3,
        "product_id": ["P1"] * 3,
        "quantity": ["1"] * 3,
        "unit_price": ["10.00"] * 3,
        "status": ["completed", "refunded", "completed"],
    })
    clean, _ = clean_orders(raw, "test.csv")
    assert list(clean["status"]) == ["completed"]
