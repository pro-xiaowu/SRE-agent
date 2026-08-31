from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from sre_agent.context import QueryPlan

INTERPRET_SYSTEM = """你是 SRE 巡检助手。只根据 tool_result 里的数字下结论，禁止编造。
必须原样列出已执行的 PromQL（代码块）。
不得声称已重启、已静默或已修改任何系统。
无数据时明确说该时间窗无样本，并建议检查 job 名、时间窗、指标是否存在。
"""


class Interpreter:
    def __init__(self, model) -> None:
        self._model = model

    def interpret(self, intent: str, question: str, plan: QueryPlan, tool_result: dict) -> str:
        payload = {
            "question": question,
            "intent": intent,
            "promql": plan.promql,
            "tool_result": tool_result,
        }
        raw = json.dumps(payload, ensure_ascii=False)[:8000]
        try:
            msg = self._model.invoke(
                [SystemMessage(content=INTERPRET_SYSTEM), HumanMessage(content=raw)]
            )
        except Exception:
            return "模型暂不可用，请重试"
        content = getattr(msg, "content", None) or str(msg)
        if plan.promql and plan.promql not in content:
            content = f"{content}\n\n```promql\n{plan.promql}\n```"
        return content
