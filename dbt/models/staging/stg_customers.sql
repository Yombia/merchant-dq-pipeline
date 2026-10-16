{{ config(
    unique_key='customer_id',
    post_hook=[
        "create index if not exists ix_{{ this.name }}__customer_id on {{ this }} (customer_id)",
    ],
) }}

-- Olist issues a new customer_id per order; customer_unique_id identifies the person.

select
    trim(customer_id)                       as customer_id,
    trim(customer_unique_id)                as customer_unique_id,
    trim(customer_zip_code_prefix)          as customer_zip_code_prefix,
    initcap(trim(customer_city))            as customer_city,
    upper(trim(customer_state))             as customer_state,
    _batch_date,
    _loaded_at
from {{ ref('customers_validated') }}
where _dq_reason is null
