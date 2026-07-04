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
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    all_stats: dict[str, dict] = {}
    for name in STAGE_MODULES:
        if (name == "scrape" and skip_scrape) or (name == "enrich" and skip_enrich):
            typer.echo(f"[{name}] skipped by flag")
            continue
        kwargs = {"all_stats": all_stats} if name == "dispatch" else {}
        all_stats[name] = _run_stage(name, **kwargs)
    for p in (all_stats.get("dispatch") or {}).get("written", []):
        typer.echo(f"  {p}")


@app.command()
def ui(api_port: int = 8400, dash_port: int = 8501) -> None:
    """Serve the read-API (FastAPI) + dashboard (Streamlit)."""
    from community.api.serve import serve_ui

    serve_ui(api_port=api_port, dash_port=dash_port)


@app.command()
def schedule() -> None:
    """Print/install the cron plan (hourly scrape→dispatch 06–01 IST, heads-up
    08–20 IST, 06:00 morning build, Sat weekly, overnight pause)."""
    from community.scheduler.cron import show_or_install

    show_or_install()


@app.command("morning-build")
def morning_build() -> None:
    """The 06:00–07:30 orchestrated sequence (arch §8): catch-up scrape → sync
    enrich → aggregate → score → drafts → compose → dispatch roundup."""
    from community.scheduler.morning import run_morning_build

    run_morning_build()


if __name__ == "__main__":
    app()
