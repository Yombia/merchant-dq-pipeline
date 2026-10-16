{{ config(unique_key='order_id') }}

-- Clean orders, typed. Incremental: each run upserts one batch (delete+insert on order_id),
-- so re-running a day replaces that day's rows instead of duplicating them.

select
    trim(order_id)                                   as order_id,
    trim(customer_id)                                as customer_id,
    lower(trim(order_status))                        as order_status,
    trim(order_purchase_timestamp)::timestamp        as purchased_at,
    {{ safe_timestamp('order_approved_at') }}             as approved_at,
    {{ safe_timestamp('order_delivered_carrier_date') }}  as delivered_carrier_at,
    {{ safe_timestamp('order_delivered_customer_date') }} as delivered_customer_at,
    {{ safe_timestamp('order_estimated_delivery_date') }} as estimated_delivery_at,
    _batch_date,
    _loaded_at
from {{ ref('orders_validated') }}
where _dq_reason is null
