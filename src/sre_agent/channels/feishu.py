from __future__ import annotations

import hashlib
import json
import threading
from typing import Any, Callable

from sre_agent.config import Settings
from sre_agent.context import IncomingMessage


def verify_feishu_signature(timestamp: str, nonce: str, encrypt_key: str, body: bytes, signature: str) -> bool:
    digest = hashlib.sha256((timestamp + nonce + encrypt_key).encode() + body).hexdigest()
    return digest == signature


def feishu_challenge(body: dict) -> dict | None:
    if body.get("type") == "url_verification" and "challenge" in body:
        return {"challenge": body["challenge"]}
    return None


def _extract_text(body: dict) -> tuple[str, str, str]:
    event = body.get("event") or body
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    chat_id = message.get("chat_id") or event.get("chat_id") or "feishu"
    user_id = (sender.get("sender_id") or {}).get("open_id") or sender.get("open_id") or "unknown"
    content = message.get("content") or "{}"
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            content = {"text": content}
    text = content.get("text") or ""
    return user_id, chat_id, text


def register(app, settings: Settings, reply_fn: Callable[..., Any] | None = None) -> None:
    from fastapi import BackgroundTasks, Header, Request

    @app.post("/feishu/event")
    async def feishu_event(
        request: Request,
        background: BackgroundTasks,
        x_lark_request_timestamp: str = Header(default=""),
        x_lark_request_nonce: str = Header(default=""),
        x_lark_signature: str = Header(default=""),
    ):
        raw = await request.body()
        if settings.feishu_encrypt_key:
            ok = verify_feishu_signature(
                x_lark_request_timestamp,
                x_lark_request_nonce,
                settings.feishu_encrypt_key,
                raw,
                x_lark_signature,
            )
            if not ok:
                return {"ok": False}
        body = json.loads(raw.decode() or "{}")
        challenge = feishu_challenge(body)
        if challenge:
            return challenge
        background.add_task(_handle_event, body, settings, reply_fn)
        return {"ok": True}


def _handle_event(body: dict, settings: Settings, reply_fn: Callable[..., Any] | None) -> None:
    from sre_agent.classify import Classifier
    from sre_agent.clients.alertmanager import AlertmanagerClient
    from sre_agent.clients.prometheus import PrometheusClient
    from sre_agent.interpret import Interpreter
    from sre_agent.llm import chat_model
    from sre_agent.pipeline import run_turn
    from sre_agent.security.approvals import build_approval_store
    from sre_agent.session import build_session_store
    from sre_agent.tools.registry import bind_clients

    user_id, session_id, text = _extract_text(body)
    if not text:
        return
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
        IncomingMessage("feishu", user_id, text, session_id),
        classifier=Classifier(model),
        interpreter=Interpreter(model),
        approvals=build_approval_store(settings.database_url),
        sessions=build_session_store(settings.database_url),
        allow_ad_hoc=settings.allow_ad_hoc_promql,
    )
    if reply_fn:
        reply_fn(session_id, out.text)
        return
    threading.Thread(target=lambda: None).start()
