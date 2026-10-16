with batch as (
    select *
    from {{ source('raw', 'sellers') }}
    where _batch_date = '{{ var("batch_date") }}'
),

ranked as (
    select
        batch.*,
        row_number() over (partition by trim(seller_id) order by _row_id) as _dup_rank
    from batch
)

select
    ranked.*,
    case
        when {{ is_blank('seller_id') }}                                          then 'missing_seller_id'
        when not {{ in_list('upper(trim(seller_state))', var('br_states')) }}     then 'invalid_state'
        when _dup_rank > 1                                                        then 'duplicate'
    end as _dq_reason
from ranked
