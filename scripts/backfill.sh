#!/usr/bin/env bash
# Run run_batch.sh for every date in a range, in order, without stopping on a failed day
# (a bad day is recorded in dq.dq_results; the next day still runs, like Airflow catchup).
#
#   scripts/backfill.sh 2018-08-01 2018-08-28

set -uo pipefail

START="${1:?usage: backfill.sh START_DATE END_DATE}"
END="${2:?usage: backfill.sh START_DATE END_DATE}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs/backfill"
mkdir -p "$LOG_DIR"

declare -a ok=() failed=()
d="$START"
while [[ "$d" < "$END" || "$d" == "$END" ]]; do
  printf '%s ... ' "$d"
  if bash "$ROOT/scripts/run_batch.sh" "$d" > "$LOG_DIR/$d.log" 2>&1; then
    echo "ok"; ok+=("$d")
  else
    echo "FAILED (log: logs/backfill/$d.log)"; failed+=("$d")
  fi
  d="$(date -I -d "$d + 1 day")"
done

echo
echo "Backfill $START..$END: ${#ok[@]} ok, ${#failed[@]} failed ${failed[*]:-}"