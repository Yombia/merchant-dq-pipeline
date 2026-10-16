-- Rebuilt every run (table), so the index is unnamed: a fixed name would still be held by
-- the previous copy of the table while dbt swaps it out, and "if not exists" would skip it.
{{ config(post_hook=["create index on {{ this }} (seller_id, valid_from)"]) }}

-- Seller dimension, SCD Type 2: one row per VERSION of a seller.
-- A fact joins to the version that was valid when the order was placed, so a seller who
-- moved from SP to RJ keeps old sales in SP and new sales in RJ.

with versions as (
    select
        seller_id,
        seller_zip_code_prefix,
        seller_city,
        seller_state,
        dbt_valid_from,
        dbt_valid_to,
        row_number() over (partition by seller_id order by dbt_valid_from) as version_number
    from {{ ref('snap_sellers') }}
)

select
    {{ surrogate_key(['seller_id', 'dbt_valid_from']) }}  as seller_key,
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state,
    version_number,
    -- The first version is treated as valid "since forever" so historical orders that
    -- predate the seller's first delivery to the warehouse still find a version.
    case when version_number = 1 then timestamp '1900-01-01' else dbt_valid_from end as valid_from,
    coalesce(dbt_valid_to, timestamp '9999-12-31')                                    as valid_to,
    dbt_valid_to is null                                                              as is_current
from versions
