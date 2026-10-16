# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SRE-Agent：用中文自然语言对 Prometheus / Alertmanager 做只读巡检和排障。核心安全约束：**LLM 只负责意图理解和结论组织，真正发给 Prometheus 的必须是经过模板或 `promql_guard` 校验的只读查询**；任何写操作只生成审批单，V1 不执行。

规格与计划（先规格后代码的流程见 `docs/superpowers/`）：
- 设计规格：`docs/superpowers/specs/2026-08-31-sre-prometheus-agent-design.md`
- 实现计划：`docs/superpowers/plans/2026-08-31-sre-prometheus-agent.md`

## Commands

```bash
uv sync --extra dev                 # 安装依赖（uv，Python >=3.11,<3.14）
uv run pytest                       # 全部测试
uv run pytest tests/test_planner.py                    # 单个测试文件
uv run pytest tests/test_planner.py::test_name         # 单个测试
uv run pytest -k ad_hoc                                 # 按关键字

uv run sre-agent ask "现在有哪些 firing 告警？"   # CLI 一次提问
uv run sre-agent chat                             # Streamlit UI
uv run sre-agent serve                            # FastAPI :9108（/api/ask + /metrics）
cd front && npm install && npm run dev            # Vue 值班台 :5173
```

配置走 `.env`（模板 `.env.example`），所有变量前缀 `SRE_AGENT_`，由 `src/sre_agent/config.py` 的 pydantic-settings 加载。测试不需要 LLM / Prometheus / PostgreSQL——管线测试用假 classifier/interpreter，store 用内存实现。

## Architecture

一条线性 LangChain 流水线（**V1 明确不用 LangGraph**，工具不被模型自由调用）：

```
Channel (cli / streamlit / feishu / dingtalk / fastapi)
  → pipeline.run_turn()
      1. policy.check_text()          写操作关键词拦截 → 审批单（不进 LLM）
      2. Classifier.classify()        with_structured_output(IntentSlots) 意图+槽位
      3. planner.plan()               模板渲染 PromQL / ad-hoc 校验
      4. tools/registry.execute_plan() 只读工具调用（bind_clients 注入的客户端）
      5. Interpreter.interpret()      LLM 基于 tool_result 生成中文结论
```

关键点（跨多文件才看得出来的）：

- **入口分两条**：`runtime.run_ask()`（cli/web 共用，每次调用 bind_clients）和 `pipeline.run_turn()`（纯函数，依赖注入 classifier/interpreter/stores，测试就靠这个注入）。
- **安全是三层的**：`security/policy.py` 关键词拦截写操作；`planner/templates.yaml` 模板渲染（slot 替换，`string.Template`）；`planner/promql_guard.py` 的 `validate_promql()`（函数白名单、range [1m,1h]、禁 admin API）。所有工具调用前都会再过一次 guard——加新工具时不要绕过。
- **ad-hoc PromQL** 默认关闭（`SRE_AGENT_ALLOW_AD_HOC_PROMQL=false`），开启后也必须过 `validate_promql`。
- **存储双实现**：`session.py` / `security/approvals.py` 各有 `Memory*`（单测）和 `Postgres*`（生产，psycopg3）实现，经 `build_*_store(database_url)` 切换。`db.py` 负责建表。
- **tools/registry.py 用模块级全局客户端**（`bind_clients`），不是构造注入——FastAPI 和 CLI 都在启动/请求时重新 bind。
- **澄清循环**：最多追问 2 次（`sessions.incr_clarification`），第 3 次直接拒绝；成功执行后 `reset_clarification`。
- **可观测**：`observability/metrics.py` 通过 prometheus_client 暴露 turn/审批/拒绝指标，`serve.py` 的 `/metrics` 输出；`observability/callbacks.py` 挂 LangChain CallbackManager。
- **意图目录**在 `classify.py` 的 `CLASSIFY_SYSTEM` prompt 和 `planner/templates.yaml` 里各有一份，改意图要同时改两处（及 `context.IntentSlots`）。
- **部署**：`deploy/docker/monitor/`（Prometheus+Alertmanager，监控机）与 `deploy/docker/app/`（PostgreSQL，应用机）分开；应用机 `.env` 的 Prom/AM 地址填监控机内网 IP。

## Conventions

- 中文用户可见文案（CLI 输出、拒绝/澄清/错误提示、Streamlit）；代码注释和 docbook 少而精。
- 错误路径不抛堆栈给用户：超时、后端不可用、LLM 不可用都有固定中文回复（见 `pipeline.py` 的 error 分支和 `classify.py`/`interpret.py` 的 except 分支）。
- `Interpreter` 的 system prompt 要求结论只能来自 tool_result、PromQL 必须原样列出；改 prompt 时保持这些约束。
