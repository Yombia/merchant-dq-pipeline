{#- Custom generic tests. Each returns the failing rows; dbt counts them. -#}

{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n_rows
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}


{% test non_negative_number(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not {{ is_non_negative_number(column_name) }}
{% endtest %}


{% test valid_timestamp(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not {{ is_timestamp(column_name) }}
{% endtest %}


{% test accepted_values_var(model, column_name, var_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not {{ in_list(column_name, var(var_name)) }}
{% endtest %}


{#- SCD Type 2 integrity: every business key has exactly one current version. -#}
{% test one_current_version(model, column_name, current_flag='is_current') %}
select {{ column_name }}
from {{ model }}
group by {{ column_name }}
having sum(case when {{ current_flag }} then 1 else 0 end) <> 1
{% endtest %}


{#- SCD Type 2 integrity: versions of the same key must not overlap in time. -#}
{% test no_overlapping_versions(model, column_name, valid_from='valid_from', valid_to='valid_to') %}
select a.{{ column_name }}
from {{ model }} a
join {{ model }} b
  on a.{{ column_name }} = b.{{ column_name }}
 and a.{{ valid_from }} < b.{{ valid_to }}
 and b.{{ valid_from }} < a.{{ valid_to }}
 and (a.{{ valid_from }}, a.{{ valid_to }}) <> (b.{{ valid_from }}, b.{{ valid_to }})
{% endtest %}
