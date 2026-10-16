"""Gate before loading: is the batch here, complete, and in the agreed shape?

Checks (all critical: a failure stops the batch before anything touches the warehouse):
  * freshness            the batch folder exists and carries the _SUCCESS marker
  * required_file(x)     every transactional file is present
  * schema_contract(x)   each file's header matches the data contract exactly
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from ingestion.common import (
    CONTRACTS,
    OPTIONAL_ENTITIES,
    REQUIRED_ENTITIES,
    SUCCESS_MARKER,
    batch_dir,
    get_conn,
    run_id_for,
)
from ingestion.dq_writer import CheckResult, write_results


def read_header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f), [])


def compare_schema(expected: list[str], actual: list[str]) -> dict:
    return {
        "missing_columns": [c for c in expected if c not in actual],
        "unexpected_columns": [c for c in actual if c not in expected],
        "order_matches": expected == actual,
    }


def run_checks(batch_date: str, folder: Path) -> list[CheckResult]:
    def result(target: str, check: str, ok: bool, details: dict | None = None) -> CheckResult:
        return CheckResult(batch_date, "landing", target, check, "critical",
                           "pass" if ok else "fail", None if ok else 1, details or {})

    fresh = folder.is_dir() and (folder / SUCCESS_MARKER).exists()
    results = [result(f"landing/{batch_date}", "freshness", fresh,
                      None if fresh else {"reason": "batch folder or _SUCCESS marker missing"})]
    if not fresh:
        return results

    for entity in REQUIRED_ENTITIES + OPTIONAL_ENTITIES:
        path = folder / f"{entity}.csv"
        if not path.exists():
            if entity in REQUIRED_ENTITIES:
                results.append(result(f"landing.{entity}", f"required_file({entity})", False,
                                      {"reason": "file missing"}))
            continue
        diff = compare_schema(CONTRACTS[entity], read_header(path))
        ok = not diff["missing_columns"] and not diff["unexpected_columns"]
        results.append(result(f"landing.{entity}", f"schema_contract({entity})", ok,
                              None if ok else diff))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="batch date, YYYY-MM-DD")
    args = parser.parse_args()

    results = run_checks(args.date, batch_dir(args.date))
    with get_conn() as conn:
        write_results(conn, run_id_for(args.date), results)

    failed = [r for r in results if r.status == "fail"]
    for r in results:
        print(f"[{r.status.upper():4}] {r.target:28} {r.check_name}"
              + (f"  {r.details}" if r.status == "fail" else ""))
    if failed:
        print(f"Landing gate FAILED for {args.date}: {len(failed)} critical check(s). Batch not loaded.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
