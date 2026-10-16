with batch as (
    select *
    from {{ source('raw', 'payments') }}
    where _batch_date = '{{ var("batch_date") }}'
),

ranked as (
    select
        batch.*,
        row_number() over (
            partition by trim(order_id), trim(payment_sequential) order by _row_id
        ) as _dup_rank
    from batch
),

known_orders as (select order_id from {{ ref('stg_orders') }})

select
    ranked.*,
    case
        when {{ is_blank('ranked.order_id') }}                          then 'missing_order_id'
        when not {{ is_integer('ranked.payment_sequential') }}          then 'invalid_payment_sequential'
        when not {{ in_list('lower(trim(ranked.payment_type))', var('payment_types')) }} then 'invalid_payment_type'
        when not {{ is_non_negative_number('ranked.payment_value') }}   then 'invalid_payment_value'
        when not {{ is_integer('ranked.payment_installments') }}        then 'invalid_installments'
        when _dup_rank > 1                                              then 'duplicate'
        when ko.order_id is null                                        then 'orphan_order'
    end as _dq_reason
from ranked
left join known_orders ko on ko.order_id = trim(ranked.order_id)
