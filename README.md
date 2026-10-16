# SRE-Agent 智能巡检助手

用自然语言做 Prometheus 监控巡检和故障排查，**不需要手写 PromQL**。

> 核心设计：**大模型只做意图映射，不直接生成查询语句。**
> 写操作一律拦截转审批，V1 阶段不执行。

---

## 解决什么问题

值班同学排查告警要手写 PromQL，但 Grafana 只有固定面板：

- 跨服务、跨实例的组合查询，Grafana 点不出来
- 遇到没预置面板的问题，只能现查文档写查询
- 交接班时「昨晚怎么查的」很难复现

本项目让值班同学直接问「过去 15 分钟 API 错误率多少」，由Agent 映射到预置查询模板。

---

## 安全边界（这是项目的重点）

模型**不拥有**执行任意查询的能力。四层防护：

| 层 | 限制什么 | 作用 |
|---|---|---|
| 1 | metric + PromQL 函数白名单 | 挡查询范围与高开销语法 |
| 2 | 查询超时（15s） | 挡慢查询打挂 Prometheus |
| 3 | 返回点数上限（1000） | 挡大结果集占满内存 |
| 4 | **客户端只有只读接口** | **即使前三层失效，最多查错，不可能改坏数据** |

写操作（静默 / 重启 / 删除）：

- 在**独立文本校验层**拦截，**不依赖模型**
- 转成审批记录，推送钉钉 / 企业微信给当前值班人员
- 审批通过后状态为 **`approved_not_executed`** —— **批了也不执行**
- V1 阶段不执行任何写操作

模型服务不可用时：返回「模型暂不可用，请重试」，**不猜答案**。

---

## 技术栈

| 层 | 选择 |
|---|---|
| Agent | LangChain（线性流水线，非 LangGraph） |
| 模型 | OpenAI 兼容协议（OpenAI / 通义 / 智谱 / 本地 vLLM） |
| 数据 | Prometheus、Alertmanager（**只读 HTTP API**） |
| 接口 | FastAPI + Streamlit + 钉钉 / 飞书机器人 |
| 自监控 | `prometheus_client` 暴露 `/metrics` |
| 存储 | PostgreSQL（会话与审批记录）；单测用内存 |
| 部署 | Docker Compose |

---

## 意图覆盖

**13 类意图**，其中 **10 类只读查询场景**：

```
firing 告警 · 服务级告警过滤 · CPU / 内存 / 磁盘使用率
接口错误率 · 接口延迟 · 重启次数 · Target 存活
ad-hoc 查询 · 解释 PromQL · 写操作拦截 · unknown
```

信息不足时自动追问补充（**上限 2 轮**），超出则明确告知无法查询，**不猜测返回**。

---

## 可观测性

暴露 **8 类自定义指标**：

```
sre_agent_requests_total{channel, intent, status}
sre_agent_request_duration_seconds{channel, intent}
sre_agent_llm_tokens_total{model, direction}
sre_agent_llm_latency_seconds{model, step}
sre_agent_prom_queries_total{api, status}
sre_agent_prom_query_duration_seconds{api}
sre_agent_approvals_total{action, state}
sre_agent_policy_rejects_total{reason}
```

Token 消耗、调用延迟、策略拒绝原因**全部可观测** —— 这是 AI 系统能不能进生产的判断依据。

---

## 测试

**18 个测试文件**，全部 pytest，**不调用模型**，跑一次约 4秒：

```
test_golden_intents.py    固定意图集断言
test_promql_guard.py      PromQL 白名单与注入校验
test_policy.py            写操作识别与越权拦截
test_clients_read_only.py 只读保证
test_pipeline_read_only.py
test_classifier_eval.py   ★ 唯一会调用模型的评估集
```

```bash
uv run pytest -m "not slow"    # 确定性逻辑，约 4 秒
uv run pytest                  # 含模型评估集
```

---

## 快速开始

### 前置

- Python `>=3.11,<3.14`
- `uv`
- 一个可用的 LLM（OpenAI 兼容）和 Prometheus

### 启动

```bash
cp .env.example .env        # 填入 LLM 和 Prometheus 配置
uv sync --extra dev

# 起依赖（监控机 ≠ 应用机）
cd deploy/docker/monitor && docker compose up -d    # Prometheus :9090 / Alertmanager :9093
cd deploy/docker/app     && docker compose up -d    # PostgreSQL

# 跑起来
uv run sre-agent ask "现在有哪些 firing 告警？"
uv run sre-agent chat
uv run sre-agent serve     # :9108，提供 /ask
```

⚠️ **应用机 `.env` 里的 Prometheus / Alertmanager 地址填监控机的内网 IP**，不要写 `127.0.0.1`。

---

## 项目收获

> 掌握将大模型能力接入运维工具的完整链路，理解 **AI 落地生产的关键在于约束边界而非模型能力本身**。

AI 系统最危险的地方不是模型答错，而是**模型拿到了它不该有的权限**。所以本项目的重心不在提示词，在四层防护和独立的写操作校验 —— **模型失效时，安全边界依然成立。**

---

## 文档

| 文件 | 内容 |
|---|---|
| [SRE-Agent完整指南](docs/SRE-Agent完整指南.md) | 从安装到问第一句话的完整步骤 |
| [从零构建教学](docs/从零构建教学.md) | 按构建顺序展示核心代码，带教学注释 |
| [设计规格](docs/superpowers/specs/2026-08-31-sre-prometheus-agent-design.md) | 架构、流水线、工具白名单、安全设计 |