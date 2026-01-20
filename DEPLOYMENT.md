# River Watch - Google Cloud VM Deployment Guide

## Prerequisites

1. **Google Cloud VM Instance** with:
   - Ubuntu 22.04 LTS (recommended)
   - At least 2 vCPUs, 4GB RAM
   - 20GB disk space
   - Firewall rules allowing ports 80 (HTTP) and 443 (HTTPS)

2. **SSH access** to your VM

## Quick Deployment Steps

### Step 1: Connect to Your VM

```bash
# Using gcloud CLI
gcloud compute ssh YOUR_VM_NAME --zone=YOUR_ZONE

# Or using SSH directly
ssh -i ~/.ssh/your-key username@YOUR_VM_IP
```

### Step 2: Install Git and Clone Repository

```bash
sudo apt-get update
sudo apt-get install -y git

# Clone your repository (or transfer files via SCP)
git clone YOUR_REPO_URL riverwatch
cd riverwatch
```

### Step 3: Run Deployment Script

```bash
chmod +x deploy.sh
./deploy.sh YOUR_VM_EXTERNAL_IP
```

Replace `YOUR_VM_EXTERNAL_IP` with your VM's external IP address (e.g., `35.192.123.45`).

The script will:
- Install Docker if not present
- Build all containers
- Start the application
- Run a health check

### Step 4: Access Your App

Open your browser and navigate to:
```
http://YOUR_VM_EXTERNAL_IP
```

---

## Manual Deployment (Alternative)

If you prefer manual deployment:

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
# Log out and back in

# 2. Install Docker Compose
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# 3. Set environment variable
export BACKEND_URL=http://YOUR_VM_IP

# 4. Build and run
docker-compose -f docker-compose.prod.yml up -d --build
```

---

## GCP Firewall Configuration

Make sure your VM's firewall allows HTTP/HTTPS traffic:

```bash
# Allow HTTP
gcloud compute firewall-rules create allow-http \
    --direction=INGRESS \
    --action=ALLOW \
    --rules=tcp:80 \
    --source-ranges=0.0.0.0/0

# Allow HTTPS (for future SSL)
gcloud compute firewall-rules create allow-https \
    --direction=INGRESS \
    --action=ALLOW \
    --rules=tcp:443 \
    --source-ranges=0.0.0.0/0
```

Or via GCP Console:
1. Go to VPC Network → Firewall
2. Create rule: Allow TCP ports 80, 443 from 0.0.0.0/0

---

## Setting Up a Domain Name (Optional)

### Option A: Use a domain with Cloud DNS

1. Go to Cloud DNS and create a zone for your domain
2. Add an A record pointing to your VM's external IP
3. Update the deployment:

```bash
export BACKEND_URL=http://yourdomain.com
docker-compose -f docker-compose.prod.yml up -d --build
```

### Option B: Use nip.io for testing

No DNS setup needed! Just use:
```
http://YOUR_IP.nip.io
```

Example: `http://35.192.123.45.nip.io`

---

## SSL/HTTPS Setup (Recommended for Production)

### Using Let's Encrypt with Certbot

```bash
# Install certbot
sudo apt-get install -y certbot

# Stop nginx temporarily
docker-compose -f docker-compose.prod.yml stop nginx

# Get certificate
sudo certbot certonly --standalone -d yourdomain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/
sudo chmod 644 nginx/ssl/*.pem

# Update nginx.conf - uncomment the HTTPS server block
# Then restart
docker-compose -f docker-compose.prod.yml up -d
```

---

## Management Commands

```bash
# View all container logs
docker-compose -f docker-compose.prod.yml logs -f

# View specific service logs
docker-compose -f docker-compose.prod.yml logs -f backend

# Restart all services
docker-compose -f docker-compose.prod.yml restart

# Stop all services
docker-compose -f docker-compose.prod.yml down

# Stop and remove volumes (WARNING: deletes database!)
docker-compose -f docker-compose.prod.yml down -v

# Rebuild after code changes
docker-compose -f docker-compose.prod.yml up -d --build
```

---

## Troubleshooting

### Container won't start
```bash
docker-compose -f docker-compose.prod.yml logs backend
docker-compose -f docker-compose.prod.yml logs frontend
```

### Port 80 already in use
```bash
sudo lsof -i :80
sudo kill -9 PID
```

### MongoDB connection issues
```bash
docker-compose -f docker-compose.prod.yml exec mongodb mongosh
```

### Frontend build fails
```bash
# Check build logs
docker-compose -f docker-compose.prod.yml logs frontend

# Rebuild from scratch
docker-compose -f docker-compose.prod.yml build --no-cache frontend
```

---

## Architecture

```
Internet
    │
    ▼
┌─────────────────────────────────────┐
│     NGINX (Port 80/443)             │
│   - SSL termination                 │
│   - Route /api/* → Backend          │
│   - Route /ws/* → Backend WebSocket │
│   - Route /* → Frontend             │
└─────────────────────────────────────┘
    │                    │
    ▼                    ▼
┌──────────┐      ┌──────────┐
│ Frontend │      │ Backend  │
│ (React)  │      │ (FastAPI)│
│ nginx    │      │ :8001    │
└──────────┘      └──────────┘
                       │
                       ▼
                 ┌──────────┐
                 │ MongoDB  │
                 │ :27017   │
                 └──────────┘
```

---

## Using with Boat Beacon AIS Feed

Once deployed, configure your AIS connection in the app:

1. Open River Watch in your browser
2. Enter the IP address of your device running Boat Beacon
3. Enter the TCP port (usually 5353)
4. Enter your vessel's MMSI

**Note:** Your GCP VM must be able to reach your Boat Beacon device. If Boat Beacon is on a local network, you may need to set up port forwarding on your router or use a VPN.

---

## Support

For issues, check the logs first:
```bash
docker-compose -f docker-compose.prod.yml logs --tail=100
```
