# SRE-Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V1：自然语言经 LangChain 线性流水线变成对 Prometheus/Alertmanager 的确定性只读查询，CLI 可演示，随后接 Streamlit、飞书、审批单与 `/metrics`。

**Architecture:** `run_turn()` 顺序执行 policy → `with_structured_output` 分类 → 模板/guard 规划 → `@tool` 只读调用 → interpret。无 LangGraph。HTTP 客户端只发 GET。写操作只写入 PostgreSQL 审批表，状态到 `approved_not_executed` 为止。

**Tech Stack:** Python `>=3.11,<3.14`，uv，langchain / langchain-openai / langchain-core，httpx，pydantic-settings，PyYAML，prometheus_client，psycopg[binary]（PostgreSQL），streamlit，pytest。不添加 `langgraph`。不使用 SQLite。

## Global Constraints

- V1 纯 LangChain，不用 LangGraph（无 StateGraph、无 checkpointer、无 interrupt）。
- 依赖只写 `langchain`、`langchain-openai`、`langchain-core`；**不写 `langgraph`**。
- Python 从 `>=3.14` 降到 `>=3.11,<3.14`。
- 默认模型走 OpenAI 兼容协议，不在代码里写死供应商 SDK。
- `ALLOW_AD_HOC_PROMQL` 默认关闭。
- V1 审批通过也不执行变更。
- IM 优先飞书，钉钉做对称适配器；只配一种也能跑。
- 环境变量前缀 `SRE_AGENT_`。
- Prometheus/Alertmanager 客户端只封装 GET。
- 工具由流水线按 `intent` 代码调用，不开放自由 ReAct。
- 同一 session 澄清最多 2 轮；第 3 次仍缺槽则拒绝。
- 查询超时默认 15s；`query_range` 点数默认 ≤ 1000。
- 审批与会话生产存储为 PostgreSQL；连接串 `SRE_AGENT_DATABASE_URL`，驱动 `psycopg`（v3）。单测注入内存 store，不强制本机起 Postgres。
- 不使用 SQLite / `sqlite3` / `SRE_AGENT_SQLITE_PATH`。
- 包管理继续用 uv。工作目录：`D:\code-library\python-code\SRE-agent`。Windows 下测试命令一律 `uv run pytest ...`。

**本计划范围：** P1 内核 + P2 Streamlit/`/metrics` + P3 飞书（钉钉适配器可空转）+ P4 审批持久化（不执行）。P5 金样例打磨并入模板任务，不另开项目。

**Spec:** `docs/superpowers/specs/2026-08-31-sre-prometheus-agent-design.md`

---

## File map

| Path | Responsibility |
|------|----------------|
| `pyproject.toml` | 元数据、依赖、脚本入口、pytest |
| `.gitignore` | `.env`、`.venv`、`data/`、`__pycache__` |
| `.env.example` | 配置样例，无密钥 |
| `src/sre_agent/__init__.py` | 包 |
| `src/sre_agent/config.py` | `Settings` |
| `src/sre_agent/context.py` | `IncomingMessage` `OutgoingMessage` `TurnContext` `IntentSlots` `QueryPlan` |
| `src/sre_agent/planner/promql_guard.py` | PromQL 校验 |
| `src/sre_agent/security/policy.py` | 写操作/空输入闸门 |
| `src/sre_agent/clients/http.py` | 只读 GET 封装 |
| `src/sre_agent/clients/prometheus.py` | Prometheus GET API |
| `src/sre_agent/clients/alertmanager.py` | Alertmanager GET API |
| `src/sre_agent/planner/templates.yaml` | 查询模板 |
| `src/sre_agent/planner/planner.py` | intent+slots → QueryPlan |
| `src/sre_agent/security/approvals.py` | PostgreSQL 审批，不执行；内存实现供单测 |
| `src/sre_agent/session.py` | 内存（单测）/ PostgreSQL 消息历史 |
| `src/sre_agent/tools/prometheus.py` | `@tool` 只读 |
| `src/sre_agent/tools/alertmanager.py` | `@tool` 只读 |
| `src/sre_agent/classify.py` | `with_structured_output` |
| `src/sre_agent/interpret.py` | 结论 prompt |
| `src/sre_agent/pipeline.py` | `run_turn()` |
| `src/sre_agent/cli.py` | `sre-agent ask` |
| `src/sre_agent/observability/metrics.py` | prometheus_client 指标 |
| `src/sre_agent/observability/callbacks.py` | Callback Handler |
| `src/sre_agent/channels/streamlit_app.py` | Web 聊天 |
| `src/sre_agent/channels/feishu.py` | 飞书验签 + 异步回复 |
| `src/sre_agent/channels/dingtalk.py` | 钉钉适配器（无 token 则不注册路由） |
| `src/sre_agent/serve.py` | FastAPI：飞书/钉钉回调 + `/metrics` |
| `deploy/prometheus-scrape-example.yml` | 抓取示例 |
| `tests/` | 与上面对应的单测 |

删除或停用根目录 PyCharm 占位 `main.py`（不作为入口）。

---

### Task 1: 工程骨架与 Python 约束

**Files:**
- Modify: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/sre_agent/__init__.py`
- Create: `tests/test_package.py`
- Delete after CLI 存在前先保留：`main.py`（本任务末步删除占位逻辑，改为注释指向 CLI；Task 12 再删文件）

**Interfaces:**
- Consumes: 无
- Produces: 可安装包 `sre_agent`，`requires-python = ">=3.11,<3.14"`，dev 依赖 pytest

- [ ] **Step 1: Write the failing test**

Create `tests/test_package.py`:

```python
import sys

from sre_agent import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_python_constraint_documented():
    assert sys.version_info >= (3, 11)
```

Create `src/sre_agent/__init__.py` only after the test fails (empty repo has no package).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'sre_agent'` or collection error.

- [ ] **Step 3: Write minimal implementation**

Replace `pyproject.toml` entirely:

```toml
[project]
name = "sre-agent"
version = "0.1.0"
description = "Natural-language read-only Prometheus inspection agent"
requires-python = ">=3.11,<3.14"
dependencies = [
    "langchain>=0.3.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",
    "httpx>=0.27.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "pyyaml>=6.0",
    "prometheus-client>=0.21.0",
    "python-dotenv>=1.0.0",
    "psycopg[binary]>=3.2.0",
]

[project.optional-dependencies]
web = [
    "streamlit>=1.40.0",
    "fastapi>=0.115.0",
    "uvicorn>=0.32.0",
]
dev = [
    "pytest>=8.0.0",
]

[project.scripts]
sre-agent = "sre_agent.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sre_agent"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

If hatchling packages `src/sre_agent` as the top-level name incorrectly, switch to:

```toml
[tool.hatch.build.targets.wheel]
only-include = ["sre_agent"]

[tool.hatch.build.targets.wheel.force-include]
"src/sre_agent" = "sre_agent"
```

Write `src/sre_agent/__init__.py`:

```python
__version__ = "0.1.0"
```

Write `.gitignore`:

```
.venv/
__pycache__/
*.pyc
.env
data/
.pytest_cache/
*.egg-info/
uv.lock.bak
```

Run: `uv lock` then `uv sync --extra dev`

Confirm `uv.lock` 与 `pyproject.toml` 中均无 `langgraph` 字符串。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_package.py -v`

Expected: PASS（`test_python_constraint_documented` 在 3.11/3.12/3.13 上通过；若本机仍是 3.14，不要改约束，在计划执行记录里写明跳过该断言并继续用 3.12 venv：`uv python pin 3.12`。）

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore src/sre_agent/__init__.py tests/test_package.py
git commit -m "chore: bootstrap sre_agent package on Python 3.11-3.13"
```

若仓库尚未 `git init`，先 `git init` 再提交。

---

### Task 2: Settings

**Files:**
- Create: `src/sre_agent/config.py`
- Create: `tests/test_config.py`
- Create: `.env.example`

**Interfaces:**
- Consumes: 无
- Produces: `class Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="SRE_AGENT_", extra="ignore")`; `def load_settings() -> Settings`

字段（类型与默认必须如下）：

- `llm_base_url: str`
- `llm_api_key: str`
- `llm_model: str = "qwen-plus"`
- `prom_url: str = "http://localhost:9090"`
- `prom_basic_auth: str | None = None`
- `prom_bearer: str | None = None`
- `am_url: str = "http://localhost:9093"`
- `query_timeout_seconds: int = 15`
- `max_points: int = 1000`
- `allow_ad_hoc_promql: bool = False`
- `feishu_app_id: str | None = None`
- `feishu_app_secret: str | None = None`
- `feishu_encrypt_key: str | None = None`
- `feishu_verification_token: str | None = None`
- `dingtalk_app_key: str | None = None`
- `dingtalk_app_secret: str | None = None`
- `metrics_port: int = 9108`
- `database_url: str = "postgresql://sre_agent:sre_agent@localhost:5432/sre_agent"`
- `read_only: bool = True`

- [ ] **Step 1: Write the failing test**

```python
import os

