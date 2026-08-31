# SRE-Agent 设计规格：自然语言监控巡检与故障排查

**Status:** Approved（2026-08-31：5 条默认项一字不改确认；编排层 V1 纯 LangChain）  
**Date:** 2026-08-31  
**Repo:** `SRE-agent`（当前仅有 PyCharm 占位 `main.py` 与空依赖 `pyproject.toml`）  
**Objective:** 用 **LangChain** 把自然语言转成对 Prometheus / Alertmanager 的**确定性只读查询**，通过飞书/钉钉机器人或 Streamlit 提供服务，实现“用说话的方式做监控巡检和故障排查”。V1 不引入 LangGraph。

---

## 1. 问题与目标

SRE 日常巡检和排障高度依赖 PromQL、Grafana 面板和告警列表。门槛高、上下文切换多，值班时容易漏查或查错。

本项目要解决的是：

1. **说人话即可查询**：例如“过去 15 分钟 API 错误率有没有飙升？”“现在有哪些 firing 告警？”
2. **查询必须确定、可审计**：大模型只负责理解意图与填槽，真正发给 Prometheus 的必须是校验过的 PromQL 或模板查询，禁止模型直接把任意字符串打到生产查询接口。
3. **默认只读**：查询可以自动执行；任何写操作（静默告警、改规则、重启）必须走审批。
4. **Agent 自身也可观测**：用 Prometheus 抓取本应用的延迟、Token、查询次数、失败率。

### 1.1 成功标准（V1）

满足以下全部条件即视为 V1 完成：

- 用中文自然语言完成至少 8 类巡检/排障问题（见第 6 节意图目录），返回可读结论 + 原始 PromQL + 关键时间序列摘要。
- 所有 Prometheus / Alertmanager 调用仅走只读 API；未知意图拒绝执行，而不是自由生成 PromQL。
- Streamlit 聊天界面可用；飞书或钉钉至少打通一种机器人（Webhook + 回调）。
- 任意疑似写操作被拦截，并生成待审批工单（V1 只做审批记录，不自动执行）。
- `/metrics` 暴露应用指标，可被外部 Prometheus 抓取。
- 查询失败、超时、无数据、权限拒绝都有明确中文回复，不抛原始堆栈给用户。

### 1.2 非目标（V1 明确不做）

- 不自动执行修复（kubectl、SSH、重启、扩容）。
- 不接入 Loki / Elasticsearch 日志、Tempo 链路、Grafana 绘图导出。
- 不自动改 Prometheus 规则文件或 Alertmanager 配置。
- 不做成通用 DevOps Copilot；只做监控查询与排障辅助。
- 不在 V1 内同时深度打磨飞书和钉钉；优先打通一种，另一种保留适配器接口。
- **不用 LangGraph**（无 StateGraph、无 checkpointer、无 interrupt 人机环）。流程是线性的，图没有收益。

---

## 2. 设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 自然语言 → PromQL 策略 | **模板优先 + 受限生成兜底** | 纯 LLM 生成 PromQL 容易写错标签、打出高基数查询；纯模板覆盖不全。模板命中则填槽执行；未命中才走 AST 校验后的受限 PromQL。 |
| 2 | Agent 编排 | **V1 纯 LangChain 线性流水线，不用 LangGraph** | 意图 → 填槽 → 模板查询 → 解读是直线。图、checkpoint、interrupt 对 V1 是多余复杂度。 |
| 3 | 大模型接入 | **OpenAI 兼容接口一层抽象** | OpenAI、通义、智谱、vLLM/Ollama 都可走 `base_url + api_key + model`。默认配置用环境变量切换，不绑死一家。 |
| 4 | 交互层 | **Streamlit 必做；IM 优先飞书，钉钉并列适配器** | Streamlit 便于本地验收。生产值班更常用 IM。两者共用同一 Agent 内核。 |
| 5 | 安全模型 | **只读客户端 + 查询白名单 + 写操作审批队列** | Prometheus 使用只读凭据；PromQL 必须通过解析器与资源限制；写操作永不由 LLM 直接调用。 |
| 6 | 查询执行 | **同步查询 + 硬超时 + 结果裁剪** | 避免 `query_range` 拖垮 Prometheus。默认超时 15s，最大点数与最大返回行数有上限。 |
| 7 | Python 版本 | **`>=3.11,<3.14`** | 仓库当前 `requires-python = ">=3.14"` 过新，多数依赖尚未声明支持。实现阶段下调。 |
| 8 | 包管理 | **继续用 uv** | 仓库已有 `uv.lock`。 |

