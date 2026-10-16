{{ config(unique_key='seller_id') }}

-- Latest known state of each seller (merchant). History is NOT kept here:
-- the snapshot snap_sellers turns changes of this table into SCD Type 2 versions.
-- updated_at = the batch that delivered this state, so a version's validity starts
-- on the business date of the change, not on the wall-clock time the pipeline ran.

with incoming as (
    select
        trim(seller_id)                         as seller_id,
        trim(seller_zip_code_prefix)            as seller_zip_code_prefix,
        initcap(trim(seller_city))              as seller_city,
        upper(trim(seller_state))               as seller_state,
        _batch_date::timestamp                  as updated_at,
        _batch_date,
        _loaded_at
    from {{ ref('sellers_validated') }}
    where _dq_reason is null
)

select incoming.*
from incoming
{% if is_incremental() %}
-- Re-running an OLD batch must never overwrite a seller with an older state
-- (e.g. backfilling 08-05 after the seller already moved on 08-10).
where not exists (
    select 1 from {{ this }} cur
    where cur.seller_id = incoming.seller_id
      and cur.updated_at > incoming.updated_at
)
{% endif %}
