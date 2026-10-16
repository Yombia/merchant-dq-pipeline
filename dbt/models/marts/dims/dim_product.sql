select
    {{ surrogate_key(['product_id']) }} as product_key,
    product_id,
    product_category,
    product_category_pt,
    photos_qty,
    weight_g,
    length_cm,
    height_cm,
    width_cm
from {{ ref('stg_products') }}
