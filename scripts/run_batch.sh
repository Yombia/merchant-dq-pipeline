#!/usr/bin/env bash
# Run the full pipeline for ONE batch date, the same steps the Airflow DAG runs.
#
#   scripts/run_batch.sh 2018-08-05
#
# 1. landing gate   (freshness + schema contract)  -> stop if critical
# 2. load raw       (idempotent delete + COPY)
# 3. dbt staging    (raw tests, validation, quarantine, staging tests)
# 4. dbt snapshot   (SCD2 sellers)
# 5. dbt marts      (star schema + mart tests)
# 6. collect DQ results, 7. volume anomaly check
# DQ results are collected even when a dbt step fails, so failures are always recorded.

set -uo pipefail

BATCH_DATE="${1:?usage: run_batch.sh YYYY-MM-DD}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DBT_BIN="${DBT_BIN:-dbt}"
PYTHON="${PYTHON:-python3}"
export RUN_ID="${RUN_ID:-manual__${BATCH_DATE}__$(date +%Y%m%dT%H%M%S)}"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

log() { printf '\n\033[1m[%s] %s\033[0m\n' "$BATCH_DATE" "$*"; }

dbt_step() {
  local step="$1"; shift
  (cd "$ROOT/dbt" && "$DBT_BIN" --no-use-colors build "$@" \
      --profiles-dir . \
      --target-path "target/${BATCH_DATE}/${step}" \
      --vars "{batch_date: '${BATCH_DATE}'}")
}

log "1/7 landing gate"
"$PYTHON" -m ingestion.check_landing --date "$BATCH_DATE" || { log "STOPPED at landing gate"; exit 2; }

log "2/7 load raw"
"$PYTHON" -m ingestion.load_raw --date "$BATCH_DATE" || exit 1

status=0
log "3/7 dbt staging"
dbt_step staging --select "source:raw" "path:models/staging" --exclude "resource_type:snapshot" || status=1

if [[ $status -eq 0 ]]; then
  log "4/7 dbt snapshot"
  dbt_step snapshot --select "resource_type:snapshot" || status=1
fi

if [[ $status -eq 0 ]]; then
  log "5/7 dbt marts"
  dbt_step marts --select "path:models/marts" "path:tests/singular" || status=1
fi

log "6/7 collect DQ results"
"$PYTHON" -m ingestion.dq_collect --date "$BATCH_DATE" || status=1

if [[ $status -eq 0 ]]; then
  log "7/7 volume anomaly"
  "$PYTHON" -m ingestion.volume_anomaly --date "$BATCH_DATE" || status=1
fi

if [[ $status -ne 0 ]]; then log "FAILED (critical DQ failure or error; see dq.dq_results)"; else log "OK"; fi
exit $status
