from langchain_core.tools import tool

from sre_agent.tools import registry


@tool
def prom_query(query: str) -> str:
    """Instant PromQL query (read-only)."""
    return registry.call_prom_query(query)


@tool
def prom_query_range(query: str, start: float, end: float, step: str) -> str:
    """Range PromQL query (read-only)."""
    return registry.call_prom_query_range(query, start, end, step)


@tool
def prom_label_values(name: str) -> str:
    """List Prometheus label values (read-only)."""
    return registry.call_prom_label_values(name)


@tool
def prom_metric_metadata(metric: str = "") -> str:
    """Prometheus metric metadata (read-only)."""
    return registry.call_prom_metric_metadata(metric)
