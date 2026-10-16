"""Generate a small SYNTHETIC dataset in the exact shape of the Olist export.

CI can't use the real Olist files (they're not redistributed in this repo), so it runs the
whole pipeline, chaos included, on this fake but structurally identical data:
same file names, same columns, same value formats, same date range.

    python -m tests.fixtures.make_fixture --out data/source
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

START, END = date(2018, 6, 1), date(2018, 8, 28)
STATES = ["SP", "RJ", "MG", "PR", "RS", "SC", "BA", "PE", "GO", "DF"]
CITIES = {"SP": "sao paulo", "RJ": "rio de janeiro", "MG": "belo horizonte", "PR": "curitiba",
          "RS": "porto alegre", "SC": "florianopolis", "BA": "salvador", "PE": "recife",
          "GO": "goiania", "DF": "brasilia"}
CATEGORIES = ["beleza_saude", "informatica_acessorios", "esporte_lazer", "moveis_decoracao",
              "utilidades_domesticas", "relogios_presentes", "telefonia", "brinquedos", ""]
PAYMENT_TYPES = ["credit_card"] * 7 + ["boleto"] * 2 + ["debit_card"]
STATUSES = ["delivered"] * 18 + ["shipped", "canceled"]


def hex_id(rng: random.Random) -> str:
    return f"{rng.getrandbits(128):032x}"


def ts(day: date, rng: random.Random) -> str:
    t = datetime(day.year, day.month, day.day) + timedelta(seconds=rng.randrange(86400))
    return t.strftime("%Y-%m-%d %H:%M:%S")


def write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def generate(out: Path, seed: int = 7) -> dict[str, int]:
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)

    sellers = [[hex_id(rng), f"{rng.randrange(10000, 99999)}", CITIES[s], s]
               for s in (rng.choice(STATES) for _ in range(40))]
    products = [[hex_id(rng), rng.choice(CATEGORIES), str(rng.randrange(20, 60)),
                 str(rng.randrange(100, 2000)), str(rng.randrange(1, 6)), str(rng.randrange(100, 5000)),
                 str(rng.randrange(10, 60)), str(rng.randrange(2, 40)), str(rng.randrange(10, 50))]
                for _ in range(150)]
    people = [hex_id(rng) for _ in range(600)]

    orders, items, payments, customers = [], [], [], []
    day = START
    while day <= END:
        n_orders = rng.randrange(20, 31) if day.weekday() < 5 else rng.randrange(14, 22)
        for _ in range(n_orders):
            order_id, customer_id = hex_id(rng), hex_id(rng)
            state = rng.choice(STATES)
            customers.append([customer_id, rng.choice(people), f"{rng.randrange(10000, 99999)}",
                              CITIES[state], state])
            purchased = ts(day, rng)
            orders.append([order_id, customer_id, rng.choice(STATUSES), purchased, purchased,
                           "", "", f"{day + timedelta(days=15)} 00:00:00"])
            total = 0.0
            for item_no in range(1, rng.choice([1, 1, 1, 2, 3]) + 1):
                price, freight = round(rng.uniform(10, 400), 2), round(rng.uniform(5, 40), 2)
                total += price + freight
                items.append([order_id, str(item_no), rng.choice(products)[0], rng.choice(sellers)[0],
                              f"{day + timedelta(days=3)} 12:00:00", f"{price:.2f}", f"{freight:.2f}"])
            if rng.random() < 0.1:  # split payment: voucher + card, still summing exactly
                voucher = round(total * 0.3, 2)
                payments.append([order_id, "1", "voucher", "1", f"{voucher:.2f}"])
                payments.append([order_id, "2", "credit_card", str(rng.randrange(1, 11)),
                                 f"{total - voucher:.2f}"])
            else:
                ptype = rng.choice(PAYMENT_TYPES)
                inst = str(rng.randrange(1, 11)) if ptype == "credit_card" else "1"
                payments.append([order_id, "1", ptype, inst, f"{total:.2f}"])
        day += timedelta(days=1)

    write(out / "olist_orders_dataset.csv",
          ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
           "order_delivered_carrier_date", "order_delivered_customer_date",
           "order_estimated_delivery_date"], orders)
    write(out / "olist_order_items_dataset.csv",
          ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price",
           "freight_value"], items)
    write(out / "olist_order_payments_dataset.csv",
          ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"],
          payments)
    write(out / "olist_customers_dataset.csv",
          ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city",
           "customer_state"], customers)
    write(out / "olist_sellers_dataset.csv",
          ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], sellers)
    write(out / "olist_products_dataset.csv",
          ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
           "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm",
           "product_width_cm"], products)
    return {"orders": len(orders), "order_items": len(items), "payments": len(payments)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(f"Synthetic Olist-shaped data written to {args.out}: {generate(args.out, args.seed)}")


if __name__ == "__main__":
    main()