| 9 | 工具 | **`@tool` 装饰器** | 参数 schema 自动进 LLM；流水线按意图**代码调用**工具，不让模型自由 ReAct 绕过模板。 |
| 10 | 结构化输出 | **`with_structured_output`（Pydantic）** | 意图/槽位用模型，不用手写 JSON 解析。 |
| 11 | 会话与审批存储 | **PostgreSQL（psycopg3）** | 审批单、聊天历史、澄清计数都进 PostgreSQL，多 worker / IM 共用。单测可用内存假存储。**不使用 LangGraph checkpointer**（含 `InMemorySaver`），也不用 SQLite。 |
| 12 | 埋点 | **LangChain `CallbackManager`** | Token、LLM 耗时、工具耗时打到 Prometheus 指标。 |

### 2.1 考虑过但未采用的方案

- **V1 上 LangGraph**：流程线性，没有循环、动态改计划和“审批后恢复图执行”。留到 V2（见 2.2）。
- **V1 上开放 ReAct（模型自己选工具、自己写 PromQL）**：灵活但会绕过模板与 guard。`@tool` 只作为被流水线调用的实现，不作为自由 agent 循环。
- **让 LLM 直接写 PromQL**：排障灵活，但不确定、不可审计、容易打出高成本查询。只作为模板未命中时的受限路径。
- **只做 Streamlit、不做 IM**：验收快，但达不到“值班说话巡检”的使用场景。
- **引入完整 RAG 知识库（Wiki/Runbook）作为 V1 主干**：有价值，但会把范围扩成知识平台。V1 只内置少量排障剧本（runbook 片段），外部文档 RAG 放到 V2。

### 2.2 何时升到 LangGraph（V2 信号，缺一不可也行，出现再评估）

V1 故意不用图。出现以下任一信号再引入 LangGraph：

1. **复杂多轮澄清超过 3 轮**（槽位补齐变成子对话，而不是“最多追问 1～2 次”）。
2. **执行中动态改计划**（例如指标不存在时自动换模板、拆成多跳排查树）。
3. **审批通过后恢复同一条流程继续执行**（真正的 interrupt → resume 执行器，而不只是记一笔审批单）。

升级时再加依赖 `langgraph`，用 StateGraph 替换 `run_turn()`；工具、guard、模板、channel 保持不变。

---

## 3. 总体架构

```
用户（飞书 / 钉钉 / Streamlit）
        │
        ▼
 Channel Adapter（鉴权、会话、卡片消息）
        │  UserMessage {channel, user_id, text, session_id}
        ▼
 LangChain 线性流水线（Python 顺序调用，不是 StateGraph）
   ├─ 安全闸门（代码）
   ├─ 意图分类 + 槽位抽取（with_structured_output）
   ├─ 查询规划（模板 / 受限 PromQL，代码）
   ├─ 工具执行（@tool 只读函数，由流水线调用）
   └─ 结论生成（LLM + 工具结果；CallbackManager 埋点）
        │
        ▼
 只读数据面
   ├─ Prometheus HTTP API
   └─ Alertmanager HTTP API

旁路：prometheus-client 暴露本应用 /metrics
旁路：审批队列（PostgreSQL），写操作停在这里
```

### 3.1 分层职责

| 层 | 职责 | 不做什么 |
|----|------|----------|
| Channel | 协议转换、用户身份、消息格式 | 不写 PromQL，不直连 Prometheus |
| Agent（LangChain 流水线） | 理解、规划、解释、有限追问 | 不绕过安全策略；模型不自由选工具 |
| Query Planner | 模板匹配、槽位校验、PromQL AST 检查 | 不发送 HTTP |
| Data Clients | 带超时的只读 HTTP | 不接受未校验查询 |
| Policy | 只读强制、速率限制、审批 | 不调用 LLM |
| Observability | 计数、直方图、 tracing span | 不改变业务路径 |

### 3.2 运行时组件

V1 单进程即可：

- `sre-agent serve`：HTTP（Streamlit 或 FastAPI 回调 + `/metrics`）
- 可选独立 Streamlit 进程调用同一内核

配置全部来自环境变量 / `.env`（不入库密钥）。

---

## 4. V1 Agent：LangChain 线性流水线

不用图。入口是一个函数 `run_turn(message, session) -> OutgoingMessage`，步骤固定、可单测。LLM **不**自己发明工具调用协议；工具由代码按意图调用。

