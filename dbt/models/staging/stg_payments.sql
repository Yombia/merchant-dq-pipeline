{{ config(unique_key=['order_id', 'payment_sequential']) }}

select
    trim(order_id)                          as order_id,
    trim(payment_sequential)::int           as payment_sequential,
    lower(trim(payment_type))               as payment_type,
    trim(payment_installments)::int         as payment_installments,
    trim(payment_value)::numeric(12, 2)     as payment_value,
    _batch_date,
    _loaded_at
from {{ ref('payments_validated') }}
where _dq_reason is null
