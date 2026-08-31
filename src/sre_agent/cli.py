from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sre-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("text")
    ask.add_argument("--session", default="cli")
    sub.add_parser("chat")
    sub.add_parser("serve")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        code = exc.code
        return 0 if code in (0, None) else int(code or 2)

    if args.cmd == "ask":
        return _cmd_ask(args.text, args.session)
    if args.cmd == "chat":
        app = Path(__file__).parent / "channels" / "streamlit_app.py"
        return subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(app)],
        )
    if args.cmd == "serve":
        from sre_agent.config import load_settings

        settings = load_settings()
        import uvicorn

        uvicorn.run("sre_agent.serve:app", host="0.0.0.0", port=settings.metrics_port)
        return 0
    return 2


def _cmd_ask(text: str, session_id: str) -> int:
    from sre_agent.classify import Classifier
    from sre_agent.clients.alertmanager import AlertmanagerClient
    from sre_agent.clients.prometheus import PrometheusClient
    from sre_agent.config import load_settings
    from sre_agent.context import IncomingMessage
    from sre_agent.interpret import Interpreter
    from sre_agent.llm import chat_model
    from sre_agent.pipeline import run_turn
    from sre_agent.security.approvals import build_approval_store
    from sre_agent.session import build_session_store
    from sre_agent.tools.registry import bind_clients

    try:
        settings = load_settings()
    except Exception:
        print("missing LLM config; set SRE_AGENT_LLM_BASE_URL and SRE_AGENT_LLM_API_KEY", file=sys.stderr)
        return 2
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
        IncomingMessage("cli", "local", text, session_id),
        classifier=Classifier(model),
        interpreter=Interpreter(model),
        approvals=build_approval_store(settings.database_url),
        sessions=build_session_store(settings.database_url),
        allow_ad_hoc=settings.allow_ad_hoc_promql,
    )
    print(out.text)
    for q in out.promql_blocks:
        print("\n```promql\n" + q + "\n```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