```
ingest            # 规范化输入，从 session store 读最近 N 条消息
  → policy_gate   # 写操作 / 越权 / 空输入（纯代码）
  → classify      # llm.with_structured_output(IntentSlots)
  → plan_query    # 绑定模板或走受限 PromQL（纯代码 + guard）
  → execute       # 调用 @tool 包装的只读函数
  → interpret     # LLM 只吃 tool_results，禁止改写已执行的 PromQL
  → persist       # 把本轮 Human/AI 消息写入 session store
  → respond
```

分支（仍是 `if/return`，不是条件边）：

- `policy_gate` 判定为写操作 → 写 PostgreSQL 审批单 → 直接返回“已创建审批，未执行”
- `classify` 置信度低或槽位缺失 → 追问用户，**同一 session 最多 2 轮澄清**（第 3 次仍缺槽则拒绝并给示例问法）
- `plan_query` 无模板且 PromQL 校验失败 → 拒绝并给示例问法
- `execute` 超时/5xx → `interpret` 走失败话术，Callback 记指标

澄清超过 3 轮若成为真实需求，再评估迁 LangGraph（见 2.2）。

### 4.1 LangChain 用法约定

| 能力 | API | 用法 |
|------|-----|------|
| 模型 | `ChatOpenAI`（`base_url` 指向任意 OpenAI 兼容服务） | 分类与解读各一次调用 |
| 意图/槽位 | `classifier.with_structured_output(IntentSlots)` | Pydantic 模型；解析失败则追问或拒绝 |
| 工具 | `@tool` 定义 `prom_query` 等 | **流水线按 `intent` 选择并调用**；工具函数内部再走 HTTP 客户端与超时 |
| 会话 | 自定义 session store | 生产用 PostgreSQL（`DATABASE_URL`）；单测用内存实现。按 `session_id` 存消息 |
| 埋点 | `CallbackManager` + 自定义 Handler | `on_llm_end` 记 token/耗时；`on_tool_end` 记 Prometheus 查询 |

不引入：`langgraph`、`StateGraph`、`MemorySaver`/`InMemorySaver`、`interrupt()`。

依赖（实现时写入 `pyproject.toml`）：`langchain`、`langchain-openai`、`langchain-core`；**不写 `langgraph`**。

### 4.2 会话上下文（逻辑模型）

每轮请求在内存中组装，**不是** LangGraph 的 `TypedDict` 图状态：

```python
class TurnContext:
    session_id: str
    user_id: str
    channel: str          # streamlit | feishu | dingtalk
    input_text: str
    history: list         # LangChain BaseMessage，最近 N 条
    intent: str | None
    slots: dict
    query_plan: dict | None     # template_id / promql / time_range
    tool_results: list
    answer: str
    citations: list             # 实际执行的 PromQL 列表
    needs_approval: bool
    approval_id: str | None
    error: str | None
```

Session store 只持久化消息与少量槽位（如最近一次 `job`/`window`），便于“再查一下 CPU”这种短跟进。不持久化中间图快照。生产实现必须走 PostgreSQL；pytest 允许注入内存 store，避免单测依赖本机数据库。

### 4.3 工具清单（V1 仅这些，全部 `@tool`）

| 工具名 | 对应 API | 权限 |
|--------|----------|------|
| `prom_query` | `GET /api/v1/query` | 只读 |
| `prom_query_range` | `GET /api/v1/query_range` | 只读，强制 step 下限 |
| `prom_label_values` | `GET /api/v1/label/<name>/values` | 只读 |
| `prom_metric_metadata` | `GET /api/v1/metadata` | 只读 |
| `am_list_alerts` | `GET /api/v2/alerts` | 只读 |
| `am_list_silences` | `GET /api/v2/silences` | 只读 |

禁止注册：`am_create_silence`、`am_delete_silence`、任意 POST/PUT/DELETE。这些只存在于审批单的“拟执行动作”字段里，V1 不执行。

---

## 5. 自然语言 → 确定性查询

### 5.1 模板优先

每个模板包含：

- `id`、中文名称、触发例句
- 槽位 schema（类型、必填、默认、允许值）
- PromQL 模板字符串（Jinja 或 format，**槽位只能替换标签值/数字/时长**，不能替换指标名以外的语法结构）
- 默认时间窗、step、结果解读提示

槽位替换后必须再走一遍 PromQL 解析。指标名只能来自模板声明或元数据白名单。

示例：

