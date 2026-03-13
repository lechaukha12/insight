# 🔍 Insight Monitoring System

<p align="center">
  <strong>Hệ thống giám sát tập trung cho Infrastructure, Kubernetes & Application Performance</strong><br/>
  <em>v5.0.6 — Kubernetes Dashboard · StorageClass · Ingress · Homebrew · Agent Token Auth</em>
</p>

---

## 📋 Tổng quan

Insight là nền tảng monitoring toàn diện dựa trên microservice, triển khai trên Kubernetes (Minikube), hỗ trợ giám sát:
- **Kubernetes clusters** — Full cluster dashboard với 12 resource types (Pods, Deployments, StatefulSets, DaemonSets, Services, Ingresses, ConfigMaps, Secrets, PVCs, PVs, StorageClasses, Events)
- **System servers** — CPU, RAM, Disk, Network, Load average (Linux, macOS & Windows)
- **Application Performance** — Distributed tracing, logs, metrics qua OpenTelemetry
- **Multi-service architecture** — Theo dõi request flow giữa nhiều services

## 🏗 Kiến trúc

```
┌────────────────────────────────────────────────────────────────────────┐
│                        MONITORED APPLICATIONS                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │  Java App    │  │ Python GW    │  │  Any Service  │               │
│  │ (OTel Agent) │  │ (OTel SDK)   │  │ (OTLP export) │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │
│         └────────────┬────┘────────────┬────┘                        │
│                      │ OTLP (gRPC/HTTP)│                             │
│               ┌──────▼──────┐                                        │
│               │  OTel Agent │ ← Collects traces, logs, metrics       │
│               └──────┬──────┘                                        │
└──────────────────────┼───────────────────────────────────────────────┘
                       │
  ┌────────────────────┼────────────────────┐
  │                    │ HTTP REST           │
  │  ┌──────────┐     │     ┌──────────┐    │
  │  │ K8s Agent│─────┼────▶│          │    │
  │  └──────────┘     │     │  Core    │    │
  │  ┌──────────┐     │     │  API     │    │
  │  │ System   │─────┼────▶│(FastAPI) │    │
  │  │ Agent    │     │     │          │    │
  │  └──────────┘     │     └────┬─────┘    │
  │                   │          │          │
  │                   │    ┌─────┴─────┐    │
  │                   │    │           │    │
  │             ┌─────▼────▼─┐  ┌─────▼──┐ │
  │             │ ClickHouse │  │ SQLite  │ │
  │             │ (time-     │  │ (config │ │
  │             │  series)   │  │  data)  │ │
  │             └────────────┘  └────────┘ │
  │                    MINIKUBE             │
  └────────────────────────────────────────┘
        │
   ┌────▼────┐
   │Dashboard│  ← Next.js 15 (dark mode, charts, real-time)
   └─────────┘
```

### Hybrid Storage

| Database | Dữ liệu | Engine |
|----------|----------|--------|
| **ClickHouse** | Metrics, Traces, Logs, Events, Processes, Audit Logs | MergeTree, daily partition, TTL |
| **SQLite** | Users, Agents, Clusters, Settings, Alert configs, Webhooks, Reports | WAL mode |

## ✨ Tính năng

### Monitoring
| Feature | Mô tả |
|---------|--------|
| Real-time monitoring | Agent scan mỗi 30s, phát hiện lỗi tức thì |
| Kubernetes Dashboard | Full cluster dashboard — 12 resource tabs, node metrics popup (Lens-style), namespace filter |
| Kubernetes Resources | Pods, Deployments, StatefulSets, DaemonSets, Services, Ingresses, ConfigMaps, Secrets, PVCs, PVs, StorageClasses, Events |
| System monitoring | CPU, RAM, Disk, Network, Process list (Linux, macOS, Windows) |
| Application monitoring | Distributed traces, request latency, error rates (OTel) |
| Multi-service tracing | Waterfall view, service dependency map |

