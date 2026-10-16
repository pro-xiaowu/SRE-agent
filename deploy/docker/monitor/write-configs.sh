#!/usr/bin/env bash
# 在监控机、本目录执行：bash write-configs.sh
# 作用：用 heredoc 写出 Prometheus / Alertmanager / Grafana 配置（与仓库文件一致）
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p prometheus alertmanager grafana/provisioning/datasources

cat > prometheus/prometheus.yml <<"EOF"
# 全局配置
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
    scrape_interval: 15s
    file_sd_configs:
      - files:
          - /etc/prometheus/sre-agent-targets.yml
        refresh_interval: 30s
EOF

cat > prometheus/alerts.yml <<"EOF"
groups:
  - name: sre-agent-demo
    rules:
      - alert: SreAgentDemoFiring
        expr: up{job="prometheus"} == 1
        for: 10s
        labels:
          severity: info
          service: prometheus
        annotations:
          summary: "演示告警：Prometheus 在线（给 SRE-Agent 列表用）"
EOF

# 把 10.0.0.20 改成【应用机】内网 IP
cat > prometheus/sre-agent-targets.yml <<"EOF"
- targets:
    - "10.0.0.20:9108"
EOF

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

cat > grafana/config.monitoring <<"EOF"
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin
GF_USERS_ALLOW_SIGN_UP=false
EOF

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

echo "写完。请编辑 prometheus/sre-agent-targets.yml 为应用机 IP，然后：docker compose up -d"
