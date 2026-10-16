# Red Hat（RHEL 8/9）部署说明

监控机 **192.168.100.30** `/opt/monitor`  
应用机 **192.168.100.31**（Agent + Postgres）

不用 `apt`、不用 `ufw`。用 `dnf` + `firewalld`。SELinux 默认 Enforcing，挂盘可能要加 `:z` 或临时排查。

---

## 1. 两台都装 Docker

RHEL 官方源往往没有 `docker-ce`，用 Docker 官方仓库：

```bash
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

当前已是 root 可省略 `sudo`。用户要进组：`usermod -aG docker 用户名` 后重新登录。

若 `docker-ce.repo` 报系统版本不匹配，把 repo 里 `$releasever` 改成 `8` 或 `9`（`cat /etc/redhat-release`）。

**没有外网 / 必须用内网源时：** 用已有的 `podman`：

```bash
dnf -y install podman podman-compose
# 命令把 docker compose 换成 podman-compose，把 docker 换成 podman
```

---

## 2. 监控机 192.168.100.30

```bash
cd /opt/monitor
# 配置文件都放这里：docker-compose.yml、prometheus/、alertmanager/、grafana/
vi prometheus/sre-agent-targets.yml
# 内容必须是应用机：
# - targets:
#     - "192.168.100.31:9108"

docker compose up -d
docker compose ps
```

cAdvisor **不要用 `google/cadvisor:v0.33.0`**（RHEL cgroup v2 上会 `Restarting (255)`）。用 `gcr.io/cadvisor/cadvisor:v0.47.2`，Docker 目录用 `/var/lib/docker`。

拉不了 gcr 时，可先注释掉 compose 里整个 `cadvisor` 服务——**SRE-Agent 不依赖它**。

旧说明：cAdvisor 数据目录红帽默认是 `/var/lib/docker`：

```yaml
- /var/lib/docker/:/var/lib/docker:ro
```

SELinux 导致容器起不来时看：

```bash
ausearch -m avc -ts recent | tail
# 先验证能否跑通（生产再收紧策略）：
# setenforce 0
```

### firewalld（只放行应用机）

```bash
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.100.31" port port="9090" protocol="tcp" accept'
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.100.31" port port="9093" protocol="tcp" accept'
# Grafana 若只在监控机浏览器看，不必对 .31 开放 3000
firewall-cmd --reload
firewall-cmd --list-rich-rules
```

本机验证：

```bash
curl -sS http://127.0.0.1:9090/-/ready
curl -sS http://127.0.0.1:9093/-/ready
```

---

## 3. 应用机 192.168.100.31

同样先装 Docker（Postgres 用 compose）。Python 用 uv（不要用系统自带的 3.6/3.9 硬跑本项目）。

```bash
cd /opt/SRE-agent   # 或你的代码目录
cd deploy/docker/app
docker compose up -d
```

`.env`：

```bash
SRE_AGENT_PROM_URL=http://192.168.100.30:9090
SRE_AGENT_AM_URL=http://192.168.100.30:9093
SRE_AGENT_DATABASE_URL=postgresql://sre_agent:sre_agent@127.0.0.1:5432/sre_agent
```

### firewalld（只让监控机抓 /metrics）

```bash
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.100.30" port port="9108" protocol="tcp" accept'
firewall-cmd --reload
```

从应用机测监控是否通：

```bash
curl -sS http://192.168.100.30:9090/-/ready
curl -sS http://192.168.100.30:9093/-/ready
```

---

## 4. 和 Ubuntu 文档的对应关系

| Ubuntu 文档 | 红帽 |
|-------------|------|
| `apt install docker.io docker-compose-v2` | `dnf install docker-ce docker-compose-plugin` |
| `ufw allow from ...` | `firewall-cmd --add-rich-rule=...` |
| 无 SELinux | 默认 Enforcing，挂载失败先查 AVC |
| `/var/lib/docker` | 常见同样是这个；你 compose 若写了 `/data/docker` 要对齐实际目录 |
