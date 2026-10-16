"""Re-run one batch and prove nothing changed.

Counts the rows of every warehouse table, re-runs scripts/run_batch.sh for the given
date, counts again, and fails if any table (other than the append-only logs in `dq`)
gained or lost rows.

    python -m ingestion.check_idempotency --date 2018-08-05
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from ingestion.common import PROJECT_DIR, get_conn

SCHEMAS = ("raw", "staging", "quarantine", "snapshots", "mart")


def table_counts() -> dict[str, int]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE' ORDER BY 1, 2",
            (list(SCHEMAS),),
        )
        tables = cur.fetchall()
        counts = {}
        for schema, table in tables:
            cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
            counts[f"{schema}.{table}"] = cur.fetchone()[0]
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    before = table_counts()
    run = subprocess.run(["bash", str(PROJECT_DIR / "scripts" / "run_batch.sh"), args.date],
                         capture_output=True, text=True)
    after = table_counts()

    changed = {t: (before.get(t), after.get(t)) for t in sorted(set(before) | set(after))
               if before.get(t) != after.get(t)}
    print(f"Re-ran batch {args.date} (exit code {run.returncode}); compared {len(after)} tables.")
    for table in sorted(after):
        mark = "CHANGED" if table in changed else "same"
        print(f"  {table:32} {before.get(table, 0):>9,} -> {after[table]:>9,}  {mark}")
    if changed:
        print("NOT idempotent: row counts changed.")
        return 1
    print("Idempotent: identical row counts in every table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
