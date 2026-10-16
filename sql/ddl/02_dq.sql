-- Data quality results: one row per check, per batch, per run.
-- Every layer writes here (landing checks, dbt tests, quarantine counts, volume anomaly),
-- which makes "how healthy was yesterday's data?" a single SQL query.

CREATE SCHEMA IF NOT EXISTS dq;

CREATE TABLE IF NOT EXISTS dq.dq_results (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT        NOT NULL,
    batch_date   DATE        NOT NULL,
    layer        TEXT        NOT NULL,                -- landing | raw | staging | quarantine | mart
    target       TEXT        NOT NULL,                -- e.g. raw.orders
    check_name   TEXT        NOT NULL,                -- e.g. unique(order_id)
    severity     TEXT        NOT NULL CHECK (severity IN ('critical', 'warning')),
    status       TEXT        NOT NULL CHECK (status IN ('pass', 'fail', 'error', 'skipped')),
    failed_rows  BIGINT,
    details      JSONB,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_dq_results_batch ON dq.dq_results (batch_date, status);

-- Execution log of every dbt node (models, snapshots, tests): status and duration.
CREATE TABLE IF NOT EXISTS dq.dbt_node_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT        NOT NULL,
    batch_date      DATE        NOT NULL,
    step            TEXT        NOT NULL,             -- staging | snapshot | marts
    unique_id       TEXT        NOT NULL,
    resource_type   TEXT        NOT NULL,
    status          TEXT        NOT NULL,
    execution_time  NUMERIC(10, 3),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Latest result per check per batch (reruns append; this view keeps only the newest run).
CREATE OR REPLACE VIEW dq.v_latest_results AS
SELECT DISTINCT ON (batch_date, layer, target, check_name) *
FROM dq.dq_results
ORDER BY batch_date, layer, target, check_name, checked_at DESC, id DESC;
