from __future__ import annotations

from sre_agent.clients.http import ReadOnlyClient, Transport


class AlertmanagerClient:
    def __init__(self, base_url: str, timeout: float, transport: Transport | None = None):
        self.http = ReadOnlyClient(base_url, timeout, transport=transport)

    def list_alerts(self, filter: str | None = None) -> list:
        # v2：active/silenced/inhibited 才是状态；filter 只用于标签匹配
        params: dict = {
            "active": "true",
            "silenced": "false",
            "inhibited": "false",
        }
        if filter and "status=" not in filter.replace(" ", ""):
            params["filter"] = filter
        data = self.http.get("/api/v2/alerts", params)
        return data if isinstance(data, list) else data.get("data", [])

    def list_silences(self) -> list:
        data = self.http.get("/api/v2/silences")
        return data if isinstance(data, list) else data.get("data", [])
