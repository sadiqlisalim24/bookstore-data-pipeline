"""CSV fayllarının təmizlənməsi.

Burada verilənlər bazası ilə iş yoxdur: hər funksiya xam DataFrame alır,
təmiz DataFrame qaytarır. Bu, qaydaları ayrıca test etməyi asanlaşdırır.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

log = logging.getLogger(__name__)

VALID_STATUSES = {"completed", "cancelled", "refunded"}

CITY_MAP = {
    "bakı": "Bakı", "baki": "Bakı", "baku": "Bakı",
    "sumqayıt": "Sumqayıt", "sumqayit": "Sumqayıt", "sumgait": "Sumqayıt",
    "gəncə": "Gəncə", "gence": "Gəncə", "ganja": "Gəncə",
    "şəki": "Şəki", "seki": "Şəki", "sheki": "Şəki",
    "lənkəran": "Lənkəran", "lenkeran": "Lənkəran", "lankaran": "Lənkəran",
}

CATEGORY_MAP = {
    "biznes": "Biznes",
    "tarix": "Tarix",
    "texnologiya": "Texnologiya", "it": "Texnologiya",
    "uşaq kitabları": "Uşaq kitabları", "usaq kitablari": "Uşaq kitabları",
    "bədii ədəbiyyat": "Bədii ədəbiyyat", "bədii": "Bədii ədəbiyyat",
}

DATE_FORMATS = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]
TIMESTAMP_FORMATS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"]


def normalize_key(value: str) -> str:
    """Müqayisə üçün açar: boşluqsuz, kiçik hərfli.

    Python 'İ'.lower() nəticəsində 'i' + nöqtə (iki simvol) verir,
    ona görə əvvəlcə 'İ' hərfini adi 'i' ilə əvəz edirik.
    """
    return " ".join(value.replace("İ", "i").lower().split())


def parse_datetime(value: str, formats: list[str]) -> datetime | None:
    """Bir neçə məlum formatı ardıcıl yoxlayır. Uyğun gəlməsə None qaytarır."""
    value = value.strip()
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def parse_price(value: str) -> float | None:
    """'22 AZN', '25,00', '6.00' -> 22.0, 25.0, 6.0. Boş dəyər -> None."""
    value = value.upper().replace("AZN", "").replace(",", ".").strip()
    if not value:
        return None
    return round(float(value), 2)


def _map_values(series: pd.Series, mapping: dict[str, str], name: str) -> pd.Series:
    keys = series.map(normalize_key)
    unknown = sorted(set(keys[~keys.isin(mapping)]))
    if unknown:
        log.warning("Xəritədə olmayan %s dəyərləri saxlanılır: %s", name, unknown)
    return keys.map(mapping).fillna(series.str.strip())


def clean_customers(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df["customer_id"] = df["customer_id"].str.strip()
    df["full_name"] = df["full_name"].str.strip()
    df["city"] = _map_values(df["city"], CITY_MAP, "şəhər")
    df["email"] = df["email"].str.strip().str.lower().replace("", None)
    df["signup_date"] = df["signup_date"].map(lambda v: parse_datetime(v, DATE_FORMATS))
    bad_dates = df["signup_date"].isna().sum()
    if bad_dates:
        log.warning("%s müştərinin qeydiyyat tarixi oxunmadı (NULL saxlanılır)", bad_dates)
    df["signup_date"] = df["signup_date"].map(lambda d: d.date() if d else None)

    # Eyni customer_id iki dəfə gəlirsə, adı BÖYÜK hərflə yazılmamış sətri saxlayırıq.
    df["_is_upper"] = df["full_name"].str.isupper()
    df = (
        df.sort_values(["customer_id", "_is_upper"])
        .drop_duplicates("customer_id", keep="first")
        .drop(columns="_is_upper")
        .sort_values("customer_id")
        .reset_index(drop=True)
    )
    return df[["customer_id", "full_name", "city", "signup_date", "email"]]


def clean_products(raw: pd.DataFrame, orders_raw: pd.DataFrame | None = None) -> pd.DataFrame:
    df = raw.copy()
    df["product_id"] = df["product_id"].str.strip()
    df["title"] = df["title"].str.strip()
    df["category"] = _map_values(df["category"], CATEGORY_MAP, "kateqoriya")
    df["list_price"] = df["price"].map(parse_price)

    # Qiyməti boş olan kitablar üçün sifarişlərdə ən çox rast gəlinən unit_price götürülür.
    missing = df["list_price"].isna()
    if missing.any() and orders_raw is not None:
        prices = orders_raw.assign(unit_price=orders_raw["unit_price"].map(parse_price))
        mode = prices.groupby("product_id")["unit_price"].agg(lambda s: s.mode().iloc[0])
        df.loc[missing, "list_price"] = df.loc[missing, "product_id"].map(mode)
        log.info("Qiyməti boş olan məhsullar sifarişlərdən dolduruldu: %s",
                 df.loc[missing, "product_id"].tolist())

    df = df.drop_duplicates("product_id", keep="last").reset_index(drop=True)
    df["is_known"] = True
    return df[["product_id", "title", "category", "list_price", "is_known"]]


def clean_orders(raw: pd.DataFrame, source_file: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sifarişləri təmizləyir. (təmiz_sifarişlər, rədd_edilənlər) qaytarır."""
    df = raw.copy()
    for col in ["order_id", "customer_id", "product_id", "status"]:
        df[col] = df[col].str.strip()

    before = len(df)
    df = df.drop_duplicates()
    if before != len(df):
        log.info("%s: %s tam dublikat sətir silindi", source_file, before - len(df))
    # Eyni order_id fərqli məzmunla təkrarlanarsa, fayldakı sonuncu sətir qalır.
    df = df.drop_duplicates("order_id", keep="last")

    df["order_ts"] = df["order_ts"].map(lambda v: parse_datetime(v, TIMESTAMP_FORMATS))
    df["status"] = df["status"].str.lower()
    df["customer_id"] = df["customer_id"].replace("", None)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = df["unit_price"].map(parse_price)

    reasons = pd.Series("", index=df.index)
    reasons[df["order_ts"].isna()] += "invalid_timestamp;"
    reasons[df["quantity"].isna() | (df["quantity"] <= 0)] += "non_positive_quantity;"
    reasons[df["unit_price"].isna() | (df["unit_price"] <= 0)] += "invalid_price;"
    reasons[~df["status"].isin(VALID_STATUSES)] += "invalid_status;"
    reasons[df["product_id"] == ""] += "missing_product;"

    bad = reasons != ""
    rejected = raw.loc[df.index[bad]].copy()
    rejected["reason"] = reasons[bad].str.rstrip(";")
    rejected["source_file"] = source_file

    clean = df[~bad].copy()
    clean["quantity"] = clean["quantity"].astype(int)
    clean["source_file"] = source_file
    cols = ["order_id", "order_ts", "customer_id", "product_id",
            "quantity", "unit_price", "status", "source_file"]
    return clean[cols].reset_index(drop=True), rejected.reset_index(drop=True)
