# VENDORED from /Users/jatin/nubra/1.Communication/nubra-ai-personalization/nubraai-comms/intelligence/lib/validation.py
# Do not edit here; run scripts/sync_guardrails.py to refresh.
# One safety vocabulary across push + community surfaces (LLD-02 §6.6).
"""Shared output validators — the reusable checks that catch the bug classes we
keep hitting across surfaces (email, report, WA text/images, persona, risk):

  1. Western currency units (₹1.27M / ₹731K) instead of Indian lakh/crore.
  2. NaN / None / "undefined" leaking into rendered copy.
  3. A stated % change that doesn't reconcile with the values it's derived from
     (the weekly-baseline bug).
  4. Trading-day gaps / duplicated daily rows (missing 06-04, FII dup).

These are pure functions over already-rendered text or plain numbers, so they're
trivially unit-testable and every renderer can call `validate_text()` on its
output before it ships. `scripts/validate_all.py` runs them across surfaces.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable


# ── issue model ───────────────────────────────────────────────────────────

@dataclass
class Issue:
    severity: str   # "HIGH" | "MED" | "LOW"
    code: str       # short machine code, e.g. "western_currency"
    message: str
    context: str = ""

    def __str__(self) -> str:
        c = f" — …{self.context}…" if self.context else ""
        return f"[{self.severity}] {self.code}: {self.message}{c}"


# ── text checks ─────────────────────────────────────────────────────────────

# ₹ (optionally with spaces) then a number then a Western magnitude suffix.
_WESTERN_CCY = re.compile(r"₹\s?[\d,]+(?:\.\d+)?\s?[MmKkBb](?![A-Za-z])")
# A bare ₹ number with 7+ digits (≥ ₹10,00,000) that should be lakh/crore.
_RAW_BIG_RUPEE = re.compile(r"₹\s?\d{1,3}(?:,?\d{3}){2,}(?:\.\d+)?(?!\s?(?:L\b|Cr|lakh|crore|K|M))")
_NAN_LEAK = re.compile(r"(?<![A-Za-z])(nan|NaN|None|undefined|NULL|Infinity)(?![A-Za-z])")
# Raw/encoded instrument symbols that must be humanised before reaching user copy:
# "PE_24000000", "CE2400000", "NIFTY24500CE". The humaniser emits spaced forms
# ("NIFTY 23000 PE") which never match, so only un-humanised leaks are flagged.
_RAW_SYMBOL = re.compile(r"\b(?:CE|PE|FUT)_?\d{4,}\b|\b[A-Z]{3,}\d{4,}(?:CE|PE|FUT)\b")


def _excerpt(text: str, m: re.Match, pad: int = 18) -> str:
    s = max(0, m.start() - pad)
    return text[s:m.end() + pad].replace("\n", " ").strip()


def check_currency(text: str) -> list[Issue]:
    """Flag Western magnitude units (M/K/B) on ₹ amounts — Indian copy must use
    lakh (L) / crore (Cr)."""
    out = []
    for m in _WESTERN_CCY.finditer(text or ""):
        out.append(Issue("HIGH", "western_currency",
                          f"rupee amount uses Western unit: {m.group(0).strip()!r} (use lakh/crore)",
                          _excerpt(text, m)))
    # A bare ₹ amount of 7+ digits (≥ ₹10 lakh) with no lakh/crore unit — the
    # auto-formatter never emits this (it switches to L/Cr above ₹1 lakh), so it's
    # an un-formatted leak. MED (surface, don't block): grouped Indian digits are
    # still readable, just not the house style.
    for m in _RAW_BIG_RUPEE.finditer(text or ""):
        out.append(Issue("MED", "unformatted_rupee",
                          f"large ₹ amount not abbreviated: {m.group(0).strip()!r} (prefer lakh/crore)",
                          _excerpt(text, m)))
    return out


def check_nan_leak(text: str) -> list[Issue]:
    """Flag nan/None/undefined leaking into rendered copy."""
    out = []
    for m in _NAN_LEAK.finditer(text or ""):
        out.append(Issue("HIGH", "nan_leak",
                          f"placeholder/None value leaked into output: {m.group(0)!r}",
                          _excerpt(text, m)))
    return out


def check_raw_symbols(text: str) -> list[Issue]:
    """Flag raw/encoded instrument symbols leaking into user-facing copy
    (e.g. 'PE_24000000', 'NIFTY24500CE') — these must be humanised first."""
    out = []
    for m in _RAW_SYMBOL.finditer(text or ""):
        out.append(Issue("HIGH", "raw_symbol",
                          f"raw instrument symbol leaked into copy: {m.group(0)!r} (humanise it)",
                          _excerpt(text, m)))
    return out


def validate_text(text: str, label: str = "") -> list[Issue]:
    """Run all text-level checks. `label` is prefixed onto messages."""
    issues = check_currency(text) + check_nan_leak(text) + check_raw_symbols(text)
    if label:
        for i in issues:
            i.message = f"{label}: {i.message}"
    return issues


# ── numeric / reconciliation checks ──────────────────────────────────────────

def reconcile_pct(prior: float | None, current: float | None,
                  stated_pct: float | None, *, tol: float = 0.06,
                  what: str = "change_pct") -> list[Issue]:
    """Verify a stated % change equals (current-prior)/prior. Catches the
    weekly-baseline bug (% measured from the wrong reference)."""
    if prior in (None, 0) or current is None or stated_pct is None:
        return []
    expected = (current - prior) / prior * 100.0
    if abs(expected - stated_pct) > tol:
        return [Issue("HIGH", "pct_mismatch",
                      f"{what} stated {stated_pct:+.2f}% but values imply {expected:+.2f}% "
                      f"(prior={prior}, current={current})")]
    return []


# ── trading-day continuity ───────────────────────────────────────────────────

def _d(x) -> date:
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return date.fromisoformat(str(x))


def check_trading_days(dates: Iterable, *, what: str = "window") -> list[Issue]:
    """Flag weekday gaps in a date sequence (a missing trading day like 06-04).
    Weekends are ignored; exchange holidays may cause benign hits."""
    ds = sorted({_d(x) for x in dates})
    if len(ds) < 2:
        return []
    out = []
    cur = ds[0]
    present = set(ds)
    while cur <= ds[-1]:
        if cur.weekday() < 5 and cur not in present:
            out.append(Issue("MED", "missing_trading_day",
                              f"{what}: no row for {cur.isoformat()} ({cur.strftime('%a')}) "
                              "— missing session or holiday"))
        cur += timedelta(days=1)
    return out


def check_duplicate_series(pairs: list[tuple], *, what: str = "series") -> list[Issue]:
    """Flag consecutive days carrying identical values — usually a missed fetch
    that copied the prior day (the FII/DII 06-02==06-03 dup)."""
    out = []
    prev_d = prev_v = None
    for d, v in sorted(pairs, key=lambda t: _d(t[0])):
        if prev_v is not None and v is not None and v == prev_v:
            out.append(Issue("MED", "duplicate_daily_value",
                             f"{what}: {_d(d).isoformat()} duplicates {_d(prev_d).isoformat()} "
                             f"(value={v}) — likely a missed daily fetch"))
        prev_d, prev_v = d, v
    return out


# ── news link validation ──────────────────────────────────────────────────

def _wellformed_url(url: str) -> bool:
    from urllib.parse import urlparse
    try:
        p = urlparse(url or "")
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def validate_news_links(items: list[dict], *, check_reachable: bool = True,
                        max_check: int = 10, timeout: int = 4,
                        url_key: str = "url") -> tuple[list[dict], dict]:
    """Return (clean_items, stats) — drop news items whose link is malformed or
    definitively dead. Well-formedness (http/https + host) is always enforced;
    reachability is a bounded, best-effort HEAD on the first `max_check` items.
    News sites routinely block bots, so only a definitive 404/410 drops an item
    — timeouts / 403 / network errors are kept (never false-drop a real story)."""
    items = items or []
    wf = [it for it in items if _wellformed_url(it.get(url_key))]
    stats = {"malformed": len(items) - len(wf), "dead": 0}
    if not check_reachable or not wf:
        return wf, stats

    import concurrent.futures
    import requests

    def _alive(url: str) -> bool:
        hdr = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.head(url, timeout=timeout, allow_redirects=True, headers=hdr)
            if r.status_code in (403, 405):           # HEAD blocked/disallowed → try GET
                r = requests.get(url, timeout=timeout, stream=True, headers=hdr)
            return r.status_code not in (404, 410)
        except Exception:
            return True                                # network hiccup / block → keep

    head, tail = wf[:max_check], wf[max_check:]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        alive = list(ex.map(lambda it: _alive(it.get(url_key)), head))
    stats["dead"] = len(head) - sum(alive)
    kept = [it for it, ok in zip(head, alive) if ok] + tail
    return kept, stats


# ── convenience ──────────────────────────────────────────────────────────────

def summarize(issues: list[Issue]) -> dict:
    out = {"HIGH": 0, "MED": 0, "LOW": 0}
    for i in issues:
        out[i.severity] = out.get(i.severity, 0) + 1
    out["total"] = len(issues)
    return out
