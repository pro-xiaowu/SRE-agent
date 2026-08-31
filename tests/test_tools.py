from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.context import QueryPlan
from sre_agent.tools.registry import bind_clients, execute_plan


class T:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if "alerts" in url:
            return []
        return {"status": "success", "data": {"result": []}}


def test_execute_plan_validates_before_http():
    t = T()
    bind_clients(PrometheusClient("http://p", 15, 1000, transport=t), None)
    result = execute_plan(
        QueryPlan(None, 'sum(rate(http_requests_total{code=~".*"}[5m]))', "prom_query", {}, None)
    )
    assert "error" in result
    assert t.calls == []


def test_execute_plan_instant():
    t = T()
    bind_clients(PrometheusClient("http://p", 15, 1000, transport=t), None)
    result = execute_plan(QueryPlan("target_health", "up == 0", "prom_query", {}, None))
    assert result["promql"] == "up == 0"
    assert t.calls