```yaml
id: http_error_rate
utterances:
  - "最近{window} {job} 的错误率"
  - "{service} 5xx 是不是高了"
slots:
  job: {type: label, required: false, default: "api"}
  window: {type: duration, default: "15m"}
promql: |
  sum(rate(http_requests_total{job="${job}",code=~"5.."}[${window}]))
  /
  sum(rate(http_requests_total{job="${job}"}[${window}]))
```

### 5.2 受限 PromQL 兜底规则

仅当分类器给出 `intent=ad_hoc_query` 且用户明确提到指标名时启用。校验全部通过才执行：

1. 用 `prometheus-api-client` 或自研/`promql-parser` 解析成功。
2. 禁止：`eval`、远端写、配置管理 API；本系统根本不暴露这些 HTTP。
3. AST 限制：
   - 不允许未知函数（函数白名单：`rate/irate/increase/sum/avg/max/min/count/histogram_quantile/topk/bottomk/quantile/abs/clamp` 等常用只读函数）。
   - `rate/increase` 的 range 必须在 `[1m, 1h]`。
   - `query_range` 的 `(end-start)/step` 点数 ≤ 11000，默认 ≤ 1000。
   - 正则选择器禁止 `.+` / `.*` 无锚点扫全量，除非模板显式允许。
4. 查询字符串长度 ≤ 2000。
5. 并发：同一用户 10 qps 令牌桶；全局可配。

### 5.3 结果解读约束

`interpret` 步骤：

- 必须原样附上执行过的 PromQL（代码块）。
- 不得声称“已重启/已静默”。
- 无数据时明确说“该时间窗无样本”，并建议检查 job 名、时间窗、指标是否存在（可调用 `prom_metric_metadata`）。
- 数字必须来自工具结果，禁止编造。

---

## 6. V1 意图目录（必须覆盖）

| 意图 ID | 用户说法示例 | 数据源 |
|---------|--------------|--------|
| `firing_alerts` | 现在有哪些告警？P1 有几条？ | Alertmanager |
| `alert_by_service` | checkout 相关告警 | Alertmanager |
| `cpu_usage` | 节点 CPU 是不是打满了 | Prometheus |
| `memory_usage` | pod/节点内存 | Prometheus |
| `http_error_rate` | 接口错误率 | Prometheus |
| `http_latency` | P99 延迟 | Prometheus |
| `restart_count` | 最近谁在重启 | Prometheus |
| `disk_usage` | 磁盘快满了吗 | Prometheus |
| `target_health` | 有没有 target down | Prometheus `up` |
| `ad_hoc_query` | 帮我查 `up{job="node"}` | Prometheus（受限） |
| `explain_promql` | 这条 PromQL 什么意思 | 不查询或可选 dry-run |
| `request_write` | 把这个告警静默 30 分钟 | 审批，不执行 |

内置模板先按 node-exporter + kube-state-metrics + 通用 `http_requests_total` 编写；具体指标名通过配置覆盖，避免写死某一套集群。

---

## 7. 安全管控

### 7.1 只读权限

- Prometheus / Alertmanager 客户端只封装 GET。
- 生产凭据使用只读账号或网络策略限制方法。
- 配置项 `SRE_AGENT_READ_ONLY=true` 恒为真；启动时若检测到写 API 封装则拒绝启动（测试可注入假客户端）。

### 7.2 查询模板化

- 默认 `QUERY_MODE=template_first`。
- `allow_ad_hoc_promql=true` 才开放受限生成。
- 所有执行记录：`user, intent, promql, duration, status, channel`。

### 7.3 操作审批流（V1）

触发：意图属于写操作，或用户话术含“静默/屏蔽/重启/扩容/删除规则”。

流程：

1. Agent 生成 `ApprovalRequest{id, action, payload, reason, requested_by}`。
2. 持久化到 PostgreSQL。
3. IM/Web 回复审批卡片：同意 / 拒绝。
4. V1 **同意后也不执行**，仅把状态标为 `approved_not_executed`，并提示“执行器未启用，请在控制台手动操作”。  
   这样审批链路可测，又不会误伤生产。

V2 再接真正的执行器（需独立开关 `ENABLE_MUTATIONS=false` 默认关）。若要做到“审批通过后从断点继续跑同一条流程”，那是迁 LangGraph 的信号之一，而不是在 V1 用图先占位。

### 7.4 身份与审计