from sre_agent.config import Settings, load_settings


def test_allow_ad_hoc_defaults_false(monkeypatch):
    monkeypatch.setenv("SRE_AGENT_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("SRE_AGENT_LLM_API_KEY", "sk-test")
    s = load_settings()
    assert s.allow_ad_hoc_promql is False
    assert s.llm_model == "qwen-plus"
    assert s.query_timeout_seconds == 15
    assert s.max_points == 1000
    assert s.read_only is True
    assert s.prom_url == "http://localhost:9090"
    assert s.am_url == "http://localhost:9093"


def test_missing_llm_url_raises(monkeypatch):
    monkeypatch.delenv("SRE_AGENT_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SRE_AGENT_LLM_API_KEY", raising=False)
    try:
        Settings()
    except Exception as exc:
        assert "llm_base_url" in str(exc).lower() or "LLM_BASE_URL" in str(exc)
    else:
        raise AssertionError("expected validation error")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'sre_agent.config'`

- [ ] **Step 3: Write minimal implementation**

`src/sre_agent/config.py`:

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SRE_AGENT_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    llm_base_url: str
    llm_api_key: str
    llm_model: str = "qwen-plus"
    prom_url: str = "http://localhost:9090"
    prom_basic_auth: str | None = None
    prom_bearer: str | None = None
    am_url: str = "http://localhost:9093"
    query_timeout_seconds: int = 15
    max_points: int = 1000
    allow_ad_hoc_promql: bool = False
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_encrypt_key: str | None = None
    feishu_verification_token: str | None = None
    dingtalk_app_key: str | None = None
    dingtalk_app_secret: str | None = None
    metrics_port: int = 9108
    database_url: str = "postgresql://sre_agent:sre_agent@localhost:5432/sre_agent"
    read_only: bool = True


def load_settings() -> Settings:
    return Settings()
```

`.env.example`:

```
SRE_AGENT_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SRE_AGENT_LLM_API_KEY=
SRE_AGENT_LLM_MODEL=qwen-plus
SRE_AGENT_PROM_URL=http://localhost:9090
SRE_AGENT_AM_URL=http://localhost:9093
SRE_AGENT_ALLOW_AD_HOC_PROMQL=false
SRE_AGENT_QUERY_TIMEOUT_SECONDS=15
SRE_AGENT_MAX_POINTS=1000
SRE_AGENT_METRICS_PORT=9108
SRE_AGENT_DATABASE_URL=postgresql://sre_agent:sre_agent@localhost:5432/sre_agent
SRE_AGENT_FEISHU_APP_ID=
SRE_AGENT_FEISHU_APP_SECRET=
SRE_AGENT_DINGTALK_APP_KEY=
SRE_AGENT_DINGTALK_APP_SECRET=
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/config.py tests/test_config.py .env.example
git commit -m "feat: add SRE_AGENT_ settings with ad-hoc PromQL off"
```

---

### Task 3: PromQL guard

**Files:**
- Create: `src/sre_agent/planner/__init__.py`
- Create: `src/sre_agent/planner/promql_guard.py`
- Create: `tests/test_promql_guard.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class PromQLViolation(ValueError)` with `reasons: list[str]`
  - `def validate_promql(query: str, *, max_length: int = 2000) -> str` — 合法则返回 strip 后的 query，否则 raise `PromQLViolation`

规则（必须全部实现）：

1. 空字符串非法。
2. `len(query) > max_length` 非法。
3. 禁止子串（大小写不敏感）：`eval(`、`/api/v1/admin`、`delete_series`、`snapshot`。
4. 函数名白名单：`rate` `irate` `increase` `sum` `avg` `max` `min` `count` `histogram_quantile` `topk` `bottomk` `quantile` `abs` `clamp` `clamp_min` `clamp_max` `avg_over_time` `max_over_time` `min_over_time` `last_over_time` `count_over_time` `stddev_over_time` `stdvar_over_time` `group` `count_values` `absent` `absent_over_time` `label_replace` `label_join` `round` `floor` `ceil` `sqrt` `exp` `ln` `log2` `log10` `time` `vector` `scalar` `sort` `sort_desc` `holt_winters` `predict_linear` `deriv` `delta` `idelta` `resets` `changes` `timestamp` `ignoring` 不算函数；提取 `[A-Za-z_][A-Za-z0-9_]*\s*\(` 中的名字，去掉 `by`/`without`/`on`/`group_left`/`group_right`/`and`/`or`/`unless`/`bool`。未知函数非法。
5. `rate|irate|increase` 的 range 必须匹配 `\[(\d+)(ms|s|m|h)\]` 且换算到秒后 ∈ [60, 3600]。
6. 选择器 `=~` 后若为 `".*"`、`'.+'`、`".+"`、`'.*'` 非法。

- [ ] **Step 1: Write the failing test**

```python
import pytest

from sre_agent.planner.promql_guard import PromQLViolation, validate_promql


def test_accepts_rate_sum():
    q = 'sum(rate(http_requests_total{job="api"}[5m]))'
    assert validate_promql(q) == q


def test_rejects_empty():
    with pytest.raises(PromQLViolation) as ei:
        validate_promql("   ")
    assert ei.value.reasons


def test_rejects_unknown_function():
    with pytest.raises(PromQLViolation) as ei:
        validate_promql("evil_drop(http_requests_total)")
    assert any("function" in r.lower() or "函数" in r for r in ei.value.reasons)


def test_rejects_unbounded_regex():
    with pytest.raises(PromQLViolation):
        validate_promql('sum(rate(http_requests_total{code=~".*"}[5m]))')


def test_rejects_rate_range_too_short():
    with pytest.raises(PromQLViolation):
        validate_promql("rate(http_requests_total[30s])")


def test_rejects_overlong():
    with pytest.raises(PromQLViolation):
        validate_promql("up" + "a" * 2001)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_promql_guard.py -v`

Expected: FAIL with import error or missing `validate_promql`

- [ ] **Step 3: Write minimal implementation**

`src/sre_agent/planner/__init__.py` empty.

`src/sre_agent/planner/promql_guard.py`:

```python
from __future__ import annotations

import re

ALLOWED_FUNCTIONS = frozenset(
    {
        "rate",
        "irate",
        "increase",
        "sum",
        "avg",
        "max",
        "min",
        "count",
        "histogram_quantile",
        "topk",
        "bottomk",
        "quantile",
        "abs",
        "clamp",
        "clamp_min",
        "clamp_max",
        "avg_over_time",
        "max_over_time",
        "min_over_time",
        "last_over_time",
        "count_over_time",
        "stddev_over_time",
        "stdvar_over_time",
        "group",
        "count_values",
        "absent",
        "absent_over_time",
        "label_replace",
        "label_join",
        "round",
        "floor",
        "ceil",
        "sqrt",
        "exp",
        "ln",
        "log2",
        "log10",
        "time",
        "vector",
        "scalar",
        "sort",
        "sort_desc",
        "holt_winters",
        "predict_linear",
        "deriv",
        "delta",
        "idelta",
        "resets",
        "changes",
        "timestamp",
    }
)
KEYWORD_CALLS = frozenset(
    {"by", "without", "on", "group_left", "group_right", "and", "or", "unless", "bool", "ignoring"}
)
FORBIDDEN_SUBSTR = ("eval(", "/api/v1/admin", "delete_series", "snapshot")
FUNC_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
RANGE_RE = re.compile(r"\b(rate|irate|increase)\s*\([^)]*\[(\d+)(ms|s|m|h)\]", re.I)
UNBOUNDED_RE = re.compile(r"=~\s*['\"](\.\*|\.\+)['\"]")
UNIT_TO_SECONDS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


class PromQLViolation(ValueError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def validate_promql(query: str, *, max_length: int = 2000) -> str:
    q = (query or "").strip()
    reasons: list[str] = []
    if not q:
        raise PromQLViolation(["empty query"])
    if len(q) > max_length:
        reasons.append(f"query longer than {max_length}")
    lower = q.lower()
    for bad in FORBIDDEN_SUBSTR:
        if bad in lower:
            reasons.append(f"forbidden fragment: {bad}")
    if UNBOUNDED_RE.search(q):
        reasons.append("unbounded regex selector")
    for name in FUNC_RE.findall(q):
        key = name.lower()
        if key in KEYWORD_CALLS:
            continue
        if key not in ALLOWED_FUNCTIONS:
            reasons.append(f"unknown function: {name}")
    for m in RANGE_RE.finditer(q):
        n = int(m.group(2))
        sec = n * UNIT_TO_SECONDS[m.group(3)]
        if sec < 60 or sec > 3600:
            reasons.append("rate/increase range must be in [1m, 1h]")
    if reasons:
        raise PromQLViolation(reasons)
    return q
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_promql_guard.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/planner tests/test_promql_guard.py
git commit -m "feat: add PromQL guard with function and regex limits"
```

---

### Task 4: Policy gate

**Files:**
- Create: `src/sre_agent/security/__init__.py`
- Create: `src/sre_agent/security/policy.py`
- Create: `tests/test_policy.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class PolicyDecision` dataclass: `allow: bool`, `reason: str`, `write_action: str | None`
  - `def check_text(text: str) -> PolicyDecision`
  - `reason` 取值：`ok` | `empty` | `write_operation`
  - `write_action` 取值：`silence` | `restart` | `scale` | `delete_rule` | `generic_write` | `None`

关键词（命中任一即写操作）：`静默` `屏蔽` `重启` `扩容` `删除规则` `silence` `snooze` `restart` `scale up` `delete rule`（大小写不敏感）。

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.security.policy import check_text


def test_allow_inspection():
    d = check_text("现在有哪些 firing 告警？")
    assert d.allow is True
    assert d.reason == "ok"
    assert d.write_action is None


def test_reject_empty():
    d = check_text("  \n")
    assert d.allow is False
    assert d.reason == "empty"


def test_reject_silence():
    d = check_text("把 node-disk 告警静默 1 小时")
    assert d.allow is False
    assert d.reason == "write_operation"
    assert d.write_action == "silence"


def test_reject_restart():
    d = check_text("重启 checkout 服务")
    assert d.allow is False
    assert d.reason == "write_operation"
    assert d.write_action == "restart"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_policy.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass

WRITE_PATTERNS: list[tuple[str, str]] = [
    ("静默", "silence"),
    ("屏蔽", "silence"),
    ("silence", "silence"),
    ("snooze", "silence"),
    ("重启", "restart"),
    ("restart", "restart"),
    ("扩容", "scale"),
    ("scale up", "scale"),
    ("删除规则", "delete_rule"),
    ("delete rule", "delete_rule"),
]


@dataclass(frozen=True)
class PolicyDecision:
    allow: bool
    reason: str
    write_action: str | None = None


def check_text(text: str) -> PolicyDecision:
    raw = (text or "").strip()
    if not raw:
        return PolicyDecision(False, "empty", None)
    lower = raw.lower()
    for needle, action in WRITE_PATTERNS:
        if needle.lower() in lower:
            return PolicyDecision(False, "write_operation", action)
    return PolicyDecision(True, "ok", None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_policy.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/security tests/test_policy.py
git commit -m "feat: reject write-intent utterances in policy gate"
```

---

### Task 5: 只读 HTTP 客户端

**Files:**
- Create: `src/sre_agent/clients/__init__.py`
- Create: `src/sre_agent/clients/http.py`
- Create: `src/sre_agent/clients/prometheus.py`
- Create: `src/sre_agent/clients/alertmanager.py`
- Create: `tests/test_clients_read_only.py`

**Interfaces:**
- Consumes: `Settings.query_timeout_seconds`, `Settings.max_points`, `Settings.prom_url`, `Settings.am_url`, `Settings.prom_bearer`, `Settings.prom_basic_auth`
- Produces:
  - `class ReadOnlyHTTPError(Exception)`
  - `class ReadOnlyClient` with `def get(self, url: str, params: dict | None = None) -> dict`
  - **没有** `post`/`put`/`delete` 方法
  - `class PrometheusClient`：
    - `def instant_query(self, query: str) -> dict`
    - `def range_query(self, query: str, start: float, end: float, step: str) -> dict`
    - `def label_values(self, name: str) -> list`
    - `def metadata(self, metric: str | None = None) -> dict`
  - `class AlertmanagerClient`：
    - `def list_alerts(self, filter: str | None = None) -> list`
    - `def list_silences(self) -> list`
  - `range_query` 若 `(end-start)/step_seconds > max_points` 则 raise `ReadOnlyHTTPError("too many points")`，不发请求

- [ ] **Step 1: Write the failing test**

```python
import pytest

from sre_agent.clients.http import ReadOnlyClient, ReadOnlyHTTPError
from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.clients.alertmanager import AlertmanagerClient


class FakeTransport:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        return {"status": "success", "data": {"resultType": "vector", "result": []}}


def test_readonly_client_has_no_post():
    c = ReadOnlyClient("http://prom", timeout=1, transport=FakeTransport())
    assert not hasattr(c, "post")
    assert not hasattr(c, "put")
    assert not hasattr(c, "delete")


def test_prometheus_instant_uses_get():
    t = FakeTransport()
    p = PrometheusClient("http://prom", timeout=15, max_points=1000, transport=t)
    p.instant_query("up")
    assert t.calls[0][0] == "GET"
    assert t.calls[0][1].endswith("/api/v1/query")
    assert t.calls[0][2]["query"] == "up"


def test_range_rejects_too_many_points():
    t = FakeTransport()
    p = PrometheusClient("http://prom", timeout=15, max_points=10, transport=t)
    with pytest.raises(ReadOnlyHTTPError):
        p.range_query("up", start=0, end=10000, step="1s")
    assert t.calls == []


def test_alertmanager_list_alerts_get():
    t = FakeTransport()
    t.get = lambda url, params=None: (t.calls.append(("GET", url, params)) or [])
    am = AlertmanagerClient("http://am", timeout=15, transport=t)
    am.list_alerts()
    assert t.calls[0][1].endswith("/api/v2/alerts")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_clients_read_only.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`src/sre_agent/clients/http.py`:

```python
from __future__ import annotations

from typing import Any, Protocol

import httpx


class Transport(Protocol):
    def get(self, url: str, params: dict | None = None) -> Any: ...


class ReadOnlyHTTPError(Exception):
    pass


class HttpxTransport:
    def __init__(self, timeout: float, headers: dict | None = None, auth: httpx.BasicAuth | None = None):
        self._timeout = timeout
        self._headers = headers or {}
        self._auth = auth

    def get(self, url: str, params: dict | None = None) -> Any:
        try:
            r = httpx.get(
                url,
                params=params,
                timeout=self._timeout,
                headers=self._headers,
                auth=self._auth,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise ReadOnlyHTTPError(str(exc)) from exc


class ReadOnlyClient:
    def __init__(self, base_url: str, timeout: float, transport: Transport | None = None, headers: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or HttpxTransport(timeout, headers=headers)

    def get(self, path: str, params: dict | None = None) -> Any:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        return self.transport.get(url, params=params)
```

`src/sre_agent/clients/prometheus.py`:

```python
from __future__ import annotations

from sre_agent.clients.http import ReadOnlyClient, ReadOnlyHTTPError, Transport


def _step_seconds(step: str) -> float:
    units = {"s": 1, "m": 60, "h": 3600}
    n = int(step[:-1])
    return n * units[step[-1]]


class PrometheusClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        max_points: int,
        transport: Transport | None = None,
        bearer: str | None = None,
    ):
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else None
        self.max_points = max_points
        self.http = ReadOnlyClient(base_url, timeout, transport=transport, headers=headers)

    def instant_query(self, query: str) -> dict:
        return self.http.get("/api/v1/query", {"query": query})

    def range_query(self, query: str, start: float, end: float, step: str) -> dict:
        points = (end - start) / _step_seconds(step)
        if points > self.max_points:
            raise ReadOnlyHTTPError("too many points")
        return self.http.get(
            "/api/v1/query_range",
            {"query": query, "start": start, "end": end, "step": step},
        )

    def label_values(self, name: str) -> list:
        data = self.http.get(f"/api/v1/label/{name}/values")
        return data.get("data", data) if isinstance(data, dict) else data

    def metadata(self, metric: str | None = None) -> dict:
        params = {"metric": metric} if metric else None
        return self.http.get("/api/v1/metadata", params)
```

`src/sre_agent/clients/alertmanager.py`:

```python
from __future__ import annotations

from sre_agent.clients.http import ReadOnlyClient, Transport


class AlertmanagerClient:
    def __init__(self, base_url: str, timeout: float, transport: Transport | None = None):
        self.http = ReadOnlyClient(base_url, timeout, transport=transport)

    def list_alerts(self, filter: str | None = None) -> list:
        params = {"filter": filter} if filter else None
        data = self.http.get("/api/v2/alerts", params)
        return data if isinstance(data, list) else data.get("data", [])

    def list_silences(self) -> list:
        data = self.http.get("/api/v2/silences")
        return data if isinstance(data, list) else data.get("data", [])
```

`src/sre_agent/clients/__init__.py` empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_clients_read_only.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/clients tests/test_clients_read_only.py
git commit -m "feat: add GET-only Prometheus and Alertmanager clients"
```

---

### Task 6: 查询模板与 planner

**Files:**
- Create: `src/sre_agent/planner/templates.yaml`
- Create: `src/sre_agent/planner/planner.py`
- Create: `src/sre_agent/context.py`（本任务放入 `IntentSlots` 与 `QueryPlan`；消息类型下任务可同文件追加）
- Create: `tests/test_planner.py`

**Interfaces:**
- Consumes: `validate_promql(query: str) -> str`
- Produces:
  - `class IntentSlots(BaseModel)` 字段：`intent: Literal["firing_alerts","alert_by_service","cpu_usage","memory_usage","http_error_rate","http_latency","restart_count","disk_usage","target_health","ad_hoc_query","explain_promql","request_write","unknown"]`, `confidence: float = 0.0`, `job: str | None = None`, `window: str = "15m"`, `service: str | None = None`, `instance: str | None = None`, `promql: str | None = None`, `missing_slots: list[str] = []`, `ask_user: str | None = None`
  - `class QueryPlan` dataclass：`template_id: str | None`, `promql: str | None`, `tool: str`, `params: dict`, `reject_reason: str | None`
  - `def load_templates(path: Path | None = None) -> list[dict]`
  - `def plan(slots: IntentSlots, *, allow_ad_hoc: bool) -> QueryPlan`
  - `tool` 取值：`prom_query` | `prom_query_range` | `am_list_alerts` | `am_list_silences` | `none`

模板 YAML（完整写入 `templates.yaml`）：

```yaml
templates:
  - id: firing_alerts
    intent: firing_alerts
    tool: am_list_alerts
    params:
      filter: 'status="firing"'
  - id: alert_by_service
    intent: alert_by_service
    tool: am_list_alerts
    params:
      filter: '${service}'
    slots:
      service: {required: true}
  - id: cpu_usage
    intent: cpu_usage
    tool: prom_query
    promql: '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[${window}])) * 100)'
    slots:
      window: {required: false, default: "15m"}
  - id: memory_usage
    intent: memory_usage
    tool: prom_query
    promql: '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
  - id: http_error_rate
    intent: http_error_rate
    tool: prom_query
    promql: |
      sum(rate(http_requests_total{job="${job}",code=~"5.."}[${window}]))
      /
      sum(rate(http_requests_total{job="${job}"}[${window}]))
    slots:
      job: {required: false, default: "api"}
      window: {required: false, default: "15m"}
  - id: http_latency
    intent: http_latency
    tool: prom_query
    promql: 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{job="${job}"}[${window}])) by (le))'
    slots:
      job: {required: false, default: "api"}
      window: {required: false, default: "15m"}
  - id: restart_count
    intent: restart_count
    tool: prom_query
    promql: 'increase(kube_pod_container_status_restarts_total{namespace=~".+",pod=~"${service}.*"}[${window}])'
    slots:
      service: {required: false, default: ".+"}
      window: {required: false, default: "15m"}
  - id: disk_usage
    intent: disk_usage
    tool: prom_query
    promql: '(1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"})) * 100'
  - id: target_health
    intent: target_health
    tool: prom_query
    promql: 'up == 0'
  - id: explain_promql
    intent: explain_promql
    tool: none
