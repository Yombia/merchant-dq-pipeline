"""DAG integrity tests. Skipped when Airflow isn't installed (the plain unit-test job);
run in the CI job that installs Airflow."""

from pathlib import Path

import pytest

pytest.importorskip("airflow.sdk")  # the real package, not this repo's airflow/ folder

from airflow.dag_processing.dagbag import DagBag  # noqa: E402

DAGS = Path(__file__).resolve().parent.parent / "airflow" / "dags"


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder=str(DAGS), include_examples=False)
    assert bag.import_errors == {}, bag.import_errors
    return bag.get_dag("merchant_daily")


def test_dag_loads(dag):
    assert dag is not None


def test_runs_are_sequential_and_replay_the_window(dag):
    assert dag.catchup is True
    assert dag.max_active_runs == 1
    assert str(dag.start_date.date()) == "2018-07-31"
    assert str(dag.end_date.date()) == "2018-08-28"


def test_task_order(dag):
    def down(task_id):
        return set(dag.get_task(task_id).downstream_task_ids)

    assert down("check_landing") == {"load_raw"}
    assert down("load_raw") == {"dbt_staging"}
    assert down("dbt_staging") == {"dbt_snapshot", "volume_anomaly"}
    assert down("dbt_snapshot") == {"dbt_marts"}
    assert down("dbt_marts") == {"collect_dq", "done"}
    assert "done" in down("collect_dq") and "done" in down("volume_anomaly")


def test_dq_is_collected_even_when_dbt_fails(dag):
    assert dag.get_task("collect_dq").trigger_rule == "all_done"
    assert dag.get_task("done").trigger_rule == "all_success"


def test_dq_failures_are_not_retried(dag):
    assert all(t.retries == 0 for t in dag.tasks)
