from sre_agent.context import IntentSlots
from sre_agent.planner.planner import plan


def test_firing_alerts_uses_alertmanager():
    p = plan(IntentSlots(intent="firing_alerts", confidence=0.9), allow_ad_hoc=False)
    assert p.tool == "am_list_alerts"
    assert p.reject_reason is None
    assert "status=" not in str(p.params.get("filter", ""))


def test_http_error_rate_fills_defaults():
    p = plan(IntentSlots(intent="http_error_rate", confidence=0.9), allow_ad_hoc=False)
    assert p.tool == "prom_query"
    assert 'job="api"' in (p.promql or "")
    assert "[15m]" in (p.promql or "")


def test_ad_hoc_disabled_by_default():
    p = plan(
        IntentSlots(intent="ad_hoc_query", confidence=0.9, promql="up"),
        allow_ad_hoc=False,
    )
    assert p.tool == "none"
    assert "disabled" in (p.reject_reason or "").lower() or "ad hoc" in (p.reject_reason or "").lower()


def test_ad_hoc_rejects_bad_regex_when_enabled():
    p = plan(
        IntentSlots(
            intent="ad_hoc_query",
            confidence=0.9,
            promql='sum(rate(http_requests_total{code=~".*"}[5m]))',
        ),
        allow_ad_hoc=True,
    )
    assert p.tool == "none"
    assert p.reject_reason