- Streamlit：本地信任，仍记录 `session_id`。
- 飞书/钉钉：校验请求签名；用户 ID 写入审计日志。
- 审计日志字段不含 LLM API Key、Prometheus 密码。

---

## 8. 交互层

### 8.1 统一消息协议

```python
@dataclass
class IncomingMessage:
    channel: str
    user_id: str
    text: str
    session_id: str
    raw: dict

@dataclass
class OutgoingMessage:
    text: str                 # Markdown
    promql_blocks: list[str]
    cards: list[dict] | None  # IM 卡片
    approval_id: str | None
```

### 8.2 Streamlit

- 单页聊天 + 侧边栏（Prometheus URL、时间窗默认值、是否显示原始 JSON）。
- 每条回答展示：结论、PromQL、关键序列表、耗时。
- 本地 `streamlit run`。

### 8.3 飞书 / 钉钉

优先实现**飞书事件订阅 + 回复消息**（或钉钉 Stream，取决于配置哪个 Token 存在）。

共同要求：

- 验签
- 超时 3s 的 IM 平台限制：先快速 ACK，后台跑 Agent，再主动发消息
- 长结果截断 + “完整结果请看时间序列摘要”

若两者 Token 都未配置，仅启动 Streamlit，不报致命错误。

---

## 9. 可观测性（监控 Agent 自身）

暴露 `GET /metrics`（prometheus_client）：

| 指标 | 类型 | 标签 |
|------|------|------|
| `sre_agent_requests_total` | Counter | channel, intent, status |
| `sre_agent_request_duration_seconds` | Histogram | channel, intent |
| `sre_agent_llm_tokens_total` | Counter | model, direction=in/out |
| `sre_agent_llm_latency_seconds` | Histogram | model, step |  # step=classify\|interpret |
| `sre_agent_prom_queries_total` | Counter | api, status |
| `sre_agent_prom_query_duration_seconds` | Histogram | api |
| `sre_agent_approvals_total` | Counter | action, state |
| `sre_agent_policy_rejects_total` | Counter | reason |

另提供一份 `deploy/prometheus-scrape-example.yml` 示例，说明如何抓取本应用。用 LangChain `CallbackManager` 自定义 Handler 打点（`on_llm_end` / `on_tool_end` / `on_chain_error`），不依赖用户查询是否成功。

日志：结构化 JSON（time, level, session_id, intent, elapsed_ms）。默认不打 PromQL 以外的用户原文到 info（隐私）；debug 可开。

---

## 10. 配置与密钥

环境变量（前缀 `SRE_AGENT_`）：

| 变量 | 含义 | 默认 |
|------|------|------|
| `LLM_BASE_URL` | OpenAI 兼容地址 | 空则报错 |
| `LLM_API_KEY` | 密钥 | 必填 |
| `LLM_MODEL` | 模型名 | `qwen-plus` 可被覆盖 |
| `PROM_URL` | Prometheus | `http://localhost:9090` |
| `PROM_BASIC_AUTH` / `PROM_BEARER` | 可选 | 空 |
| `AM_URL` | Alertmanager | `http://localhost:9093` |
| `QUERY_TIMEOUT_SECONDS` | | `15` |
| `MAX_POINTS` | | `1000` |
| `ALLOW_AD_HOC_PROMQL` | | `false` |
| `FEISHU_APP_ID/SECRET` 等 | IM | 可选 |
| `DINGTALK_*` | IM | 可选 |
| `METRICS_PORT` | | `9108` |
| `DATABASE_URL` | PostgreSQL 连接串（审批 + 会话） | `postgresql://sre_agent:sre_agent@localhost:5432/sre_agent` |

`.env.example` 入库；`.env` 不入库。

### 10.1 PostgreSQL 表结构

同一数据库、同一 `DATABASE_URL`。启动时 `CREATE TABLE IF NOT EXISTS`。驱动：`psycopg` v3（`psycopg[binary]`）。

```sql
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    payload TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_session_id_idx ON messages (session_id, id);
CREATE TABLE IF NOT EXISTS clarifications (
    session_id TEXT PRIMARY KEY,
    n INT NOT NULL DEFAULT 0
);
```

`approvals.state` 仅允许：`pending` | `approved_not_executed` | `rejected`。V1 没有“已执行”状态。

---

## 11. 仓库结构（实现时创建，当前仅文档）

