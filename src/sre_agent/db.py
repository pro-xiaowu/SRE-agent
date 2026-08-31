from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    payload TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_id_idx ON messages (session_id, id);
CREATE TABLE IF NOT EXISTS clarifications (
    session_id TEXT PRIMARY KEY,
    n INT NOT NULL DEFAULT 0
);
"""


def connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row, autocommit=True)


def init_schema(conn) -> None:
    for stmt in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
        conn.execute(stmt)