### Alerting & Notification
| Feature | Mô tả |
|---------|--------|
| Multi-channel alerts | Telegram, Email (SMTP), Webhook |
| Alert deduplication | Không gửi trùng alert trong 5 phút |
| Notification rules | Routing theo severity, agent, category |
| Threshold alerting | CPU > 90%, RAM > 90%, Disk > 95% |
| Daily report | Báo cáo tổng hợp hàng ngày |

### Dashboard & Administration
| Feature | Mô tả |
|---------|--------|
| Dashboard | Overview với live metrics charts (Recharts) |
| K8s Agent Grid | Agent list dạng Grid/List với quick stats (Nodes, Pods, NS, Warnings) |
| K8s Cluster Detail | Cluster overview, resource browser, node popup |
| Agent management | Register, filter by category, detail tabs, token-based auth |
| Agent Tokens | Generate / revoke agent tokens cho secure registration |
| Events & Alerts | Severity tracking, acknowledge, filter |
| Error Logs | Centralized log viewer |
| Settings | General, Webhooks, Data Retention tabs |
| RBAC | Admin / Operator / Viewer roles |
| Audit Log | Track all admin actions |
| User management | CRUD users (admin only) |

### Data Management
| Feature | Mô tả |
|---------|--------|
| ClickHouse backend | High-performance time-series storage |
| Data retention | Configurable TTL per data type (dashboard UI) |
| Storage statistics | Real-time table sizes, row counts |
| Purge all data | Admin-only destructive action with audit log |

## 🚀 Quick Start

### Prerequisites

- **Minikube** v1.30+ với `docker` driver
- **Docker** v24+
- **kubectl** v1.28+

### Deploy to Minikube

```bash
# 1. Start Minikube
minikube start --cpus=4 --memory=8192 --driver=docker

# 2. Create namespace & config
kubectl apply -f deploy/minikube/namespace.yaml
kubectl apply -f deploy/minikube/configmap.yaml
kubectl apply -f deploy/minikube/rbac.yaml
kubectl apply -f deploy/minikube/pvc.yaml

# 3. Deploy ClickHouse
kubectl apply -f clickhouse/k8s-deploy.yaml
kubectl rollout status sts/clickhouse -n insight-system --timeout=120s
kubectl exec -n insight-system clickhouse-0 -- \
  clickhouse-client --database=insight --multiquery \
  --query="$(cat clickhouse/init-schema.sql)"

# 4. Deploy Core API + Dashboard + Agents
kubectl apply -f deploy/minikube/deployments.yaml
kubectl rollout status deploy/insight-api -n insight-system
kubectl rollout status deploy/insight-dashboard -n insight-system

# 5. Access Dashboard
kubectl port-forward svc/insight-dashboard 3000:3000 -n insight-system
# Open: http://localhost:3000
# Login: admin / insight2024
```

### Local Development

```bash
# Backend
cd core
pip install -r requirements.txt
python -m uvicorn api_gateway.main:app --port 8080 --reload

# Dashboard
cd dashboard
npm install && npm run dev
# Open: http://localhost:3000
```

### Multi-Service Demo (OTel)

```bash
# Deploy demo services
kubectl apply -f demo-java-app/k8s-deploy.yaml
kubectl apply -f demo-gateway/k8s-deploy.yaml

# OTel Agent collects traces/logs/metrics automatically
```

## 📁 Project Structure

