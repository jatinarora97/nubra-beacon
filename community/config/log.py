"""Structured pipeline logging (2026-07-09): every line carries an IST
timestamp + level + component so out/cron.log can answer "what ran, what did
it do, and exactly where did it break" without guessing. Stdout only — cron
and docker both capture it. LOG_LEVEL env overrides (default INFO).

Usage:  from community.config.log import get_logger
        log = get_logger("scrape")
        log.info("reddit: 18 subs across new,hot,rising")
        log.exception("stage failed")   # inside except: full traceback
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


class _ISTFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return datetime.fromtimestamp(record.created, IST).strftime("%Y-%m-%d %H:%M:%S")


_configured = False


def get_logger(component: str) -> logging.Logger:
    global _configured
    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_ISTFormatter(
            "%(asctime)s IST %(levelname)-7s [%(name)s] %(message)s"))
        root = logging.getLogger("beacon")
        root.addHandler(handler)
        root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
        root.propagate = False
        _configured = True
    return logging.getLogger(f"beacon.{component}")
