# Shortcuts. Everything runs inside the Airflow scheduler container, so the host only
# needs Docker. (Windows without make: copy the command after the colon.)

COMPOSE := docker compose
RUN     := $(COMPOSE) exec airflow-scheduler

.PHONY: up down nuke prepare bootstrap run backfill verify idempotency benchmark psql test lint

up:          ## build and start the stack (Airflow :8080, dashboard :8501)
	$(COMPOSE) up -d --build

down:        ## stop the stack, keep data
	$(COMPOSE) down

nuke:        ## stop the stack and delete the warehouse volume
	$(COMPOSE) down -v

prepare:     ## clean warehouse, build landing batches + chaos; then unpause the DAG in Airflow
	$(RUN) bash scripts/bootstrap.sh --reset --prepare-only

bootstrap:   ## same as prepare, plus the initial load from the shell (no Airflow)
	$(RUN) bash scripts/bootstrap.sh --reset

run:         ## run one batch:  make run DATE=2018-08-05
	$(RUN) bash scripts/run_batch.sh $(DATE)

backfill:    ## run a range:   make backfill START=2018-08-01 END=2018-08-28
	$(RUN) bash scripts/backfill.sh $(START) $(END)

verify:      ## prove every injected defect was detected
	$(RUN) python -m ingestion.verify_chaos --report docs/chaos_report.md

idempotency: ## re-run one day and prove no table changed:  make idempotency DATE=2018-08-02
	$(RUN) python -m ingestion.check_idempotency --date $(DATE)

benchmark:   ## index tuning before/after -> docs/performance.md
	$(RUN) python -m ingestion.benchmark

psql:        ## open a SQL shell on the warehouse
	$(COMPOSE) exec postgres psql -U dwh -d dwh

test:        ## unit tests (no database needed)
	$(RUN) python -m pytest -q

lint:
	$(RUN) python -m ruff check ingestion tests airflow dashboard
