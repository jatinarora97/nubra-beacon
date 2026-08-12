"""Instagram media helpers: S3 persistence, whisper transcription, Haiku vision.

Design: docs/instagram-collector-plan-2026-08-12.md §3–§5. CDN URLs expire in
hours, so media is downloaded AT FETCH and persisted to S3
(nubra_beacon/instagram/<creator>/{reels,images}/<shortCode>...). Transcription
is faster-whisper large-v3 int8 task=translate (POC-locked: VAD off, language
auto-detect) — always outputs English; music-only reels yield nothing and are
a documented limitation. All helpers are best-effort: failures log and return
None/empty, never break collection.
"""
from __future__ import annotations

import base64
import os
import subprocess
import tempfile
from pathlib import Path

import httpx

from community.config.log import get_logger

log = get_logger("scrape.instagram.av")

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
_S3_PREFIX = "nubra_beacon/instagram"


# ── S3 ─────────────────────────────────────────────────────────────────────

def _bucket() -> str:
    return os.getenv("S3_BUCKET", "").strip()


def _s3():
    import boto3
    return boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))


def s3_enabled() -> bool:
    return bool(_bucket())


def media_key(creator: str, short_code: str, kind: str, suffix: str = "") -> str:
    folder = "reels" if kind == "reel" else "images"
    ext = ".mp4" if kind == "reel" else ".jpg"
    return f"{_S3_PREFIX}/{creator}/{folder}/{short_code}{suffix}{ext}"


def store_media(url: str, key: str) -> str | None:
    """Download a (soon-expiring) CDN URL and persist to S3. Returns the key,
    or None on any failure (collection continues without media)."""
    if not s3_enabled() or not url:
        return None
    try:
        with httpx.Client(timeout=90, follow_redirects=True, headers=_UA) as c:
            r = c.get(url)
            r.raise_for_status()
        _s3().put_object(Bucket=_bucket(), Key=key, Body=r.content)
        return key
    except Exception as e:  # noqa: BLE001 — media is best-effort by design
        log.warning("media store failed for %s (%s: %s)", key, type(e).__name__, str(e)[:120])
        return None


def fetch_media(key: str) -> Path | None:
    """Pull an S3 object to a temp file (caller unlinks). None on failure."""
    if not s3_enabled():
        return None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(key).suffix)
        _s3().download_fileobj(_bucket(), key, tmp)
        tmp.close()
        return Path(tmp.name)
    except Exception as e:  # noqa: BLE001
        log.warning("media fetch failed for %s (%s)", key, type(e).__name__)
        return None


# ── whisper (tier 1) ───────────────────────────────────────────────────────

_model = None
_model_name = None


def _whisper(model_name: str):
    """Lazy singleton — ~2-3GB RAM while loaded; tiers run SEQUENTIALLY."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        from faster_whisper import WhisperModel
        _model = WhisperModel(model_name, device="cpu", compute_type="int8")
        _model_name = model_name
    return _model


def _clip_from(path: Path, offset_s: float, cap_s: float | None) -> Path | None:
    """ffmpeg-copy a resume window (-ss offset [-t cap]) to a temp file."""
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        out.close()
        cmd = [ff, "-y", "-loglevel", "error", "-ss", str(offset_s), "-i", str(path)]
        if cap_s:
            cmd += ["-t", str(cap_s)]
        cmd += ["-c", "copy", out.name]
        subprocess.run(cmd, check=True, timeout=120)
        return Path(out.name)
    except Exception as e:  # noqa: BLE001
        log.warning("ffmpeg clip failed (%s)", type(e).__name__)
        return None


def transcribe(path: Path, *, model_name: str = "large-v3", offset_s: float = 0.0,
               cap_s: float | None = None) -> dict:
    """POC-locked config: task=translate, language auto-detect, NO VAD.
    Returns {text, end_s, language, language_probability} — text is English
    regardless of spoken language; empty for music-only audio. Trailing
    hallucination guard: high-no_speech_prob tail segments are dropped."""
    src: Path | None = path
    clipped = None
    if offset_s > 0 or cap_s:
        clipped = _clip_from(path, offset_s, cap_s)
        src = clipped or path
    try:
        segments, info = _whisper(model_name).transcribe(
            str(src), task="translate", language=None,
            vad_filter=False, condition_on_previous_text=False,
        )
        segs = list(segments)
        while segs and segs[-1].no_speech_prob > 0.6:
            segs.pop()
        return {
            "text": " ".join(s.text.strip() for s in segs).strip(),
            "end_s": offset_s + (segs[-1].end if segs else 0.0),
            "language": info.language,
            "language_probability": round(info.language_probability, 2),
        }
    finally:
        if clipped:
            clipped.unlink(missing_ok=True)


# ── Haiku vision (tier 2) ──────────────────────────────────────────────────

def describe_images(keys: list[str], caption: str) -> tuple[str | None, dict]:
    """One vision call over ALL slides (≤10, user decision). Returns
    (on_screen_text, usage). Recorded in llm_usage/Langfuse via trace."""
    from community.config.settings import settings
    from community.llm import trace
    from community.llm.client import client

    content: list[dict] = []
    paths: list[Path] = []
    try:
        for key in keys[:10]:
            p = fetch_media(key)
            if not p:
                continue
            paths.append(p)
            b64 = base64.standard_b64encode(p.read_bytes()).decode()
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
        if not content:
            return None, {}
        content.append({"type": "text", "text":
            "These are the slides/keyframe of an Instagram post by an Indian finance "
            f"creator. Caption: {caption[:400]!r}. Produce a faithful compact "
            "transcription+description of what is ON-SCREEN across the slides, in "
            "order: visible text, charts, tickers, numbers, claims. No interpretation "
            "beyond what is visible. Max 200 words."})
        with trace.timer() as t:
            r = client().messages.create(model=settings.enrich_model, max_tokens=700,
                                         messages=[{"role": "user", "content": content}])
        text = next((b.text for b in r.content if b.type == "text"), "").strip()
        trace.record(model=settings.enrich_model,
                     input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens,
                     duration_ms=t.ms, prompt=f"[instagram vision x{len(paths)} slides]",
                     response=text, metadata={"stage": "instagram_vision", "slides": len(paths)})
        usage = {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens}
        return (text or None), usage
    except Exception as e:  # noqa: BLE001
        log.warning("vision failed (%s: %s)", type(e).__name__, str(e)[:120])
        return None, {}
    finally:
        for p in paths:
            p.unlink(missing_ok=True)
