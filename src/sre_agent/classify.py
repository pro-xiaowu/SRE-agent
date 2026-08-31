from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from sre_agent.context import IntentSlots

CLASSIFY_SYSTEM = """你是 SRE 巡检助手的意图分类器。只输出结构化字段。
可选 intent：firing_alerts, alert_by_service, cpu_usage, memory_usage, http_error_rate,
http_latency, restart_count, disk_usage, target_health, ad_hoc_query, explain_promql,
request_write, unknown。
不要编造数字。槽位缺失时填 missing_slots 和 ask_user。
"""


class Classifier:
    def __init__(self, model) -> None:
        self._structured = model.with_structured_output(IntentSlots)

    def classify(self, text: str, history: list[tuple[str, str]]) -> IntentSlots:
        messages: list = [SystemMessage(content=CLASSIFY_SYSTEM)]
        for role, content in history:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=text))
        try:
            result = self._structured.invoke(messages)
        except Exception:
            return IntentSlots(
                intent="unknown",
                confidence=0.0,
                ask_user="模型暂不可用，请重试",
            )
        if isinstance(result, IntentSlots):
            return result
        return IntentSlots.model_validate(result)


def build_classifier(model) -> Classifier:
    return Classifier(model)
