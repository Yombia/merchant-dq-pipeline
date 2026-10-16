"""Data quality dashboard for the merchant pipeline.

Reads only the dq schema (+ quarantine counts): the dashboard shows what the pipeline
itself recorded, so it can never disagree with the checks.

    streamlit run dashboard/app.py
"""

from __future__ import annotations

import os

import altair as alt
import pandas as pd
import psycopg2
import streamlit as st

# Palette: status colors are reserved for state; series colors for identity.
CRITICAL, WARNING, GOOD = "#d03b3b", "#fab219", "#0ca30c"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
SURFACE = "#fcfcfb"

st.set_page_config(page_title="Merchant DQ", page_icon="🛡️", layout="wide")


@st.cache_data(ttl=60)
def query(sql: str) -> pd.DataFrame:
    with psycopg2.connect(
        host=os.environ.get("DWH_HOST", "localhost"),
        port=int(os.environ.get("DWH_PORT", "5432")),
        user=os.environ.get("DWH_USER", "dwh"),
        password=os.environ.get("DWH_PASSWORD", "dwh"),
        dbname=os.environ.get("DWH_DB", "dwh"),
    ) as conn:
        return pd.read_sql_query(sql, conn)


def themed(chart: alt.Chart, height: int = 260) -> alt.Chart:
    return (
        chart.properties(height=height, background=SURFACE)
        .configure_view(stroke=None)
        .configure_axis(labelColor=MUTED, titleColor=INK_2, gridColor=GRID, domainColor="#c3c2b7",
                        tickColor="#c3c2b7", labelFontSize=11, titleFontSize=11, titleFontWeight="normal")
        .configure_legend(labelColor=INK_2, titleColor=INK_2, orient="top", title=None, labelFontSize=12)
    )


# --------------------------------------------------------------------------- data
try:
    results = query("SELECT * FROM dq.v_latest_results")
except Exception as exc:  # warehouse not bootstrapped yet
    st.title("Merchant pipeline · data quality")
    st.info(f"No DQ results yet. Run the bootstrap and at least one batch first.\n\n`{exc}`")
    st.stop()

if results.empty:
    st.title("Merchant pipeline · data quality")
    st.info("No DQ results yet. Run the bootstrap and at least one batch first.")
    st.stop()

results["batch_date"] = pd.to_datetime(results["batch_date"])
failing = results[results["status"].isin(["fail", "error"])]

per_batch = (
    results.groupby("batch_date")
    .apply(lambda g: pd.Series({
        "blocked": bool(((g["layer"] == "landing") & (g["status"] == "fail")).any()),
        "critical": int(((g["severity"] == "critical") & g["status"].isin(["fail", "error"])).sum()),
        "warning": int(((g["severity"] == "warning") & (g["status"] == "fail")).sum()),
        "checks": len(g),
    }), include_groups=False)
    .reset_index()
)
per_batch["state"] = per_batch.apply(
    lambda r: "blocked" if r.blocked else "critical" if r.critical else "warning" if r.warning else "clean",
    axis=1,
)

QUARANTINE_TABLES = ["orders", "order_items", "payments", "customers", "sellers", "products"]
# Quarantine tables are created by the first dbt run; right after a reset (or while the very
# first batch is still running) they don't exist yet, so only query the ones that do.
existing = query(
    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'quarantine'"
)["table_name"].tolist()
present = [t for t in QUARANTINE_TABLES if t in existing]
quarantine = query(" UNION ALL ".join(
    f"SELECT '{t}' AS entity, _batch_date, _dq_reason, count(*) AS n FROM quarantine.{t} GROUP BY 1, 2, 3"
    for t in present
)) if present else pd.DataFrame(columns=["entity", "_batch_date", "_dq_reason", "n"])

volume = query("""
    SELECT batch_date, status,
           (details->>'observed')::int          AS observed,
           (details->>'baseline_median')::float AS baseline,
           (details->>'ratio_to_median')::float AS ratio,
           (details->>'robust_z')::float        AS robust_z
    FROM dq.v_latest_results
    WHERE check_name = 'volume_anomaly(daily_orders)' AND status IN ('pass', 'fail')
    ORDER BY batch_date
""")
volume["batch_date"] = pd.to_datetime(volume["batch_date"])

