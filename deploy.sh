#!/bin/bash

# River Watch - GCP VM Deployment Script
# Usage: ./deploy.sh [YOUR_VM_IP_OR_DOMAIN]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 River Watch Deployment Script${NC}"
echo "=================================="

# Check if domain/IP is provided
if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: ./deploy.sh [YOUR_VM_IP_OR_DOMAIN]${NC}"
    echo "Example: ./deploy.sh 35.192.123.45"
    echo "Example: ./deploy.sh riverwatch.example.com"
    exit 1
fi

BACKEND_URL="http://$1"
echo -e "${GREEN}Backend URL will be: ${BACKEND_URL}${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Installing...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo -e "${GREEN}Docker installed. Please log out and back in, then run this script again.${NC}"
    exit 0
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed. Installing...${NC}"
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

# Create SSL directory (even if empty for now)
mkdir -p nginx/ssl

# Export the backend URL for docker-compose
export BACKEND_URL="${BACKEND_URL}"

# Stop existing containers
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Build and start containers
echo -e "${GREEN}Building and starting containers...${NC}"
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to start
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Health check
echo -e "${YELLOW}Running health check...${NC}"
if curl -s "http://localhost/health" | grep -q "healthy"; then
    echo -e "${GREEN}✅ Health check passed!${NC}"
else
    echo -e "${RED}❌ Health check failed. Checking logs...${NC}"
    docker-compose -f docker-compose.prod.yml logs --tail=50
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Access your app at: ${GREEN}http://$1${NC}"
echo ""
echo "Useful commands:"
echo "  View logs:    docker-compose -f docker-compose.prod.yml logs -f"
echo "  Stop:         docker-compose -f docker-compose.prod.yml down"
echo "  Restart:      docker-compose -f docker-compose.prod.yml restart"
echo ""