```
insight/
├── core/                         # Backend (Python FastAPI)
│   ├── api_gateway/              # REST API Gateway + Auth
│   │   ├── main.py               # 50+ API endpoints
│   │   ├── auth.py               # JWT auth, RBAC
│   │   └── k8s_resources.py      # Direct K8s API queries (14 resource types)
│   ├── alert_service/            # Telegram, Email, Webhook alerts
│   ├── report_service/           # Report generation
│   └── shared/
│       └── database/
│           └── db.py             # Hybrid DB layer (ClickHouse + SQLite)
│
├── dashboard/                    # Next.js 15 Admin Dashboard
│   └── app/
│       ├── components/           # AuthProvider, Sidebar, ClientLayout
│       ├── lib/                  # API client, utils, TimeRangeContext
│       ├── agents/               # Agent list & detail pages
│       ├── monitoring/
│       │   ├── kubernetes/       # K8s agent grid page
│       │   │   └── [agentId]/    # Cluster detail — 12 resource tabs
│       │   ├── application/      # Application monitoring (OTel)
│       │   └── system/           # System monitoring
│       ├── events/               # Events & Alerts page
│       ├── logs/                 # Error Logs viewer
│       ├── settings/             # General, Webhooks, Data Retention
│       ├── rules/                # Notification rules
│       ├── reports/              # Report history
│       ├── users/                # User management (admin)
│       ├── audit/                # Audit log viewer
│       ├── profile/              # User profile
│       └── login/                # Login page
│
├── agents/
│   ├── k8s-agent/                # Kubernetes cluster monitoring
│   ├── system-agent/             # Linux/macOS/Windows system monitoring
│   └── otel-agent/               # OpenTelemetry collector → Insight
│
├── homebrew/
│   └── insight-agent.rb          # Homebrew formula for macOS agent
│
├── clickhouse/
│   ├── init-schema.sql           # ClickHouse schema (6 tables)
│   └── k8s-deploy.yaml          # StatefulSet + PVC + Service
│
├── demo-java-app/                # Sample Java app (Spring Boot style)
│   ├── App.java                  # Multi-endpoint demo service
│   ├── Dockerfile                # With OTel Java Agent
│   └── k8s-deploy.yaml          # K8s deployment
│
├── demo-gateway/                 # Sample Python API Gateway
│   ├── app.py                    # Flask gateway → Java app
│   ├── Dockerfile                # With OTel SDK
│   └── k8s-deploy.yaml          # K8s deployment
│
├── deploy/
│   ├── minikube/                 # K8s manifests
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   ├── deployments.yaml      # All deployments + services + RBAC
│   │   ├── rbac.yaml
│   │   └── pvc.yaml
│   ├── deploy-minikube.sh        # Automated deployment script
│   └── docker-compose.yaml       # Local development
│
├── MANIFEST.md                   # Current image versions
├── INSTALL.md                    # Detailed installation guide
└── README.md                     # This file
```

## 📊 API Endpoints

### Authentication
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `POST` | `/api/v1/auth/login` | - | Login, get JWT token |
| `GET` | `/api/v1/auth/me` | ✅ | Get current user info |
| `POST` | `/api/v1/auth/change-password` | ✅ | Change password |

### User Management (Admin)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/users` | Admin | List all users |
| `POST` | `/api/v1/users` | Admin | Create new user |
| `DELETE` | `/api/v1/users/{id}` | Admin | Delete user |

### Agents
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `POST` | `/api/v1/agents/register` | API Key | Register new agent |
| `GET` | `/api/v1/agents` | ✅ | List agents (filter: cluster, category) |
| `GET` | `/api/v1/agents/{id}` | ✅ | Agent detail |
| `POST` | `/api/v1/agents/{id}/heartbeat` | API Key | Agent heartbeat |

### Telemetry Data
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `POST` | `/api/v1/metrics` | API Key | Receive metrics batch |
| `GET` | `/api/v1/metrics` | ✅ | Query metrics |
| `POST` | `/api/v1/events` | API Key | Receive events |
| `GET` | `/api/v1/events` | ✅ | Query events |
| `POST` | `/api/v1/events/{id}/ack` | ✅ | Acknowledge event |
| `POST` | `/api/v1/logs` | API Key | Receive error logs |
| `GET` | `/api/v1/logs` | ✅ | Query logs |
| `POST` | `/api/v1/traces` | API Key | Receive OTLP traces |
| `GET` | `/api/v1/traces` | ✅ | Query traces |
| `GET` | `/api/v1/traces/summary` | - | Trace aggregate stats |
| `POST` | `/api/v1/processes` | API Key | Receive process snapshots |
| `GET` | `/api/v1/processes` | ✅ | Query process snapshots |

