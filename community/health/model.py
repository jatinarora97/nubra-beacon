# community/health/model.py
"""Shared result type for health checks.

A check function takes (cfg, now) and returns list[Result]. `owns(...)` tags it
with the key prefixes it is responsible for, so the engine can tell "this key
is no longer reported because the problem cleared" from "this key is missing
because the check crashed".
"""
from __future__ import annotations

from dataclasses import dataclass

OK = "ok"
WARN = "warn"
CRIT = "crit"
RANK = {OK: 0, WARN: 1, CRIT: 2}


@dataclass(frozen=True)
class Result:
    key: str
    level: str
    detail: str
    hint: str = ""


def owns(*prefixes: str):
    def deco(fn):
        fn.PREFIXES = prefixes
        return fn
    return deco
