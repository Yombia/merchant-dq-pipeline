select
    to_char(d, 'YYYYMMDD')::int          as date_key,
    d::date                              as full_date,
    extract(year from d)::int            as year,
    extract(quarter from d)::int         as quarter,
    extract(month from d)::int           as month,
    to_char(d, 'Mon')                    as month_name,
    extract(day from d)::int             as day_of_month,
    extract(isodow from d)::int          as day_of_week,
    to_char(d, 'Dy')                     as day_name,
    extract(isodow from d) in (6, 7)     as is_weekend
from generate_series(date '2016-01-01', date '2019-12-31', interval '1 day') as d
