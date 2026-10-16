"""Turn the static Olist export into daily landing batches.

Simulates a source system that drops one folder of CSVs per day:

    landing/<batch_date>/{orders,order_items,payments,customers,sellers,products}.csv
    landing/<batch_date>/_SUCCESS

* Everything purchased up to INITIAL_BATCH lands as one historical "initial load".
* Each day from REPLAY_START to REPLAY_END becomes its own batch.
* Child rows (items, payments, customers) follow the batch of their order.
* Master data (sellers, products) is delivered the first time it is needed.

Values are kept as raw strings: the source is not cleaned here; that is the warehouse's job.
"""

from __future__ import annotations

import argparse
import shutil

import pandas as pd

from ingestion.common import (
    INITIAL_BATCH,
    LANDING_DIR,
    REPLAY_END,
    SOURCE_DIR,
    SOURCE_FILES,
    SUCCESS_MARKER,
)


def read_source(entity: str) -> pd.DataFrame:
    return pd.read_csv(
        SOURCE_DIR / SOURCE_FILES[entity], dtype=str, keep_default_na=False, encoding="utf-8-sig"
    )


def assign_batches(orders: pd.DataFrame) -> pd.DataFrame:
    purchase_day = orders["order_purchase_timestamp"].str[:10]
    batch = purchase_day.where(purchase_day > INITIAL_BATCH, INITIAL_BATCH)
    orders = orders.assign(_batch=batch)
    return orders[orders["_batch"] <= REPLAY_END]


def first_appearance(items: pd.DataFrame, key: str) -> pd.Series:
    """Batch in which each seller/product is first referenced by an order item."""
    return items.groupby(key)["_batch"].min()


def split() -> dict[str, int]:
    orders = assign_batches(read_source("orders"))
    order_batch = orders.set_index("order_id")["_batch"]

    items = read_source("order_items")
    items = items[items["order_id"].isin(order_batch.index)]
    items = items.assign(_batch=items["order_id"].map(order_batch))

    payments = read_source("payments")
    payments = payments[payments["order_id"].isin(order_batch.index)]
    payments = payments.assign(_batch=payments["order_id"].map(order_batch))

    customer_batch = orders.set_index("customer_id")["_batch"]
    customers = read_source("customers")
    customers = customers[customers["customer_id"].isin(customer_batch.index)]
    customers = customers.assign(_batch=customers["customer_id"].map(customer_batch))

    sellers = read_source("sellers")
    seller_first = first_appearance(items, "seller_id")
    sellers = sellers.assign(_batch=sellers["seller_id"].map(seller_first).fillna(INITIAL_BATCH))
    sellers = sellers[sellers["_batch"] <= REPLAY_END]

    products = read_source("products")
    product_first = first_appearance(items, "product_id")
    products = products.assign(_batch=products["product_id"].map(product_first).fillna(INITIAL_BATCH))
    products = products[products["_batch"] <= REPLAY_END]

    frames = {
        "orders": orders, "order_items": items, "payments": payments,
        "customers": customers, "sellers": sellers, "products": products,
    }

    if LANDING_DIR.exists():
        shutil.rmtree(LANDING_DIR)
    LANDING_DIR.mkdir(parents=True)

    batches = sorted(orders["_batch"].unique())
    for batch in batches:
        out = LANDING_DIR / batch
        out.mkdir()
        for entity, df in frames.items():
            part = df[df["_batch"] == batch].drop(columns="_batch")
            if part.empty and entity in ("sellers", "products"):
                continue  # master data only ships when there is something new
            part.to_csv(out / f"{entity}.csv", index=False)
        (out / SUCCESS_MARKER).touch()

    return {b: int((orders["_batch"] == b).sum()) for b in batches}


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    counts = split()
    print(f"Wrote {len(counts)} batches to {LANDING_DIR}")
    print(f"  initial load {INITIAL_BATCH}: {counts[INITIAL_BATCH]:,} orders")
    daily = {k: v for k, v in counts.items() if k != INITIAL_BATCH}
    print(f"  daily batches {min(daily)}..{max(daily)}: {sum(daily.values()):,} orders")


if __name__ == "__main__":
    main()
