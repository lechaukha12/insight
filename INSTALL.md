# Insight Monitoring System — Installation Guide

## Prerequisites

| Tool | Version | Check Command |
|------|---------|--------------|
| Minikube | v1.30+ | `minikube version` |
| Docker | v24+ | `docker version` |
| kubectl | v1.28+ | `kubectl version --client` |
| Node.js | v18+ | `node -v` *(local dev only)* |
| Python | v3.10+ | `python3 --version` *(local dev only)* |

---

## 🚀 Minikube Deployment (Production-like)

### Step 1: Start Minikube

```bash
minikube start --cpus=4 --memory=8192 --driver=docker
```

### Step 2: Create Namespace & Infrastructure

```bash
kubectl apply -f deploy/minikube/namespace.yaml
kubectl apply -f deploy/minikube/configmap.yaml
kubectl apply -f deploy/minikube/rbac.yaml
kubectl apply -f deploy/minikube/pvc.yaml
```

### Step 3: Deploy ClickHouse

```bash
# Deploy StatefulSet (PVC 10Gi)
kubectl apply -f clickhouse/k8s-deploy.yaml
kubectl rollout status statefulset/clickhouse -n insight-system --timeout=120s

# Initialize schema (first time only)
kubectl exec -n insight-system clickhouse-0 -- \
  clickhouse-client --database=insight --multiquery \
  --query="$(cat clickhouse/init-schema.sql)"

# Verify
kubectl exec -n insight-system clickhouse-0 -- \
  clickhouse-client --database=insight --query="SHOW TABLES"
# Expected: audit_logs  events  logs  metrics  processes  traces
```

### Step 4: Build & Deploy Core API

```bash
# Build Docker image
docker build -t lechaukha12/insight-api:v5.0.0 ./core/
docker push lechaukha12/insight-api:v5.0.0

# Deploy (includes CLICKHOUSE_URL env)
kubectl apply -f deploy/minikube/deployments.yaml
kubectl rollout status deploy/insight-api -n insight-system --timeout=120s

# Verify
kubectl logs deploy/insight-api -n insight-system --tail=5
# Should see: [DB] ClickHouse connected: audit_logs events logs metrics processes traces
```

### Step 5: Build & Deploy Dashboard

```bash
docker build -t lechaukha12/insight-dashboard:v5.0.0 ./dashboard/
docker push lechaukha12/insight-dashboard:v5.0.0
kubectl rollout status deploy/insight-dashboard -n insight-system --timeout=120s
```

### Step 6: Deploy Agents

#### K8s Agent (auto-deployed via deployments.yaml)
Already included in `deployments.yaml`.

#### System Agent (optional, for non-K8s servers)
```bash
docker build -t lechaukha12/insight-system-agent:v5.0.0 ./agents/system-agent/
docker push lechaukha12/insight-system-agent:v5.0.0
# Deploy on target machines
```

#### OTel Agent (for application monitoring)
Already included in `deployments.yaml`.

### Step 7: Deploy Demo Applications (optional)

```bash
# Java demo app (instrumented with OTel Java Agent)
kubectl apply -f demo-java-app/k8s-deploy.yaml

# Python gateway (instrumented with OTel SDK)
kubectl apply -f demo-gateway/k8s-deploy.yaml
```

### Step 8: Access Dashboard

```bash
kubectl port-forward svc/insight-dashboard 3000:3000 -n insight-system
```

Open http://localhost:3000

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `insight2024` |

---

## 🖥 Local Development

### Backend (Core API)

```bash
cd core
pip install -r requirements.txt

# Without ClickHouse (SQLite only)
python -m uvicorn api_gateway.main:app --port 8080 --reload

# With ClickHouse
CLICKHOUSE_URL=http://localhost:8123 python -m uvicorn api_gateway.main:app --port 8080 --reload
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
# Open: http://localhost:3000
```

### Agents

```bash
# System Agent
cd agents/system-agent
pip install -r requirements.txt
INSIGHT_CORE_URL=http://localhost:8080 python agent.py

# K8s Agent (requires kubeconfig)
cd agents/k8s-agent
pip install -r requirements.txt
INSIGHT_CORE_URL=http://localhost:8080 python agent.py
```

---

## ⚙️ Configuration

### Environment Variables

#### Core API
| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | `insight.db` | No | SQLite path or PostgreSQL URL |
| `CLICKHOUSE_URL` | *(empty)* | No | ClickHouse HTTP URL |
| `INSIGHT_API_KEY` | `insight-secret-key` | Yes | Agent authentication key |
| `PORT` | `8080` | No | API server port |
| `JWT_SECRET` | *(auto-generated)* | No | JWT signing secret |

