"""İnteqrasiya testləri: ayrıca test bazası tələb edir (TEST_DATABASE_URL).

Testlər cədvəlləri silib yenidən yaradır, ona görə əsas DATABASE_URL heç vaxt
istifadə olunmur. TEST_DATABASE_URL verilməyibsə və ya baza əlçatan deyilsə, skip.
"""
import os

import psycopg2
import pytest

from pipeline import load
from pipeline.config import DATA_DIR, INCREMENTAL_ORDERS_FILE
from pipeline.db import connect, drop_schema


@pytest.fixture(scope="module")
def conn():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL verilməyib")
    try:
        c = connect(url, retries=1)
    except psycopg2.OperationalError:
        pytest.skip("Test bazası əlçatan deyil")
    drop_schema(c)
    c.commit()
    yield c
    c.close()


def snapshot(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), sum(amount), "
                    "count(*) FILTER (WHERE status = 'refunded') FROM fact_orders")
        orders = cur.fetchone()
        cur.execute("SELECT (SELECT count(*) FROM dim_customer), (SELECT count(*) FROM dim_product)")
        return orders + cur.fetchone()


def test_full_load_is_idempotent(conn):
    load.full_load(conn)
    first = snapshot(conn)
    load.full_load(conn)
    assert snapshot(conn) == first
    assert first[0] == 2382  # 2425 - 25 dublikat - 18 mənfi miqdar


def test_incremental_updates_status_without_duplicates(conn):
    path = DATA_DIR / INCREMENTAL_ORDERS_FILE
    before = snapshot(conn)
    load.incremental_load(conn, path)
    after = snapshot(conn)
    assert after[0] == before[0] + 60   # 68 sətir = 60 yeni + 8 köhnə
    assert after[2] == before[2] + 13   # 5 yeni refunded + 8 köhnə sifariş refunded oldu
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM fact_orders WHERE order_id = 'O000610'")
        assert cur.fetchone()[0] == "refunded"  # əvvəl completed idi
    load.incremental_load(conn, path)
    assert snapshot(conn) == after


def test_reloading_old_file_does_not_revert_status(conn):
    after_incremental = snapshot(conn)
    load.full_load(conn)
    assert snapshot(conn) == after_incremental


def order_status(conn, order_id):
    with conn.cursor() as cur:
        cur.execute("SELECT status, source_file FROM fact_orders WHERE order_id = %s", (order_id,))
        return cur.fetchone()


def test_unchanged_newer_file_protects_from_older_file(conn, tmp_path):
    header = "order_id,order_ts,customer_id,product_id,quantity,unit_price,status\n"
    row = "O000610,12.10.2026 00:18,{c},{p},{q},{u},{s}\n"
    with conn.cursor() as cur:
        cur.execute("SELECT customer_id, product_id, quantity, unit_price FROM fact_orders "
                    "WHERE order_id = 'O000610'")
        c, p, q, u = cur.fetchone()
    newer = tmp_path / "orders_2026_12_01.csv"
    newer.write_text(header + row.format(c=c, p=p, q=q, u=u, s="refunded"))
    load.incremental_load(conn, newer)
    assert order_status(conn, "O000610") == ("refunded", newer.name)

    older = tmp_path / "orders_2026_11_15.csv"
    older.write_text(header + row.format(c=c, p=p, q=q, u=u, s="completed"))
    load.incremental_load(conn, older)
    assert order_status(conn, "O000610") == ("refunded", newer.name)


def test_failed_reset_keeps_existing_tables(conn, tmp_path):
    before = snapshot(conn)
    drop_schema(conn)
    with pytest.raises(FileNotFoundError):
        load.full_load(conn, data_dir=tmp_path)  # boş qovluq: fayllar yoxdur
    conn.rollback()
    assert snapshot(conn) == before
