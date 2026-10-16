{#- Validation step for one batch of raw orders.
    Every row gets a _dq_reason: NULL = clean (goes to staging),
    anything else = quarantined with that reason. First failing rule wins. -#}

with batch as (
    select *
    from {{ source('raw', 'orders') }}
    where _batch_date = '{{ var("batch_date") }}'
),

ranked as (
    select
        batch.*,
        -- duplicates: keep the first delivered copy of each order_id
        row_number() over (partition by trim(order_id) order by _row_id) as _dup_rank
    from batch
)

select
    ranked.*,
    case
        when {{ is_blank('order_id') }}                                  then 'missing_order_id'
        when {{ is_blank('customer_id') }}                               then 'missing_customer_id'
        when not {{ is_timestamp('order_purchase_timestamp') }}          then 'invalid_purchase_timestamp'
        when not {{ in_list('lower(trim(order_status))', var('order_statuses')) }} then 'invalid_order_status'
        when _dup_rank > 1                                               then 'duplicate'
    end as _dq_reason
from ranked