### Charts
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/charts/metrics` | ✅ | Metrics timeseries data |
| `GET` | `/api/v1/charts/events` | ✅ | Event counts by hour |

### Alerting & Notification
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/alerts/configs` | ✅ | List alert configs |
| `POST` | `/api/v1/alerts/configs` | Admin/Op | Create alert config |
| `DELETE` | `/api/v1/alerts/configs/{id}` | Admin | Delete alert config |
| `GET` | `/api/v1/rules` | ✅ | List notification rules |
| `POST` | `/api/v1/rules` | Admin/Op | Create notification rule |
| `DELETE` | `/api/v1/rules/{id}` | Admin | Delete rule |
| `PUT` | `/api/v1/rules/{id}/toggle` | ✅ | Enable/disable rule |

### Webhooks
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/webhooks` | ✅ | List webhooks |
| `POST` | `/api/v1/webhooks` | Admin/Op | Create webhook |
| `DELETE` | `/api/v1/webhooks/{id}` | Admin | Delete webhook |
| `PUT` | `/api/v1/webhooks/{id}/toggle` | Admin/Op | Enable/disable webhook |
| `POST` | `/api/v1/webhooks/{id}/test` | Admin/Op | Test webhook delivery |

### Settings, Reports & Storage
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/settings` | ✅ | Get system settings |
| `PUT` | `/api/v1/settings` | Admin | Update settings |
| `POST` | `/api/v1/reports/generate` | Admin/Op | Generate & send report |
| `GET` | `/api/v1/reports` | ✅ | List report history |
| `GET` | `/api/v1/audit` | Admin | Get audit logs |
| `GET` | `/api/v1/storage/stats` | ✅ | ClickHouse storage statistics |
| `POST` | `/api/v1/retention/apply` | ✅ | Apply retention TTL policies |
| `POST` | `/api/v1/storage/purge` | Admin | Purge all time-series data |

### Kubernetes Resources (Direct K8s API)
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/k8s/nodes` | ✅ | List cluster nodes with CPU/RAM metrics |
| `GET` | `/api/v1/k8s/namespaces` | ✅ | List namespaces |
| `GET` | `/api/v1/k8s/namespaces/{ns}/pods` | ✅ | List pods (ns=`_all` for all) |
| `GET` | `/api/v1/k8s/namespaces/{ns}/deployments` | ✅ | List deployments |
| `GET` | `/api/v1/k8s/namespaces/{ns}/statefulsets` | ✅ | List statefulsets |
| `GET` | `/api/v1/k8s/namespaces/{ns}/daemonsets` | ✅ | List daemonsets |
| `GET` | `/api/v1/k8s/namespaces/{ns}/services` | ✅ | List services |
| `GET` | `/api/v1/k8s/namespaces/{ns}/ingresses` | ✅ | List ingresses |
| `GET` | `/api/v1/k8s/namespaces/{ns}/configmaps` | ✅ | List configmaps |
| `GET` | `/api/v1/k8s/namespaces/{ns}/secrets` | ✅ | List secrets |
| `GET` | `/api/v1/k8s/namespaces/{ns}/events` | ✅ | List events |
| `GET` | `/api/v1/k8s/pvs` | ✅ | List persistent volumes |
| `GET` | `/api/v1/k8s/pvcs` | ✅ | List persistent volume claims |
| `GET` | `/api/v1/k8s/storageclasses` | ✅ | List storage classes |

### Agent Tokens
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/api/v1/agent-tokens` | Admin | List agent tokens |
| `POST` | `/api/v1/agent-tokens` | Admin | Generate new token |
| `DELETE` | `/api/v1/agent-tokens/{id}` | Admin | Revoke token |

