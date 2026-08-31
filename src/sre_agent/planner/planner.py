from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from sre_agent.context import IntentSlots, QueryPlan
from sre_agent.planner.promql_guard import PromQLViolation, validate_promql

TEMPLATES_PATH = Path(__file__).with_name("templates.yaml")


def load_templates(path: Path | None = None) -> list[dict]:
    data = yaml.safe_load((path or TEMPLATES_PATH).read_text(encoding="utf-8"))
    return data["templates"]


def plan(slots: IntentSlots, *, allow_ad_hoc: bool) -> QueryPlan:
    if slots.intent == "unknown":
        return QueryPlan(None, None, "none", {}, "unknown intent")
    if slots.intent == "explain_promql":
        return QueryPlan("explain_promql", slots.promql, "none", {}, None)
    if slots.intent == "ad_hoc_query":
        if not allow_ad_hoc:
            return QueryPlan(None, None, "none", {}, "ad hoc PromQL disabled")
        if not slots.promql:
            return QueryPlan(None, None, "none", {}, "missing slot: promql")
        try:
            q = validate_promql(slots.promql)
        except PromQLViolation as exc:
            return QueryPlan(None, None, "none", {}, "; ".join(exc.reasons))
        return QueryPlan(None, q, "prom_query", {}, None)
    templates = {t["intent"]: t for t in load_templates()}
    tmpl = templates.get(slots.intent)
    if not tmpl:
        return QueryPlan(None, None, "none", {}, "unknown intent")
    mapping = {
        "job": slots.job or "api",
        "window": slots.window or "15m",
        "service": slots.service or "",
        "instance": slots.instance or "",
    }
    slot_defs = tmpl.get("slots") or {}
    for name, spec in slot_defs.items():
        if spec.get("required") and not getattr(slots, name, None):
            return QueryPlan(tmpl.get("id"), None, "none", {}, f"missing slot: {name}")
        if not mapping.get(name):
            mapping[name] = spec.get("default") or mapping.get(name, "")
    params = {}
    for k, v in (tmpl.get("params") or {}).items():
        params[k] = Template(str(v)).safe_substitute(mapping)
    promql = tmpl.get("promql")
    if promql:
        rendered = Template(promql).safe_substitute(mapping)
        try:
            rendered = validate_promql(rendered)
        except PromQLViolation as exc:
            return QueryPlan(tmpl.get("id"), None, "none", params, "; ".join(exc.reasons))
        return QueryPlan(tmpl.get("id"), rendered, tmpl["tool"], params, None)
    return QueryPlan(tmpl.get("id"), None, tmpl["tool"], params, None)
