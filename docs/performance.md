# Performance notes

Measured with `python -m ingestion.benchmark` on the full Olist replay (112,956 rows in `mart.fact_order_items`), PostgreSQL 16, median of 7 runs of `EXPLAIN (ANALYZE)`. Absolute numbers depend on the machine; the plan change is the point.

## Index tuning

| Query | Without index | With index | Speed-up | Plan without → with |
|---|---|---|---|---|
| **Merchant lookup: one seller's sales history**<br><sub>what a merchant-ops or risk analyst runs when reviewing one merchant</sub> | 19.78 ms | 1.31 ms | 15.1× | Seq Scan on fact_order_items → Bitmap Heap Scan on fact_order_items; Bitmap Index Scan on ix_fact_order_items__seller_id_purchased_at |
| **Weekly GMV by seller state (star join, date filter)**<br><sub>a typical dashboard query: fact filtered by date, joined to the SCD2 dimension</sub> | 13.85 ms | 5.01 ms | 2.8× | Seq Scan on dim_seller; Seq Scan on fact_order_items → Bitmap Heap Scan on fact_order_items; Bitmap Index Scan on ix_fact_order_items__date_key; Seq Scan on dim_seller |
| **Incremental upsert: delete one day's keys before re-insert**<br><sub>the statement dbt's delete+insert strategy runs on every daily load</sub> | 73.19 ms | 1.77 ms | 41.4× | Seq Scan on stg_order_items → Index Scan on ix_stg_order_items__batch_date; Index Scan on ix_stg_order_items__order_id_order_item_id |

The indexes are created by `post_hook`s on the dbt models (`create index if not exists ...`), so they exist in every environment the models are built in.

## Incremental vs full history

Every daily run processes one batch only (incremental models filtered on `batch_date`, upserted with `delete+insert`). From the pipeline's own run log (`dq.dbt_node_runs`, sum of model + snapshot execution time):

| Run | dbt model time |
|---|---|
| Initial load (all history up to 2018-07-31, ~93k orders) | 18.72 s |
| Average daily batch (~250 orders) | 8.99 s |

Per model (seconds):

| Model | Materialization | Initial load | Daily batch |
|---|---|---|---|
| `dim_customer` | table (full rebuild) | 0.75 | 0.92 |
| `fact_order_items` | incremental | 0.78 | 0.27 |
| `mart_seller_daily` | table (full rebuild) | 0.70 | 1.46 |
| `stg_order_items` | incremental | 3.30 | 0.36 |
| `stg_orders` | incremental | 1.84 | 0.32 |

Reading it honestly: on a daily batch the incremental models are down to the fixed per-model overhead (~0.3 s), so they no longer grow with history. The full-rebuild tables (dimensions, `mart_seller_daily`) cost about the same every day and *do* grow with history: they are the next candidates for incremental builds if the data grew.

`--full-refresh` is disabled on the incremental models (`full_refresh: false`), because they only ever see one batch and a full refresh would rebuild them from that batch alone. The rebuild path is replaying batches, which is safe because every step is idempotent.
