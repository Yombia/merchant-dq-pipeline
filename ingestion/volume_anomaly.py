"""Statistical volume anomaly check on daily order counts.

A batch can pass every row-level test and still be wrong: half the orders missing,
or the same day sent four times. This check compares today's count of clean orders
with the previous 7 days:

  * on a LOG scale, because volume changes are multiplicative (x2 and /2 are equally big)
  * with a ROBUST z-score (median and MAD instead of mean and std), so one past
    anomaly does not distort the baseline for the following week

Flagged (warning) when BOTH:
  |robust z| > Z_THRESHOLD      (statistically unusual for this series)
  ratio outside [LOW, HIGH]     (and big enough to matter in business terms)
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from datetime import date, timedelta

from ingestion.common import INITIAL_BATCH, get_conn, run_id_for
from ingestion.dq_writer import CheckResult, write_results

LOOKBACK_DAYS = 7
Z_THRESHOLD = 3.5
LOW_RATIO, HIGH_RATIO = 0.5, 2.0
MAD_SCALE = 1.4826  # makes MAD comparable to a standard deviation for normal data


def evaluate(observed: int, history: list[int]) -> dict:
    """Pure function (unit-tested): decide whether `observed` is anomalous vs `history`."""
    baseline = [h for h in history if h > 0]  # days with no batch are "unknown", not zero sales
    if len(baseline) < 3:
        return {"status": "skipped", "reason": "not enough history", "observed": observed}
    median = statistics.median(baseline)
    ratio = observed / median

    logs = [math.log(h) for h in baseline]
    log_median = statistics.median(logs)
    log_mad = statistics.median(abs(v - log_median) for v in logs) * MAD_SCALE
    log_obs = math.log(observed) if observed > 0 else math.log(0.5)  # zero orders = extreme drop
    robust_z = (log_obs - log_median) / log_mad if log_mad > 0 else 0.0

    anomalous = abs(robust_z) > Z_THRESHOLD and not (LOW_RATIO <= ratio <= HIGH_RATIO)
    return {
        "status": "fail" if anomalous else "pass",
        "observed": observed,
        "baseline_median": median,
        "robust_z": round(robust_z, 2),
        "ratio_to_median": round(ratio, 2),
        "history": history,
    }


def daily_counts(conn, batch_date: str) -> tuple[int, list[int]]:
    d = date.fromisoformat(batch_date)
    start = d - timedelta(days=LOOKBACK_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT purchased_at::date AS day, count(*)
            FROM staging.stg_orders
            WHERE purchased_at::date BETWEEN %s AND %s
            GROUP BY 1
            """,
            (start, d),
        )
        counts = dict(cur.fetchall())
    history = [counts.get(start + timedelta(days=i), 0) for i in range(LOOKBACK_DAYS)]
    return counts.get(d, 0), history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    with get_conn() as conn:
        if args.date == INITIAL_BATCH:
            outcome = {"status": "skipped", "reason": "initial historical load"}
            observed = None
        else:
            observed, history = daily_counts(conn, args.date)
            outcome = evaluate(observed, history)
        status = outcome.pop("status")
        write_results(conn, run_id_for(args.date), [CheckResult(
            args.date, "staging", "staging.stg_orders", "volume_anomaly(daily_orders)",
            "warning", status, observed if status == "fail" else None, outcome,
        )])
    print(f"volume_anomaly {args.date}: {status.upper()} {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
