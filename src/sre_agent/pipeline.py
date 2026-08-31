from __future__ import annotations

import json
import time

from sre_agent.classify import Classifier
from sre_agent.context import IncomingMessage, OutgoingMessage, QueryPlan
from sre_agent.interpret import Interpreter
from sre_agent.observability.metrics import observe_approval, observe_policy_reject, observe_turn
from sre_agent.planner.planner import plan
from sre_agent.security.approvals import ApprovalStore
from sre_agent.security.policy import check_text
from sre_agent.session import SessionStore
from sre_agent.tools.registry import execute_plan

EXAMPLE_ASKS = "例如：「现在有哪些 firing 告警？」「过去 15 分钟 API 5xx 比率多少？」「哪台机器 CPU 超过 80%？」"


def run_turn(
    message: IncomingMessage,
    *,
    classifier: Classifier,
    interpreter: Interpreter,
    approvals: ApprovalStore,
    sessions: SessionStore,
    allow_ad_hoc: bool,
) -> OutgoingMessage:
    started = time.perf_counter()
    intent_label = "unknown"
    status = "ok"
    out: OutgoingMessage
    try:
        out = _run_turn_inner(
            message,
            classifier=classifier,
            interpreter=interpreter,
            approvals=approvals,
            sessions=sessions,
            allow_ad_hoc=allow_ad_hoc,
        )
        intent_label = out.intent or "unknown"
        status = out.status
        return out
    finally:
        observe_turn(message.channel, intent_label, status, time.perf_counter() - started)


def _run_turn_inner(
    message: IncomingMessage,
    *,
    classifier: Classifier,
    interpreter: Interpreter,
    approvals: ApprovalStore,
    sessions: SessionStore,
    allow_ad_hoc: bool,
) -> OutgoingMessage:
    history = sessions.history(message.session_id)
    decision = check_text(message.text)
    if decision.reason == "empty":
        observe_policy_reject("empty")
        return OutgoingMessage("请输入要巡检或排查的问题。", [], None, None, None, "rejected")
    if decision.reason == "write_operation":
        rec = approvals.create(
            decision.write_action or "generic_write",
            json.dumps({"text": message.text}, ensure_ascii=False),
            "user asked a write operation",
            message.user_id,
        )
        observe_approval(rec.action, rec.state)
        observe_policy_reject("write_operation")
        text = f"已记录审批单 #{rec.id}，V1 不执行。"
        sessions.append(message.session_id, "human", message.text)
        sessions.append(message.session_id, "ai", text)
        return OutgoingMessage(text, [], None, rec.id, "request_write", "approval_created")

    slots = classifier.classify(message.text, history)
    if slots.ask_user and "模型暂不可用" in slots.ask_user:
        return OutgoingMessage(slots.ask_user, [], None, None, "unknown", "rejected")

    needs_clarify = (
        slots.intent == "unknown"
        or slots.confidence < 0.4
        or bool(slots.missing_slots)
        or bool(slots.ask_user)
    )
    if needs_clarify:
        n = sessions.incr_clarification(message.session_id)
        if n > 2:
            text = f"仍缺少必要信息，已停止追问。{EXAMPLE_ASKS}"
            sessions.append(message.session_id, "human", message.text)
            sessions.append(message.session_id, "ai", text)
            return OutgoingMessage(text, [], None, None, slots.intent, "rejected")
        text = slots.ask_user or "请补充服务名或时间窗。"
        sessions.append(message.session_id, "human", message.text)
        sessions.append(message.session_id, "ai", text)
        return OutgoingMessage(text, [], None, None, slots.intent, "rejected")

    query_plan: QueryPlan = plan(slots, allow_ad_hoc=allow_ad_hoc)
    if query_plan.reject_reason:
        reason = query_plan.reject_reason
        if "ad hoc" in reason.lower() or "disabled" in reason.lower():
            text = f"当前不允许临时 PromQL。请改用具体指标或服务名，{EXAMPLE_ASKS}"
        else:
            text = f"{reason}。{EXAMPLE_ASKS}"
        sessions.append(message.session_id, "human", message.text)
        sessions.append(message.session_id, "ai", text)
        return OutgoingMessage(text, [], None, None, slots.intent, "rejected")

    tool_result = execute_plan(query_plan)
    error = tool_result.get("error")
    if error:
        err = str(error).lower()
        if "timeout" in err:
            text = "查询超过 15s 已取消，请缩小时间窗。"
        else:
            text = "监控后端连不上，检查 PROM_URL"
        sessions.append(message.session_id, "human", message.text)
        sessions.append(message.session_id, "ai", text)
        blocks = [query_plan.promql] if query_plan.promql else []
        return OutgoingMessage(text, blocks, None, None, slots.intent, "rejected")

    sessions.reset_clarification(message.session_id)
    answer = interpreter.interpret(slots.intent, message.text, query_plan, tool_result)
    sessions.append(message.session_id, "human", message.text)
    sessions.append(message.session_id, "ai", answer)
    blocks = [query_plan.promql] if query_plan.promql else []
    return OutgoingMessage(answer, blocks, None, None, slots.intent, "ok")
