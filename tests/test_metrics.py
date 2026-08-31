from prometheus_client import generate_latest

from sre_agent.observability.metrics import observe_turn


def test_metrics_exposition():
    observe_turn("cli", "cpu_usage", "ok", 0.2)
    body = generate_latest().decode()
    assert "sre_agent_requests_total" in body
    assert "sre_agent_request_duration_seconds" in body
