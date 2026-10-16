{#- Small, reusable predicates for validating raw TEXT values.
    All of them are NULL-safe: a NULL input evaluates to false (never to NULL),
    so "not is_number(x)" correctly flags a missing value instead of letting it slip through. -#}

{% macro is_blank(col) -%}
    (nullif(trim({{ col }}), '') is null)
{%- endmacro %}

{% macro is_number(col) -%}
    (coalesce(trim({{ col }}), '') ~ '^-?[0-9]+(\.[0-9]+)?$')
{%- endmacro %}

{% macro is_non_negative_number(col) -%}
    (coalesce(trim({{ col }}), '') ~ '^[0-9]+(\.[0-9]+)?$')
{%- endmacro %}

{% macro is_integer(col) -%}
    (coalesce(trim({{ col }}), '') ~ '^[0-9]+$')
{%- endmacro %}

{#- ISO-like "YYYY-MM-DD HH:MM:SS", the format the source contract promises. -#}
{% macro is_timestamp(col) -%}
    (coalesce(trim({{ col }}), '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$')
{%- endmacro %}

{% macro in_list(col, values) -%}
    (coalesce({{ col }}, '') in ({% for v in values %}'{{ v }}'{% if not loop.last %}, {% endif %}{% endfor %}))
{%- endmacro %}

{#- Cast helpers that never crash a run: an invalid value becomes NULL. -#}
{% macro safe_timestamp(col) -%}
    case when {{ is_timestamp(col) }} then trim({{ col }})::timestamp end
{%- endmacro %}

{% macro safe_numeric(col) -%}
    case when {{ is_number(col) }} then trim({{ col }})::numeric end
{%- endmacro %}

{% macro safe_int(col) -%}
    case when {{ is_integer(col) }} then trim({{ col }})::int end
{%- endmacro %}

{#- Deterministic surrogate key (md5 of the business key parts). -#}
{% macro surrogate_key(cols) -%}
    md5({% for c in cols %}coalesce(cast({{ c }} as text), '_null_'){% if not loop.last %} || '|' || {% endif %}{% endfor %})
{%- endmacro %}
