"""Prove it: was every injected defect detected?

Reads landing/_chaos_manifest.json (what inject_chaos broke and which checks should fire)
and compares it with dq.v_latest_results. Also verifies the SCD2 seller relocation end to end,
and lists every other failing check, so nothing is hidden.

Exit code 1 if any expected detection is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ingestion.common import LANDING_DIR, get_conn


def check_expectations(cur, entry: dict) -> list[dict]:
    rows = []
    for exp in entry["expect"]:
        # "Detected" = the check failed in at least one run of that batch. (After an incident is
        # fixed and the batch re-run, the latest result is a pass, but the detection still happened.)
        cur.execute(
            """SELECT status, failed_rows FROM dq.dq_results
               WHERE batch_date = %s AND target = %s AND check_name = %s
               ORDER BY (status = 'fail') DESC, checked_at DESC
               LIMIT 1""",
            (entry["batch_date"], exp["target"], exp["check_name"]),
        )
        hit = cur.fetchone()
        rows.append({
            "batch_date": entry["batch_date"], "scenario": entry["scenario"],
            "target": exp["target"], "check": exp["check_name"],
            "detected": bool(hit and hit[0] == "fail"),
            "failed_rows": hit[1] if hit else None,
        })
    return rows


def check_scd2(cur, entry: dict) -> list[dict]:
    rows = []
    for seller_id in entry["seller_ids"]:
        cur.execute(
            """SELECT count(*),
                      max(seller_city || ', ' || seller_state) FILTER (WHERE is_current),
                      max(seller_city || ', ' || seller_state) FILTER (WHERE NOT is_current)
               FROM mart.dim_seller WHERE seller_id = %s""",
            (seller_id,),
        )
        versions, new_state, old_state = cur.fetchone()
        # facts on/after the change must point at the new version, earlier ones at the old one
        cur.execute(
            """SELECT
                 count(*) FILTER (WHERE f.purchased_at >= %s::date AND NOT d.is_current),
                 count(*) FILTER (WHERE f.purchased_at <  %s::date AND d.is_current),
                 count(*) FILTER (WHERE f.purchased_at >= %s::date)
               FROM mart.fact_order_items f
               JOIN mart.dim_seller d USING (seller_key)
               WHERE f.seller_id = %s""",
            (entry["batch_date"], entry["batch_date"], entry["batch_date"], seller_id),
        )
        wrong_after, wrong_before, facts_after = cur.fetchone()
        rows.append({
            "seller_id": seller_id, "versions": versions, "old_state": old_state,
            "new_state": new_state, "facts_after_change": facts_after,
            "ok": versions == 2 and wrong_after == 0 and wrong_before == 0,
        })
    return rows


def other_failures(cur, expected: set[tuple[str, str, str]]) -> list[tuple]:
    cur.execute(
        """SELECT batch_date::text, layer, target, check_name, severity, failed_rows
           FROM dq.v_latest_results WHERE status <> 'pass' AND status <> 'skipped'
           ORDER BY batch_date, layer, target, check_name"""
    )
    return [r for r in cur.fetchall() if (r[0], r[2], r[3]) not in expected]


def render(results, scd2, others) -> str:
    lines = ["# Chaos verification report", "",
             "Every defect injected by `inject_chaos.py`, and whether the DQ layer caught it.", "",
             "| Batch | Scenario | Target | Check | Detected | Rows |", "|---|---|---|---|---|---|"]
    for r in results:
        rows = r["failed_rows"] if r["failed_rows"] is not None else ""
        lines.append(f"| {r['batch_date']} | {r['scenario']} | `{r['target']}` | `{r['check']}` | "
                     f"{'✅' if r['detected'] else '❌'} | {rows} |")
    lines += ["", "## SCD Type 2: seller relocation", "",
              "| Seller | Versions | Before → After | Facts after change | Correct version used |",
              "|---|---|---|---|---|"]
    for s in scd2:
        lines.append(f"| `{s['seller_id'][:12]}…` | {s['versions']} | {s['old_state']} → {s['new_state']} | "
                     f"{s['facts_after_change']} | {'✅' if s['ok'] else '❌'} |")
    lines += ["", "## Other non-passing checks (not directly injected)", "",
              "Knock-on effects of the injected incidents (e.g. items whose seller or product was "
              "in a blocked batch) and findings on the real data itself. Listed so nothing is hidden.", "",
              "| Batch | Layer | Target | Check | Severity | Rows |", "|---|---|---|---|---|---|"]
    for o in others:
        rows = o[5] if o[5] is not None else ""
        lines.append(f"| {o[0]} | {o[1]} | `{o[2]}` | `{o[3]}` | {o[4]} | {rows} |")
    missed = sum(not r["detected"] for r in results) + sum(not s["ok"] for s in scd2)
    lines += ["", f"**Result: {len(results) - sum(not r['detected'] for r in results)}/{len(results)} "
              f"expected detections, SCD2 {sum(s['ok'] for s in scd2)}/{len(scd2)} correct"
              f"{' — ALL PASSED' if not missed else ' — MISSING DETECTIONS'}.**", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="also write a markdown report here")
    args = parser.parse_args()

    manifest = json.loads((LANDING_DIR / "_chaos_manifest.json").read_text())
    with get_conn() as conn, conn.cursor() as cur:
        results, scd2 = [], []
        for entry in manifest:
            results += check_expectations(cur, entry)
            if entry["scenario"] == "seller_relocation":
                scd2 += check_scd2(cur, entry)
        expected = {(r["batch_date"], r["target"], r["check"]) for r in results}
        others = other_failures(cur, expected)

    report = render(results, scd2, others)
    print(report)
    if args.report:
        args.report.write_text(report)
    missed = [r for r in results if not r["detected"]] + [s for s in scd2 if not s["ok"]]
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
