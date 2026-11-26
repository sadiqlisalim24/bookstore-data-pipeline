-- Ulduz sxemi: bir fakt cədvəli (fact_orders) + ölçü cədvəlləri (dim_*).
-- Bütün CREATE əmrləri IF NOT EXISTS ilə yazılıb ki, skript təkrar işə salına bilsin.

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_id  TEXT PRIMARY KEY,
    full_name    TEXT,
    city         TEXT,
    signup_date  DATE,
    email        TEXT,
    is_known     BOOLEAN NOT NULL DEFAULT TRUE,   -- FALSE: sifarişdə var, customers.csv-də yox
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_id   TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    category     TEXT NOT NULL,
    list_price   NUMERIC(10, 2),
    is_known     BOOLEAN NOT NULL DEFAULT TRUE,   -- FALSE: sifarişdə var, products.csv-də yox (məs. P999)
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INTEGER PRIMARY KEY,             -- YYYYMMDD, məs. 20260815
    full_date    DATE NOT NULL UNIQUE,
    year         SMALLINT NOT NULL,
    quarter      SMALLINT NOT NULL,
    month        SMALLINT NOT NULL,
    year_month   CHAR(7) NOT NULL,                -- '2026-08'
    day          SMALLINT NOT NULL,
    iso_weekday  SMALLINT NOT NULL,               -- 1 = bazar ertəsi, 7 = bazar
    is_weekend   BOOLEAN NOT NULL
);

-- Bir sətir = bir sifariş (fayllarda hər sifarişdə yalnız bir məhsul var).
CREATE TABLE IF NOT EXISTS fact_orders (
    order_id     TEXT PRIMARY KEY,
    order_ts     TIMESTAMP NOT NULL,
    date_key     INTEGER NOT NULL REFERENCES dim_date (date_key),
    customer_id  TEXT REFERENCES dim_customer (customer_id),   -- NULL: müştəri məlum deyil
    product_id   TEXT NOT NULL REFERENCES dim_product (product_id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0),
    amount       NUMERIC(12, 2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
    status       TEXT NOT NULL CHECK (status IN ('completed', 'cancelled', 'refunded')),
    is_revenue   BOOLEAN GENERATED ALWAYS AS (status = 'completed') STORED,
    source_file  TEXT NOT NULL,
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fact_orders_date ON fact_orders (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_orders_customer ON fact_orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_fact_orders_product ON fact_orders (product_id);

-- Təmizləmədən keçməyən sətirlər silinmir, səbəbi ilə birlikdə burada saxlanılır.
CREATE TABLE IF NOT EXISTS rejected_orders (
    source_file  TEXT NOT NULL,
    source_row   INTEGER NOT NULL,                -- fayldakı sətir nömrəsi (başlıq = 1)
    order_id     TEXT,
    reason       TEXT NOT NULL,
    order_ts     TEXT,
    customer_id  TEXT,
    product_id   TEXT,
    quantity     TEXT,
    unit_price   TEXT,
    status       TEXT,
    rejected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_file, source_row)
);
