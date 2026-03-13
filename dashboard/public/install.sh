#!/bin/bash
# ════════════════════════════════════════════════════
# Insight System Agent — Quick Install Script
# Usage: curl -sSL https://insight.chaukha.tech/install.sh | bash -s -- \
#   --token="YOUR_TOKEN" --core-url=https://insight.chaukha.tech
# ════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
AGENT_TOKEN=""
CORE_URL="http://localhost:8080"
AGENT_NAME=""
IMAGE="lechaukha12/insight-system-agent:latest"
CONTAINER_NAME="insight-agent"

# Parse args
for arg in "$@"; do
  case $arg in
    --token=*)  AGENT_TOKEN="${arg#*=}" ;;
    --core-url=*) CORE_URL="${arg#*=}" ;;
    --name=*)   AGENT_NAME="${arg#*=}" ;;
    --image=*)  IMAGE="${arg#*=}" ;;
    --help)
      echo "Usage: curl -sSL <url>/install.sh | bash -s -- [options]"
      echo ""
      echo "Options:"
      echo "  --token=TOKEN      Agent token (required, get from dashboard)"
      echo "  --core-url=URL     API server URL (default: http://localhost:8080)"
      echo "  --name=NAME        Agent display name (default: auto-detect hostname)"
      echo "  --image=IMAGE      Docker image (default: lechaukha12/insight-system-agent:latest)"
      exit 0
      ;;
  esac
done

echo -e "${BLUE}══════════════════════════════════════════${NC}"
echo -e "${BLUE}  Insight System Agent — Installer${NC}"
echo -e "${BLUE}══════════════════════════════════════════${NC}"
echo ""

# Validate
if [ -z "$AGENT_TOKEN" ]; then
  echo -e "${RED}✗ Error: --token is required${NC}"
  echo -e "  Get a token from your Insight dashboard → Agents → Install Agent"
  exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
  echo -e "${RED}✗ Docker is not installed${NC}"
  echo -e "  Install Docker: https://docs.docker.com/engine/install/"
  exit 1
fi
echo -e "${GREEN}✓ Docker found${NC}"

# Stop existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo -e "${YELLOW}→ Stopping existing container '${CONTAINER_NAME}'...${NC}"
  docker stop "$CONTAINER_NAME" 2>/dev/null || true
  docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# Pull latest image
echo -e "${YELLOW}→ Pulling ${IMAGE}...${NC}"
docker pull "$IMAGE"

# Build env args
ENV_ARGS="-e AGENT_TOKEN=${AGENT_TOKEN} -e INSIGHT_CORE_URL=${CORE_URL}"
if [ -n "$AGENT_NAME" ]; then
  ENV_ARGS="${ENV_ARGS} -e AGENT_NAME=${AGENT_NAME}"
fi

# Run container
echo -e "${YELLOW}→ Starting agent...${NC}"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart=unless-stopped \
  --network=host \
  --pid=host \
  -v /proc:/host/proc:ro \
  -v /sys:/host/sys:ro \
  -v /var/log:/var/log:ro \
  -e AGENT_TOKEN="$AGENT_TOKEN" \
  -e INSIGHT_CORE_URL="$CORE_URL" \
  ${AGENT_NAME:+-e AGENT_NAME="$AGENT_NAME"} \
  "$IMAGE"

echo ""
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ Insight Agent installed successfully!${NC}"
echo -e "${GREEN}══════════════════════════════════════════${NC}"
echo ""
echo -e "  Container:  ${CONTAINER_NAME}"
echo -e "  Core URL:   ${CORE_URL}"
echo -e "  Image:      ${IMAGE}"
echo ""
echo -e "  ${BLUE}Commands:${NC}"
echo -e "    docker logs -f ${CONTAINER_NAME}     # View logs"
echo -e "    docker restart ${CONTAINER_NAME}      # Restart"
echo -e "    docker stop ${CONTAINER_NAME}         # Stop"
echo -e "    docker rm -f ${CONTAINER_NAME}        # Remove"
echo ""
