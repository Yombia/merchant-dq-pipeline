{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['order_id', 'payment_sequential']
) }}

-- Grain: one row per payment record of an order (an order can be split across
-- several payment methods / vouchers, identified by payment_sequential).

with payments as (
    select * from {{ ref('stg_payments') }}
    where _batch_date = '{{ var("batch_date") }}'
)

select
    p.order_id,
    p.payment_sequential,
    to_char(o.purchased_at, 'YYYYMMDD')::int        as date_key,
    {{ surrogate_key(['c.customer_unique_id']) }}   as customer_key,
    p.payment_type,
    p.payment_installments,
    p.payment_value,
    p._batch_date
from payments p
join {{ ref('stg_orders') }} o
    on o.order_id = p.order_id
left join {{ ref('stg_customers') }} c
    on c.customer_id = o.customer_id
