# community/health/icons.py
"""Emoji for the Slack health messages, and nowhere else.

User decision 2026-10-09: Slack health alerts and the daily digest may use emoji. CLAUDE.md's
"emoji-free system chrome" still holds for the UI, logs, CLI output, config and docs, so every
emoji lives in this one module (a test fails if one appears in any other community/health
file). The plain tags ([CRITICAL], [RESOLVED], [TEST]) stay in the text, so messages remain
readable and greppable without the icons.
"""
from __future__ import annotations

# alert lines
CRITICAL = "\U0001F6A8"          # rotating light
REMINDER = "\U0001F501"          # repeat button
OK = "✅"                    # check mark button
TEST = "\U0001F514"              # bell
WARNING = "⚠️"         # warning sign

# overall status circles
HEALTHY = "\U0001F7E2"           # green circle
DEGRADED = "\U0001F7E1"          # yellow circle
CRITICAL_STATUS = "\U0001F534"   # red circle

# digest section headers
DIGEST = "\U0001FA7A"            # stethoscope (Slack subject line)
ACTIONS = "\U0001F3AF"           # direct hit
CHANGES = "\U0001F4C8"           # chart increasing
JOBS = "⚙️"            # gear
SOURCES = "\U0001F4E1"           # satellite antenna
LLM = "\U0001F4B0"               # money bag
RESOURCES = "\U0001F4CA"         # bar chart

# job state markers
NONE = "⚪"                  # white circle: nothing recorded yet
RUNNING = "\U0001F504"           # counterclockwise arrows
