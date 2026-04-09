SET NAMES utf8mb4;
SET collation_connection = 'utf8mb4_unicode_ci';

CREATE TABLE IF NOT EXISTS banks (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    bank_name   VARCHAR(100) NOT NULL UNIQUE,
    license_no  VARCHAR(15)  NOT NULL UNIQUE,
    rating      VARCHAR(5)   NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS clients (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    full_name   VARCHAR(255) NOT NULL,
    passport    VARCHAR(20)  NOT NULL UNIQUE,
    phone       VARCHAR(20)  NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS product_types (
    id          SMALLINT PRIMARY KEY,
    type_name   VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS risk_level (
    id          SMALLINT PRIMARY KEY,
    category    VARCHAR(20) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tbl_currencies (
    id            SMALLINT PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS products (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    bank_id       INT NOT NULL,
    type_id       SMALLINT NOT NULL,
    risk_id       SMALLINT NOT NULL,
    currency_id   SMALLINT NOT NULL,
    client_id     INT NULL,
    product_title VARCHAR(150) NOT NULL,
    interest_rate DECIMAL(5,2) NOT NULL,
    min_deposit   DECIMAL(15,2) NOT NULL,
    term_months   INT NOT NULL,
    description   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_products_bank FOREIGN KEY (bank_id) REFERENCES banks(id),
    CONSTRAINT fk_products_type FOREIGN KEY (type_id) REFERENCES product_types(id),
    CONSTRAINT fk_products_risk FOREIGN KEY (risk_id) REFERENCES risk_level(id),
    CONSTRAINT fk_products_currency FOREIGN KEY (currency_id) REFERENCES tbl_currencies(id),
    CONSTRAINT fk_products_client FOREIGN KEY (client_id) REFERENCES clients(id),
    CONSTRAINT ck_rate_range CHECK (interest_rate >= 0 AND interest_rate <= 30),
    CONSTRAINT ck_min_deposit_range CHECK (min_deposit >= 0 AND min_deposit <= 1000000),
    CONSTRAINT ck_term_range CHECK (term_months >= 0 AND term_months <= 600)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_products_bank_id ON products(bank_id);
CREATE INDEX idx_products_type_id ON products(type_id);
CREATE INDEX idx_products_risk_id ON products(risk_id);
CREATE INDEX idx_products_currency_id ON products(currency_id);
CREATE INDEX idx_products_title ON products(product_title);
CREATE INDEX idx_products_rate ON products(interest_rate);
CREATE INDEX idx_products_min_deposit ON products(min_deposit);
