with batch as (
    select *
    from {{ source('raw', 'products') }}
    where _batch_date = '{{ var("batch_date") }}'
),

ranked as (
    select
        batch.*,
        row_number() over (partition by trim(product_id) order by _row_id) as _dup_rank
    from batch
)

select
    ranked.*,
    case
        when {{ is_blank('product_id') }}  then 'missing_product_id'
        when _dup_rank > 1                 then 'duplicate'
    end as _dq_reason
from ranked