```
SRE-agent/
  README.md
  pyproject.toml
  .env.example
  docs/
    superpowers/specs/2026-08-31-sre-prometheus-agent-design.md
  src/sre_agent/
    __init__.py
    config.py
    db.py                 # psycopg 连接与建表
    pipeline.py           # run_turn() 线性流水线入口
    context.py            # TurnContext
    session.py            # InMemory（单测）/ PostgreSQL 会话
    classify.py           # with_structured_output(IntentSlots)
    interpret.py          # 结论生成 prompt
    tools/prometheus.py   # @tool 只读
    tools/alertmanager.py
    planner/templates.yaml
    planner/promql_guard.py
    channels/streamlit_app.py
    channels/feishu.py
    channels/dingtalk.py
    security/policy.py
    security/approvals.py
    observability/metrics.py
    observability/callbacks.py   # CallbackManager Handler
  tests/
    test_promql_guard.py
    test_policy.py
    test_planner.py
    test_pipeline_read_only.py
  deploy/
    prometheus-scrape-example.yml
```

---

## 12. 错误处理

| 场景 | 用户可见 | 内部 |
|------|----------|------|
| LLM 超时 | 模型暂不可用，请重试 | 指标 + error 日志 |
| Prometheus 连接失败 | 监控后端连不上，检查 PROM_URL | 不重试超过 1 次 |
| 查询超时 | 查询超过 15s 已取消，请缩小时间窗 | histogram 记 timeout |
| 无匹配模板且不允许 ad hoc | 给我更具体的指标/服务名，或打开示例问法 | policy_rejects |
| PromQL 校验失败 | 拒绝执行，列出违规点 | 不把非法查询发出 |
| 写操作 | 已记录审批单 #id，V1 不执行 | approvals_total |

---

## 13. 测试策略

优先单测，不依赖真实集群：

1. `promql_guard`：合法/非法查询表驱动。
2. `policy`：写操作识别与只读保证。
3. `planner`：例句 → 模板 id + 槽位。
4. `pipeline_read_only`：假 HTTP 客户端断言无 POST。
5. 可选集成测试：`docker compose` 起 Prometheus 时用环境变量开启。

---

## 14. 分阶段交付

| 阶段 | 内容 | 可演示 |
|------|------|--------|
| P0 | 文档（本规格）+ superpowers 工作流 | 本文档 |
| P1 | 内核：配置、只读客户端、模板、guard、LangChain 流水线、单测 | CLI：`sre-agent ask "当前有哪些告警"` |
| P2 | Streamlit 聊天 + `/metrics` | 浏览器对话 |
| P3 | 飞书或钉钉之一 | 群里说话巡检 |
| P4 | 审批队列 UI/卡片（不执行） | 说“静默”得到审批单 |
| P5 | 模板覆盖率与解读质量打磨 | 8 类意图金样例 |

编码从 P1 开始。规格已评审通过。实现计划见 `docs/superpowers/plans/2026-08-31-sre-prometheus-agent.md`。

---

## 15. 风险

- **指标名因集群而异**：模板必须可配置，解读时对缺失指标要引导，而不是硬编。
- **LLM 幻觉数字**：interpret 步骤只引用 tool_results。
- **高基数查询**：guard + 超时 + 最大点数。
- **IM 3 秒超时**：异步回复。
- **密钥泄漏**：环境变量 + 审计脱敏。

---

## 16. 已确认（一字不改）

1. IM 优先飞书，钉钉做对称适配器；只配一种也能跑。
2. `ALLOW_AD_HOC_PROMQL` 默认关闭。
3. V1 审批通过也不执行变更。
4. Python 从 `>=3.14` 降到 `>=3.11,<3.14`。
5. 默认模型走 OpenAI 兼容协议，不在代码里写死供应商 SDK。
6. **V1 纯 LangChain，不用 LangGraph。** `@tool` + `with_structured_output` + `CallbackManager`；会话与审批用 PostgreSQL，不用图 checkpointer。升 LangGraph 的三个信号见 2.2。

---

## 附录 A. 对话金样例（验收用）

1. “现在有哪些 firing 告警？”
2. “过去 15 分钟 API 5xx 比率多少？”
3. “哪台机器 CPU 超过 80%？”
4. “checkout 服务最近有没有重启？”
5. “帮我解释 `sum(rate(http_requests_total[5m]))`”
6. “把 node-disk 告警静默 1 小时” → 必须出审批单且不调用 POST。
7. “查一下 `sum(rate(http_requests_total{code=~".*"}[5m])) by (le)`” → 若未开 ad hoc 或校验失败，应拒绝。
8. “磁盘还剩多少？”
