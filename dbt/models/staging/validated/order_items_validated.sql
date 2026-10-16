{#- Validation step for one batch of raw order items.
    Besides value checks, an item must point to a known seller, a known product and a
    clean order: an item of a quarantined order is quarantined too, instead of silently
    vanishing, and an item whose seller/product never arrived (e.g. its master data was
    in a batch that got blocked) waits in quarantine instead of breaking the star schema. -#}

with batch as (
    select *
    from {{ source('raw', 'order_items') }}
    where _batch_date = '{{ var("batch_date") }}'
),

ranked as (
    select
        batch.*,
        row_number() over (
            partition by trim(order_id), trim(order_item_id) order by _row_id
        ) as _dup_rank
    from batch
),

known_sellers  as (select seller_id  from {{ ref('stg_sellers') }}),
known_products as (select product_id from {{ ref('stg_products') }}),
known_orders   as (select order_id   from {{ ref('stg_orders') }})

select
    ranked.*,
    case
        when {{ is_blank('ranked.order_id') }}                     then 'missing_order_id'
        when not {{ is_integer('ranked.order_item_id') }}          then 'invalid_order_item_id'
        when {{ is_blank('ranked.product_id') }}                   then 'missing_product_id'
        when {{ is_blank('ranked.seller_id') }}                    then 'missing_seller_id'
        when not {{ is_non_negative_number('ranked.price') }}      then 'invalid_price'
        when not {{ is_non_negative_number('ranked.freight_value') }} then 'invalid_freight_value'
        when _dup_rank > 1                                         then 'duplicate'
        when ks.seller_id is null                                  then 'orphan_seller'
        when kp.product_id is null                                 then 'orphan_product'
        when ko.order_id is null                                   then 'orphan_order'
    end as _dq_reason
from ranked
left join known_sellers  ks on ks.seller_id  = trim(ranked.seller_id)
left join known_products kp on kp.product_id = trim(ranked.product_id)
left join known_orders   ko on ko.order_id   = trim(ranked.order_id)
