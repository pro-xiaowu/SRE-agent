# SRE-Agent

用自然语言做 Prometheus 监控巡检和故障排查。

大模型只负责理解问题和组织回答；真正打到 Prometheus / Alertmanager 的是**经过模板或 AST 校验的只读查询**。

> 当前状态：**V1 代码已落地（CLI / Streamlit / `/metrics` / 飞书与钉钉适配器）。**  
> 规格：[`docs/superpowers/specs/2026-08-31-sre-prometheus-agent-design.md`](docs/superpowers/specs/2026-08-31-sre-prometheus-agent-design.md)  
> 计划：[`docs/superpowers/plans/2026-08-31-sre-prometheus-agent.md`](docs/superpowers/plans/2026-08-31-sre-prometheus-agent.md)

## 目标

值班同学可以直接说：

- “现在有哪些 P1 告警？”
- “过去 15 分钟 API 错误率有没有飙升？”
- “哪台机器 CPU 打满了？”

Agent 返回：结论、实际执行的 PromQL、关键数值。写操作（静默、重启等）只建审批单，V1 不执行。

## 技术栈（已锁定，见规格）

| 层 | 选择 |
|----|------|
| Agent | **V1 纯 LangChain**（线性流水线；不用 LangGraph） |
| 模型 | OpenAI 兼容协议（OpenAI / 通义 / 智谱 / 本地 vLLM） |
| 数据 | Prometheus、Alertmanager（只读 HTTP API） |
| 交互 | Streamlit；飞书 / 钉钉机器人 |
| 安全 | 只读客户端 + 查询模板化 + 写操作审批 |
| 自监控 | `prometheus_client` 暴露 `/metrics` |
| 存储 | PostgreSQL（`SRE_AGENT_DATABASE_URL`）；单测用内存 |
| 包管理 | uv，Python `>=3.11,<3.14` |

## 文档

| 文件 | 内容 |
|------|------|
| [设计规格](docs/superpowers/specs/2026-08-31-sre-prometheus-agent-design.md) | 架构、LangChain 流水线、工具白名单、安全、意图目录、分阶段交付 |
| [文档索引](docs/README.md) | 文档入口 |

## Superpowers 插件

本机已通过 Grok 安装并启用 [obra/superpowers](https://github.com/obra/superpowers)（v6.3.0）：先写规格，评审后再写实现计划与代码。

```bash
grok plugin marketplace add obra/superpowers-marketplace
grok plugin install superpowers@obra/superpowers-marketplace --trust
grok plugin enable superpowers
```

新开一个 Grok 会话后，插件技能才会进入当前对话。

## 运行

```bash
cp .env.example .env
uv sync --extra dev
uv run sre-agent ask "现在有哪些 firing 告警？"
uv run sre-agent chat
uv run sre-agent serve
```

需要可用的 LLM（OpenAI 兼容）和 Prometheus。审批与会话写入 PostgreSQL。
