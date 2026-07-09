"""Nubra Community Manager — pipeline runner (CLI).

Usage:
    ./cm run-local                 # end-to-end: scrape → … → dispatch
    ./cm stage scrape              # single stage (see STAGE_MODULES)
    ./cm ui                        # read-API (:8400) + dashboard (:8501)
    ./cm migrate

Pipeline stages map 1:1 to packages under community/:
    scrape/    pull raw data (X, Reddit)             → community.scrape.ingest
    clean/     normalize · dedup · de-noise          → community.clean.dedup
    enrich/    tag topic/intent/entities (LLM)       → community.enrich.tagger
    aggregate/ trends · issues · features · voices   → community.aggregate.rollups
    recommend/ score + draft + compliance            → …recommend.score, …recommend.draft
    compose/   build messages (analytics + actions)  → community.compose.roundup
    dispatch/  send: Slack · Gmail · archive         → community.dispatch.local
"""
from __future__ import annotations

import json
import time

import typer

from community.config.settings import settings

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

STAGE_MODULES = {
    "scrape": "community.scrape.ingest",
    "clean": "community.clean.dedup",
    "enrich": "community.enrich.tagger",
    "aggregate": "community.aggregate.rollups",
    "score": "community.recommend.score",
    "draft": "community.recommend.draft",
    "compose": "community.compose.roundup",
    "dispatch": "community.dispatch.local",
}


def _run_stage(name: str, **kwargs) -> dict:
    import importlib

    mod = importlib.import_module(STAGE_MODULES[name])
    t0 = time.time()
    stats = mod.run(**kwargs) or {}
    stats["_seconds"] = round(time.time() - t0, 1)
    typer.echo(f"[{name}] {json.dumps(stats, default=str)[:400]}")
    return stats


# One pipeline at a time: the 06:00 morning build (runs to ~07:30) overlaps the
# 07:00 hourly by design, and Saturday's weekly compose collides with the 10:00
# hourly. Concurrent pipelines double-submit LLM batches, race feature-key
# minting, and double-send heads-ups — so acquire a session-scoped Postgres
# advisory lock and SKIP (exit 0) when another run holds it. The lock dies with
# the connection, so a killed run can never wedge the next one.
_PIPELINE_LOCK_KEY = 0x6E756272  # "nubr"


def _acquire_pipeline_lock():
    """Returns the lock-holding connection, or None if another run is active."""
    import psycopg

    conn = psycopg.connect(settings.db_url, autocommit=True)
    got = conn.execute("SELECT pg_try_advisory_lock(%s)", (_PIPELINE_LOCK_KEY,)).fetchone()[0]
    if not got:
        conn.close()
        return None
    return conn


def _with_pipeline_lock(label: str, fn) -> None:
    lock = _acquire_pipeline_lock()
    if lock is None:
        typer.echo(f"[{label}] another pipeline run is active — skipping this run")
        raise typer.Exit(0)
    try:
        fn()
    finally:
        lock.close()  # releases the advisory lock


@app.command()
def migrate() -> None:
    from migrations.run_migrations import main

    main()


@app.command()
def stage(name: str) -> None:
    if name not in STAGE_MODULES:
        raise typer.BadParameter(f"unknown stage {name!r}; one of {list(STAGE_MODULES)}")
    _run_stage(name)


@app.command("run-local")
def run_local(skip_scrape: bool = False, skip_enrich: bool = False) -> None:
    """End-to-end run: scrape → clean → enrich → aggregate → score → draft →
    compose → dispatch (messages to Slack/Gmail when configured + out/messages/)."""
    _with_pipeline_lock("run-local", lambda: _run_local_inner(skip_scrape, skip_enrich))


def _run_local_inner(skip_scrape: bool, skip_enrich: bool) -> None:
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    all_stats: dict[str, dict] = {}
    for name in STAGE_MODULES:
        if (name == "scrape" and skip_scrape) or (name == "enrich" and skip_enrich):
            typer.echo(f"[{name}] skipped by flag")
            continue
        kwargs = {"all_stats": all_stats} if name == "dispatch" else {}
        # Per-stage isolation: watermarks make every stage independently safe,
        # so one failing stage (chromium crash, LLM outage) degrades the run
        # instead of forfeiting every stage behind it for the hour.
        try:
            all_stats[name] = _run_stage(name, **kwargs)
        except Exception as e:  # noqa: BLE001
            all_stats[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            typer.echo(f"[{name}] STAGE FAILED — continuing: {all_stats[name]['error']}")
    for p in (all_stats.get("dispatch") or {}).get("written", []):
        typer.echo(f"  {p}")


@app.command()
def ui(api_port: int = 8400, dash_port: int = 3000) -> None:
    """Serve the read-API (FastAPI, :8400) + the Next.js dashboard (:3000)."""
    from community.api.serve import serve_ui

    serve_ui(api_port=api_port, dash_port=dash_port)


@app.command()
def schedule(install: bool = typer.Option(False, "--install"),
             docker: bool = typer.Option(False, "--docker",
                                         help="prod flavor: exec into the api container")) -> None:
    """Print/install the cron plan (hourly scrape→dispatch 06–01 IST, heads-up
    08–20 IST, 06:00 morning build, Sat weekly, overnight pause)."""
    from community.scheduler.cron import cron_block, show_or_install

    if docker and not install:
        print(cron_block(docker=True))
        print("\n# canonical prod copy: deploy/crontab.prod (set APP_DIR there)")
        return
    show_or_install(install)


@app.command("morning-build")
def morning_build() -> None:
    """The 06:00–07:30 orchestrated sequence (arch §8): catch-up scrape → sync
    enrich → aggregate → score → drafts → compose → dispatch roundup."""
    from community.scheduler.morning import run_morning_build

    _with_pipeline_lock("morning-build", run_morning_build)


if __name__ == "__main__":
    app()
