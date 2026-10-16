-- Customer dimension (SCD Type 1: latest address wins), one row per real person.

with ranked as (
    select
        customer_unique_id,
        customer_zip_code_prefix,
        customer_city,
        customer_state,
        row_number() over (
            partition by customer_unique_id order by _batch_date desc, customer_id
        ) as rn
    from {{ ref('stg_customers') }}
)

select
    {{ surrogate_key(['customer_unique_id']) }} as customer_key,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    customer_state
from ranked
where rn = 1
