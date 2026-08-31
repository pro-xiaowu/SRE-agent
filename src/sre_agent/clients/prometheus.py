from __future__ import annotations

from sre_agent.clients.http import ReadOnlyClient, ReadOnlyHTTPError, Transport


def _step_seconds(step: str) -> float:
    units = {"s": 1, "m": 60, "h": 3600}
    n = int(step[:-1])
    return n * units[step[-1]]


class PrometheusClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        max_points: int,
        transport: Transport | None = None,
        bearer: str | None = None,
    ):
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else None
        self.max_points = max_points
        self.http = ReadOnlyClient(base_url, timeout, transport=transport, headers=headers)

    def instant_query(self, query: str) -> dict:
        return self.http.get("/api/v1/query", {"query": query})

    def range_query(self, query: str, start: float, end: float, step: str) -> dict:
        points = (end - start) / _step_seconds(step)
        if points > self.max_points:
            raise ReadOnlyHTTPError("too many points")
        return self.http.get(
            "/api/v1/query_range",
            {"query": query, "start": start, "end": end, "step": step},
        )

    def label_values(self, name: str) -> list:
        data = self.http.get(f"/api/v1/label/{name}/values")
        return data.get("data", data) if isinstance(data, dict) else data

    def metadata(self, metric: str | None = None) -> dict:
        params = {"metric": metric} if metric else None
        return self.http.get("/api/v1/metadata", params)
