from __future__ import annotations

from sre_agent.clients.http import ReadOnlyClient, Transport


class AlertmanagerClient:
    def __init__(self, base_url: str, timeout: float, transport: Transport | None = None):
        self.http = ReadOnlyClient(base_url, timeout, transport=transport)

    def list_alerts(self, filter: str | None = None) -> list:
        params = {"filter": filter} if filter else None
        data = self.http.get("/api/v2/alerts", params)
        return data if isinstance(data, list) else data.get("data", [])

    def list_silences(self) -> list:
        data = self.http.get("/api/v2/silences")
        return data if isinstance(data, list) else data.get("data", [])
