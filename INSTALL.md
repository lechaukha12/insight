# Insight Monitoring System - Installation Guide

## Prerequisites

- **Minikube** v1.30+ with `docker` driver
- **Docker** v24+
- **kubectl** v1.28+

## Quick Start

### 1. Start Minikube

```bash
minikube start --cpus=4 --memory=8192 --driver=docker
```

### 2. Create Namespace

```bash
kubectl create namespace insight-system
```

### 3. Deploy ClickHouse (Time-Series Database)

```bash
kubectl apply -f clickhouse/k8s-deploy.yaml
kubectl rollout status statefulset/clickhouse -n insight-system --timeout=120s

# Init schema (only needed first time)
kubectl exec -n insight-system clickhouse-0 -- clickhouse-client --database=insight --multiquery --query="$(cat clickhouse/init-schema.sql)"
```

### 4. Deploy Core API

```bash
# Build
docker build -t lechaukha12/insight-api:latest ./core/
docker push lechaukha12/insight-api:latest

# Deploy
kubectl apply -f deploy/minikube/deployments.yaml
kubectl rollout status deploy/insight-api -n insight-system --timeout=120s
```

### 5. Deploy Dashboard

```bash
docker build -t lechaukha12/insight-dashboard:latest ./dashboard/
docker push lechaukha12/insight-dashboard:latest
kubectl rollout status deploy/insight-dashboard -n insight-system --timeout=120s
```

### 6. Access Dashboard

```bash
kubectl port-forward svc/insight-dashboard 3000:3000 -n insight-system
```

Open http://localhost:3000 — Login: **admin / insight2024**

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dashboard   │────▶│  Core API    │────▶│  ClickHouse  │ (metrics, traces, logs, events)
│  (Next.js)   │     │  (FastAPI)   │────▶│  SQLite      │ (users, agents, settings, config)
└──────────────┘     └──────────────┘     └──────────────┘
                            ▲
                     ┌──────┴───────┐
                     │  OTel Agent  │ (receives OTLP from instrumented apps)
                     └──────────────┘
```

## Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `insight.db` | SQLite path or PostgreSQL URL |
| `CLICKHOUSE_URL` | (empty) | ClickHouse HTTP URL, e.g. `http://clickhouse:8123` |

## Data Retention

Configure in Dashboard → Settings → 🗄️ Data Retention:

| Data Type | Default | Range |
|-----------|---------|-------|
| Traces | 7 days | 1-90 |
| Logs | 14 days | 1-90 |
| Metrics | 30 days | 1-365 |
| Events | 30 days | 1-90 |
| Processes | 3 days | 1-30 |
| Audit Logs | 90 days | 1-365 |

## ClickHouse Tables

| Table | Engine | Partition | TTL |
|-------|--------|-----------|-----|
| metrics | MergeTree | Daily | 30d |
| traces | MergeTree | Daily | 7d |
| logs | MergeTree | Daily | 14d |
| events | MergeTree | Daily | 30d |
| processes | MergeTree | Daily | 3d |
| audit_logs | MergeTree | Daily | 90d |

## Troubleshooting

### Check ClickHouse Status
```bash
kubectl exec -n insight-system clickhouse-0 -- clickhouse-client --query="SELECT 'ok'"
```

### Check Data Counts
```bash
kubectl exec -n insight-system clickhouse-0 -- clickhouse-client --database=insight \
  --query="SELECT 'metrics' as t, count() FROM metrics UNION ALL SELECT 'traces', count() FROM traces UNION ALL SELECT 'logs', count() FROM logs"
```

### View API Logs
```bash
kubectl logs deploy/insight-api -n insight-system --tail=50
```