durations = query("""
    WITH latest AS (
        SELECT DISTINCT ON (batch_date) batch_date, run_id
        FROM dq.dbt_node_runs ORDER BY batch_date, recorded_at DESC
    )
    SELECT r.batch_date, r.step, round(sum(r.execution_time), 2) AS seconds
    FROM dq.dbt_node_runs r JOIN latest l USING (batch_date, run_id)
    GROUP BY 1, 2 ORDER BY 1, 2
""")
durations["batch_date"] = pd.to_datetime(durations["batch_date"])

# --------------------------------------------------------------------------- header
st.title("Merchant pipeline · data quality")
last = results["checked_at"].max()
st.caption(f"Every number below comes from `dq.dq_results`, written by the pipeline itself. "
           f"Last check recorded {pd.Timestamp(last).strftime('%Y-%m-%d %H:%M')} UTC.")

daily = per_batch[per_batch["batch_date"] > per_batch["batch_date"].min()]
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Batches processed", f"{(~per_batch['blocked']).sum()} / {len(per_batch)}")
c2.metric("Batches blocked at the gate", int(per_batch["blocked"].sum()))
c3.metric("Checks recorded", f"{len(results):,}")
c4.metric("Failing checks", f"{len(failing):,}",
          help="critical = stops the pipeline · warning = recorded, batch continues")
c5.metric("Rows quarantined", f"{int(quarantine['n'].sum()):,}")

# --------------------------------------------------------------------------- batch health
st.subheader("Batch health")
st.caption("Failing checks per batch, by severity. Blocked batches never reached the warehouse.")

health = per_batch.melt(id_vars=["batch_date", "state", "blocked"], value_vars=["critical", "warning"],
                        var_name="severity", value_name="failing")
blocked_marks = per_batch[per_batch["blocked"]].assign(label="blocked")

bars = alt.Chart(health).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3, stroke=SURFACE,
                                   strokeWidth=2).encode(
    x=alt.X("yearmonthdate(batch_date):O", title=None, axis=alt.Axis(format="%d %b", labelAngle=-45)),
    y=alt.Y("failing:Q", title="Failing checks", stack=True),
    color=alt.Color("severity:N", scale=alt.Scale(domain=["critical", "warning"], range=[CRITICAL, WARNING]),
                    legend=alt.Legend(title=None)),
    order=alt.Order("severity:N", sort="ascending"),
    tooltip=[alt.Tooltip("yearmonthdate(batch_date):T", title="Batch"), alt.Tooltip("severity:N"),
             alt.Tooltip("failing:Q", title="Failing checks"), alt.Tooltip("state:N", title="Batch state")],
)
blocked_text = alt.Chart(blocked_marks).mark_text(text="⛔ blocked", baseline="top", color=CRITICAL,
                                                  fontSize=10, fontWeight="bold").encode(
    x=alt.X("yearmonthdate(batch_date):O"), y=alt.value(4),
)
st.altair_chart(themed(bars + blocked_text, 280), use_container_width=True)

# --------------------------------------------------------------------------- volume + quarantine
left, right = st.columns([3, 2])
with left:
    st.subheader("Daily order volume vs baseline")
    st.caption("Robust check: log scale, 7-day median/MAD. Flagged when both statistically unusual "
               "and outside 0.5×–2× of the median.")
    if volume.empty:
        st.info("No volume checks yet.")
    else:
        base = alt.Chart(volume).encode(x=alt.X("batch_date:T", title=None, axis=alt.Axis(format="%d %b")))
        observed = base.mark_line(color=SERIES[0], strokeWidth=2, point=alt.OverlayMarkDef(size=36)).encode(
            y=alt.Y("observed:Q", title="Orders per day"),
            tooltip=[alt.Tooltip("batch_date:T", title="Batch"), alt.Tooltip("observed:Q", title="Orders"),
                     alt.Tooltip("baseline:Q", title="7-day median", format=".0f"),
                     alt.Tooltip("ratio:Q", title="× median", format=".2f"),
                     alt.Tooltip("robust_z:Q", title="robust z", format=".1f")],
        )
        baseline = base.mark_line(color=MUTED, strokeWidth=2, strokeDash=[4, 4]).encode(y="baseline:Q")
        flagged = alt.Chart(volume[volume["status"] == "fail"]).mark_point(
            shape="triangle-up", size=160, filled=True, color=WARNING, stroke=INK, strokeWidth=1,
        ).encode(x="batch_date:T", y="observed:Q",
                 tooltip=[alt.Tooltip("batch_date:T", title="Anomaly on"), alt.Tooltip("observed:Q"),
                          alt.Tooltip("ratio:Q", title="× median", format=".2f")])
        flagged_text = alt.Chart(volume[volume["status"] == "fail"]).mark_text(
            text="⚠ anomaly", dy=-16, color=INK_2, fontSize=11).encode(x="batch_date:T", y="observed:Q")
        st.altair_chart(themed(observed + baseline + flagged + flagged_text), use_container_width=True)
        st.caption("Solid: observed clean orders · dashed: 7-day median baseline · ▲ flagged anomaly")

