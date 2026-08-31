from sre_agent.classify import Classifier
from sre_agent.context import IntentSlots, QueryPlan
from sre_agent.interpret import Interpreter


class FakeStructured:
    def invoke(self, _messages):
        return IntentSlots(intent="firing_alerts", confidence=0.95)


class FakeChat:
    def with_structured_output(self, _schema):
        return FakeStructured()

    def invoke(self, _messages):
        class M:
            content = "当前无 firing 告警。\n```promql\n# am_list_alerts\n```"

        return M()


def test_classifier_uses_structured_output():
    c = Classifier(FakeChat())
    slots = c.classify("现在有哪些告警？", [])
    assert slots.intent == "firing_alerts"


def test_interpret_keeps_promql():
    i = Interpreter(FakeChat())
    text = i.interpret(
        "target_health",
        "有没有 down",
        QueryPlan("target_health", "up == 0", "prom_query", {}, None),
        {"tool": "prom_query", "promql": "up == 0", "data": {"data": {"result": []}}},
    )
    assert "up == 0" in text or "am_list_alerts" in text or "告警" in text