#### Agent
| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `INSIGHT_CORE_URL` | `http://localhost:8080` | Yes | Core API URL |
| `INSIGHT_API_KEY` | `insight-secret-key` | Yes | Must match Core API |
| `AGENT_NAME` | *(hostname)* | No | Display name |
| `CLUSTER_ID` | `default` | No | Cluster assignment |
| `SCAN_INTERVAL` | `30` | No | Scan interval (seconds) |

### Kubernetes ConfigMap

Edit `deploy/minikube/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: insight-config
  namespace: insight-system
data:
  INSIGHT_API_KEY: "insight-secret-key"
  SCAN_INTERVAL: "30"
```

---

## 🗄️ ClickHouse Management

### Schema

6 MergeTree tables with daily partitioning and TTL:

| Table | Partition | Order By | Default TTL |
|-------|-----------|----------|------------|
| metrics | `toYYYYMMDD(timestamp)` | `(agent_id, metric_name, timestamp)` | 30 days |
| traces | `toYYYYMMDD(timestamp)` | `(service_name, trace_id, timestamp)` | 7 days |
| logs | `toYYYYMMDD(timestamp)` | `(agent_id, timestamp)` | 14 days |
| events | `toYYYYMMDD(created_at)` | `(agent_id, level, created_at)` | 30 days |
| processes | `toYYYYMMDD(timestamp)` | `(agent_id, timestamp)` | 3 days |
| audit_logs | `toYYYYMMDD(timestamp)` | `(user_id, action, timestamp)` | 90 days |

### Data Retention

Configure via Dashboard → Settings → 🗄️ Data Retention:

1. Set retention days per data type
2. Click **💾 Save & Apply** to update ClickHouse TTL
3. ClickHouse automatically drops expired data during merge operations

### Purge All Data

Admin users can purge all time-series data via **⚠️ Danger Zone** section (double-confirm required).

### CLI Management

```bash
# Connect to ClickHouse
kubectl exec -it -n insight-system clickhouse-0 -- clickhouse-client --database=insight

# Check data counts
SELECT 'metrics' as t, count() FROM metrics
UNION ALL SELECT 'traces', count() FROM traces
UNION ALL SELECT 'logs', count() FROM logs
UNION ALL SELECT 'events', count() FROM events;

# Check storage size
SELECT table, formatReadableSize(sum(bytes_on_disk)) as size, sum(rows) as rows
FROM system.parts WHERE database = 'insight' AND active = 1
GROUP BY table ORDER BY sum(bytes_on_disk) DESC;

# Manual TTL cleanup
OPTIMIZE TABLE metrics FINAL;
```

---

## 🔍 Troubleshooting

### Services not starting

```bash
# Check pod status
kubectl get pods -n insight-system

# Check logs
kubectl logs deploy/insight-api -n insight-system --tail=50
kubectl logs deploy/insight-dashboard -n insight-system --tail=50

# Describe pod for events
kubectl describe pod -l app=insight-api -n insight-system
```

### ClickHouse connection failed

```bash
# Verify ClickHouse is running
kubectl exec -n insight-system clickhouse-0 -- clickhouse-client --query="SELECT 1"

# Check API can reach ClickHouse
kubectl exec -n insight-system deploy/insight-api -- \
  python3 -c "import clickhouse_connect; c = clickhouse_connect.get_client(host='clickhouse', port=8123, database='insight'); print(c.command('SHOW TABLES'))"
```

### Dashboard not loading data

```bash
# Verify API is accessible from dashboard
kubectl exec -n insight-system deploy/insight-dashboard -- \
  wget -qO- http://insight-api:8080/health

# Check CORS / proxy config
kubectl logs deploy/insight-dashboard -n insight-system --tail=20
```

### Agents not reporting

```bash
# Check agent logs
kubectl logs deploy/insight-k8s-agent -n insight-system --tail=20

# Verify agent registration
kubectl exec -n insight-system deploy/insight-api -- \
  curl -s http://localhost:8080/api/v1/agents | python3 -m json.tool
```

---

## 📌 Version History

| Version | Date | Highlights |
|---------|------|------------|
| v5.0.0 | 2026-03-12 | ClickHouse migration, Multi-service demo, OTel, Data retention, Purge |
| v3.0.0 | - | Recharts dashboard with live metrics charts |
| v2.0.0 | - | UI redesign with custom branding |
| v1.0.0 | - | MVP — K8s monitoring, alerts, dashboard |