with right:
    st.subheader("Quarantined rows by reason")
    st.caption("Bad rows are kept, never dropped. Knock-on reasons (orphan_*) follow blocked batches.")
    if quarantine.empty:
        st.success("Nothing quarantined.")
    else:
        q = quarantine.groupby(["_dq_reason"], as_index=False)["n"].sum().sort_values("n", ascending=False)
        qchart = alt.Chart(q).mark_bar(color=SERIES[0], cornerRadiusTopRight=3, cornerRadiusBottomRight=3,
                                       height=14).encode(
            y=alt.Y("_dq_reason:N", sort="-x", title=None, axis=alt.Axis(labelColor=INK_2, labelLimit=200)),
            x=alt.X("n:Q", title="Rows"),
            tooltip=[alt.Tooltip("_dq_reason:N", title="Reason"), alt.Tooltip("n:Q", title="Rows")],
        )
        labels = qchart.mark_text(align="left", dx=4, color=INK_2, fontSize=11).encode(text="n:Q")
        st.altair_chart(themed(qchart + labels, 300), use_container_width=True)

# --------------------------------------------------------------------------- run time
st.subheader("dbt run time per batch")
st.caption("Incremental models process one day at a time, so run time stays flat after the initial load.")
if durations.empty:
    st.info("No dbt runs recorded yet.")
else:
    dchart = alt.Chart(durations[durations["batch_date"] > durations["batch_date"].min()]).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=30)).encode(
        x=alt.X("batch_date:T", title=None, axis=alt.Axis(format="%d %b")),
        y=alt.Y("seconds:Q", title="Seconds (sum of nodes)"),
        color=alt.Color("step:N", scale=alt.Scale(domain=["staging", "snapshot", "marts"], range=SERIES)),
        tooltip=[alt.Tooltip("batch_date:T", title="Batch"), "step:N",
                 alt.Tooltip("seconds:Q", format=".2f")],
    )
    st.altair_chart(themed(dchart, 220), use_container_width=True)
    init = durations[durations["batch_date"] == durations["batch_date"].min()]["seconds"].sum()
    st.caption(f"Initial historical load (not shown, ~93k orders): {init:.1f}s of dbt node time.")

# --------------------------------------------------------------------------- drill-down
st.subheader("Inspect a batch")
dates = sorted(per_batch["batch_date"].dt.date.unique(), reverse=True)
default = next((i for i, d in enumerate(dates)
                if per_batch.loc[per_batch["batch_date"].dt.date == d, "state"].iloc[0] != "clean"), 0)
picked = st.selectbox("Batch date", dates, index=default)
row = per_batch[per_batch["batch_date"].dt.date == picked].iloc[0]
icon = {"blocked": "⛔", "critical": "🟥", "warning": "🟨", "clean": "✅"}[row.state]
st.markdown(f"**{icon} {row.state.capitalize()}** · {row.checks} checks · "
            f"{row.critical} critical failing · {row.warning} warning failing")

detail = results[(results["batch_date"].dt.date == picked) & (results["status"] != "pass")][
    ["layer", "target", "check_name", "severity", "status", "failed_rows"]
].sort_values(["severity", "layer", "target"])
if detail.empty:
    st.success("All checks passed for this batch.")
else:
    st.dataframe(detail, hide_index=True, use_container_width=True)

qb = quarantine[pd.to_datetime(quarantine["_batch_date"]).dt.date == picked]
if not qb.empty:
    st.markdown("**Quarantined in this batch**")
    st.dataframe(qb.rename(columns={"_dq_reason": "reason", "n": "rows"})[["entity", "reason", "rows"]],
                 hide_index=True, use_container_width=True)

with st.expander("All checks, as a table"):
    st.dataframe(results.sort_values(["batch_date", "layer", "target", "check_name"]),
                 hide_index=True, use_container_width=True)