"""Shared config: paths, DB connection, and the landing-file data contracts."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_DIR / "data"))
SOURCE_DIR = DATA_DIR / "source"
LANDING_DIR = DATA_DIR / "landing"
DBT_DIR = PROJECT_DIR / "dbt"

# The historical backlog is delivered as one "initial load" batch on this date;
# every day after it is replayed as its own daily batch.
INITIAL_BATCH = "2018-07-31"
REPLAY_START = "2018-08-01"
REPLAY_END = "2018-08-28"

# Data contract per landing entity: the exact columns the source must deliver.
# A file whose header differs is a schema drift and blocks the batch.
CONTRACTS: dict[str, list[str]] = {
    "orders": [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    ],
    "order_items": [
        "order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value",
    ],
    "payments": [
        "order_id", "payment_sequential", "payment_type",
        "payment_installments", "payment_value",
    ],
    "customers": [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state",
    ],
    "sellers": ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    "products": [
        "product_id", "product_category_name", "product_name_lenght",
        "product_description_lenght", "product_photos_qty", "product_weight_g",
        "product_length_cm", "product_height_cm", "product_width_cm",
    ],
}

# Transactional files must arrive every day; master data only when something is new/changed.
REQUIRED_ENTITIES = ["orders", "order_items", "payments", "customers"]
OPTIONAL_ENTITIES = ["sellers", "products"]

SOURCE_FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
}

SUCCESS_MARKER = "_SUCCESS"


def get_conn():
    """Connect to the warehouse using DWH_* environment variables."""
    return psycopg2.connect(
        host=os.environ.get("DWH_HOST", "localhost"),
        port=int(os.environ.get("DWH_PORT", "5432")),
        user=os.environ.get("DWH_USER", "dwh"),
        password=os.environ.get("DWH_PASSWORD", "dwh"),
        dbname=os.environ.get("DWH_DB", "dwh"),
    )


def batch_dir(batch_date: str) -> Path:
    return LANDING_DIR / batch_date


def run_id_for(batch_date: str) -> str:
    """Airflow passes its run_id via env; manual runs get a readable fallback."""
    return os.environ.get("RUN_ID") or f"manual__{batch_date}"
