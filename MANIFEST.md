# Insight Monitoring System — Manifest
# Version: v5.0.6
# Date: 2026-03-13

## Docker Images

| Component       | Image                                    | Tag    |
|-----------------|------------------------------------------|--------|
| API Gateway     | lechaukha12/insight-api                  | v5.0.6 |
| Dashboard       | lechaukha12/insight-dashboard            | v5.0.5 |
| System Agent    | lechaukha12/insight-system-agent         | v5.0.3 |
| K8s Agent       | lechaukha12/insight-k8s-agent            | v5.0.3 |
| OTEL Agent      | lechaukha12/insight-otel-agent           | latest |
| Demo Gateway    | lechaukha12/insight-demo-gateway         | latest |
| Demo Java App   | lechaukha12/insight-demo-java-app        | latest |

## Kubernetes Deployment

```bash
# Apply all resources
kubectl apply -f deploy/minikube/deployments.yaml

# Verify rollout
kubectl rollout status deploy/insight-api deploy/insight-dashboard -n insight-system
```

## Homebrew (macOS System Agent)

```bash
brew tap lechaukha12/insight
brew install insight-agent
```
