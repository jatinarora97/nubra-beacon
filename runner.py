"""Nubra Community Manager — pipeline runner (CLI).

Local (non-prod) usage:
    .venv/bin/python runner.py run-local          # end-to-end: ingest → … → messages/*.md
    .venv/bin/python runner.py stage ingest       # single stage
    .venv/bin/python runner.py migrate

Stage contract (each module exposes `run(**kwargs) -> dict` returning stats that
feed the heads-up ops summary):
    community.pipeline.ingest.run()      -> {fetched_by_source, backfilled, x_live_note, ...}
    community.pipeline.dedup.run()       -> {checked, exact_dupes, near_dupes}
    community.pipeline.enrich.run()      -> {prefiltered_noise, enriched, llm_calls, fallback}
    community.pipeline.aggregate.run()   -> {conversations, topics_rising, issues, features}
    community.pipeline.score.run()       -> {scored, new_ge70, nubra_mentions}
    community.pipeline.recommend.run()   -> {drafted, gated, dropped, proposals}
    community.pipeline.roundup.run()     -> {payload}
    community.delivery.render            -> writes out/messages/*.md (local) / Slack+email (prod)
"""
from __future__ import annotations

import json
import time

import typer

from community.config.settings import settings

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

STAGES = ["ingest", "dedup", "enrich", "aggregate", "score", "recommend", "roundup"]


def _run_stage(name: str, **kwargs) -> dict:
    import importlib

    mod = importlib.import_module(f"community.pipeline.{name}")
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
    if name not in STAGES:
        raise typer.BadParameter(f"unknown stage {name!r}; one of {STAGES}")
    _run_stage(name)


@app.command("run-local")
def run_local(skip_ingest: bool = False, skip_enrich: bool = False) -> None:
    """End-to-end local run: real Reddit fetch + X CSV backfill (+ X live capped),
    enrich via Haiku (sync), aggregate, score, drafts+compliance, then write the
    heads-up + daily roundup as markdown into out/messages/."""
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    # Local-run stage kwargs: backfilled CSV data is days old, so scoring needs a
    # wide lookback (prod default is the recent window).
    stage_kwargs: dict[str, dict] = {"score": {"lookback_hours": 24 * 14}}
    all_stats: dict[str, dict] = {}
    for name in STAGES:
        if (name == "ingest" and skip_ingest) or (name == "enrich" and skip_enrich):
            typer.echo(f"[{name}] skipped by flag")
            continue
        all_stats[name] = _run_stage(name, **stage_kwargs.get(name, {}))

    from community.delivery import render

    paths = render.write_local_messages(all_stats)
    typer.echo("\nMessages written:")
    for p in paths:
        typer.echo(f"  {p}")


if __name__ == "__main__":
    app()
