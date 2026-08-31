import pytest

from sre_agent.clients.alertmanager import AlertmanagerClient
from sre_agent.clients.http import ReadOnlyClient, ReadOnlyHTTPError
from sre_agent.clients.prometheus import PrometheusClient


class FakeTransport:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return {"status": "success", "data": {"resultType": "vector", "result": []}}


def test_readonly_client_has_no_post():
    c = ReadOnlyClient("http://prom", timeout=1, transport=FakeTransport())
    assert not hasattr(c, "post")
    assert not hasattr(c, "put")
    assert not hasattr(c, "delete")


def test_prometheus_instant_uses_get():
    t = FakeTransport()
    p = PrometheusClient("http://prom", timeout=15, max_points=1000, transport=t)
    p.instant_query("up")
    assert t.calls[0][0] == "GET"
    assert t.calls[0][1].endswith("/api/v1/query")
    assert t.calls[0][2]["query"] == "up"


def test_range_rejects_too_many_points():
    t = FakeTransport()
    p = PrometheusClient("http://prom", timeout=15, max_points=10, transport=t)
    with pytest.raises(ReadOnlyHTTPError):
        p.range_query("up", start=0, end=10000, step="1s")
    assert t.calls == []


def test_alertmanager_list_alerts_get():
    t = FakeTransport()

    def get(url, params=None):
        t.calls.append(("GET", url, params))
        return []

    t.get = get  # type: ignore[method-assign]
    am = AlertmanagerClient("http://am", timeout=15, transport=t)
    am.list_alerts()
    assert t.calls[0][1].endswith("/api/v2/alerts")
