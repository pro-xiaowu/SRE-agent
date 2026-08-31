from __future__ import annotations

from typing import Any, Protocol

import httpx


class Transport(Protocol):
    def get(self, url: str, params: dict | None = None) -> Any: ...


class ReadOnlyHTTPError(Exception):
    pass


class HttpxTransport:
    def __init__(
        self,
        timeout: float,
        headers: dict | None = None,
        auth: httpx.BasicAuth | None = None,
    ):
        self._timeout = timeout
        self._headers = headers or {}
        self._auth = auth

    def get(self, url: str, params: dict | None = None) -> Any:
        try:
            r = httpx.get(
                url,
                params=params,
                timeout=self._timeout,
                headers=self._headers,
                auth=self._auth,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise ReadOnlyHTTPError(str(exc)) from exc


class ReadOnlyClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: Transport | None = None,
        headers: dict | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or HttpxTransport(timeout, headers=headers)

    def get(self, path: str, params: dict | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return self.transport.get(url, params=params)
