from __future__ import annotations


def main() -> None:
    import streamlit as st

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

    st.set_page_config(page_title="SRE-Agent")
    settings = load_settings()
    st.sidebar.write("Prometheus", settings.prom_url)
    show_raw = st.sidebar.checkbox("显示原始 JSON", value=False)
    if "sid" not in st.session_state:
        st.session_state.sid = "streamlit"
    if "msgs" not in st.session_state:
        st.session_state.msgs = []
    for role, content in st.session_state.msgs:
        st.chat_message(role).write(content)
    text = st.chat_input("用说话的方式做巡检…")
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
        IncomingMessage("streamlit", "local", text, st.session_state.sid),
        classifier=Classifier(model),
        interpreter=Interpreter(model),
        approvals=build_approval_store(settings.database_url),
        sessions=build_session_store(settings.database_url),
        allow_ad_hoc=settings.allow_ad_hoc_promql,
    )
    body = out.text
    if out.promql_blocks:
        body += "\n\n" + "\n".join(f"```promql\n{q}\n```" for q in out.promql_blocks)
    if show_raw:
        body += f"\n\n```\nstatus={out.status} intent={out.intent}\n```"
    st.session_state.msgs.append(("user", text))
    st.session_state.msgs.append(("assistant", body))
    st.chat_message("user").write(text)
    st.chat_message("assistant").write(body)


if __name__ == "__main__":
    main()
