from __future__ import annotations

from prometheus_client import Counter, Histogram, REGISTRY

_PREFIX = "sre_agent"


def _get_or_create_counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    existing = getattr(REGISTRY, "_names_to_collectors", {}).get(name)
    if isinstance(existing, Counter):
        return existing
    try:
        return Counter(name, documentation, labelnames)
    except ValueError:
        found = REGISTRY._names_to_collectors.get(name)
        if isinstance(found, Counter):
            return found
        raise


def _get_or_create_histogram(name: str, documentation: str, labelnames: list[str]) -> Histogram:
    existing = getattr(REGISTRY, "_names_to_collectors", {}).get(f"{name}_bucket") or getattr(
        REGISTRY, "_names_to_collectors", {}
    ).get(name)
    if isinstance(existing, Histogram):
        return existing
    try:
        return Histogram(name, documentation, labelnames)
    except ValueError:
        for key in (name, f"{name}_bucket"):
            found = REGISTRY._names_to_collectors.get(key)
            if isinstance(found, Histogram):
                return found
        raise


REQUESTS = _get_or_create_counter(
    f"{_PREFIX}_requests_total", "Agent requests", ["channel", "intent", "status"]
)
REQUEST_DURATION = _get_or_create_histogram(
    f"{_PREFIX}_request_duration_seconds", "Agent request duration", ["channel", "intent"]
)
LLM_TOKENS = _get_or_create_counter(
    f"{_PREFIX}_llm_tokens_total", "LLM tokens", ["model", "direction"]
)
LLM_LATENCY = _get_or_create_histogram(
    f"{_PREFIX}_llm_latency_seconds", "LLM latency", ["model", "step"]
)
PROM_QUERIES = _get_or_create_counter(
    f"{_PREFIX}_prom_queries_total", "Prometheus queries", ["api", "status"]
)
PROM_DURATION = _get_or_create_histogram(
    f"{_PREFIX}_prom_query_duration_seconds", "Prometheus query duration", ["api"]
)
APPROVALS = _get_or_create_counter(
    f"{_PREFIX}_approvals_total", "Approval records", ["action", "state"]
)
POLICY_REJECTS = _get_or_create_counter(
    f"{_PREFIX}_policy_rejects_total", "Policy rejects", ["reason"]
)


def observe_turn(channel: str, intent: str, status: str, duration_s: float) -> None:
    REQUESTS.labels(channel=channel or "unknown", intent=intent or "unknown", status=status).inc()
    REQUEST_DURATION.labels(channel=channel or "unknown", intent=intent or "unknown").observe(duration_s)


def observe_approval(action: str, state: str) -> None:
    APPROVALS.labels(action=action, state=state).inc()


def observe_policy_reject(reason: str) -> None:
    POLICY_REJECTS.labels(reason=reason).inc()
