#!/bin/bash
# ─── Insight Local Dev Runner ───
# Run the API Gateway and Dashboard locally for development

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting Insight Monitoring System (Local Dev)..."
echo ""

# Install core dependencies
echo "📦 Installing Core API dependencies..."
pip3 install -q -r "$PROJECT_DIR/core/requirements.txt" 2>/dev/null

# Start API Gateway
echo "🔌 Starting API Gateway on port 8080..."
cd "$PROJECT_DIR/core"
DATABASE_URL="$PROJECT_DIR/insight.db" python3 -m uvicorn api-gateway.main:app --host 0.0.0.0 --port 8080 --reload &
API_PID=$!
echo "   PID: $API_PID"

# Wait for API to be ready
sleep 3

# Start Dashboard
echo "🎨 Starting Dashboard on port 3000..."
cd "$PROJECT_DIR/dashboard"
NEXT_PUBLIC_API_URL=http://localhost:8080 npm run dev &
DASH_PID=$!
echo "   PID: $DASH_PID"

echo ""
echo "✅ Insight is running!"
echo "   📊 Dashboard: http://localhost:3000"
echo "   🔌 API:       http://localhost:8080"
echo "   📄 API Docs:  http://localhost:8080/docs"
echo ""
echo "Press Ctrl+C to stop all services"

# Cleanup on exit
trap "kill $API_PID $DASH_PID 2>/dev/null; exit 0" INT TERM

wait