### Other
| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| `GET` | `/health` | - | Health check |
| `GET` | `/` | - | API info |
| `WS` | `/ws/dashboard` | - | Real-time WebSocket |
| `GET` | `/api/v1/clusters` | ✅ | List clusters |
| `POST` | `/api/v1/clusters` | Admin | Create cluster |
| `GET` | `/api/v1/dashboard/summary` | ✅ | Dashboard overview data |

## ⚙️ Environment Variables

### Core API
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `insight.db` | SQLite path hoặc PostgreSQL URL |
| `CLICKHOUSE_URL` | *(empty)* | ClickHouse HTTP URL, e.g. `http://clickhouse:8123` |
| `INSIGHT_API_KEY` | `insight-secret-key` | API key cho agent authentication |
| `PORT` | `8080` | API server port |
| `JWT_SECRET` | *(auto)* | JWT signing secret |
| `SMTP_HOST` | *(empty)* | SMTP server cho email alerts |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | *(empty)* | SMTP username |
| `SMTP_PASS` | *(empty)* | SMTP password |

### Agents
| Variable | Default | Description |
|----------|---------|-------------|
| `INSIGHT_CORE_URL` | `http://localhost:8080` | Core API URL |
| `AGENT_TOKEN` | *(empty)* | Agent token (recommended, get from dashboard) |
| `INSIGHT_API_KEY` | `insight-secret-key` | API key (legacy fallback) |
| `AGENT_NAME` | *(hostname)* | Agent display name |
| `CLUSTER_ID` | `default` | Cluster assignment |
| `SCAN_INTERVAL` | `30` | Scan interval (seconds) |
| `OTEL_GRPC_PORT` | `4317` | OTel GRPC receiver port |

## 🗄️ Data Retention

Cấu hình trong Dashboard → Settings → 🗄️ Data Retention:

| Data Type | Default TTL | Range | Note |
|-----------|-------------|-------|------|
| Traces | 7 ngày | 1-90 | Distributed traces từ OTel |
| Logs | 14 ngày | 1-90 | Error logs từ agents |
| Metrics | 30 ngày | 1-365 | CPU, RAM, Disk, Network |
| Events | 30 ngày | 1-90 | K8s events, system events |
| Processes | 3 ngày | 1-30 | Process snapshots |
| Audit Logs | 90 ngày | 1-365 | Admin action history |

## 🛠 Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12, FastAPI, Uvicorn |
| **Dashboard** | Next.js 15, React 19, Recharts |
| **Time-series DB** | ClickHouse (MergeTree, TTL, daily partitions) |
| **Config DB** | SQLite (WAL mode) |
| **Agents** | Python, psutil, kubernetes-client, OpenTelemetry |
| **Deployment** | Docker, Kubernetes, Minikube |
| **Protocols** | REST, WebSocket, gRPC (OTLP), Protobuf |
| **Auth** | JWT, RBAC (Admin/Operator/Viewer) |
| **Alerts** | Telegram Bot API, SMTP, Webhook |

## 📌 Release History

| Version | Highlights |
|---------|-----------|
| **v5.0.6** | K8s Dashboard redesign (12 resource tabs, cluster detail, node popup), StorageClass/Ingress support, Homebrew formula, Agent Token auth |
| **v5.0.4** | Agent token management, time range picker in header, compact UI |
| **v5.0.3** | macOS system agent, agent category filter, improved detail tabs |
| **v5.0.0** | ClickHouse migration, Multi-service demo, OTel enhancement, Data retention UI, Purge feature |
| **v3.0.0** | Recharts dashboard with live metrics charts |
| **v2.0.0** | UI redesign with custom branding |
| **v1.0.0** | MVP — K8s monitoring, alerts, dashboard |

## 🍺 macOS Agent (Homebrew)

```bash
# Install directly from formula
brew install --formula ./homebrew/insight-agent.rb

# Configure and run
export INSIGHT_CORE_URL="http://your-api-server:8080"
export AGENT_TOKEN="your-agent-token"
insight-agent

# Or run as background service
brew services start insight-agent
```

## 📜 License

MIT
