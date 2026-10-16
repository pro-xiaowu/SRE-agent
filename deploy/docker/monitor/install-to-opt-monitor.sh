#!/usr/bin/env bash
# 在监控机执行（目录必须是 /opt/monitor）：
#   bash install-to-opt-monitor.sh
# 或把本脚本内容整段粘贴到 [root@monitor monitor]# 下。
set -euo pipefail
cd /opt/monitor

mkdir -p prometheus alertmanager grafana/provisioning/datasources

cat > docker-compose.yml <<'EOF'
volumes:
  prometheus_data: {}
  grafana_data: {}
  alertmanager_data: {}

networks:
  monitoring:
    driver: bridge

services:
  prometheus:
    image: prom/prometheus:v3.9.1
    container_name: prometheus
    restart: always
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./prometheus/:/etc/prometheus/
      - prometheus_data:/prometheus
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.path=/prometheus
      - --web.console.libraries=/usr/share/prometheus/console_libraries
      - --web.console.templates=/usr/share/prometheus/consoles
      - --web.enable-lifecycle
      - --storage.tsdb.retention.time=30d
    networks:
      - monitoring
    expose:
      - "9090"
    ports:
      - "9090:9090"
    depends_on:
      - alertmanager
      - node_exporter

  alertmanager:
    image: prom/alertmanager:v0.31.1
    container_name: alertmanager
    restart: always
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./alertmanager/:/etc/alertmanager/
      - alertmanager_data:/alertmanager
    command:
      - --config.file=/etc/alertmanager/config.yml
      - --storage.path=/alertmanager
    networks:
      - monitoring
    expose:
      - "9093"
    ports:
      - "9093:9093"

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:v0.47.2
    container_name: cadvisor
    restart: unless-stopped
    privileged: true
    devices:
      - /dev/kmsg:/dev/kmsg
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker:/var/lib/docker:ro
      - /dev/disk:/dev/disk:ro
    networks:
      - monitoring
    expose:
      - "8080"

  node_exporter:
    image: prom/node-exporter:v1.10.2
    container_name: node-exporter
    restart: always
    pid: host
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - --path.procfs=/host/proc
      - --path.sysfs=/host/sys
      - --collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc|rootfs/var/lib/docker)($$|/)
    networks:
      - monitoring
    expose:
      - "9100"
    ports:
      - "9100:9100"

  grafana:
    image: grafana/grafana:12.4.0
    container_name: grafana
    restart: always
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning/:/etc/grafana/provisioning/
    env_file:
      - ./grafana/config.monitoring
    networks:
      - monitoring
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
EOF

cat > prometheus/prometheus.yml <<'EOF'
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
          instance: Prometheus服务器

  - job_name: node-exporter
    static_configs:
      - targets: ["node_exporter:9100"]
        labels:
          instance: Prometheus服务器

  - job_name: sre-agent
    scrape_interval: 15s
    file_sd_configs:
      - files:
          - /etc/prometheus/sre-agent-targets.yml
        refresh_interval: 30s
EOF

cat > prometheus/alerts.yml <<'EOF'
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

cat > prometheus/sre-agent-targets.yml <<'EOF'
- targets:
    - "192.168.100.31:9108"
EOF

cat > alertmanager/config.yml <<'EOF'
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

cat > grafana/config.monitoring <<'EOF'
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=password
GF_USERS_ALLOW_SIGN_UP=false
EOF

cat > grafana/provisioning/datasources/datasource.yml <<'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
EOF

echo "已写入 /opt/monitor"
echo "下一步: 编辑 prometheus/sre-agent-targets.yml 为应用机IP，然后 docker compose up -d"
ls -l /opt/monitor /opt/monitor/prometheus /opt/monitor/alertmanager /opt/monitor/grafana
