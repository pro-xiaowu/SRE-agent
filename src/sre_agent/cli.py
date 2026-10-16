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
    from sre_agent.config import load_settings
    from sre_agent.runtime import run_ask

    try:
        load_settings()
    except Exception:
        print("missing LLM config; set SRE_AGENT_LLM_BASE_URL and SRE_AGENT_LLM_API_KEY", file=sys.stderr)
        return 2
    out = run_ask(text, channel="cli", session_id=session_id)
    print(out.text)
    for q in out.promql_blocks:
        if q and q != "null":
            print("\n```promql\n" + q + "\n```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


