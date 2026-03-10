# 🔍 Insight Monitoring System

<p align="center">
  <strong>Hệ thống giám sát tập trung cho Infrastructure & Kubernetes</strong>
</p>

---

## 📋 Tổng quan

Insight là nền tảng monitoring dựa trên microservice, triển khai trên Kubernetes, hỗ trợ giám sát:
- **Kubernetes clusters** — Pod status, node resources, error logs, CrashLoopBackOff detection
- **Linux servers** — CPU, RAM, Disk, Network, Load average
- **Windows servers** — System metrics + Windows Event Log errors

## 🏗 Kiến trúc

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  K8s Agent   │     │ Linux Agent  │     │ Windows Agent│
│  (Python)    │     │  (psutil)    │     │ (psutil+WMI) │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │ HTTP REST
                   ┌────────▼────────┐
                   │   API Gateway   │
                   │   (FastAPI)     │
                   └───┬────┬────┬──┘
                       │    │    │
              ┌────────┘    │    └────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Alert    │  │ Report   │  │ Database │
        │ Service  │  │ Service  │  │ (SQLite) │
        └──────────┘  └──────────┘  └──────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
Telegram   Email     Webhook
```

## ✨ Tính năng

| Feature | Mô tả |
|---|---|
| Real-time monitoring | Scan mỗi 30s, phát hiện lỗi tức thì |
| Daily report | Báo cáo tổng hợp hàng ngày lúc 7:45 AM |
| Multi-channel alerts | Telegram, Email (SMTP), Webhook |
| Alert deduplication | Không gửi trùng alert trong 5 phút |
| Dashboard | Dark mode UI, auto-refresh |
| Threshold alerting | CPU > 90%, RAM > 90%, Disk > 95% |
| Readonly RBAC | K8s agent chỉ có quyền đọc |

## 🚀 Quick Start

### Local Development

```bash
# 1. Start API Gateway
cd core
pip install -r requirements.txt
python -m uvicorn api_gateway.main:app --port 8080 --reload

# 2. Start Dashboard
cd dashboard
npm install && npm run dev
# Open: http://localhost:3000

# 3. Run Linux Agent
cd agents/linux-agent
pip install -r requirements.txt
INSIGHT_CORE_URL=http://localhost:8080 python agent.py
```

### Deploy to Minikube

```bash
cd deploy
bash deploy-minikube.sh

# Access
kubectl port-forward svc/insight-dashboard 3000:3000 -n insight-system
kubectl port-forward svc/insight-api 8080:8080 -n insight-system
```

## 📁 Project Structure

```
insight/
├── core/                     # Backend (Python FastAPI)
│   ├── api_gateway/          # REST API Gateway
│   ├── alert_service/        # Telegram, Email, Webhook
│   ├── report_service/       # Report generation
│   └── shared/               # Database, Models
├── dashboard/                # Next.js Admin Dashboard
├── agents/
│   ├── k8s-agent/            # Kubernetes monitoring
│   ├── linux-agent/          # Linux system monitor
│   └── windows-agent/        # Windows system monitor
└── deploy/
    ├── docker-compose.yaml   # Local development
    ├── deploy-minikube.sh    # K8s deployment
    └── minikube/             # K8s manifests
```

## 📊 API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/agents/register` | Register agent |
| `GET` | `/api/v1/agents` | List agents |
| `POST` | `/api/v1/metrics` | Receive metrics |
| `POST` | `/api/v1/events` | Receive events |
| `POST` | `/api/v1/logs` | Receive error logs |
| `GET` | `/api/v1/dashboard/summary` | Dashboard data |
| `POST` | `/api/v1/reports/generate` | Generate report |
| `GET/POST` | `/api/v1/settings/alerts` | Alert config |

## 🛠 Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLite
- **Dashboard:** Next.js 15, React 19
- **Agents:** Python, psutil, kubernetes-client
- **Deployment:** Docker, Kubernetes, Minikube
- **Alerts:** Telegram Bot API, SMTP, Webhook

## 📜 License

MIT
