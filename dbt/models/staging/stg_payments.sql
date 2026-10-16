{{ config(
    unique_key=['order_id', 'payment_sequential'],
    post_hook=[
        "create index if not exists ix_{{ this.name }}__order_id_payment_sequential on {{ this }} (order_id, payment_sequential)",
        "create index if not exists ix_{{ this.name }}__batch_date on {{ this }} (_batch_date)",
    ],
) }}

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
