{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['order_id', 'order_item_id']
) }}

-- Grain: one row per item in an order. Incremental: only this batch's items are processed.
-- seller_key is the SCD2 version valid at purchase time (point-in-time join).

with items as (
    select * from {{ ref('stg_order_items') }}
    where _batch_date = '{{ var("batch_date") }}'
),

orders as (
    select order_id, customer_id, order_status, purchased_at
    from {{ ref('stg_orders') }}
),

customers as (
    select customer_id, customer_unique_id from {{ ref('stg_customers') }}
)

select
    i.order_id,
    i.order_item_id,
    to_char(o.purchased_at, 'YYYYMMDD')::int        as date_key,
    {{ surrogate_key(['c.customer_unique_id']) }}   as customer_key,
    s.seller_key,
    {{ surrogate_key(['i.product_id']) }}           as product_key,
    i.seller_id,
    o.order_status,
    o.purchased_at,
    i.price,
    i.freight_value,
    i.price + i.freight_value                       as item_total,
    i._batch_date
from items i
join orders o
    on o.order_id = i.order_id
left join customers c
    on c.customer_id = o.customer_id
left join {{ ref('dim_seller') }} s
    on  s.seller_id = i.seller_id
    and o.purchased_at >= s.valid_from
    and o.purchased_at <  s.valid_to
