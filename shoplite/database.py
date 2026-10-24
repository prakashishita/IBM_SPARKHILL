"""SQLite access for ShopLite.

Every SQL statement is counted, both per request (exposed as the
X-DB-Queries response header) and globally since startup (exposed at
/stats/query-count), so load tests can report exact query numbers.
"""

import os
import sqlite3
import threading

from flask import g

DB_PATH = os.environ.get(
    "SHOPLITE_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL,
    price     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL,
    amount      REAL NOT NULL,
    created_at  TEXT NOT NULL
);
"""

_total_queries = 0
_lock = threading.Lock()


def _record_query(counter):
    global _total_queries
    with _lock:
        _total_queries += 1
    if counter is not None:
        counter[0] += 1


def connect(counter=None):
    """Open a new connection. `counter` is an optional one-item list incremented per statement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.set_trace_callback(lambda _sql: _record_query(counter))
    return conn


def get_db():
    """Return the connection for the current request, opening it on first use."""
    if "db" not in g:
        g.query_counter = [0]
        g.db = connect(g.query_counter)
    return g.db


def request_query_count():
    counter = g.get("query_counter")
    return counter[0] if counter else 0


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def total_query_count():
    with _lock:
        return _total_queries


def reset_total_query_count():
    global _total_queries
    with _lock:
        _total_queries = 0


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()
