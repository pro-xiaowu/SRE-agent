# 两台 Linux：监控机 ≠ 应用机

```
监控机（monitor）                    应用机（app）
┌─────────────────────────┐         ┌─────────────────────────┐
│ Prometheus    :9090     │◄─查询───│ uv: sre-agent           │
│ Alertmanager  :9093     │         │ Docker: PostgreSQL      │
│ Grafana       :3000     │──抓取──►│ /metrics :9108          │
│ node-exporter / cAdvisor│         │                         │
└─────────────────────────┘         └─────────────────────────┘
```

Grafana **只给人看图**，Agent 不读它。默认登录 `admin` / `password`（`grafana/config.monitoring`）。

两边都要能走内网 TCP：

| 方向 | 端口 | 目的 |
|------|------|------|
| App → Monitor | 9090 | Agent 查 PromQL |
| App → Monitor | 9093 | Agent 查告警 |
| Monitor → App | 9108 | Prometheus 抓 Agent 自身指标 |

不要把 5432 / 9090 / 9093 / 9108 / 3000 对公网开放。

**红帽 RHEL：** 安装、firewalld、SELinux 见 [`RHEL.md`](RHEL.md)。监控机 `192.168.100.30` `/opt/monitor`，应用机 `192.168.100.31`。不要用 `apt` / `ufw`。

---

## 监控机配置（可直接 `cat` 粘贴）

仓库里已经有这些文件。若要自己生成，在 `deploy/docker/monitor` 执行：

```bash
bash write-configs.sh
```

或逐个粘贴（YAML **必须缩进**，不能像纯文本左对齐）：

```bash
cd deploy/docker/monitor
mkdir -p prometheus alertmanager grafana/provisioning/datasources
```

**Grafana 登录：**

```bash
cat > grafana/config.monitoring <<"EOF"
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin
GF_USERS_ALLOW_SIGN_UP=false
EOF
```

**Grafana 自动接 Prometheus（不用在 UI 里手加数据源）：**

```bash
cat > grafana/provisioning/datasources/datasource.yml <<"EOF"
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
EOF
```

**Prometheus：**

```bash
cat > prometheus/prometheus.yml <<"EOF"
global:
  scrape_interval: 15s
  evaluation_interval: 15s
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]
rule_files:
  - /etc/prometheus/alerts.yml
scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]
  - job_name: alertmanager
    static_configs:
      - targets: ["alertmanager:9093"]
  - job_name: cadvisor
    static_configs:
      - targets: ["cadvisor:8080"]
        labels:
          instance: monitor
  - job_name: node-exporter
    static_configs:
      - targets: ["node-exporter:9100"]
        labels:
          instance: monitor
  - job_name: sre-agent
    file_sd_configs:
      - files:
          - /etc/prometheus/sre-agent-targets.yml
        refresh_interval: 30s
EOF
```

**抓应用机 Agent（改成你的应用机 IP）：**

```bash
cat > prometheus/sre-agent-targets.yml <<"EOF"
- targets:
    - "10.0.0.20:9108"
EOF
```

**Alertmanager（给 Agent 查告警够用；发邮件不是 Agent 需要的）：**

```bash
cat > alertmanager/alertmanager.yml <<"EOF"
global:
  resolve_timeout: 5m
route:
  group_by: ["alertname"]
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 10m
  receiver: "null"
receivers:
  - name: "null"
inhibit_rules: []
EOF
```

然后：`docker compose up -d`

浏览器：Prometheus `http://监控机:9090` ，Grafana `http://监控机:3000` （admin/admin）。

---

## 0. 两边都装 Docker

Ubuntu / Debian：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
# 重新登录后再用 docker
```

下面把 IP 换成你的：

```text
MONITOR_IP=10.0.0.10    # 监控机内网
APP_IP=10.0.0.20        # 应用机内网
```

---

## 1. 监控机：Prometheus + Alertmanager

把仓库拷到监控机后：

```bash
# 填写应用机 IP（Prometheus 要来抓 :9108）
nano deploy/docker/monitor/prometheus/sre-agent-targets.yml
```

内容示例：

```yaml
- targets:
    - "10.0.0.20:9108"
```

启动：

```bash
cd deploy/docker/monitor
docker compose up -d
docker compose ps
```

本机检查：

```bash
curl -sS http://127.0.0.1:9090/-/ready
curl -sS http://127.0.0.1:9093/-/ready
# Grafana：浏览器 http://监控机:3000  用户 admin 密码 password
```

防火墙只放行应用机：

```bash
sudo ufw allow from 10.0.0.20 to any port 9090 proto tcp
sudo ufw allow from 10.0.0.20 to any port 9093 proto tcp
sudo ufw deny 9090
sudo ufw deny 9093
# 若未开 ufw，用安全组：入站 9090/9093 源 = APP_IP
```

---

## 2. 应用机：PostgreSQL + Agent

```bash
cd deploy/docker/app
docker compose up -d
docker exec sre-postgres pg_isready -U sre_agent -d sre_agent
```

仓库根目录 `.env`（可参考 `deploy/docker/app/.env.example`）：

```bash
SRE_AGENT_PROM_URL=http://10.0.0.10:9090
SRE_AGENT_AM_URL=http://10.0.0.10:9093
SRE_AGENT_DATABASE_URL=postgresql://sre_agent:sre_agent@127.0.0.1:5432/sre_agent
SRE_AGENT_METRICS_PORT=9108
# 再加上 LLM_BASE_URL / LLM_API_KEY
```

防火墙只让监控机抓 metrics：

```bash
sudo ufw allow from 10.0.0.10 to any port 9108 proto tcp
```

跑 Agent：

```bash
cd /path/to/SRE-agent
uv sync --extra dev
uv run sre-agent serve          # 后台提供 /metrics，给监控机抓
uv run sre-agent ask "现在有哪些 firing 告警？"
```

`serve` 监听 `0.0.0.0:9108`，这样监控机才能抓到；靠防火墙限制来源。

连通性（在**应用机**上测监控是否可达）：

```bash
curl -sS http://10.0.0.10:9090/-/ready
curl -sS http://10.0.0.10:9093/-/ready
curl -sS 'http://10.0.0.10:9090/api/v1/query?query=up'
```

在**监控机**上测能否抓到 Agent：

```bash
curl -sS http://10.0.0.20:9108/metrics | head
```

---

## 3. 停服务

监控机：

```bash
cd deploy/docker/monitor
docker compose down        # 保留数据卷
docker compose down -v     # 连指标数据一起删
```

应用机：

```bash
cd deploy/docker/app
docker compose down
docker compose down -v     # 连 Postgres 数据一起删
```

---

## 4. 注意

- 演示告警 `SreAgentDemoFiring` 在监控机 Prometheus 在线时会 firing，用来测「现在有哪些告警」。
- CPU/内存模板需要 node-exporter 等，本 compose 没装；问 CPU 可能「无样本」。
- 生产已有 Prometheus 时：**不要用 monitor 这套**，应用机 `.env` 直接填现有 Prom/AM 地址即可，只需 `app` 的 Postgres。
