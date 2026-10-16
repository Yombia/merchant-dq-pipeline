"""Single place that writes rows into dq.dq_results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    batch_date: str
    layer: str
    target: str
    check_name: str
    severity: str          # critical | warning
    status: str            # pass | fail | error | skipped
    failed_rows: int | None = None
    details: dict = field(default_factory=dict)


def write_results(conn, run_id: str, results: list[CheckResult]) -> None:
    if not results:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO dq.dq_results
                (run_id, batch_date, layer, target, check_name, severity, status, failed_rows, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (run_id, r.batch_date, r.layer, r.target, r.check_name, r.severity,
                 r.status, r.failed_rows, json.dumps(r.details) if r.details else None)
                for r in results
            ],
        )
    conn.commit()
