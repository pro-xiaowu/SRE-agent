from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Callable

from sre_agent.config import Settings
from sre_agent.context import IncomingMessage


def dingtalk_routes_enabled(settings: Settings) -> bool:
    return bool(settings.dingtalk_app_secret)


def verify_signature(secret: str, timestamp: str, signature: str) -> bool:
    mac = hmac.new(secret.encode(), f"{timestamp}\n{secret}".encode(), hashlib.sha256).digest()
    import base64

    expected = base64.b64encode(mac).decode()
    return expected == signature


def register(app, settings: Settings, reply_fn: Callable[..., Any] | None = None) -> None:
    from fastapi import BackgroundTasks, Request

    @app.post("/dingtalk/event")
    async def dingtalk_event(request: Request, background: BackgroundTasks):
        body = await request.json()
        text = (body.get("text") or {}).get("content") or body.get("content") or ""
        user_id = str(body.get("senderStaffId") or body.get("senderId") or "unknown")
        session_id = str(body.get("conversationId") or "dingtalk")
        background.add_task(_handle, settings, user_id, session_id, text.strip(), reply_fn)
        return {"ok": True}


def _handle(
    settings: Settings,
    user_id: str,
    session_id: str,
    text: str,
    reply_fn: Callable[..., Any] | None,
) -> None:
    if not text:
        return
    from sre_agent.classify import Classifier
    from sre_agent.clients.alertmanager import AlertmanagerClient
    from sre_agent.clients.prometheus import PrometheusClient
    from sre_agent.interpret import Interpreter
    from sre_agent.llm import chat_model
    from sre_agent.pipeline import run_turn
    from sre_agent.security.approvals import build_approval_store
    from sre_agent.session import build_session_store
    from sre_agent.tools.registry import bind_clients

    model = chat_model(settings)
    bind_clients(
        PrometheusClient(
            settings.prom_url,
            settings.query_timeout_seconds,
            settings.max_points,
            bearer=settings.prom_bearer,
        ),
        AlertmanagerClient(settings.am_url, settings.query_timeout_seconds),
    )
    out = run_turn(
        IncomingMessage("dingtalk", user_id, text, session_id),
        classifier=Classifier(model),
        interpreter=Interpreter(model),
        approvals=build_approval_store(settings.database_url),
        sessions=build_session_store(settings.database_url),
        allow_ad_hoc=settings.allow_ad_hoc_promql,
    )
    if reply_fn:
        reply_fn(session_id, out.text)
