from __future__ import annotations

from sre_agent.classify import Classifier
from sre_agent.clients.alertmanager import AlertmanagerClient
from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.config import load_settings
from sre_agent.context import IncomingMessage, OutgoingMessage
from sre_agent.interpret import Interpreter
from sre_agent.llm import chat_model
from sre_agent.pipeline import run_turn
from sre_agent.security.approvals import build_approval_store
from sre_agent.session import build_session_store
from sre_agent.tools.registry import bind_clients


def run_ask(text: str, *, channel: str = "cli", session_id: str = "cli") -> OutgoingMessage:
    settings = load_settings()
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
    return run_turn(
        IncomingMessage(channel, "local", text, session_id),
        classifier=Classifier(model),
        interpreter=Interpreter(model),
        approvals=build_approval_store(settings.database_url),
        sessions=build_session_store(settings.database_url),
        allow_ad_hoc=settings.allow_ad_hoc_promql,
    )