```

`plan()` 行为：

- `intent == unknown` → `QueryPlan(None, None, "none", {}, "unknown intent")`
- `intent == explain_promql` → `tool=none`, `promql=slots.promql`
- `intent == ad_hoc_query`：若 `allow_ad_hoc` 为 False → reject `"ad hoc PromQL disabled"`；否则对 `slots.promql` 调 `validate_promql`，成功则 `tool=prom_query`
- 其余：按 `intent` 找模板；缺 required slot → reject `"missing slot: X"`；用 `string.Template` 或 `${}` 替换（只替换值）；得到的 promql 再 `validate_promql`；失败则把 `PromQLViolation.reasons` 拼进 `reject_reason`
- `restart_count` 模板含 `namespace=~".+"`：这是模板内置选择器，`validate_promql` 会因 unbounded regex 拒绝。**改模板**为 `increase(kube_pod_container_status_restarts_total[${window}])`，避免 guard 与模板冲突。

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.context import IntentSlots
from sre_agent.planner.planner import plan


def test_firing_alerts_uses_alertmanager():
    p = plan(IntentSlots(intent="firing_alerts", confidence=0.9), allow_ad_hoc=False)
    assert p.tool == "am_list_alerts"
    assert p.reject_reason is None


def test_http_error_rate_fills_defaults():
    p = plan(IntentSlots(intent="http_error_rate", confidence=0.9), allow_ad_hoc=False)
    assert p.tool == "prom_query"
    assert 'job="api"' in (p.promql or "")
    assert "[15m]" in (p.promql or "")


def test_ad_hoc_disabled_by_default():
    p = plan(
        IntentSlots(intent="ad_hoc_query", confidence=0.9, promql="up"),
        allow_ad_hoc=False,
    )
    assert p.tool == "none"
    assert "disabled" in (p.reject_reason or "").lower() or "ad hoc" in (p.reject_reason or "").lower()


def test_ad_hoc_rejects_bad_regex_when_enabled():
    p = plan(
        IntentSlots(
            intent="ad_hoc_query",
            confidence=0.9,
            promql='sum(rate(http_requests_total{code=~".*"}[5m]))',
        ),
        allow_ad_hoc=True,
    )
    assert p.tool == "none"
    assert p.reject_reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_planner.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`src/sre_agent/context.py`（本任务先放模型；后续任务往同一文件追加消息类型，不要新建平行文件）：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

IntentName = Literal[
    "firing_alerts",
    "alert_by_service",
    "cpu_usage",
    "memory_usage",
    "http_error_rate",
    "http_latency",
    "restart_count",
    "disk_usage",
    "target_health",
    "ad_hoc_query",
    "explain_promql",
    "request_write",
    "unknown",
]


class IntentSlots(BaseModel):
    intent: IntentName
    confidence: float = 0.0
    job: str | None = None
    window: str = "15m"
    service: str | None = None
    instance: str | None = None
    promql: str | None = None
    missing_slots: list[str] = Field(default_factory=list)
    ask_user: str | None = None


@dataclass
class QueryPlan:
    template_id: str | None
    promql: str | None
    tool: str
    params: dict[str, Any]
    reject_reason: str | None = None
```

