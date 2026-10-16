import random

import pandas as pd

from ingestion import inject_chaos
from ingestion.common import CONTRACTS


def make_folder(tmp_path, n=20):
    folder = tmp_path / "2018-08-02"
    folder.mkdir()
    ids = [f"{i:032x}" for i in range(n)]
    pd.DataFrame({c: ["x"] * n for c in CONTRACTS["orders"]} | {
        "order_id": ids, "order_purchase_timestamp": ["2018-08-02 10:00:00"] * n,
    }).to_csv(folder / "orders.csv", index=False)
    pd.DataFrame({c: ["1"] * n for c in CONTRACTS["order_items"]} | {
        "order_id": ids, "seller_id": ["s"] * n, "price": ["10.50"] * n,
    }).to_csv(folder / "order_items.csv", index=False)
    pd.DataFrame({c: ["1"] * n for c in CONTRACTS["payments"]} | {
        "order_id": ids, "payment_type": ["boleto"] * n, "payment_value": ["12.00"] * n,
    }).to_csv(folder / "payments.csv", index=False)
    pd.DataFrame({c: ["c"] * n for c in CONTRACTS["customers"]} | {
        "customer_id": [f"c{i}" for i in range(n)],
    }).to_csv(folder / "customers.csv", index=False)
    return folder


def read(folder, entity):
    return pd.read_csv(folder / f"{entity}.csv", dtype=str, keep_default_na=False)


def test_duplicate_rows_adds_exact_copies(tmp_path):
    folder = make_folder(tmp_path)
    inject_chaos.duplicate_rows(folder, random.Random(1))
    orders = read(folder, "orders")
    assert len(orders) == 25
    assert orders["order_id"].duplicated().sum() == 5


def test_null_keys_blanks_values(tmp_path):
    folder = make_folder(tmp_path)
    inject_chaos.null_keys(folder, random.Random(1))
    assert (read(folder, "order_items")["seller_id"] == "").sum() == 3
    assert (read(folder, "orders")["customer_id"] == "").sum() == 2


def test_invalid_values_makes_negatives_and_unknown_types(tmp_path):
    folder = make_folder(tmp_path)
    inject_chaos.invalid_values(folder, random.Random(1))
    pay = read(folder, "payments")
    assert pay["payment_value"].str.startswith("-").sum() == 4
    assert (pay["payment_type"] == "crypto_wallet").sum() == 2


def test_volume_spike_creates_new_valid_ids(tmp_path):
    folder = make_folder(tmp_path)
    inject_chaos.volume_spike(folder, random.Random(1))
    orders, items = read(folder, "orders"), read(folder, "order_items")
    assert len(orders) == 80
    assert orders["order_id"].is_unique            # every row valid on its own...
    assert set(items["order_id"]) == set(orders["order_id"])  # ...and children follow


def test_schema_drift_drops_a_column(tmp_path):
    folder = make_folder(tmp_path)
    info = inject_chaos.schema_drift(folder, random.Random(1))
    assert "payment_installments" not in read(folder, "payments").columns
    assert info["expect"] == [("landing.payments", "schema_contract(payments)")]


def test_missing_batch_removes_folder(tmp_path):
    folder = make_folder(tmp_path)
    inject_chaos.missing_batch(folder, random.Random(1))
    assert not folder.exists()


def test_malformed_values_breaks_formats(tmp_path):
    folder = make_folder(tmp_path)
    inject_chaos.malformed_values(folder, random.Random(1))
    assert read(folder, "orders")["order_purchase_timestamp"].str.contains("/").sum() == 3
    assert read(folder, "order_items")["price"].str.startswith("R$").sum() == 2


def test_every_scheduled_scenario_exists():
    assert set(inject_chaos.SCHEDULE.values()) <= set(inject_chaos.SCENARIOS)
