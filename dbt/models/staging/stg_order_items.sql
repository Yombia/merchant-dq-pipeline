{{ config(unique_key=['order_id', 'order_item_id']) }}

select
    trim(order_id)                          as order_id,
    trim(order_item_id)::int                as order_item_id,
    trim(product_id)                        as product_id,
    trim(seller_id)                         as seller_id,
    {{ safe_timestamp('shipping_limit_date') }} as shipping_limit_at,
    trim(price)::numeric(12, 2)             as price,
    trim(freight_value)::numeric(12, 2)     as freight_value,
    _batch_date,
    _loaded_at
from {{ ref('order_items_validated') }}
where _dq_reason is null
