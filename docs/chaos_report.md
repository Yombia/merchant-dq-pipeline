# Chaos verification report

Every defect injected by `inject_chaos.py`, and whether the DQ layer caught it.

| Batch | Scenario | Target | Check | Detected | Rows |
|---|---|---|---|---|---|
| 2018-08-02 | duplicate_rows | `raw.orders` | `unique(order_id)` | ✅ | 5 |
| 2018-08-02 | duplicate_rows | `raw.order_items` | `unique_combination(order_id, order_item_id)` | ✅ | 5 |
| 2018-08-02 | duplicate_rows | `quarantine.orders` | `quarantined(duplicate)` | ✅ | 5 |
| 2018-08-02 | duplicate_rows | `quarantine.order_items` | `quarantined(duplicate)` | ✅ | 5 |
| 2018-08-04 | null_keys | `raw.orders` | `not_null(customer_id)` | ✅ | 2 |
| 2018-08-04 | null_keys | `raw.order_items` | `not_null(seller_id)` | ✅ | 3 |
| 2018-08-04 | null_keys | `quarantine.orders` | `quarantined(missing_customer_id)` | ✅ | 2 |
| 2018-08-04 | null_keys | `quarantine.order_items` | `quarantined(missing_seller_id)` | ✅ | 3 |
| 2018-08-06 | invalid_values | `raw.payments` | `non_negative_number(payment_value)` | ✅ | 4 |
| 2018-08-06 | invalid_values | `raw.payments` | `accepted_values_var(payment_type)` | ✅ | 2 |
| 2018-08-06 | invalid_values | `quarantine.payments` | `quarantined(invalid_payment_value)` | ✅ | 4 |
| 2018-08-06 | invalid_values | `quarantine.payments` | `quarantined(invalid_payment_type)` | ✅ | 2 |
| 2018-08-08 | orphan_seller | `raw.order_items` | `relationships(seller_id)` | ✅ | 3 |
| 2018-08-08 | orphan_seller | `quarantine.order_items` | `quarantined(orphan_seller)` | ✅ | 3 |
| 2018-08-13 | volume_spike | `staging.stg_orders` | `volume_anomaly(daily_orders)` | ✅ | 1168 |
| 2018-08-15 | schema_drift | `landing.payments` | `schema_contract(payments)` | ✅ | 1 |
| 2018-08-17 | missing_batch | `landing/2018-08-17` | `freshness` | ✅ | 1 |
| 2018-08-19 | malformed_values | `raw.orders` | `valid_timestamp(order_purchase_timestamp)` | ✅ | 3 |
| 2018-08-19 | malformed_values | `raw.order_items` | `non_negative_number(price)` | ✅ | 2 |
| 2018-08-19 | malformed_values | `quarantine.orders` | `quarantined(invalid_purchase_timestamp)` | ✅ | 3 |
| 2018-08-19 | malformed_values | `quarantine.order_items` | `quarantined(invalid_price)` | ✅ | 2 |

## SCD Type 2: seller relocation

| Seller | Versions | Before → After | Facts after change | Correct version used |
|---|---|---|---|---|
| `18e694e0e48e…` | 2 | Varzea Paulista, SP → Rio De Janeiro, RJ | 18 | ✅ |
| `7299e27ed73d…` | 2 | Araguari, MG → Curitiba, PR | 8 | ✅ |
| `213b25e6f546…` | 2 | Salto, SP → Belo Horizonte, MG | 21 | ✅ |
| `c3e1abd72a42…` | 2 | Mogi Guacu, SP → Salvador, BA | 4 | ✅ |
| `b8555308bfdb…` | 2 | Sao Bernardo Do Campo, SP → Recife, PE | 2 | ✅ |

## Other non-passing checks (not directly injected)

Knock-on effects of the injected incidents (e.g. items whose seller or product was in a blocked batch) and findings on the real data itself. Listed so nothing is hidden.

| Batch | Layer | Target | Check | Severity | Rows |
|---|---|---|---|---|---|
| 2018-07-31 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 227 |
| 2018-08-02 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-04 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 3 |
| 2018-08-04 | quarantine | `quarantine.order_items` | `quarantined(orphan_order)` | warning | 2 |
| 2018-08-04 | quarantine | `quarantine.payments` | `quarantined(orphan_order)` | warning | 2 |
| 2018-08-06 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-07 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-08 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 2 |
| 2018-08-09 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 6 |
| 2018-08-10 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-16 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-16 | quarantine | `quarantine.order_items` | `quarantined(orphan_product)` | warning | 2 |
| 2018-08-18 | quarantine | `quarantine.order_items` | `quarantined(orphan_product)` | warning | 2 |
| 2018-08-19 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-19 | quarantine | `quarantine.order_items` | `quarantined(orphan_order)` | warning | 4 |
| 2018-08-19 | quarantine | `quarantine.payments` | `quarantined(orphan_order)` | warning | 3 |
| 2018-08-20 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-20 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 1 |
| 2018-08-20 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 1 |
| 2018-08-21 | quarantine | `quarantine.order_items` | `quarantined(orphan_product)` | warning | 3 |
| 2018-08-21 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 1 |
| 2018-08-21 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 1 |
| 2018-08-22 | quarantine | `quarantine.order_items` | `quarantined(orphan_product)` | warning | 1 |
| 2018-08-22 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 1 |
| 2018-08-22 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 1 |
| 2018-08-23 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 2 |
| 2018-08-23 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 3 |
| 2018-08-23 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 3 |
| 2018-08-24 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 1 |
| 2018-08-24 | quarantine | `quarantine.order_items` | `quarantined(orphan_product)` | warning | 1 |
| 2018-08-24 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 1 |
| 2018-08-24 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 1 |
| 2018-08-24 | staging | `staging.stg_orders` | `volume_anomaly(daily_orders)` | warning | 99 |
| 2018-08-25 | quarantine | `quarantine.order_items` | `quarantined(orphan_product)` | warning | 1 |
| 2018-08-25 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 2 |
| 2018-08-25 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 2 |
| 2018-08-26 | mart | `mart.fact_payments` | `assert_payments_reconcile_with_items` | warning | 5 |
| 2018-08-26 | quarantine | `quarantine.order_items` | `quarantined(orphan_seller)` | warning | 1 |
| 2018-08-26 | raw | `raw.order_items` | `relationships(seller_id)` | warning | 1 |

**Result: 21/21 expected detections, SCD2 5/5 correct — ALL PASSED.**
