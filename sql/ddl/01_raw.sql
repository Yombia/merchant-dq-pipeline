-- Raw layer: an exact, append-only copy of what the source delivered.
-- Every business column is TEXT on purpose: nothing is cast or rejected at load time,
-- so a malformed value is kept (and later caught by DQ checks) instead of crashing the load.
-- Metadata columns make every row traceable to its batch and file.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.orders (
    _row_id                        BIGSERIAL PRIMARY KEY,
    order_id                       TEXT,
    customer_id                    TEXT,
    order_status                   TEXT,
    order_purchase_timestamp       TEXT,
    order_approved_at              TEXT,
    order_delivered_carrier_date   TEXT,
    order_delivered_customer_date  TEXT,
    order_estimated_delivery_date  TEXT,
    _batch_date                    DATE NOT NULL,
    _source_file                   TEXT NOT NULL,
    _loaded_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.order_items (
    _row_id              BIGSERIAL PRIMARY KEY,
    order_id             TEXT,
    order_item_id        TEXT,
    product_id           TEXT,
    seller_id            TEXT,
    shipping_limit_date  TEXT,
    price                TEXT,
    freight_value        TEXT,
    _batch_date          DATE NOT NULL,
    _source_file         TEXT NOT NULL,
    _loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.payments (
    _row_id               BIGSERIAL PRIMARY KEY,
    order_id              TEXT,
    payment_sequential    TEXT,
    payment_type          TEXT,
    payment_installments  TEXT,
    payment_value         TEXT,
    _batch_date           DATE NOT NULL,
    _source_file          TEXT NOT NULL,
    _loaded_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.customers (
    _row_id                   BIGSERIAL PRIMARY KEY,
    customer_id               TEXT,
    customer_unique_id        TEXT,
    customer_zip_code_prefix  TEXT,
    customer_city             TEXT,
    customer_state            TEXT,
    _batch_date               DATE NOT NULL,
    _source_file              TEXT NOT NULL,
    _loaded_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.sellers (
    _row_id                 BIGSERIAL PRIMARY KEY,
    seller_id               TEXT,
    seller_zip_code_prefix  TEXT,
    seller_city             TEXT,
    seller_state            TEXT,
    _batch_date             DATE NOT NULL,
    _source_file            TEXT NOT NULL,
    _loaded_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.products (
    _row_id                     BIGSERIAL PRIMARY KEY,
    product_id                  TEXT,
    product_category_name       TEXT,
    product_name_lenght         TEXT,
    product_description_lenght  TEXT,
    product_photos_qty          TEXT,
    product_weight_g            TEXT,
    product_length_cm           TEXT,
    product_height_cm           TEXT,
    product_width_cm            TEXT,
    _batch_date                 DATE NOT NULL,
    _source_file                TEXT NOT NULL,
    _loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Loads delete + re-insert one batch at a time, so the batch column must be fast to filter.
CREATE INDEX IF NOT EXISTS ix_raw_orders_batch      ON raw.orders (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_order_items_batch ON raw.order_items (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_payments_batch    ON raw.payments (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_customers_batch   ON raw.customers (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_sellers_batch     ON raw.sellers (_batch_date);
CREATE INDEX IF NOT EXISTS ix_raw_products_batch    ON raw.products (_batch_date);
