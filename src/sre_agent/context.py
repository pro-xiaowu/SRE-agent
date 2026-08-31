from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

IntentName = Literal[
    "firing_alerts",
    "alert_by_service",
    "cpu_usage",
    "memory_usage",
    "http_error_rate",
    "http_latency",
    "restart_count",
    "disk_usage",
    "target_health",
    "ad_hoc_query",
    "explain_promql",
    "request_write",
    "unknown",
]


class IntentSlots(BaseModel):
    intent: IntentName
    confidence: float = 0.0
    job: str | None = None
    window: str = "15m"
    service: str | None = None
    instance: str | None = None
    promql: str | None = None
    missing_slots: list[str] = Field(default_factory=list)
    ask_user: str | None = None


@dataclass
class QueryPlan:
    template_id: str | None
    promql: str | None
    tool: str
    params: dict[str, Any]
    reject_reason: str | None = None


@dataclass
class IncomingMessage:
    channel: str
    user_id: str
    text: str
    session_id: str


@dataclass
class OutgoingMessage:
    text: str
    promql_blocks: list[str]
    cards: list[dict] | None
    approval_id: str | None
    intent: str | None = None
    status: str = "ok"
