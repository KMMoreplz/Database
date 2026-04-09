CREATE TABLE IF NOT EXISTS banks (
    id          SERIAL PRIMARY KEY,
    bank_name   VARCHAR(100) NOT NULL UNIQUE,
    license_no  VARCHAR(15)  NOT NULL UNIQUE,
    rating      VARCHAR(5)   NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id          SERIAL PRIMARY KEY,
    full_name   VARCHAR(255) NOT NULL,
    passport    VARCHAR(20)  NOT NULL UNIQUE,
    phone       VARCHAR(20)  NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS product_types (
    id          SMALLINT PRIMARY KEY,
    type_name   VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS risk_level (
    id          SMALLINT PRIMARY KEY,
    category    VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tbl_currencies (
    id            SMALLINT PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL UNIQUE CHECK (currency_code ~ '^[A-Z]{3}$')
);

CREATE TABLE IF NOT EXISTS products (
    id            SERIAL PRIMARY KEY,
    bank_id       INTEGER  NOT NULL REFERENCES banks(id),
    type_id       SMALLINT NOT NULL REFERENCES product_types(id),
    risk_id       SMALLINT NOT NULL REFERENCES risk_level(id),
    currency_id   SMALLINT NOT NULL REFERENCES tbl_currencies(id),
    client_id     INTEGER  NULL REFERENCES clients(id),
    product_title VARCHAR(150) NOT NULL,
    interest_rate NUMERIC(5,2)  NOT NULL CHECK (interest_rate >= 0 AND interest_rate <= 30),
    min_deposit   NUMERIC(15,2) NOT NULL CHECK (min_deposit >= 0 AND min_deposit <= 1000000),
    term_months   INTEGER NOT NULL CHECK (term_months >= 0 AND term_months <= 600),
    description   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_bank_id ON products(bank_id);
CREATE INDEX IF NOT EXISTS idx_products_type_id ON products(type_id);
CREATE INDEX IF NOT EXISTS idx_products_risk_id ON products(risk_id);
CREATE INDEX IF NOT EXISTS idx_products_currency_id ON products(currency_id);
CREATE INDEX IF NOT EXISTS idx_products_title ON products(product_title);
CREATE INDEX IF NOT EXISTS idx_products_rate ON products(interest_rate);
CREATE INDEX IF NOT EXISTS idx_products_min_deposit ON products(min_deposit);
