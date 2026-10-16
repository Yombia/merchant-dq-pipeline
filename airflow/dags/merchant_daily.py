"""
### merchant_daily

Daily batch pipeline for marketplace merchants, orders and payments, with data quality
checks at every layer. One DAG run = one batch date (`ds`).

```
check_landing -> load_raw -> dbt_staging -> dbt_snapshot -> dbt_marts -> collect_dq -> done
                                  \\-> volume_anomaly ------------------------------/
```

* **check_landing** - freshness + schema contract. Fails (and stops the run) if the batch
  is missing or its columns changed.
* **load_raw** - idempotent load of the landing CSVs into `raw` (all TEXT).
* **dbt_staging** - raw-layer tests (warn), validation, quarantine, staging tests (error).
* **dbt_snapshot** - SCD Type 2 history of sellers.
* **dbt_marts** - star schema + mart tests (error) + reconciliation (warn).
* **collect_dq** - dbt test results + quarantine counts into `dq.dq_results`.
  Runs even when a dbt step failed, so failures are always recorded.
* **volume_anomaly** - robust (log, median/MAD) check on daily order volume.
* **done** - fails the run if any critical step failed.

The replay window is 2018-07-31 (initial historical load) to 2018-08-28. Runs are strictly
sequential (`max_active_runs=1`): SCD2 history and volume baselines depend on order.
A failed day does not block the next one (`depends_on_past=False`), like a real feed.

Manual run for a specific day: trigger with config `{"batch_date": "2018-08-05"}`.
"""

from __future__ import annotations

import os

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG, Param
from airflow.task.trigger_rule import TriggerRule

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/opt/project")
DBT_BIN = os.environ.get("DBT_BIN", "dbt")

# Scheduled runs use the logical date; a manual run can pass {"batch_date": "YYYY-MM-DD"}.
BATCH_DATE = "{{ params.batch_date if params.batch_date else ds }}"


def python_step(module: str, extra: str = "") -> str:
    return f"cd {PROJECT_DIR} && python -m ingestion.{module} --date {BATCH_DATE} {extra}".strip()


def dbt_step(step: str, select: str) -> str:
    return (
        f"cd {PROJECT_DIR}/dbt && {DBT_BIN} --no-use-colors build --select {select} "
        f"--profiles-dir . --target-path target/{BATCH_DATE}/{step} "
        f"--vars \"{{batch_date: '{BATCH_DATE}'}}\""
    )


default_args = {
    "owner": "data-quality",
    "retries": 0,               # a DQ failure is a finding, not a flaky error: don't retry it
    "depends_on_past": False,
    "env": {"RUN_ID": "{{ run_id }}", "PYTHONPATH": PROJECT_DIR},
    "append_env": True,         # keep the container env (DWH_*, DBT_BIN, ...)
}

with DAG(
    dag_id="merchant_daily",
    description="Daily merchant data pipeline with layered data quality checks",
    doc_md=__doc__,
    schedule="@daily",
    start_date=pendulum.datetime(2018, 7, 31, tz="UTC"),
    end_date=pendulum.datetime(2018, 8, 28, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args=default_args,
    params={"batch_date": Param(None, type=["null", "string"],
                                description="Override the batch date (YYYY-MM-DD) for a manual run")},
    tags=["data-quality", "dbt", "merchant"],
) as dag:
    check_landing = BashOperator(task_id="check_landing", bash_command=python_step("check_landing"))

    load_raw = BashOperator(task_id="load_raw", bash_command=python_step("load_raw"))

    dbt_staging = BashOperator(
        task_id="dbt_staging",
        bash_command=dbt_step("staging", "source:raw path:models/staging"),
    )

    dbt_snapshot = BashOperator(
        task_id="dbt_snapshot",
        bash_command=dbt_step("snapshot", "resource_type:snapshot"),
    )

    dbt_marts = BashOperator(
        task_id="dbt_marts",
        bash_command=dbt_step("marts", "path:models/marts path:tests/singular"),
    )

    # all_done: record DQ evidence even when a dbt step failed.
    # Exits 99 (-> "skipped") when the landing gate blocked the batch: nothing to collect.
    collect_dq = BashOperator(
        task_id="collect_dq",
        bash_command=python_step("dq_collect", "--skip-if-gate-failed"),
        trigger_rule=TriggerRule.ALL_DONE,
    )

    volume_anomaly = BashOperator(task_id="volume_anomaly", bash_command=python_step("volume_anomaly"))

    # The run's final verdict: fails if any critical step upstream failed.
    done = EmptyOperator(task_id="done", trigger_rule=TriggerRule.ALL_SUCCESS)

    check_landing >> load_raw >> dbt_staging >> dbt_snapshot >> dbt_marts >> collect_dq
    dbt_staging >> volume_anomaly
    [dbt_marts, collect_dq, volume_anomaly] >> done
