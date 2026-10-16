with batch as (
    select *
    from {{ source('raw', 'customers') }}
    where _batch_date = '{{ var("batch_date") }}'
),

ranked as (
    select
        batch.*,
        row_number() over (partition by trim(customer_id) order by _row_id) as _dup_rank
    from batch
)

select
    ranked.*,
    case
        when {{ is_blank('customer_id') }}         then 'missing_customer_id'
        when {{ is_blank('customer_unique_id') }}  then 'missing_customer_unique_id'
        when _dup_rank > 1                         then 'duplicate'
    end as _dq_reason
from ranked
