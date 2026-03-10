#!/bin/bash
# ─── Insight Monitoring System - Deploy Script ───
# Quick deploy to Minikube

set -e

echo "🚀 Deploying Insight Monitoring System to Minikube..."

# Check minikube
if ! command -v minikube &> /dev/null; then
    echo "❌ minikube not found. Install: https://minikube.sigs.k8s.io/docs/start/"
    exit 1
fi

# Use minikube docker
echo "📦 Configuring Docker for Minikube..."
eval $(minikube docker-env)

# Build images
echo "🔨 Building API Gateway..."
docker build -t insight-api:latest ../core/

echo "🔨 Building Dashboard..."
docker build -t insight-dashboard:latest ../dashboard/

echo "🔨 Building K8s Agent..."
docker build -t insight-k8s-agent:latest ../agents/k8s-agent/

# Deploy
echo "📋 Applying K8s manifests..."
kubectl apply -f minikube/namespace.yaml
kubectl apply -f minikube/rbac.yaml
kubectl apply -f minikube/configmap.yaml
kubectl apply -f minikube/deployments.yaml

echo "⏳ Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=insight-api -n insight-system --timeout=120s
kubectl wait --for=condition=ready pod -l app=insight-dashboard -n insight-system --timeout=120s

echo ""
echo "✅ Insight deployed successfully!"
echo ""
echo "📊 Dashboard URL:"
minikube service insight-dashboard -n insight-system --url
echo ""
echo "🔌 API Gateway (port-forward):"
echo "   kubectl port-forward svc/insight-api 8080:8080 -n insight-system"
echo ""
echo "📝 View pods:"
echo "   kubectl get pods -n insight-system"
echo ""
echo "📋 View agent logs:"
echo "   kubectl logs -f deploy/insight-k8s-agent -n insight-system"
