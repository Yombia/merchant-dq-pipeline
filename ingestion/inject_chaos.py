"""Deliberately damage some landing batches, to prove the DQ layer catches real defects.

Each scenario is applied to one date and recorded in landing/_chaos_manifest.json,
together with the DQ checks that are EXPECTED to fire. scripts/verify_chaos.py then
compares that manifest against dq.dq_results: every injected defect must be detected.

Deterministic (fixed seed), so the same run always produces the same damage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

import pandas as pd

from ingestion.common import LANDING_DIR

SEED = 42

# date -> scenario. Spread over the first three weeks of the replay window; the last
# week stays untouched so it also shows how the checks behave on the real data's own tail.
SCHEDULE = {
    "2018-08-02": "duplicate_rows",
    "2018-08-04": "null_keys",
    "2018-08-06": "invalid_values",
    "2018-08-08": "orphan_seller",
    "2018-08-10": "seller_relocation",
    "2018-08-13": "volume_spike",
    "2018-08-15": "schema_drift",
    "2018-08-17": "missing_batch",
    "2018-08-19": "malformed_values",
}


def _read(folder: Path, entity: str) -> pd.DataFrame:
    return pd.read_csv(folder / f"{entity}.csv", dtype=str, keep_default_na=False)


def _write(df: pd.DataFrame, folder: Path, entity: str) -> None:
    df.to_csv(folder / f"{entity}.csv", index=False)


def duplicate_rows(folder: Path, rng: random.Random) -> dict:
    orders, items = _read(folder, "orders"), _read(folder, "order_items")
    dup_o = orders.sample(5, random_state=rng.randint(0, 9999))
    dup_i = items.sample(5, random_state=rng.randint(0, 9999))
    _write(pd.concat([orders, dup_o]), folder, "orders")
    _write(pd.concat([items, dup_i]), folder, "order_items")
    return {
        "injected": {"orders": 5, "order_items": 5},
        "expect": [
            ("raw.orders", "unique(order_id)"),
            ("raw.order_items", "unique_combination(order_id, order_item_id)"),
            ("quarantine.orders", "quarantined(duplicate)"),
            ("quarantine.order_items", "quarantined(duplicate)"),
        ],
    }


def null_keys(folder: Path, rng: random.Random) -> dict:
    orders, items = _read(folder, "orders"), _read(folder, "order_items")
    o_idx = rng.sample(list(orders.index), 2)
    i_idx = rng.sample(list(items.index), 3)
    orders.loc[o_idx, "customer_id"] = ""
    items.loc[i_idx, "seller_id"] = ""
    _write(orders, folder, "orders")
    _write(items, folder, "order_items")
    return {
        "injected": {"orders.customer_id": 2, "order_items.seller_id": 3},
        "expect": [
            ("raw.orders", "not_null(customer_id)"),
            ("raw.order_items", "not_null(seller_id)"),
            ("quarantine.orders", "quarantined(missing_customer_id)"),
            ("quarantine.order_items", "quarantined(missing_seller_id)"),
        ],
    }


def invalid_values(folder: Path, rng: random.Random) -> dict:
    pay = _read(folder, "payments")
    neg = rng.sample(list(pay.index), 4)
    pay.loc[neg, "payment_value"] = "-" + pay.loc[neg, "payment_value"]
    bad_type = rng.sample([i for i in pay.index if i not in neg], 2)
    pay.loc[bad_type, "payment_type"] = "crypto_wallet"
    _write(pay, folder, "payments")
    return {
        "injected": {"payments.payment_value<0": 4, "payments.payment_type unknown": 2},
        "expect": [
            ("raw.payments", "non_negative_number(payment_value)"),
            ("raw.payments", "accepted_values_var(payment_type)"),
            ("quarantine.payments", "quarantined(invalid_payment_value)"),
            ("quarantine.payments", "quarantined(invalid_payment_type)"),
        ],
    }


def orphan_seller(folder: Path, rng: random.Random) -> dict:
    items = _read(folder, "order_items")
    idx = rng.sample(list(items.index), 3)
    items.loc[idx, "seller_id"] = [f"{rng.getrandbits(128):032x}" for _ in idx]
    _write(items, folder, "order_items")
    return {
        "injected": {"order_items.seller_id unknown": 3},
        "expect": [
            ("raw.order_items", "relationships(seller_id)"),
            ("quarantine.order_items", "quarantined(orphan_seller)"),
        ],
    }


def seller_relocation(folder: Path, rng: random.Random) -> dict:
    """Not a defect: a legitimate master-data change that must create SCD2 versions."""
    initial = LANDING_DIR / "2018-07-31"
    sellers = _read(initial, "sellers")
    later_items = pd.concat(
        _read(LANDING_DIR / d, "order_items") for d in sorted(p.name for p in LANDING_DIR.iterdir()
                                                               if p.is_dir() and p.name > folder.name
                                                               and (p / "order_items.csv").exists())
    )
    active = sellers[sellers["seller_id"].isin(later_items["seller_id"])]
    moved = active.sample(5, random_state=rng.randint(0, 9999)).copy()
    targets = [("Rio De Janeiro", "RJ", "20040"), ("Belo Horizonte", "MG", "30110"),
               ("Curitiba", "PR", "80010"), ("Salvador", "BA", "40010"), ("Recife", "PE", "50010")]
    for idx, row in moved.iterrows():
        # move each seller to a different state than the one it is in now
        city, state, zip_ = next(t for t in targets if t[1] != row["seller_state"])
        targets.remove((city, state, zip_))
        moved.loc[idx, ["seller_city", "seller_state", "seller_zip_code_prefix"]] = [city, state, zip_]
    path = folder / "sellers.csv"
    existing = _read(folder, "sellers") if path.exists() else moved.iloc[0:0]
    _write(pd.concat([existing, moved]), folder, "sellers")
    return {
        "injected": {"sellers relocated": 5},
        "seller_ids": moved["seller_id"].tolist(),
        "expect": [],  # verified separately: 2 SCD2 versions each, later facts use version 2
    }


def volume_spike(folder: Path, rng: random.Random) -> dict:
    """The day is delivered 4 times with fresh IDs: every row is valid, the total is not."""
    frames = {e: _read(folder, e) for e in ("orders", "order_items", "payments", "customers")}
    out = {e: [df] for e, df in frames.items()}
    for copy in range(1, 4):
        def remap(s: pd.Series, copy: int = copy) -> pd.Series:
            # new, collision-free 32-char IDs derived from the original
            return s.map(lambda v: hashlib.md5(f"{v}#{copy}".encode()).hexdigest())
        remapped_cols = {"orders": ["order_id", "customer_id"], "order_items": ["order_id"],
                         "payments": ["order_id"], "customers": ["customer_id"]}
        for e, cols in remapped_cols.items():
            df = frames[e].copy()
            for col in cols:
                df[col] = remap(df[col])
            out[e].append(df)
    for e, parts in out.items():
        _write(pd.concat(parts), folder, e)
    return {
        "injected": {"orders multiplier": 4, "orders": int(len(frames["orders"]) * 4)},
        "expect": [("staging.stg_orders", "volume_anomaly(daily_orders)")],
    }


def schema_drift(folder: Path, rng: random.Random) -> dict:
    pay = _read(folder, "payments").drop(columns=["payment_installments"])
    _write(pay, folder, "payments")
    return {
        "injected": {"payments column dropped": "payment_installments"},
        "expect": [("landing.payments", "schema_contract(payments)")],
    }


def missing_batch(folder: Path, rng: random.Random) -> dict:
    shutil.rmtree(folder)
    return {
        "injected": {"batch folder removed": folder.name},
        "expect": [(f"landing/{folder.name}", "freshness")],
    }


def malformed_values(folder: Path, rng: random.Random) -> dict:
    orders, items = _read(folder, "orders"), _read(folder, "order_items")
    o_idx = rng.sample(list(orders.index), 3)
    # same day, wrong format: DD/MM/YYYY instead of the contract's YYYY-MM-DD
    orders.loc[o_idx, "order_purchase_timestamp"] = orders.loc[o_idx, "order_purchase_timestamp"].map(
        lambda ts: f"{ts[8:10]}/{ts[5:7]}/{ts[0:4]} {ts[11:16]}")
    i_idx = rng.sample(list(items.index), 2)
    items.loc[i_idx, "price"] = "R$ " + items.loc[i_idx, "price"]
    _write(orders, folder, "orders")
    _write(items, folder, "order_items")
    return {
        "injected": {"orders.order_purchase_timestamp bad format": 3, "order_items.price non-numeric": 2},
        "expect": [
            ("raw.orders", "valid_timestamp(order_purchase_timestamp)"),
            ("raw.order_items", "non_negative_number(price)"),
            ("quarantine.orders", "quarantined(invalid_purchase_timestamp)"),
            ("quarantine.order_items", "quarantined(invalid_price)"),
        ],
    }


SCENARIOS = {f.__name__: f for f in (
    duplicate_rows, null_keys, invalid_values, orphan_seller, seller_relocation,
    volume_spike, schema_drift, missing_batch, malformed_values,
)}


def inject() -> list[dict]:
    rng = random.Random(SEED)
    manifest = []
    for batch_date, scenario in SCHEDULE.items():
        folder = LANDING_DIR / batch_date
        if not folder.is_dir():
            raise SystemExit(f"{folder} not found: run split_by_day first")
        info = SCENARIOS[scenario](folder, rng)
        info["expect"] = [{"target": t, "check_name": c} for t, c in info["expect"]]
        manifest.append({"batch_date": batch_date, "scenario": scenario, **info})
    (LANDING_DIR / "_chaos_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    for m in inject():
        print(f"{m['batch_date']}  {m['scenario']:18} {m['injected']}")


if __name__ == "__main__":
    main()
