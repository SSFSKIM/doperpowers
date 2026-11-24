CREATE TABLE accounts (
    id          bigserial PRIMARY KEY,
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    timezone    text,              -- IANA name; NULL until the account sets it in Settings
    plan        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE billing_contacts (
    id          bigserial PRIMARY KEY,
    account_id  bigint NOT NULL REFERENCES accounts,
    name        text NOT NULL,
    email       text NOT NULL,
    phone       text,
    is_primary  boolean NOT NULL DEFAULT false
);

CREATE TABLE invoices (
    id          bigserial PRIMARY KEY,
    account_id  bigint NOT NULL REFERENCES accounts,
    number      text NOT NULL,
    issued_at   timestamptz NOT NULL,
    due_at      timestamptz NOT NULL,
    total       numeric(14, 2) NOT NULL,
    currency    char(3) NOT NULL,
    notes       text
);

CREATE TABLE invoice_lines (
    id          bigserial PRIMARY KEY,
    invoice_id  bigint NOT NULL REFERENCES invoices,
    account_id  bigint NOT NULL REFERENCES accounts,
    description text NOT NULL,
    amount      numeric(14, 2) NOT NULL,
    cost        numeric(14, 2)
);

CREATE TABLE usage_events (
    id          bigserial PRIMARY KEY,
    account_id  bigint NOT NULL REFERENCES accounts,
    product_id  bigint NOT NULL REFERENCES products,
    occurred_at timestamptz NOT NULL,
    quantity    numeric(14, 4) NOT NULL,
    unit_price  numeric(14, 6),
    currency    char(3) NOT NULL
);
CREATE INDEX usage_events_account_time ON usage_events (account_id, occurred_at);

CREATE TABLE exports_legacy (
    id          bigserial PRIMARY KEY,
    account_id  bigint NOT NULL REFERENCES accounts,
    report_id   bigint NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    body        bytea NOT NULL
);
