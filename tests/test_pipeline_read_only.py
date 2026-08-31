from sre_agent.context import IncomingMessage, IntentSlots
from sre_agent.pipeline import run_turn
from sre_agent.security.approvals import build_approval_store
from sre_agent.session import build_session_store


class C:
    def __init__(self, slots):
        self.slots = slots
        self.calls = 0

    def classify(self, text, history):
        self.calls += 1
        return self.slots


class I:
    def interpret(self, intent, question, plan, tool_result):
        return f"结论 {plan.promql}"


def _deps(slots):
    return dict(
        classifier=C(slots),
        interpreter=I(),
        approvals=build_approval_store(None),
        sessions=build_session_store(None),
        allow_ad_hoc=False,
    )


def test_write_creates_approval_without_classify():
    deps = _deps(IntentSlots(intent="firing_alerts", confidence=0.9))
    msg = IncomingMessage("cli", "u", "把 node-disk 告警静默 1 小时", "s1")
    out = run_turn(msg, **deps)
    assert out.approval_id
    assert out.status == "approval_created"
    assert "不执行" in out.text
    assert deps["classifier"].calls == 0


def test_ok_promql_in_blocks(monkeypatch):
    from sre_agent import pipeline as pmod

    def fake_exec(plan):
        return {"tool": plan.tool, "promql": plan.promql, "data": {"data": {"result": []}}}

    monkeypatch.setattr(pmod, "execute_plan", fake_exec)
    deps = _deps(IntentSlots(intent="target_health", confidence=0.9))
    out = run_turn(IncomingMessage("cli", "u", "有没有 target down", "s1"), **deps)
    assert out.status == "ok"
    assert out.promql_blocks == ["up == 0"]
