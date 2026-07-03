"""Vendor the comms guardrails into community/lib/comms_guardrails/ (LLD-02 §6.6).

Copies stdlib-only modules verbatim from nubra-ai-personalization with a provenance
header; re-run to refresh; CI diff-checks for drift (--check).
"""
from __future__ import annotations

import pathlib
import re
import sys

COMMS = pathlib.Path(
    "/Users/jatin/nubra/1.Communication/nubra-ai-personalization/nubraai-comms/intelligence"
)
DEST = pathlib.Path(__file__).resolve().parent.parent / "community" / "lib" / "comms_guardrails"

VERBATIM = {  # dest name -> source path
    "content_policy.py": COMMS / "lib" / "content_policy.py",
    "validation.py": COMMS / "lib" / "validation.py",
}


def header(src: pathlib.Path) -> str:
    # Comments, not a docstring — vendored modules may start with `from __future__`.
    return (
        f"# VENDORED from {src}\n"
        "# Do not edit here; run scripts/sync_guardrails.py to refresh.\n"
        "# One safety vocabulary across push + community surfaces (LLD-02 §6.6).\n"
    )


def extract_copy_rules() -> str:
    """Extract the denylists + validate_copy from notifications/guardrails.py
    (that module also imports push-only deps we must not drag in)."""
    src = (COMMS / "notifications" / "guardrails.py").read_text()
    wanted = []
    for name in ("_FEAR_PHRASES", "_BUY_SELL_CALL_PATTERNS"):
        m = re.search(rf"^{name} = \[.*?^\]", src, re.M | re.S)
        if not m:
            raise SystemExit(f"could not extract {name} from comms guardrails.py")
        wanted.append(m.group(0))
    m = re.search(r"^@dataclass\nclass ValidationResult:.*?^def validate_copy.*?^    return ValidationResult\(True\)",
                  src, re.M | re.S)
    if not m:
        raise SystemExit("could not extract validate_copy from comms guardrails.py")
    body = "\n\n\n".join(wanted + [m.group(0)])
    return (
        header(COMMS / "notifications" / "guardrails.py")
        + "from dataclasses import dataclass\n\n\n"
        + body
        + "\n"
    )


def main(check: bool = False) -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    (DEST / "__init__.py").write_text("")
    outputs = {DEST / "copy_rules.py": extract_copy_rules()}
    for name, src in VERBATIM.items():
        outputs[DEST / name] = header(src) + src.read_text()
    drift = []
    for path, content in outputs.items():
        if check:
            if not path.exists() or path.read_text() != content:
                drift.append(path.name)
        else:
            path.write_text(content)
            print(f"vendored: {path.relative_to(DEST.parent.parent.parent)}")
    if check and drift:
        raise SystemExit(f"guardrails drift vs comms repo: {drift} — run scripts/sync_guardrails.py")
    if check:
        print("guardrails in sync")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
