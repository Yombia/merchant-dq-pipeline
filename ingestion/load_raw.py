"""Load one landing batch into the raw schema, idempotently.

For each file: in a single transaction, delete whatever this batch loaded before, then
COPY the file in. Re-running the same date always ends with exactly one copy of the batch.
"""

from __future__ import annotations

import argparse
import shutil
import sys

from psycopg2 import sql

from ingestion.common import CONTRACTS, DBT_DIR, batch_dir, get_conn


def load_entity(conn, entity: str, batch_date: str, path) -> int:
    cols = CONTRACTS[entity]
    col_list = sql.SQL(", ").join(map(sql.Identifier, cols))
    table = sql.Identifier("raw", entity)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DELETE FROM {} WHERE _batch_date = %s").format(table), (batch_date,))
        # Temp table of plain TEXT columns + a sequence that preserves file order.
        cur.execute(
            sql.SQL("CREATE TEMP TABLE _stage (_seq BIGSERIAL, {}) ON COMMIT DROP").format(
                sql.SQL(", ").join(sql.SQL("{} TEXT").format(sql.Identifier(c)) for c in cols)
            )
        )
        with path.open(encoding="utf-8-sig") as f:
            cur.copy_expert(
                sql.SQL("COPY _stage ({}) FROM STDIN WITH (FORMAT csv, HEADER true)")
                .format(col_list).as_string(conn),
                f,
            )
        cur.execute(
            sql.SQL(
                "INSERT INTO {} ({cols}, _batch_date, _source_file) "
                "SELECT {cols}, %s, %s FROM _stage ORDER BY _seq"
            ).format(table, cols=col_list),
            (batch_date, f"{batch_date}/{path.name}"),
        )
        return cur.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="batch date, YYYY-MM-DD")
    args = parser.parse_args()

    # A fresh load invalidates any dbt artifacts left by an earlier run of this batch,
    # so the DQ collector can never pick up stale test results.
    shutil.rmtree(DBT_DIR / "target" / args.date, ignore_errors=True)

    folder = batch_dir(args.date)
    with get_conn() as conn:
        for entity in CONTRACTS:
            path = folder / f"{entity}.csv"
            if not path.exists():
                continue
            n = load_entity(conn, entity, args.date, path)
            conn.commit()
            print(f"raw.{entity:12} {n:>8,} rows  ({path.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
