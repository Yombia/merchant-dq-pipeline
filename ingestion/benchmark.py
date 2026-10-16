"""Index tuning benchmark: the same queries with and without the indexes the dbt models create.

For each query: drop the relevant indexes, run EXPLAIN (ANALYZE) N times, recreate them,
run again, and report the median execution time plus the plan's access method.
Writes docs/performance.md.

    python -m ingestion.benchmark --runs 7
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from ingestion.common import PROJECT_DIR, get_conn


@dataclass
class Case:
    name: str
    why: str
    sql: str
    indexes: list[tuple[str, str]]   # (index name, CREATE statement), mirrors the dbt post_hooks
    write: bool = False              # run inside a rolled-back transaction


def busiest_seller(cur) -> str:
    cur.execute("SELECT seller_id FROM mart.fact_order_items GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    return cur.fetchone()[0]


def cases(seller_id: str) -> list[Case]:
    return [
        Case(
            "Merchant lookup: one seller's sales history",
            "what a merchant-ops or risk analyst runs when reviewing one merchant",
            f"""SELECT purchased_at::date AS day, count(*) AS items, sum(price) AS gmv
                FROM mart.fact_order_items WHERE seller_id = '{seller_id}'
                GROUP BY 1 ORDER BY 1""",
            [("ix_fact_order_items__seller_id_purchased_at",
              "CREATE INDEX ix_fact_order_items__seller_id_purchased_at "
              "ON mart.fact_order_items (seller_id, purchased_at)")],
        ),
        Case(
            "Weekly GMV by seller state (star join, date filter)",
            "a typical dashboard query: fact filtered by date, joined to the SCD2 dimension",
            """SELECT s.seller_state, sum(f.price) AS gmv, count(DISTINCT f.order_id) AS orders
               FROM mart.fact_order_items f
               JOIN mart.dim_seller s USING (seller_key)
               WHERE f.date_key BETWEEN 20180806 AND 20180812
               GROUP BY 1 ORDER BY 2 DESC""",
            [("ix_fact_order_items__date_key",
              "CREATE INDEX ix_fact_order_items__date_key ON mart.fact_order_items (date_key)")],
        ),
        Case(
            "Incremental upsert: delete one day's keys before re-insert",
            "the statement dbt's delete+insert strategy runs on every daily load",
            """DELETE FROM staging.stg_order_items t
               USING (SELECT order_id, order_item_id FROM staging.stg_order_items
                      WHERE _batch_date = '2018-08-20') s
               WHERE t.order_id = s.order_id AND t.order_item_id = s.order_item_id""",
            [("ix_stg_order_items__order_id_order_item_id",
              "CREATE INDEX ix_stg_order_items__order_id_order_item_id "
              "ON staging.stg_order_items (order_id, order_item_id)"),
             ("ix_stg_order_items__batch_date",
              "CREATE INDEX ix_stg_order_items__batch_date ON staging.stg_order_items (_batch_date)")],
            write=True,
        ),
    ]


def access_methods(plan: dict) -> set[str]:
    found = set()
    def walk(node):
        if "Scan" in node["Node Type"]:
            target = node.get("Index Name") or node.get("Relation Name", "?")
            found.add(f"{node['Node Type']} on {target}")
        for child in node.get("Plans", []):
            walk(child)
    walk(plan["Plan"])
    return found


def measure(conn, case: Case, runs: int) -> tuple[float, set[str]]:
    times, methods = [], set()
    for _ in range(runs):
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {case.sql}")
            plan = cur.fetchone()[0][0]
        conn.rollback()  # never keep a benchmark's writes
        times.append(plan["Execution Time"])
        methods = access_methods(plan)
    return statistics.median(times), methods


def set_indexes(conn, case: Case, present: bool) -> None:
    with conn.cursor() as cur:
        for name, ddl in case.indexes:
            schema = ddl.split(" ON ")[1].split(".")[0]
            cur.execute(f"DROP INDEX IF EXISTS {schema}.{name}")
            if present:
                cur.execute(ddl)
        cur.execute("ANALYZE")
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--out", type=Path, default=PROJECT_DIR / "docs" / "performance.md")
    args = parser.parse_args()

    rows = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            seller = busiest_seller(cur)
            cur.execute("SELECT count(*) FROM mart.fact_order_items")
            fact_rows = cur.fetchone()[0]
        for case in cases(seller):
            set_indexes(conn, case, present=False)
            before, before_plan = measure(conn, case, args.runs)
            set_indexes(conn, case, present=True)
            after, after_plan = measure(conn, case, args.runs)
            rows.append((case, before, after, before_plan, after_plan))
            print(f"{case.name}: {before:.2f} ms -> {after:.2f} ms")

        with conn.cursor() as cur:  # incremental vs full history, from the pipeline's own run log
            cur.execute("""
                WITH latest AS (SELECT DISTINCT ON (batch_date) batch_date, run_id
                                FROM dq.dbt_node_runs ORDER BY batch_date, recorded_at DESC)
                SELECT r.batch_date = (SELECT min(batch_date) FROM latest) AS initial,
                       round(avg(t.s)::numeric, 2)
                FROM (SELECT batch_date, run_id, sum(execution_time) AS s
                      FROM dq.dbt_node_runs WHERE resource_type IN ('model', 'snapshot')
                      GROUP BY 1, 2) t
                JOIN latest r USING (batch_date, run_id)
                GROUP BY 1""")
            runtime = {bool(k): float(v) for k, v in cur.fetchall()}
            cur.execute("""
                WITH latest AS (SELECT DISTINCT ON (batch_date) batch_date, run_id
                                FROM dq.dbt_node_runs ORDER BY batch_date, recorded_at DESC)
                SELECT split_part(unique_id, '.', 3) AS model,
                       round(avg(execution_time) FILTER (
                           WHERE batch_date = (SELECT min(batch_date) FROM latest))::numeric, 2),
                       round(avg(execution_time) FILTER (
                           WHERE batch_date > (SELECT min(batch_date) FROM latest))::numeric, 2)
                FROM dq.dbt_node_runs JOIN latest USING (batch_date, run_id)
                WHERE resource_type = 'model'
                  AND split_part(unique_id, '.', 3) IN
                      ('stg_order_items', 'stg_orders', 'fact_order_items',
                       'dim_customer', 'mart_seller_daily')
                GROUP BY 1 ORDER BY 1""")
            per_model = cur.fetchall()

    lines = [
        "# Performance notes",
        "",
        f"Measured with `python -m ingestion.benchmark` on the full Olist replay "
        f"({fact_rows:,} rows in `mart.fact_order_items`), PostgreSQL 16, median of {args.runs} runs "
        "of `EXPLAIN (ANALYZE)`. Absolute numbers depend on the machine; the plan change is the point.",
        "",
        "## Index tuning",
        "",
        "| Query | Without index | With index | Speed-up | Plan without → with |",
        "|---|---|---|---|---|",
    ]
    for case, before, after, bp, ap in rows:
        speed = f"{before / after:.1f}×" if after > 0 else "n/a"
        lines.append(f"| **{case.name}**<br><sub>{case.why}</sub> | {before:.2f} ms | {after:.2f} ms | "
                     f"{speed} | {'; '.join(sorted(bp))} → {'; '.join(sorted(ap))} |")
    lines += [
        "",
        "The indexes are created by `post_hook`s on the dbt models (`create index if not exists ...`), "
        "so they exist in every environment the models are built in.",
        "",
        "## Incremental vs full history",
        "",
        "Every daily run processes one batch only (incremental models filtered on `batch_date`, "
        "upserted with `delete+insert`). From the pipeline's own run log (`dq.dbt_node_runs`, "
        "sum of model + snapshot execution time):",
        "",
        "| Run | dbt model time |",
        "|---|---|",
        f"| Initial load (all history up to 2018-07-31, ~93k orders) | {runtime.get(True, 0):.2f} s |",
        f"| Average daily batch (~250 orders) | {runtime.get(False, 0):.2f} s |",
        "",
        "Per model (seconds):",
        "",
        "| Model | Materialization | Initial load | Daily batch |",
        "|---|---|---|---|",
        *[f"| `{m}` | {'table (full rebuild)' if m.startswith(('dim_', 'mart_')) else 'incremental'} "
          f"| {a} | {b} |" for m, a, b in per_model],
        "",
        "Reading it honestly: on a daily batch the incremental models are down to the fixed per-model "
        "overhead (~0.3 s), so they no longer grow with history. The full-rebuild tables (dimensions, "
        "`mart_seller_daily`) cost about the same every day and *do* grow with history: they are the "
        "next candidates for incremental builds if the data grew.",
        "",
        "`--full-refresh` is disabled on the incremental models (`full_refresh: false`), because they only "
        "ever see one batch and a full refresh would rebuild them from that batch alone. The rebuild path "
        "is replaying batches, which is safe because every step is idempotent.",
        "",
    ]
    args.out.write_text("\n".join(lines))
    print(f"Wrote {args.out}")
    print(json.dumps(runtime))
    return 0


if __name__ == "__main__":
    sys.exit(main())
