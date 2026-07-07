"""LLM traceability: llm_usage rows in OUR Postgres + optional Langfuse stream.

INTEGRATION PLAN (N5/N6, work plan 2026-07-07 — replicates the
nubra-ai-personalization pattern, adapted to this stage-based pipeline):

  Run ids     One `./cm` invocation = one run. A process-scoped `run_id`
              (uuid4) is minted lazily on the first traced call, so
              `./cm run-local`, `./cm stage enrich` and `./cm morning-build`
              each read as a single run in the dashboard. The read-API
              process gets its own run_id per process (stage='api' calls,
              e.g. future brief revisions). No caller has to thread ids.

  Attribution Stage + purpose are inferred from the CALL STACK: the first
              frame outside community/llm belongs to the calling stage
              package (community.enrich.* -> 'enrich', recommend.score ->
              'score', ...). Purpose = '<module>.<function>' of that frame
              (e.g. 'tagger.run', 'draft._content_proposals'). This keeps
              every call site untouched — the whole integration lives in
              community/llm/ (client.py wraps, trace.py records).

  Batch calls The Batch API path writes ONE row per submitted batch
              (batch=true) with aggregate tokens across chunks and
              metadata {batch_id, chunks, succeeded}; the -50% batch
              discount is applied in pricing. Sync retries inside
              enrich_batch each write their own row — they are real calls.

  Cost        Priced at WRITE time from the dated table below and stored in
              cost_usd, so history never silently re-prices. Unknown model
              -> cost_usd NULL (tokens still recorded; dashboard flags it).

  Config-gating (same philosophy as the Slack/Gmail senders)
              Postgres write: always on (table is part of the schema).
              Langfuse: only when LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY
              (+ optional LANGFUSE_HOST) are in .env — otherwise a silent
              no-op. Keys come from a SEPARATE Langfuse project
              ('nubra-beacon'), not the personalization one.

  Failure     Tracing must never break or slow the pipeline: every write is
              wrapped; failures log to stdout and the call proceeds.
"""
from __future__ import annotations

import contextvars
import os
import time
import uuid
from functools import lru_cache

# ── pricing (USD per 1M tokens; Anthropic list prices as of 2026-07-07,
#    cost plan §2.1). Batch API = 50% of both directions. Prefix-matched so
#    dated model ids ('claude-haiku-4-5-20251001') resolve too.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
}
BATCH_DISCOUNT = 0.5

_STAGE_BY_PACKAGE = {
    "scrape": "scrape", "clean": "clean", "enrich": "enrich",
    "aggregate": "aggregate", "recommend": None,  # split by module below
    "compose": "compose", "dispatch": "dispatch", "api": "api",
    "scheduler": "compose",  # morning-build orchestration
}

_run_id: str | None = None
_explicit_stage: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_stage", default=None)


def run_id() -> str:
    """Process-scoped run id — one per ./cm invocation / API process."""
    global _run_id
    if _run_id is None:
        _run_id = str(uuid.uuid4())
    return _run_id


def stage_context(stage: str):
    """Optional explicit override (e.g. the API's brief-revision endpoint)."""
    class _Ctx:
        def __enter__(self):
            self._tok = _explicit_stage.set(stage)

        def __exit__(self, *exc):
            _explicit_stage.reset(self._tok)
            return False
    return _Ctx()


def _infer_caller() -> tuple[str, str]:
    """(stage, purpose) from the first stack frame outside community/llm."""
    import inspect

    for frame_info in inspect.stack()[2:]:
        mod = frame_info.frame.f_globals.get("__name__", "")
        if mod.startswith("community.") and not mod.startswith("community.llm"):
            parts = mod.split(".")           # community.<pkg>.<module>
            pkg = parts[1] if len(parts) > 1 else "other"
            module = parts[-1]
            if pkg == "recommend":
                stage = "score" if module == "score" else "draft"
            else:
                stage = _STAGE_BY_PACKAGE.get(pkg) or pkg
            return stage, f"{module}.{frame_info.function}"
    return "other", "unknown.unknown"


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             batch: bool = False) -> float | None:
    for prefix, (in_rate, out_rate) in PRICES_PER_MTOK.items():
        if model.startswith(prefix):
            c = (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
            return round(c * (BATCH_DISCOUNT if batch else 1.0), 6)
    return None


@lru_cache(maxsize=1)
def _langfuse():
    """Lazy Langfuse client; None when keys absent / import fails (no-op mode).
    Keys belong to the dedicated 'nubra-beacon' Langfuse project — a separate
    stream from nubra-ai-personalization."""
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not (pk and sk):
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(public_key=pk, secret_key=sk,
                        host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"))
    except Exception as e:  # noqa: BLE001 — observability must not break calls
        print(f"[trace] langfuse init failed ({e}) — continuing without")
        return None


def _record_langfuse(purpose: str, model: str, prompt: str, system: str,
                     response: str, input_tokens: int, output_tokens: int,
                     stage: str, batch: bool, metadata: dict) -> str | None:
    c = _langfuse()
    if c is None:
        return None
    try:
        with c.start_as_current_observation(
            as_type="generation",
            name=purpose,
            input=({"prompt": (prompt or "")[:8000], "system": (system or "")[:2000]}
                   if system else (prompt or "")[:8000]),
            output=(response or "")[:8000],
            model=model,
            usage_details={"input": int(input_tokens), "output": int(output_tokens)},
            metadata={"stage": stage, "run_id": run_id(), "batch": batch,
                      **{k: v for k, v in metadata.items() if v is not None}},
        ):
            trace_id = c.get_current_trace_id()
        try:
            c.flush()
        except Exception:  # noqa: BLE001
            pass
        return trace_id
    except Exception as e:  # noqa: BLE001
        print(f"[trace] langfuse record failed ({e}) — continuing without")
        return None


def record(*, model: str, input_tokens: int, output_tokens: int,
           duration_ms: int | None = None, batch: bool = False,
           prompt: str = "", system: str = "", response: str = "",
           metadata: dict | None = None) -> None:
    """Write one llm_usage row (+ Langfuse generation when configured).
    NEVER raises — a tracing problem must not kill an LLM call."""
    try:
        stage = _explicit_stage.get()
        if stage:
            _, purpose = _infer_caller()
        else:
            stage, purpose = _infer_caller()
        meta = metadata or {}
        lf_id = _record_langfuse(purpose, model, prompt, system, response,
                                 input_tokens, output_tokens, stage, batch, meta)
        from community.store import db
        db.execute(
            """
            INSERT INTO llm_usage (run_id, stage, purpose, model, input_tokens,
                                   output_tokens, cost_usd, duration_ms, batch,
                                   langfuse_trace_id, metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (run_id(), stage, purpose, model, int(input_tokens), int(output_tokens),
             cost_usd(model, input_tokens, output_tokens, batch), duration_ms,
             batch, lf_id, db.jsonb(meta) if meta else None),
        )
    except Exception as e:  # noqa: BLE001
        print(f"[trace] llm_usage write failed ({e}) — call unaffected")


class timer:
    """Tiny context helper: `with timer() as t: ...; t.ms`."""
    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.monotonic() - self._t0) * 1000)
        return False
