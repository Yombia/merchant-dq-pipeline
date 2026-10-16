-- Runs once, on the first start of the Postgres container.
-- One server, two databases: Airflow's metadata DB and the data warehouse.
CREATE ROLE airflow LOGIN PASSWORD 'airflow';
CREATE DATABASE airflow OWNER airflow;

CREATE ROLE dwh LOGIN PASSWORD 'dwh';
CREATE DATABASE dwh OWNER dwh;