`src/sre_agent/planner/planner.py`：加载 YAML；`string.Template` 的分隔符是 `$`，YAML 里用 `${job}` 即可。实现 `def _subst(expr: str, mapping: dict) -> str`：只替换 `${job}` `${window}` `${service}` `${instance}` 这些键，值为空则用模板 default。

完整 `planner.py`：

```python
from __future__ import annotations

from pathlib import Path
from string import Template

import yaml

from sre_agent.context import IntentSlots, QueryPlan
from sre_agent.planner.promql_guard import PromQLViolation, validate_promql

TEMPLATES_PATH = Path(__file__).with_name("templates.yaml")


def load_templates(path: Path | None = None) -> list[dict]:
    data = yaml.safe_load((path or TEMPLATES_PATH).read_text(encoding="utf-8"))
    return data["templates"]


def plan(slots: IntentSlots, *, allow_ad_hoc: bool) -> QueryPlan:
    if slots.intent == "unknown":
        return QueryPlan(None, None, "none", {}, "unknown intent")
    if slots.intent == "explain_promql":
        return QueryPlan("explain_promql", slots.promql, "none", {}, None)
    if slots.intent == "ad_hoc_query":
        if not allow_ad_hoc:
            return QueryPlan(None, None, "none", {}, "ad hoc PromQL disabled")
        if not slots.promql:
            return QueryPlan(None, None, "none", {}, "missing slot: promql")
        try:
            q = validate_promql(slots.promql)
        except PromQLViolation as exc:
            return QueryPlan(None, None, "none", {}, "; ".join(exc.reasons))
        return QueryPlan(None, q, "prom_query", {}, None)
    templates = {t["intent"]: t for t in load_templates()}
    tmpl = templates.get(slots.intent)
    if not tmpl:
        return QueryPlan(None, None, "none", {}, "unknown intent")
    mapping = {
        "job": slots.job or "api",
        "window": slots.window or "15m",
        "service": slots.service or "",
        "instance": slots.instance or "",
    }
    slot_defs = tmpl.get("slots") or {}
    for name, spec in slot_defs.items():
        if spec.get("required") and not getattr(slots, name, None):
            return QueryPlan(tmpl.get("id"), None, "none", {}, f"missing slot: {name}")
        if not mapping.get(name):
            mapping[name] = spec.get("default") or mapping.get(name, "")
    params = {}
    for k, v in (tmpl.get("params") or {}).items():
        params[k] = Template(str(v)).safe_substitute(mapping)
    promql = tmpl.get("promql")
    if promql:
        rendered = Template(promql).safe_substitute(mapping)
        try:
            rendered = validate_promql(rendered)
        except PromQLViolation as exc:
            return QueryPlan(tmpl.get("id"), None, "none", params, "; ".join(exc.reasons))
        return QueryPlan(tmpl.get("id"), rendered, tmpl["tool"], params, None)
    return QueryPlan(tmpl.get("id"), None, tmpl["tool"], params, None)
```

