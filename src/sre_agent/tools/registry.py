from __future__ import annotations

import json
from typing import Any

from sre_agent.clients.alertmanager import AlertmanagerClient
from sre_agent.clients.http import ReadOnlyHTTPError
from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.context import QueryPlan
from sre_agent.planner.promql_guard import PromQLViolation, validate_promql

_prom: PrometheusClient | None = None
_am: AlertmanagerClient | None = None


def bind_clients(prom: PrometheusClient | None, am: AlertmanagerClient | None) -> None:
    global _prom, _am
    _prom = prom
    _am = am


def call_prom_query(query: str) -> str:
    try:
        q = validate_promql(query)
    except PromQLViolation as exc:
        return json.dumps({"error": "; ".join(exc.reasons)})
    if _prom is None:
        return json.dumps({"error": "prometheus client not bound"})
    try:
        data = _prom.instant_query(q)
    except ReadOnlyHTTPError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"promql": q, "data": data}, ensure_ascii=False)


def call_prom_query_range(query: str, start: float, end: float, step: str) -> str:
    try:
        q = validate_promql(query)
    except PromQLViolation as exc:
        return json.dumps({"error": "; ".join(exc.reasons)})
    if _prom is None:
        return json.dumps({"error": "prometheus client not bound"})
    try:
        data = _prom.range_query(q, start, end, step)
    except ReadOnlyHTTPError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"promql": q, "data": data}, ensure_ascii=False)


def call_prom_label_values(name: str) -> str:
    if _prom is None:
        return json.dumps({"error": "prometheus client not bound"})
    try:
        data = _prom.label_values(name)
    except ReadOnlyHTTPError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"data": data}, ensure_ascii=False)


def call_prom_metric_metadata(metric: str = "") -> str:
    if _prom is None:
        return json.dumps({"error": "prometheus client not bound"})
    try:
        data = _prom.metadata(metric or None)
    except ReadOnlyHTTPError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"data": data}, ensure_ascii=False)


def call_am_list_alerts(filter: str = "") -> str:
    if _am is None:
        return json.dumps({"error": "alertmanager client not bound"})
    try:
        data = _am.list_alerts(filter or None)
    except ReadOnlyHTTPError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"data": data}, ensure_ascii=False)


def call_am_list_silences() -> str:
    if _am is None:
        return json.dumps({"error": "alertmanager client not bound"})
    try:
        data = _am.list_silences()
    except ReadOnlyHTTPError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"data": data}, ensure_ascii=False)


def execute_plan(plan: QueryPlan) -> dict[str, Any]:
    if plan.tool == "none":
        return {"tool": "none", "promql": plan.promql, "data": None}
    if plan.tool == "prom_query":
        raw = call_prom_query(plan.promql or "")
        parsed = json.loads(raw)
        if "error" in parsed:
            return {"tool": plan.tool, "promql": plan.promql, "error": parsed["error"], "data": None}
        return {"tool": plan.tool, "promql": parsed.get("promql", plan.promql), "data": parsed.get("data")}
    if plan.tool == "prom_query_range":
        start = float(plan.params.get("start", 0))
        end = float(plan.params.get("end", 0))
        step = str(plan.params.get("step", "15s"))
        raw = call_prom_query_range(plan.promql or "", start, end, step)
        parsed = json.loads(raw)
        if "error" in parsed:
            return {"tool": plan.tool, "promql": plan.promql, "error": parsed["error"], "data": None}
        return {"tool": plan.tool, "promql": parsed.get("promql", plan.promql), "data": parsed.get("data")}
    if plan.tool == "am_list_alerts":
        raw = call_am_list_alerts(str(plan.params.get("filter", "")))
        parsed = json.loads(raw)
        if "error" in parsed:
            return {"tool": plan.tool, "promql": plan.promql, "error": parsed["error"], "data": None}
        return {"tool": plan.tool, "promql": plan.promql, "data": parsed.get("data")}
    if plan.tool == "am_list_silences":
        raw = call_am_list_silences()
        parsed = json.loads(raw)
        if "error" in parsed:
            return {"tool": plan.tool, "promql": plan.promql, "error": parsed["error"], "data": None}
        return {"tool": plan.tool, "promql": plan.promql, "data": parsed.get("data")}
    return {"tool": "none", "promql": plan.promql, "error": f"unknown tool {plan.tool}", "data": None}
