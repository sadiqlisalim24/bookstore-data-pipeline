"""İnteqrasiya testləri: işləyən PostgreSQL tələb edir (DATABASE_URL).

Baza yoxdursa testlər ötürülür (skip).
"""
import psycopg2
import pytest

from pipeline import load
from pipeline.config import DATA_DIR, INCREMENTAL_ORDERS_FILE
from pipeline.db import connect, drop_schema


@pytest.fixture(scope="module")
def conn():
    try:
        c = connect(retries=1)
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL əlçatan deyil")
    drop_schema(c)
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
