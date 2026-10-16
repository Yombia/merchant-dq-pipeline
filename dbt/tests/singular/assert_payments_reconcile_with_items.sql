{{ config(severity='warn', tags=['consistency']) }}

-- Cross-table consistency for this batch: what the customer paid should equal
-- the items' price + freight. Returns the orders that don't reconcile within tolerance.
-- WARN only: in the real Olist data some orders legitimately differ (interest on
-- installments, vouchers), so this is a signal to monitor, not a reason to stop.

with paid as (
    select order_id, sum(payment_value) as paid
    from {{ ref('fact_payments') }}
    where _batch_date = '{{ var("batch_date") }}'
    group by order_id
),

billed as (
    select order_id, sum(item_total) as billed
    from {{ ref('fact_order_items') }}
    where _batch_date = '{{ var("batch_date") }}'
    group by order_id
)

select
    paid.order_id,
    paid.paid,
    billed.billed,
    paid.paid - billed.billed as difference
from paid
join billed using (order_id)
where abs(paid.paid - billed.billed) > {{ var('payment_tolerance') }}
