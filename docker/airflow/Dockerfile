# Airflow image extended with the project's tooling.
# dbt lives in its own virtualenv so its dependencies never clash with Airflow's.
FROM apache/airflow:3.2.2-python3.12

USER root
# psql / pg_isready for the bootstrap script
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt

RUN python -m venv /opt/airflow/dbt-venv \
 && /opt/airflow/dbt-venv/bin/pip install --no-cache-dir dbt-core==1.12.6 dbt-postgres==1.11.0

ENV DBT_BIN=/opt/airflow/dbt-venv/bin/dbt \
    PYTHON=python \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
