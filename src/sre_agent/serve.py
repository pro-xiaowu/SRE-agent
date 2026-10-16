from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from uuid import uuid4

from sre_agent.config import Settings

app = FastAPI(title="SRE-Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


class AskBody(BaseModel):
    text: str = Field(min_length=1)
    session_id: str = "web"


class SessionBody(BaseModel):
    title: str = "新会话"
    session_id: str | None = None


@app.post("/api/ask")
def api_ask(body: AskBody):
    from sre_agent.runtime import run_ask

    out = run_ask(body.text, channel="web", session_id=body.session_id)
    return {
        "text": out.text,
        "promql_blocks": [q for q in out.promql_blocks if q and q != "null"],
        "approval_id": out.approval_id,
        "intent": out.intent,
        "status": out.status,
    }


@app.get("/api/health")
def api_health():
    return {"ok": True}


def _session_store():
    from sre_agent.config import load_settings
    from sre_agent.session import build_session_store

    return build_session_store(load_settings().database_url)


@app.get("/api/sessions")
def api_sessions():
    return {"sessions": _session_store().list_sessions()}


@app.post("/api/sessions")
def api_create_session(body: SessionBody):
    session_id = body.session_id or f"web-{uuid4().hex[:12]}"
    _session_store().create_session(session_id, body.title)
    return {"id": session_id, "title": body.title or "新会话", "messages": []}


@app.get("/api/sessions/{session_id}/messages")
def api_session_messages(session_id: str):
    history = _session_store().history(session_id, limit=100)
    return {"messages": [{"role": role, "content": content} for role, content in history]}


@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str):
    _session_store().delete_session(session_id)
    return {"ok": True}


def create_app() -> FastAPI:
    try:
        settings = Settings()
    except Exception:
        return app
    if settings.feishu_app_secret:
        from sre_agent.channels import feishu

        feishu.register(app, settings)
    from sre_agent.channels import dingtalk

    if dingtalk.dingtalk_routes_enabled(settings):
        dingtalk.register(app, settings)
    return app


create_app()
