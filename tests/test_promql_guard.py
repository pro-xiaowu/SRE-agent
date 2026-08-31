import pytest

from sre_agent.planner.promql_guard import PromQLViolation, validate_promql


def test_accepts_rate_sum():
    q = 'sum(rate(http_requests_total{job="api"}[5m]))'
    assert validate_promql(q) == q


def test_rejects_empty():
    with pytest.raises(PromQLViolation) as ei:
        validate_promql("   ")
    assert ei.value.reasons


def test_rejects_unknown_function():
    with pytest.raises(PromQLViolation) as ei:
        validate_promql("evil_drop(http_requests_total)")
    assert any("function" in r.lower() or "函数" in r for r in ei.value.reasons)


def test_rejects_unbounded_regex():
    with pytest.raises(PromQLViolation):
        validate_promql('sum(rate(http_requests_total{code=~".*"}[5m]))')


def test_rejects_rate_range_too_short():
    with pytest.raises(PromQLViolation):
        validate_promql("rate(http_requests_total[30s])")


def test_rejects_overlong():
    with pytest.raises(PromQLViolation):
        validate_promql("up" + "a" * 2001)
