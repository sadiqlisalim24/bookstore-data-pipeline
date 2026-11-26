import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
SQL_DIR = ROOT / "sql"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bookstore")

CUSTOMERS_FILE = "customers.csv"
PRODUCTS_FILE = "products.csv"
BASE_ORDERS_FILE = "orders_2026_08_10.csv"
INCREMENTAL_ORDERS_FILE = "orders_2026_11_01.csv"
