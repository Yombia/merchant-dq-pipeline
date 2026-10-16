from ingestion.check_landing import compare_schema, run_checks
from ingestion.common import CONTRACTS, SUCCESS_MARKER


def write_batch(folder, drop_column=None, skip=()):
    folder.mkdir(parents=True)
    for entity in ("orders", "order_items", "payments", "customers"):
        if entity in skip:
            continue
        cols = [c for c in CONTRACTS[entity] if c != drop_column]
        (folder / f"{entity}.csv").write_text(",".join(cols) + "\n")
    (folder / SUCCESS_MARKER).touch()


def statuses(results):
    return {r.check_name: r.status for r in results}


def test_clean_batch_passes(tmp_path):
    write_batch(tmp_path / "2018-08-01")
    results = run_checks("2018-08-01", tmp_path / "2018-08-01")
    assert all(r.status == "pass" for r in results)
    assert all(r.severity == "critical" for r in results)


def test_missing_folder_fails_freshness(tmp_path):
    results = run_checks("2018-08-17", tmp_path / "2018-08-17")
    assert statuses(results) == {"freshness": "fail"}


def test_missing_success_marker_fails_freshness(tmp_path):
    folder = tmp_path / "2018-08-01"
    write_batch(folder)
    (folder / SUCCESS_MARKER).unlink()
    assert statuses(run_checks("2018-08-01", folder))["freshness"] == "fail"


def test_dropped_column_is_schema_drift(tmp_path):
    folder = tmp_path / "2018-08-15"
    write_batch(folder, drop_column="payment_installments")
    result = statuses(run_checks("2018-08-15", folder))
    assert result["schema_contract(payments)"] == "fail"
    assert result["schema_contract(orders)"] == "pass"


def test_missing_required_file_fails(tmp_path):
    folder = tmp_path / "2018-08-01"
    write_batch(folder, skip=("payments",))
    assert statuses(run_checks("2018-08-01", folder))["required_file(payments)"] == "fail"


def test_compare_schema_reports_differences():
    diff = compare_schema(["a", "b", "c"], ["a", "c", "x"])
    assert diff["missing_columns"] == ["b"]
    assert diff["unexpected_columns"] == ["x"]
    assert diff["order_matches"] is False
