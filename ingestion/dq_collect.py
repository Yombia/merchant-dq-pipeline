"""Collect DQ evidence for one batch into dq.dq_results.

Sources of evidence:
  * dbt test results  (target/<date>/<step>/run_results.json + manifest.json)
  * quarantine counts (rows moved to the quarantine schema, grouped by reason)
Also logs every dbt node's status and duration into dq.dbt_node_runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from ingestion.common import DBT_DIR, get_conn, run_id_for
from ingestion.dq_writer import CheckResult, write_results

STEPS = ["staging", "snapshot", "marts"]
QUARANTINE_TABLES = ["orders", "order_items", "payments", "customers", "sellers", "products"]
SEVERITY = {"error": "critical", "warn": "warning"}


def tested_node_id(node: dict, manifest: dict) -> str:
    """The node a test is attached to. A relationships test depends on TWO nodes
    (child and parent); the tested one is the `model` argument, not just the first parent."""
    model_arg = (node.get("test_metadata") or {}).get("kwargs", {}).get("model", "")
    if m := re.search(r"source\('(\w+)',\s*'(\w+)'\)", model_arg):
        uid = next((k for k, s in manifest["sources"].items()
                    if s["source_name"] == m[1] and s["name"] == m[2]), None)
        if uid:
            return uid
    if m := re.search(r"ref\('(\w+)'\)", model_arg):
        uid = next((k for k, n in manifest["nodes"].items()
                    if n["resource_type"] in ("model", "snapshot") and n["name"] == m[1]), None)
        if uid:
            return uid
    parents = node.get("depends_on", {}).get("nodes", [])
    return node.get("attached_node") or (parents[0] if parents else "")


def describe_test(node: dict, manifest: dict) -> tuple[str, str, str]:
    """(layer, target, check_name) for a dbt test node."""
    parents = node.get("depends_on", {}).get("nodes", [])
    parent_id = tested_node_id(node, manifest)
    if parent_id.startswith("source."):
        src = manifest["sources"][parent_id]
        layer, target = "raw", f"{src['schema']}.{src['name']}"
    elif parent_id:
        model = manifest["nodes"][parent_id]
        layer = "mart" if "/marts/" in "/" + model["original_file_path"] else "staging"
        target = f"{model['schema']}.{model.get('alias') or model['name']}"
    else:
        layer, target = "unknown", "unknown"

    meta = node.get("test_metadata")
    if meta:  # generic test, e.g. unique(order_id) or unique_combination(order_id, order_item_id)
        kwargs = meta.get("kwargs", {})
        arg = node.get("column_name") or ", ".join(kwargs.get("columns", []))
        name = f"{meta['name']}({arg})" if arg else meta["name"]
    else:     # singular test: its file name says what it checks
        name = node["name"]
        if parents:
            layer = "mart"
    return layer, target, name


def collect_dbt(batch_date: str, run_id: str, conn) -> list[CheckResult]:
    results: list[CheckResult] = []
    node_rows = []
    for step in STEPS:
        folder = DBT_DIR / "target" / batch_date / step
        rr_path, mf_path = folder / "run_results.json", folder / "manifest.json"
        if not rr_path.exists() or not mf_path.exists():
            continue
        run_results = json.loads(rr_path.read_text())
        manifest = json.loads(mf_path.read_text())
        for r in run_results["results"]:
            node = manifest["nodes"].get(r["unique_id"])
            if node is None:
                continue
            node_rows.append((run_id, batch_date, step, r["unique_id"], node["resource_type"],
                              r["status"], r.get("execution_time")))
            if node["resource_type"] != "test":
                continue
            layer, target, name = describe_test(node, manifest)
            status = {"pass": "pass", "fail": "fail", "warn": "fail", "error": "error",
                      "skipped": "skipped"}.get(r["status"], "error")
            results.append(CheckResult(
                batch_date, layer, target, name,
                SEVERITY.get(node["config"].get("severity", "error").lower(), "critical"),
                status, r.get("failures"),
                {"dbt_test": node["name"]} if status != "pass" else {},
            ))
    if node_rows:
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO dq.dbt_node_runs
                   (run_id, batch_date, step, unique_id, resource_type, status, execution_time)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                node_rows,
            )
        conn.commit()
    return results


def collect_quarantine(batch_date: str, conn) -> list[CheckResult]:
    """One result per quarantine reason found in this batch (+ a pass row if a table is clean)."""
    results = []
    with conn.cursor() as cur:
        for table in QUARANTINE_TABLES:
            cur.execute("SELECT to_regclass(%s)", (f"quarantine.{table}",))
            if cur.fetchone()[0] is None:
                continue
            cur.execute(
                f"SELECT _dq_reason, count(*) FROM quarantine.{table} "
                "WHERE _batch_date = %s GROUP BY 1 ORDER BY 1",
                (batch_date,),
            )
            rows = cur.fetchall()
            if not rows:
                results.append(CheckResult(batch_date, "quarantine", f"quarantine.{table}",
                                           "quarantined_rows", "warning", "pass", 0))
            for reason, n in rows:
                results.append(CheckResult(batch_date, "quarantine", f"quarantine.{table}",
                                           f"quarantined({reason})", "warning", "fail", n))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    run_id = run_id_for(args.date)

    with get_conn() as conn:
        results = collect_dbt(args.date, run_id, conn) + collect_quarantine(args.date, conn)
        write_results(conn, run_id, results)

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    print(f"Collected {len(results)} DQ results for {args.date}: {by_status}")
    for r in results:
        if r.status != "pass":
            print(f"  [{r.severity:8}] {r.status:7} {r.target:28} {r.check_name}  rows={r.failed_rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