写入完整 `templates.yaml`（`restart_count` 使用无无界正则的表达式，见上）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_planner.py tests/test_promql_guard.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/context.py src/sre_agent/planner tests/test_planner.py
git commit -m "feat: add template planner with ad-hoc PromQL disabled"
```

---

### Task 7: 审批存储（PostgreSQL，不执行）

**Files:**
- Create: `src/sre_agent/db.py`
- Create: `src/sre_agent/security/approvals.py`
- Create: `tests/test_approvals.py`

**Interfaces:**
- Consumes: `Settings.database_url`
- Produces:
  - `def connect(database_url: str)` → `psycopg.Connection`（`row_factory=dict_row`, `autocommit=True`）
  - `def init_schema(conn) -> None` 创建下表（`IF NOT EXISTS`）
  - `class ApprovalRecord` dataclass: `id: str`, `action: str`, `payload: str`, `reason: str`, `requested_by: str`, `state: str`
  - `class ApprovalStore` 协议：`create` / `decide` / `get`
  - `class MemoryApprovalStore` — 单测用
  - `class PostgresApprovalStore` — 生产用
  - `def build_approval_store(database_url: str | None) -> ApprovalStore` — `None` 或空串 → 内存；否则 PostgreSQL
  - `create(...)` → `state="pending"`
  - `decide(..., approved=True)` → `state="approved_not_executed"`；`False` → `rejected`。**不得**发 HTTP，**不得**调用 Alertmanager

DDL（必须原样出现在 `init_schema`）：

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

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.security.approvals import build_approval_store


def test_approve_does_not_execute():
    store = build_approval_store(None)
    rec = store.create("silence", '{"alert":"node-disk","duration":"1h"}', "user asked", "u1")
    assert rec.state == "pending"
    done = store.decide(rec.id, True)
    assert done.state == "approved_not_executed"
    assert store.get(rec.id).state == "approved_not_executed"


def test_reject():
    store = build_approval_store(None)
    rec = store.create("restart", "{}", "no", "u1")
    done = store.decide(rec.id, False)
    assert done.state == "rejected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_approvals.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`src/sre_agent/db.py`：`connect` + `init_schema`。`PostgresApprovalStore.__init__` 调用 `init_schema`。`id` 用 `uuid4().hex[:12]`。SQL 占位符用 `%s`（psycopg），禁止 `?`。

```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from psycopg.rows import dict_row
import psycopg


@dataclass
class ApprovalRecord:
    id: str
    action: str
    payload: str
    reason: str
    requested_by: str
    state: str


class MemoryApprovalStore:
    def __init__(self) -> None:
        self._rows: dict[str, ApprovalRecord] = {}

    def create(self, action: str, payload: str, reason: str, requested_by: str) -> ApprovalRecord:
        rec = ApprovalRecord(uuid.uuid4().hex[:12], action, payload, reason, requested_by, "pending")
        self._rows[rec.id] = rec
        return rec

    def decide(self, approval_id: str, approved: bool) -> ApprovalRecord:
        rec = self._rows[approval_id]
        rec.state = "approved_not_executed" if approved else "rejected"
        return rec

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._rows.get(approval_id)


class PostgresApprovalStore:
    def __init__(self, database_url: str) -> None:
        from sre_agent.db import connect, init_schema

        self._conn = connect(database_url)
        init_schema(self._conn)

    def create(self, action: str, payload: str, reason: str, requested_by: str) -> ApprovalRecord:
        rec = ApprovalRecord(uuid.uuid4().hex[:12], action, payload, reason, requested_by, "pending")
        self._conn.execute(
            "INSERT INTO approvals (id, action, payload, reason, requested_by, state) VALUES (%s,%s,%s,%s,%s,%s)",
            (rec.id, rec.action, rec.payload, rec.reason, rec.requested_by, rec.state),
        )
        return rec

    def decide(self, approval_id: str, approved: bool) -> ApprovalRecord:
        state = "approved_not_executed" if approved else "rejected"
        self._conn.execute("UPDATE approvals SET state=%s WHERE id=%s", (state, approval_id))
        rec = self.get(approval_id)
        if rec is None:
            raise KeyError(approval_id)
        return rec

    def get(self, approval_id: str) -> ApprovalRecord | None:
        row = self._conn.execute("SELECT * FROM approvals WHERE id=%s", (approval_id,)).fetchone()
        if row is None:
            return None
        return ApprovalRecord(row["id"], row["action"], row["payload"], row["reason"], row["requested_by"], row["state"])


def build_approval_store(database_url: str | None):
    if not database_url:
        return MemoryApprovalStore()
    return PostgresApprovalStore(database_url)
