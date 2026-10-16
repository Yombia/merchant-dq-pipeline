-- Daily seller performance, the kind of table a merchant-ops or risk team reads.
-- Window functions:
--   LAG        -> change vs the seller's previous active day
--   SUM OVER   -> running (cumulative) GMV per seller
--   RANK       -> seller's rank within its state on that day
-- The state comes from the SCD2 version valid on that day.

with daily as (
    select
        seller_id,
        seller_key,
        date_key,
        purchased_at::date                 as order_date,
        count(distinct order_id)           as orders,
        count(*)                           as items,
        sum(price)                         as gmv,
        sum(freight_value)                 as freight
    from {{ ref('fact_order_items') }}
    where order_status not in ('canceled', 'unavailable')
    group by 1, 2, 3, 4
)

select
    d.order_date,
    d.date_key,
    d.seller_id,
    s.seller_state,
    s.seller_city,
    d.orders,
    d.items,
    d.gmv,
    d.freight,
    lag(d.gmv) over w_seller                                   as prev_active_day_gmv,
    d.gmv - lag(d.gmv) over w_seller                           as gmv_change,
    sum(d.gmv) over (w_seller rows between unbounded preceding and current row) as cumulative_gmv,
    rank() over (partition by d.order_date, s.seller_state order by d.gmv desc) as state_rank
from daily d
join {{ ref('dim_seller') }} s
    on s.seller_key = d.seller_key
window w_seller as (partition by d.seller_id order by d.order_date)
