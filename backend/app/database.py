"""SQLite connections and the sales data schema."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

BUSINESS_SCHEMA = '''
CREATE TABLE IF NOT EXISTS divisions (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, region TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, line TEXT NOT NULL, model TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY, division_id TEXT NOT NULL REFERENCES divisions(id),
    product_id TEXT NOT NULL REFERENCES products(id), industry_group TEXT NOT NULL,
    industry TEXT NOT NULL, signed_on TEXT NOT NULL,
    gross_cents INTEGER NOT NULL, net_cents INTEGER, is_solution INTEGER CHECK(is_solution IN (0,1))
);
CREATE TABLE IF NOT EXISTS monthly_sales (
    contract_id TEXT NOT NULL REFERENCES contracts(id), period TEXT NOT NULL,
    revenue_cents INTEGER, net_revenue_cents INTEGER, paid_cents INTEGER,
    PRIMARY KEY (contract_id, period)
);
CREATE TABLE IF NOT EXISTS annual_targets (
    division_id TEXT NOT NULL REFERENCES divisions(id), year INTEGER NOT NULL,
    commercial_cents INTEGER, solution_cents INTEGER, PRIMARY KEY (division_id, year)
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, division_id TEXT NOT NULL REFERENCES divisions(id),
    contract_id TEXT REFERENCES contracts(id), landed_on TEXT,
    risk TEXT NOT NULL CHECK(risk IN ('低风险','中风险','高风险')), stage TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset (
    id TEXT PRIMARY KEY, version TEXT NOT NULL, as_of TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contracts_signed ON contracts(signed_on);
CREATE INDEX IF NOT EXISTS monthly_sales_period ON monthly_sales(period);
'''


@contextmanager
def connection(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path: Path) -> None:
    with connection(path) as db:
        db.executescript(BUSINESS_SCHEMA)
