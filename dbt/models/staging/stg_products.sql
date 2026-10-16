{{ config(unique_key='product_id') }}

select
    p.product_id,
    -- ~600 products have no category, and 2 categories have no English translation:
    -- fall back explicitly instead of leaving NULLs for the BI layer to guess about.
    coalesce(t.product_category_name_english, p.category_pt, 'uncategorized') as product_category,
    p.category_pt                                                              as product_category_pt,
    p.photos_qty,
    p.weight_g,
    p.length_cm,
    p.height_cm,
    p.width_cm,
    p._batch_date,
    p._loaded_at
from (
    select
        trim(product_id)                                  as product_id,
        nullif(trim(product_category_name), '')           as category_pt,
        {{ safe_int('product_photos_qty') }}              as photos_qty,
        {{ safe_numeric('product_weight_g') }}            as weight_g,
        {{ safe_numeric('product_length_cm') }}           as length_cm,
        {{ safe_numeric('product_height_cm') }}           as height_cm,
        {{ safe_numeric('product_width_cm') }}            as width_cm,
        _batch_date,
        _loaded_at
    from {{ ref('products_validated') }}
    where _dq_reason is null
) p
left join {{ ref('product_category_name_translation') }} t
    on t.product_category_name = p.category_pt