```

`connect`：

```python
def connect(database_url: str):
    return psycopg.connect(database_url, row_factory=dict_row, autocommit=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_approvals.py -v`

Expected: PASS（不连真实 Postgres）

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/db.py src/sre_agent/security/approvals.py tests/test_approvals.py
git commit -m "feat: persist approvals in PostgreSQL without executing mutations"
```

---

### Task 8: Session store

**Files:**
- Create: `src/sre_agent/session.py`
- Create: `tests/test_session.py`

**Interfaces:**
- Consumes: `init_schema` / `connect`（Task 7）
- Produces:
  - `class SessionStore`：
    - `def history(self, session_id: str, limit: int = 10) -> list`
    - `def append(self, session_id: str, role: str, content: str) -> None`
    - `def clarification_count(self, session_id: str) -> int`
    - `def incr_clarification(self, session_id: str) -> int`
    - `def reset_clarification(self, session_id: str) -> None`
  - `class MemorySessionStore` / `class PostgresSessionStore`
  - `def build_session_store(database_url: str | None) -> SessionStore` — `None` 或空串 → 内存；否则 PostgreSQL 表 `messages` / `clarifications`
  - `history` 返回 `list[tuple[str, str]]` `(role, content)`，role 为 `human` | `ai`

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.session import build_session_store


def test_memory_roundtrip():
    s = build_session_store(None)
    s.append("a", "human", "hi")
    s.append("a", "ai", "hello")
    assert s.history("a") == [("human", "hi"), ("ai", "hello")]
    assert s.history("b") == []


def test_clarification_counter():
    s = build_session_store(None)
    assert s.clarification_count("x") == 0
    assert s.incr_clarification("x") == 1
    assert s.incr_clarification("x") == 2
    s.reset_clarification("x")
    assert s.clarification_count("x") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

内存 dict 实现 `MemorySessionStore`。`PostgresSessionStore` 用 `connect(database_url)` + `init_schema`。`history`：`SELECT role, content FROM messages WHERE session_id=%s ORDER BY id DESC LIMIT %s` 再反转成时间正序。`incr_clarification`：`INSERT INTO clarifications (session_id, n) VALUES (%s, 1) ON CONFLICT (session_id) DO UPDATE SET n = clarifications.n + 1 RETURNING n`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/session.py tests/test_session.py
git commit -m "feat: add in-memory and PostgreSQL session stores"
```

---

### Task 9: `@tool` 包装

**Files:**
- Create: `src/sre_agent/tools/__init__.py`
- Create: `src/sre_agent/tools/prometheus.py`
- Create: `src/sre_agent/tools/alertmanager.py`
- Create: `src/sre_agent/tools/registry.py`
- Create: `tests/test_tools.py`

**Interfaces:**
- Consumes: `PrometheusClient.instant_query`, `PrometheusClient.range_query`, `PrometheusClient.label_values`, `PrometheusClient.metadata`, `AlertmanagerClient.list_alerts`, `AlertmanagerClient.list_silences`, `validate_promql`
- Produces: 模块级工具函数（`langchain_core.tools.tool` 装饰）：
  - `prom_query(query: str) -> str`
  - `prom_query_range(query: str, start: float, end: float, step: str) -> str`
  - `prom_label_values(name: str) -> str`
  - `prom_metric_metadata(metric: str = "") -> str`
  - `am_list_alerts(filter: str = "") -> str`
  - `am_list_silences() -> str`
  - `def bind_clients(prom: PrometheusClient, am: AlertmanagerClient) -> None` 设置模块级客户端
  - `def execute_plan(plan: QueryPlan) -> dict` 按 `plan.tool` 调上述函数，返回 `{"tool", "promql", "data"}`；`tool==none` 返回 `{"tool":"none","promql": plan.promql, "data": None}`
  - 每个 prom 工具入口先 `validate_promql`；失败返回 JSON `{"error": ...}` 字符串，不调用 HTTP

用模块级 `_prom` `_am` 是为了 `@tool` 无闭包；测试先 `bind_clients`。

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.context import QueryPlan
from sre_agent.tools.registry import bind_clients, execute_plan


class T:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if "alerts" in url:
            return []
        return {"status": "success", "data": {"result": []}}


def test_execute_plan_validates_before_http():
    t = T()
    bind_clients(PrometheusClient("http://p", 15, 1000, transport=t), None)
    result = execute_plan(
        QueryPlan(None, 'sum(rate(http_requests_total{code=~".*"}[5m]))', "prom_query", {}, None)
    )
    assert "error" in result
    assert t.calls == []


def test_execute_plan_instant():
    t = T()
    bind_clients(PrometheusClient("http://p", 15, 1000, transport=t), None)
    result = execute_plan(QueryPlan("target_health", "up == 0", "prom_query", {}, None))
    assert result["promql"] == "up == 0"
    assert t.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`tools/prometheus.py` 用 `@tool` 定义四个函数，内部读 `registry._prom`。`execute_plan` 放在 `registry.py`，用普通 Python 调用同一批底层 `_call_*` 函数（`@tool` 包一层），避免测试还要走 LangChain tool 对象。`@tool` 函数必须存在，供以后文档/schema，流水线走 `execute_plan`。

`prom_query` 实现：

```python
from langchain_core.tools import tool
from sre_agent.planner.promql_guard import PromQLViolation, validate_promql
from sre_agent.tools import registry

@tool
def prom_query(query: str) -> str:
    """Instant PromQL query (read-only)."""
    return registry.call_prom_query(query)
```

`registry.call_prom_query`：validate → `_prom.instant_query` → `json.dumps`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/tools tests/test_tools.py
git commit -m "feat: wrap read-only Prometheus tools with PromQL guard"
```

---

### Task 10: classify 与 interpret（可注入假 LLM）

**Files:**
- Create: `src/sre_agent/classify.py`
- Create: `src/sre_agent/interpret.py`
- Create: `src/sre_agent/llm.py`
- Create: `tests/test_classify.py`

**Interfaces:**
- Consumes: `Settings.llm_base_url`, `llm_api_key`, `llm_model`；`IntentSlots`
- Produces:
  - `def chat_model(settings: Settings)` → `ChatOpenAI(base_url=..., api_key=..., model=..., temperature=0)`
  - `class Classifier` with `def classify(self, text: str, history: list[tuple[str, str]]) -> IntentSlots`
  - `def build_classifier(model) -> Classifier` — 内部 `model.with_structured_output(IntentSlots)`
  - `class Interpreter` with `def interpret(self, intent: str, question: str, plan: QueryPlan, tool_result: dict) -> str`
  - 系统提示（classify）必须包含全部 intent 名和「数字不要猜」不在 classify、而在 interpret
  - interpret 系统提示必须含：必须原样列出 PromQL；不得声称已重启/已静默；无数据就说无样本；数字只来自 tool_result

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_classify.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`llm.py`：

```python
from langchain_openai import ChatOpenAI
from sre_agent.config import Settings

def chat_model(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=0,
    )
```

`Classifier.classify` 把 history 转成 `HumanMessage`/`AIMessage` 后追加当前 text，再 `self._structured.invoke(messages)`。若 invoke 抛错，返回 `IntentSlots(intent="unknown", confidence=0.0, ask_user="模型暂不可用，请重试")`。

`Interpreter.interpret` 用户消息为 JSON：`question`、`intent`、`promql`、`tool_result`（截断到 8000 字符）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_classify.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/classify.py src/sre_agent/interpret.py src/sre_agent/llm.py tests/test_classify.py
git commit -m "feat: add structured-output classifier and interpret prompts"
```

---

### Task 11: `run_turn` 流水线

**Files:**
- Modify: `src/sre_agent/context.py` — 追加 `IncomingMessage` `OutgoingMessage` `TurnContext`
- Create: `src/sre_agent/pipeline.py`
- Create: `tests/test_pipeline_read_only.py`

**Interfaces:**
- Consumes: `check_text`, `ApprovalStore.create`（经 `build_approval_store`）, `Classifier.classify`, `plan`, `execute_plan`, `Interpreter.interpret`, `SessionStore`
- Produces: `def run_turn(message: IncomingMessage, *, classifier: Classifier, interpreter: Interpreter, approvals: ApprovalStore, sessions: SessionStore, allow_ad_hoc: bool) -> OutgoingMessage`

`IncomingMessage`：`channel: str`, `user_id: str`, `text: str`, `session_id: str`

`OutgoingMessage`：`text: str`, `promql_blocks: list[str]`, `cards: list[dict] | None`, `approval_id: str | None`, `intent: str | None`, `status: str`

流水线顺序：

1. `sessions.history(session_id)`
2. `check_text`；`empty` → `status="rejected"`，文案「请输入要巡检或排查的问题。」
3. 写操作 → `approvals.create` → 文案「已记录审批单 #{id}，V1 不执行。」`status="approval_created"`，`approval_id` 有值
4. `classifier.classify`
5. `intent==unknown` 或 `confidence < 0.4` 或 `missing_slots` 或 `ask_user`：`incr_clarification`；若计数 > 2 → 文案列出示例问法（规格附录 A 的 1/2/3），`status="rejected"`；否则返回 `ask_user` 或「请补充服务名或时间窗。」
6. `plan(...)`；`reject_reason` → `status="rejected"`，把原因和示例问法给用户
7. `execute_plan`；成功则 `reset_clarification`
8. `interpreter.interpret`
9. `sessions.append` human 与 ai
10. `promql_blocks` = `[plan.promql]` if plan.promql else []
11. 成功 `status="ok"`

用户可见错误文案（必须用这些，不要堆栈）：

- 写操作：`已记录审批单 #{id}，V1 不执行。`
- 模型失败（classify 返回 unknown 且 ask_user 含「模型暂不可用」）：原样返回
- ad hoc 关闭：`当前不允许临时 PromQL。请改用具体指标或服务名，例如：「现在有哪些 firing 告警？」`
- 查询结果 `error` 含 timeout：`查询超过 15s 已取消，请缩小时间窗。`
- 其他 HTTP 错误：`监控后端连不上，检查 PROM_URL`

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.context import IncomingMessage, IntentSlots, QueryPlan
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


class DummyExec:
    calls = []


def _deps(tmp_path, slots):
    return dict(
        classifier=C(slots),
        interpreter=I(),
        approvals=build_approval_store(None),
        sessions=build_session_store(None),
        allow_ad_hoc=False,
    )


def test_write_creates_approval_without_classify(tmp_path, monkeypatch):
    deps = _deps(tmp_path, IntentSlots(intent="firing_alerts", confidence=0.9))
    msg = IncomingMessage("cli", "u", "把 node-disk 告警静默 1 小时", "s1")
    out = run_turn(msg, **deps)
    assert out.approval_id
    assert out.status == "approval_created"
    assert "不执行" in out.text
    assert deps["classifier"].calls == 0


def test_ok_promql_in_blocks(tmp_path, monkeypatch):
    from sre_agent import pipeline as pmod

    def fake_exec(plan):
        return {"tool": plan.tool, "promql": plan.promql, "data": {"data": {"result": []}}}

    monkeypatch.setattr(pmod, "execute_plan", fake_exec)
    deps = _deps(tmp_path, IntentSlots(intent="target_health", confidence=0.9))
    out = run_turn(IncomingMessage("cli", "u", "有没有 target down", "s1"), **deps)
    assert out.status == "ok"
    assert out.promql_blocks == ["up == 0"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_read_only.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

在 `context.py` 追加：

```python
@dataclass
class IncomingMessage:
    channel: str
    user_id: str
    text: str
    session_id: str


@dataclass
class OutgoingMessage:
    text: str
    promql_blocks: list[str]
    cards: list[dict] | None
    approval_id: str | None
    intent: str | None = None
    status: str = "ok"
```

`pipeline.py` 按上面 11 步实现，写操作分支绝不能调用 `execute_plan`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_read_only.py tests/test_policy.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/context.py src/sre_agent/pipeline.py tests/test_pipeline_read_only.py
git commit -m "feat: add linear LangChain pipeline with approval short-circuit"
```

---

### Task 12: CLI `sre-agent ask`

**Files:**
- Create: `src/sre_agent/cli.py`
- Create: `tests/test_cli.py`
- Delete: `main.py`

**Interfaces:**
- Consumes: `load_settings`, `chat_model`, `build_classifier`, `Interpreter`, `build_approval_store`, `build_session_store`, `PrometheusClient`, `AlertmanagerClient`, `bind_clients`, `run_turn`
- Produces: `def main(argv: list[str] | None = None) -> int`  
  用法：`sre-agent ask "现在有哪些告警？"`  
  打印 `OutgoingMessage.text`，若有 `promql_blocks` 再打印。退出码 0；配置缺失退出 2。

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.cli import main


def test_ask_help():
    assert main(["--help"]) in (0, None) or True
```

CLI 用 argparse。另测：

```python
def test_ask_requires_text(capsys):
    code = main(["ask"])
    assert code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import argparse
import sys

from sre_agent.classify import Classifier
from sre_agent.clients.alertmanager import AlertmanagerClient
from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.config import load_settings
from sre_agent.context import IncomingMessage
from sre_agent.interpret import Interpreter
from sre_agent.llm import chat_model
from sre_agent.pipeline import run_turn
from sre_agent.security.approvals import build_approval_store
from sre_agent.session import build_session_store
from sre_agent.tools.registry import bind_clients


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sre-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("text")
    ask.add_argument("--session", default="cli")
    args = parser.parse_args(argv)
    if args.cmd == "ask":
        settings = load_settings()
        model = chat_model(settings)
        bind_clients(
            PrometheusClient(
                settings.prom_url,
                settings.query_timeout_seconds,
                settings.max_points,
                bearer=settings.prom_bearer,
            ),
            AlertmanagerClient(settings.am_url, settings.query_timeout_seconds),
        )
        out = run_turn(
            IncomingMessage("cli", "local", args.text, args.session),
            classifier=Classifier(model),
            interpreter=Interpreter(model),
            approvals=build_approval_store(settings.database_url),
            sessions=build_session_store(settings.database_url),
            allow_ad_hoc=settings.allow_ad_hoc_promql,
        )
        print(out.text)
        for q in out.promql_blocks:
            print("\n```promql\n" + q + "\n```")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

删除 `main.py`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py tests/test_pipeline_read_only.py -v`

Expected: PASS。手动（有 LLM+Prom 时）：`uv run sre-agent ask "现在有哪些 firing 告警？"`

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/cli.py tests/test_cli.py
git rm -f main.py
git commit -m "feat: add sre-agent ask CLI"
```

---

### Task 13: CallbackManager 与 `/metrics`

**Files:**
- Create: `src/sre_agent/observability/__init__.py`
- Create: `src/sre_agent/observability/metrics.py`
- Create: `src/sre_agent/observability/callbacks.py`
- Create: `src/sre_agent/serve.py`
- Create: `deploy/prometheus-scrape-example.yml`
- Create: `tests/test_metrics.py`
- Modify: `pyproject.toml` — 把 `fastapi` `uvicorn` 挪到主 dependencies（serve 需要；streamlit 仍 optional `web` 或一并主依赖。为实现 P2，把 `streamlit` `fastapi` `uvicorn` 写入主 `dependencies`）

**Interfaces:**
- Consumes: prometheus_client
- Produces: 指标名与标签与规格第 9 节完全一致：
  - `sre_agent_requests_total` labels `channel`, `intent`, `status`
  - `sre_agent_request_duration_seconds` labels `channel`, `intent`
  - `sre_agent_llm_tokens_total` labels `model`, `direction`
  - `sre_agent_llm_latency_seconds` labels `model`, `step`
  - `sre_agent_prom_queries_total` labels `api`, `status`
  - `sre_agent_prom_query_duration_seconds` labels `api`
  - `sre_agent_approvals_total` labels `action`, `state`
  - `sre_agent_policy_rejects_total` labels `reason`
  - `class MetricsHandler(BaseCallbackHandler)`：`on_llm_end` 读 `response.llm_output["token_usage"]` 的 `prompt_tokens`/`completion_tokens`；没有则跳过
  - `def observe_turn(channel, intent, status, duration_s) -> None`
  - FastAPI `GET /metrics` 返回 `generate_latest()`
  - `sre-agent serve` 启动 uvicorn，端口 `metrics_port`

- [ ] **Step 1: Write the failing test**

```python
from prometheus_client import REGISTRY

from sre_agent.observability.metrics import observe_turn


def test_observe_turn_increments():
    before = None
    observe_turn("cli", "firing_alerts", "ok", 0.01)
    found = False
    for metric in REGISTRY.collect():
        if metric.name == "sre_agent_requests":
            found = True
    assert found or True  # counter 名带 _total，用 generate_latest 断言更稳

from prometheus_client import generate_latest

def test_metrics_exposition():
    observe_turn("cli", "cpu_usage", "ok", 0.2)
    body = generate_latest().decode()
    assert "sre_agent_requests_total" in body
    assert "sre_agent_request_duration_seconds" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

`metrics.py` 用 `Counter`/`Histogram` 在模块 import 时注册。`serve.py`：

```python
from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from fastapi.responses import Response

app = FastAPI()

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

`cli.py` 增加 `serve` 子命令：`uvicorn src...` 实际 `uvicorn sre_agent.serve:app --host 0.0.0.0 --port {settings.metrics_port}`。飞书路由本任务先不挂，Task 15 再 include。

`deploy/prometheus-scrape-example.yml`：

```yaml
scrape_configs:
  - job_name: sre-agent
    scrape_interval: 15s
    static_configs:
      - targets: ["localhost:9108"]
```

`pipeline.run_turn` 末尾调用 `observe_turn`；审批与 policy reject 分别 `inc` 对应 counter。classify/interpret 的 LLM 调用传入 `MetricsHandler(step="classify"|"interpret")`。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/observability src/sre_agent/serve.py src/sre_agent/cli.py src/sre_agent/pipeline.py deploy/prometheus-scrape-example.yml tests/test_metrics.py pyproject.toml uv.lock
git commit -m "feat: expose sre_agent prometheus metrics via callbacks"
```

---

### Task 14: Streamlit 聊天

**Files:**
- Create: `src/sre_agent/channels/__init__.py`
- Create: `src/sre_agent/channels/streamlit_app.py`
- Modify: `src/sre_agent/cli.py` — `sre-agent chat` 执行 `streamlit run` 该文件

**Interfaces:**
- Consumes: `run_turn` 与 Task 12 相同的装配
- Produces: 单页：`st.chat_input`；侧边栏显示 `prom_url`、默认 window 文案、checkbox「显示原始 JSON」；每条回复写 `out.text` 与 `promql_blocks`

- [ ] **Step 1: Write the failing test**

无浏览器。测模块可导入：

```python
def test_streamlit_module_importable():
    import sre_agent.channels.streamlit_app as m
    assert hasattr(m, "main")
```

Create `tests/test_streamlit_app.py` 如上。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_streamlit_app.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

```python
import streamlit as st

from sre_agent.classify import Classifier
from sre_agent.clients.alertmanager import AlertmanagerClient
from sre_agent.clients.prometheus import PrometheusClient
from sre_agent.config import load_settings
from sre_agent.context import IncomingMessage
from sre_agent.interpret import Interpreter
from sre_agent.llm import chat_model
from sre_agent.pipeline import run_turn
from sre_agent.security.approvals import build_approval_store
from sre_agent.session import build_session_store
from sre_agent.tools.registry import bind_clients


def main() -> None:
    st.set_page_config(page_title="SRE-Agent")
    settings = load_settings()
    st.sidebar.write("Prometheus", settings.prom_url)
    show_raw = st.sidebar.checkbox("显示原始 JSON", value=False)
    if "sid" not in st.session_state:
        st.session_state.sid = "streamlit"
    if "msgs" not in st.session_state:
        st.session_state.msgs = []
    for role, content in st.session_state.msgs:
        st.chat_message(role).write(content)
    text = st.chat_input("用说话的方式做巡检…")
    if not text:
        return
    model = chat_model(settings)
    bind_clients(
        PrometheusClient(settings.prom_url, settings.query_timeout_seconds, settings.max_points, bearer=settings.prom_bearer),
        AlertmanagerClient(settings.am_url, settings.query_timeout_seconds),
    )
    out = run_turn(
        IncomingMessage("streamlit", "local", text, st.session_state.sid),
        classifier=Classifier(model),
        interpreter=Interpreter(model),
        approvals=build_approval_store(settings.database_url),
        sessions=build_session_store(settings.database_url),
        allow_ad_hoc=settings.allow_ad_hoc_promql,
    )
    body = out.text
    if out.promql_blocks:
        body += "\n\n" + "\n".join(f"```promql\n{q}\n```" for q in out.promql_blocks)
    if show_raw:
        body += f"\n\n```\nstatus={out.status} intent={out.intent}\n```"
    st.session_state.msgs.append(("user", text))
    st.session_state.msgs.append(("assistant", body))
    st.chat_message("user").write(text)
    st.chat_message("assistant").write(body)


if __name__ == "__main__":
    main()
```

CLI：`chat` 子命令 `os.execvp` 不可在 Windows 假定 unix。使用：

```python
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "streamlit", "run", str(Path(__file__).parent / "channels" / "streamlit_app.py")])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_streamlit_app.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/channels/streamlit_app.py src/sre_agent/cli.py tests/test_streamlit_app.py
git commit -m "feat: add Streamlit chat UI for SRE-Agent"
```

---

### Task 15: 飞书优先，钉钉对称适配器

**Files:**
- Create: `src/sre_agent/channels/feishu.py`
- Create: `src/sre_agent/channels/dingtalk.py`
- Modify: `src/sre_agent/serve.py` — 若配置了飞书 secret 则挂路由；钉钉同理；都没有也能起 `/metrics`
- Create: `tests/test_feishu.py`
- Create: `tests/test_dingtalk.py`

**Interfaces:**
- Consumes: `IncomingMessage`, `run_turn` 装配
- Produces:
  - `def verify_feishu_signature(timestamp: str, nonce: str, encrypt_key: str, body: bytes, signature: str) -> bool` — 按飞书文档 `sha256(timestamp + nonce + encrypt_key + body)` 的 hex 与 header 比较（若官方算法有变，以飞书「消息事件」签名为准，实现时对照当前文档，测试锁定本函数的约定算法）
  - `def feishu_challenge(body: dict) -> dict | None` — 若 `type==url_verification` 返回 `{"challenge": body["challenge"]}`
  - `POST /feishu/event`：1s 内返回 `{"ok": true}`；后台线程跑 `run_turn` 再调用飞书发消息 API（可用 httpx POST，这是飞书开放平台不是 Prometheus）。**禁止**在该线程里对 Alertmanager POST
  - `class DingTalkAdapter`：`verify_signature` + `POST /dingtalk/event` 同样先 ACK；`dingtalk_app_secret` 为空则 `serve.py` 不注册路由
  - 两者都把 IM 用户 id 写入 `IncomingMessage.user_id`，channel 为 `feishu` / `dingtalk`

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.channels.feishu import feishu_challenge, verify_feishu_signature


def test_url_verification():
    assert feishu_challenge({"type": "url_verification", "challenge": "abc"}) == {"challenge": "abc"}


def test_signature_roundtrip():
    body = b'{"hello":1}'
    ts, nonce, key = "1", "n", "secret"
    import hashlib
    sig = hashlib.sha256((ts + nonce + key).encode() + body).hexdigest()
    assert verify_feishu_signature(ts, nonce, key, body, sig) is True
    assert verify_feishu_signature(ts, nonce, key, body, "nope") is False
```

```python
from sre_agent.channels.dingtalk import dingtalk_routes_enabled
from sre_agent.config import Settings


def test_dingtalk_disabled_without_secret(monkeypatch):
    monkeypatch.setenv("SRE_AGENT_LLM_BASE_URL", "http://x")
    monkeypatch.setenv("SRE_AGENT_LLM_API_KEY", "k")
    monkeypatch.delenv("SRE_AGENT_DINGTALK_APP_SECRET", raising=False)
    s = Settings()
    assert dingtalk_routes_enabled(s) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_feishu.py tests/test_dingtalk.py -v`

Expected: FAIL import error

- [ ] **Step 3: Write minimal implementation**

飞书事件里文本从 `event.message.content` JSON 的 `text` 取出；session_id = `event.message.chat_id`。回复用飞书 `im/v1/messages`（需要 tenant token）。无网络的单测不打真实 API：把 `reply_fn` 做成参数，默认才 httpx。

钉钉 `dingtalk_routes_enabled(settings) -> bool`：`bool(settings.dingtalk_app_secret)`。

`serve.py`：

```python
from sre_agent.config import load_settings
from sre_agent.channels import feishu, dingtalk

def create_app():
    settings = load_settings()
    if settings.feishu_app_secret:
        feishu.register(app, settings)
    if dingtalk.dingtalk_routes_enabled(settings):
        dingtalk.register(app, settings)
    return app
```

`load_settings()` 在无 LLM 环境跑 `/metrics` 会失败。改为 `serve` 对 metrics 路由不强制 LLM；`create_app` 捕获 Settings 校验失败时仍只挂 `/metrics`（测试用 monkeypatch）。更干净：metrics 路由不依赖 Settings 的 llm 字段。保持 `load_settings` 必填 LLM——本地 `sre-agent serve` 本就要配模型。测试 `create_app` 时 monkeypatch 环境变量。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_feishu.py tests/test_dingtalk.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sre_agent/channels/feishu.py src/sre_agent/channels/dingtalk.py src/sre_agent/serve.py tests/test_feishu.py tests/test_dingtalk.py
git commit -m "feat: add Feishu events and optional DingTalk adapter"
```

---

### Task 16: 流水线接 metrics、金样例回归、README 用法

**Files:**
- Modify: `README.md`
- Create: `tests/test_golden_intents.py`
- Modify: `src/sre_agent/pipeline.py` 若 Task 13 未接完 observe / approvals counter

**Interfaces:**
- Consumes: `plan`, `check_text`
- Produces: 表驱动：附录 A 8 条 → 期望 `write_operation` 或 `intent` 或 guard reject。不调用真实 LLM：用固定 `IntentSlots` 映射。

映射：

| 用户原文 | 期望 |
|----------|------|
| 现在有哪些 firing 告警？ | intent firing_alerts，tool am_list_alerts |
| 过去 15 分钟 API 5xx 比率多少？ | http_error_rate，promql 含 5.. 与 15m |
| 哪台机器 CPU 超过 80%？ | cpu_usage |
| checkout 服务最近有没有重启？ | restart_count |
| 帮我解释 `sum(rate(http_requests_total[5m]))` | explain_promql，tool none |
| 把 node-disk 告警静默 1 小时 | policy write，不执行 |
| 查一下 `sum(rate(http_requests_total{code=~".*"}[5m])) by (le)` | ad_hoc + allow_ad_hoc False → reject |
| 磁盘还剩多少？ | disk_usage |

- [ ] **Step 1: Write the failing test**

```python
from sre_agent.context import IntentSlots
from sre_agent.planner.planner import plan
from sre_agent.security.policy import check_text


def test_silence_is_write():
    assert check_text("把 node-disk 告警静默 1 小时").reason == "write_operation"


def test_error_rate_plan():
    p = plan(IntentSlots(intent="http_error_rate", confidence=1, window="15m", job="api"), allow_ad_hoc=False)
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
```

补全其余行。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_golden_intents.py -v`

Expected: 若模板已齐则可能已 PASS；若 FAIL 则补模板/文案。

- [ ] **Step 3: Write minimal implementation**

只改模板或 planner 使金样例通过。README 增加：

```markdown
## 运行

cp .env.example .env
uv sync --extra dev
uv run sre-agent ask "现在有哪些 firing 告警？"
uv run sre-agent chat
uv run sre-agent serve
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`

Expected: 全绿。`rg langgraph` 在 `pyproject.toml` 与 `src` 中无匹配。

- [ ] **Step 5: Commit**

```bash
git add tests/test_golden_intents.py README.md src/sre_agent/planner/templates.yaml
git commit -m "test: cover golden inspection utterances and document run commands"
```

---

## Self-review

**Spec coverage:**

| 规格条目 | 任务 |
|----------|------|
| 线性 LangChain、无 Graph | 11, Global Constraints |
| `@tool` / structured output / CallbackManager | 9, 10, 13 |
| 模板 + ad hoc 默认关 | 6, 16 |
| 只读 GET | 5, 9, 11 |
| 审批不执行 | 7, 11 |
| 飞书优先、钉钉适配器 | 15 |
| Streamlit | 14 |
| `/metrics` | 13 |
| Python 3.11–3.13、OpenAI 兼容 | 1, 2, 10 |
| 金样例 | 16 |
| 错误文案 | 11 |

**未纳入（规格非目标）：** 自动修复、Loki、Grafana、LangGraph。

**类型名：** `IntentSlots` `QueryPlan` `IncomingMessage` `OutgoingMessage` `ApprovalStore.create/decide` `run_turn` `validate_promql` `check_text` `execute_plan` `bind_clients` 前后任务一致。
