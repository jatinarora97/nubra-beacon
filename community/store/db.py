"""Postgres access helpers (psycopg3). One module, tiny surface.

Usage:
    from community.store.db import query, execute, executemany, one
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from community.config.settings import settings


@contextmanager
def conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.db_url, row_factory=dict_row) as c:
        yield c


def query(sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    with conn() as c:
        return c.execute(sql, params).fetchall()


def one(sql: str, params: tuple | dict | None = None) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | dict | None = None) -> int:
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.rowcount


def executemany(sql: str, seq: list[tuple]) -> None:
    if not seq:
        return
    with conn() as c:
        c.cursor().executemany(sql, seq)


def jsonb(value: Any) -> Json:
    """Wrap a python object for a jsonb parameter."""
    return Json(value)
