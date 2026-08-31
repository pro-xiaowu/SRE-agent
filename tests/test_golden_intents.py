from sre_agent.context import IntentSlots
from sre_agent.planner.planner import plan
from sre_agent.security.policy import check_text


def test_silence_is_write():
    assert check_text("把 node-disk 告警静默 1 小时").reason == "write_operation"


def test_error_rate_plan():
    p = plan(
        IntentSlots(intent="http_error_rate", confidence=1, window="15m", job="api"),
        allow_ad_hoc=False,
    )
    assert p.reject_reason is None
    assert "5.." in (p.promql or "")


def test_ad_hoc_star_rejected():
    p = plan(
        IntentSlots(
            intent="ad_hoc_query",
            confidence=1,
            promql='sum(rate(http_requests_total{code=~".*"}[5m])) by (le)',
        ),
        allow_ad_hoc=False,
    )
    assert p.tool == "none"


def test_firing_alerts():
    p = plan(IntentSlots(intent="firing_alerts", confidence=1), allow_ad_hoc=False)
    assert p.tool == "am_list_alerts"


def test_cpu_usage():
    p = plan(IntentSlots(intent="cpu_usage", confidence=1), allow_ad_hoc=False)
    assert p.reject_reason is None
    assert p.tool == "prom_query"


def test_restart_count():
    p = plan(IntentSlots(intent="restart_count", confidence=1, service="checkout"), allow_ad_hoc=False)
    assert p.reject_reason is None


def test_explain_promql():
    p = plan(
        IntentSlots(intent="explain_promql", confidence=1, promql="sum(rate(http_requests_total[5m]))"),
        allow_ad_hoc=False,
    )
    assert p.tool == "none"


def test_disk_usage():
    p = plan(IntentSlots(intent="disk_usage", confidence=1), allow_ad_hoc=False)
    assert p.reject_reason is None
    assert p.tool == "prom_query"
