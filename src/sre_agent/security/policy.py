from __future__ import annotations

from dataclasses import dataclass

WRITE_PATTERNS: list[tuple[str, str]] = [
    ("静默", "silence"),
    ("屏蔽", "silence"),
    ("silence", "silence"),
    ("snooze", "silence"),
    ("重启", "restart"),
    ("restart", "restart"),
    ("扩容", "scale"),
    ("scale up", "scale"),
    ("删除规则", "delete_rule"),
    ("delete rule", "delete_rule"),
]


@dataclass(frozen=True)
class PolicyDecision:
    allow: bool
    reason: str
    write_action: str | None = None


def check_text(text: str) -> PolicyDecision:
    raw = (text or "").strip()
    if not raw:
        return PolicyDecision(False, "empty", None)
    lower = raw.lower()
    for needle, action in WRITE_PATTERNS:
        if needle.lower() in lower:
            return PolicyDecision(False, "write_operation", action)
    return PolicyDecision(True, "ok", None)
