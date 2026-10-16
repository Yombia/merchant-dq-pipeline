#!/usr/bin/env bash
# One-time setup of the warehouse and the simulated source.
#
#   scripts/bootstrap.sh            create schemas, seed, build landing batches, run initial load
#   scripts/bootstrap.sh --reset    same, but drop every warehouse schema first (clean slate)
#
# Requires the Olist CSVs in data/source/ (see README).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
DBT_BIN="${DBT_BIN:-dbt}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PGHOST="${DWH_HOST:-localhost}" PGPORT="${DWH_PORT:-5432}" PGUSER="${DWH_USER:-dwh}" \
       PGPASSWORD="${DWH_PASSWORD:-dwh}" PGDATABASE="${DWH_DB:-dwh}"

log() { printf '\n\033[1m[bootstrap] %s\033[0m\n' "$*"; }

log "waiting for the warehouse at ${PGHOST}:${PGPORT}"
for _ in $(seq 1 30); do pg_isready -q && break; sleep 2; done
pg_isready -q || { echo "warehouse not reachable"; exit 1; }

if [[ "${1:-}" == "--reset" ]]; then
  log "dropping warehouse schemas"
  psql -q -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS raw, staging, quarantine, snapshots, mart, reference, dq CASCADE;"
  rm -rf "$ROOT/dbt/target"
fi

log "creating raw + dq schemas"
for f in "$ROOT"/sql/ddl/*.sql; do psql -q -v ON_ERROR_STOP=1 -f "$f"; done

log "loading reference seed (category translations)"
(cd "$ROOT/dbt" && "$DBT_BIN" --no-use-colors seed --profiles-dir . --target-path target/seed)

ls "$ROOT"/data/source/olist_orders_dataset.csv >/dev/null 2>&1 || {
  echo "Olist CSVs not found in data/source/ — download them first (see README)"; exit 1; }

log "splitting the source into daily landing batches"
"$PYTHON" -m ingestion.split_by_day

log "injecting chaos (deliberate defects) into selected batches"
"$PYTHON" -m ingestion.inject_chaos

log "running the initial historical load"
"$ROOT/scripts/run_batch.sh" 2018-07-31

log "done. Next: scripts/backfill.sh 2018-08-01 2018-08-28  (or trigger the Airflow DAG)"
