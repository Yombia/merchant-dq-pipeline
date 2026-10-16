{{ config(
    alias='order_items',
    unique_key='_batch_date',
    pre_hook="{% if is_incremental() %}delete from {{ this }} where _batch_date = '{{ var(\"batch_date\") }}'{% endif %}"
) }}

-- Rows of raw.order_items that failed validation, kept with the reason (_dq_reason) so they can be
-- inspected, fixed at the source and replayed. Nothing is silently dropped.
-- pre_hook clears this batch first, so re-running a day never leaves stale quarantine rows.

select *
from {{ ref('order_items_validated') }}
where _dq_reason is not null
