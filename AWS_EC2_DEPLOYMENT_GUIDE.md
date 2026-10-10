# 🛰️ T.R.A.C.E. AWS EC2 Hosting & Deployment Guide

This comprehensive guide details how to deploy **T.R.A.C.E. (Terrain Analysis & Change Evaluation)** — Bi-Temporal Satellite Change Intelligence Engine on Amazon Web Services (AWS) EC2 for live hackathon presentations, client evaluations, and cloud operations.

---

## 📑 Table of Contents
1. [Architecture & Hardware Sizing](#1-architecture--hardware-sizing)
2. [Step-by-Step EC2 Setup](#2-step-by-step-ec2-setup)
   - [Step 1: Launch EC2 Instance](#step-1-launch-ec2-instance)
   - [Step 2: Connect via SSH](#step-2-connect-via-ssh)
   - [Step 3: Clone Repository & Run Automated Setup](#step-3-clone-repository--run-automated-setup)
   - [Step 4: Launch Web Server](#step-4-launch-web-server)
3. [Production Deployment: Systemd & Nginx](#3-production-deployment-systemd--nginx)
   - [Background Service with Systemd](#background-service-with-systemd)
   - [Nginx Reverse Proxy (Port 80)](#nginx-reverse-proxy-port-80)
   - [Free HTTPS / SSL Certificate (Certbot)](#free-https--ssl-certificate-certbot)
4. [Dual Interface Access](#4-dual-interface-access)
5. [AWS Cost Optimization Tips](#5-aws-cost-optimization-tips)
6. [Troubleshooting & FAQs](#6-troubleshooting--faqs)

---

## 1. Architecture & Hardware Sizing

T.R.A.C.E. combines dual deep-learning models (Track A Bitemporal Transformer for high-resolution aerial imagery and Track B Sentinel-2 multispectral network), geospatial vectorization (`rasterio`, `geopandas`, `shapely`), and a high-performance interactive mission control console.

```
       Internet / Evaluators / Officers
                     │
                     ▼
             [Port 80 / 443]
          Nginx Reverse Proxy
                     │
                     ▼ (proxy to 127.0.0.1:8765)
     ┌─────────────────────────────────────────────────────┐
     │  FastAPI + Uvicorn Application Server               │
     │  ├── /api/upload-and-analyse (Bi-Temporal Pipeline) │
     │  ├── /api/explain (Copilot Reasoning)               │
     │  ├── /api/report (11-Part Auditable PDF Dossiers)   │
     │  └── Standalone Single-Page Console (web/index.html)│
     └─────────────────────────────────────────────────────┘
                     │
                     ▼
     ┌─────────────────────────────────────────────────────┐
     │  Deep Learning & Geospatial Engines                 │
     │  ├── Track A: Bitemporal Transformer (BIT)          │
     │  ├── Track B: Sentinel-2 Multispectral MLP          │
     │  ├── Physics Indices: dNBR (Fire) & MNDWI (Flood)   │
     │  └── Vectorizer: True Geodesic Metric Areas (m²)    │
     └─────────────────────────────────────────────────────┘
```

### Recommended EC2 Instance Types

| Use Case | Instance Type | vCPU | RAM | GPU / Acceleration | Est. On-Demand Cost | Est. Spot Cost |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Hackathon Presentation (CPU)** *(Recommended)* | **`t3.xlarge`** | 4 | 16 GB | - | ~$0.166 / hr ($4.00 / day) | ~$0.05 / hr |
| **Budget Minimum (CPU)** | **`t3.large`** | 2 | 8 GB | - | ~$0.083 / hr ($2.00 / day) | ~$0.025 / hr |
| **High-Throughput GPU Inference** | **`g4dn.xlarge`** | 4 | 16 GB | NVIDIA T4 (16 GB) | ~$0.526 / hr ($12.60 / day) | ~$0.16 / hr |
| **AWS Graviton ARM64 (Cost-Saver)** | **`t4g.xlarge`** | 4 | 16 GB | Graviton3 | ~$0.134 / hr ($3.20 / day) | ~$0.04 / hr |

> [!TIP]
> A standard **`t3.xlarge`** instance is ideal for evaluations. Sliding-window inference across standard $1024 \times 1024$ GeoTIFFs takes ~1.5–3.0 seconds on CPU, while memory consumption stays comfortably under 4 GB.

---

## 2. Step-by-Step EC2 Setup

### Step 1: Launch EC2 Instance

1. Log into your [AWS Management Console](https://console.aws.amazon.com/ec2/).
2. Select your target region (e.g. `ap-south-1` Mumbai for lowest latency in India, or `us-east-1`).
3. Click **Launch Instance** and configure:
   - **Name:** `trace-satellite-server`
   - **AMI (Operating System):** **Ubuntu Server 22.04 LTS (HVM)** or **Ubuntu Server 24.04 LTS**, 64-bit (x86).
   - **Instance Type:** `t3.xlarge` (or `g4dn.xlarge` if NVIDIA GPU desired).
   - **Key Pair:** Select or create a `.pem` key pair (e.g., `trace-key.pem`).
   - **Storage:** 40 GB **gp3** SSD root volume (provides ample room for OS, PyTorch, and GeoTIFF scenes).
   - **Security Group (Firewall):** Add the following inbound rules:

| Type | Protocol | Port Range | Source | Description |
| :--- | :---: | :---: | :---: | :--- |
| **SSH** | TCP | 22 | `My IP` (or `0.0.0.0/0`) | Secure Terminal Access |
| **HTTP** | TCP | 80 | `0.0.0.0/0` | Public Web Console Access |
| **HTTPS** | TCP | 443 | `0.0.0.0/0` | Secure SSL Web Access |
| **Custom TCP** | TCP | 8765 | `My IP` | Only needed without Nginx (with `--install-nginx` the app binds to 127.0.0.1) |
| **Custom TCP** | TCP | 8501 | `0.0.0.0/0` | Streamlit GIS Console Port |

4. Click **Launch Instance**.
5. (Recommended) Allocate an **Elastic IP** in `EC2 -> Network & Security -> Elastic IPs` and associate it with the instance so your public IP never changes upon stopping/restarting.

---

### Step 2: Connect via SSH

On your local machine terminal:
```bash
chmod 400 trace-key.pem
ssh -i trace-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
```

---

### Step 3: Clone Repository & Run Automated Setup

Once connected to your EC2 instance:

```bash
# 1. Clone your repository
git clone <YOUR_GIT_REPO_URL>
cd HFD

# 2. Run the automated deployment script
chmod +x setup.sh run_server.sh
./setup.sh
```

> [!NOTE]
> If you are using a CPU instance (like `t3.xlarge`), you can optionally run `./setup.sh --cpu-only` to download the lightweight CPU PyTorch wheels, saving bandwidth and disk space.

The `setup.sh` script automatically:
1. Detects OS and installs system GIS libraries (`gdal-bin`, `libgdal-dev`, `libgeos-dev`, `libproj-dev`, `build-essential`).
2. Creates and configures the Python virtual environment (`.venv`).
3. Installs CUDA or CPU-optimized PyTorch and all geospatial packages from `requirements.txt`.
4. Initializes `.env` configuration.
5. Verifies pre-trained model weights (`checkpoints/BIT_LEVIR_best.pt` and `checkpoints/s2_track_b.pt`).
6. Runs an automated end-to-end sanity check validating model inference and FastAPI endpoints.

---

### Step 4: Launch Web Server

Start the primary server using the helper script:

```bash
./run_server.sh
```

Or run directly with uvicorn:
```bash
source .venv/bin/activate
uvicorn src.server.app:app --host 0.0.0.0 --port 8765 --workers 2
```

Open your browser and navigate to:
```
http://<YOUR_EC2_PUBLIC_IP>:8765
```

---

## 3. High-Speed Production Deployment: Nginx & 24/7 Daemon

To achieve **instant page loading (<100ms)** and keep the application running 24/7 with automatic crash recovery, run the dedicated production deployment script:

```bash
sudo ./setup_production.sh
```

This single command automatically:
1. **Pre-compresses static assets** with `gzip -9` (`web/index.html.gz` and `web/scenes.json.gz`), cutting transfer payloads by >55%.
2. **Configures Nginx on Port 80** to forward to Port 8765, serving pre-compressed static files directly from kernel cache via `gzip_static on;` with zero Python overhead.
3. **Installs the Systemd Daemon** (`trace.service`) configured with `StartLimitIntervalSec=0`, `Restart=always`, and `RestartSec=5` so that if the application crashes for any reason, it automatically restarts in **5 seconds**.
4. **Enables Gzip compression for all proxied API responses** (`gzip_proxied any;`) and configures `client_max_body_size 500M` for multi-band satellite uploads.
5. **Runs an automated health check** verifying port 80 forwarding and daemon status.

---

### Manual Verification of Daemon & Nginx

#### Verify Daemon Auto-Restart Policy
```bash
# Check service status
sudo systemctl status trace

# Verify restart policy (should show Restart=always and 5s delay)
systemctl show trace.service -p Restart -p RestartSecUSec

# Follow live server logs
sudo journalctl -u trace -f
```

#### Test Crash Recovery (Simulate Failure)
To verify that the daemon automatically recovers from crashes in 5 seconds:
```bash
# Kill the running uvicorn process
sudo pkill -9 -f uvicorn

# Within 5 seconds, systemd automatically detects the crash and respawns it:
sleep 6
sudo systemctl status trace
```

#### Nginx Port 80 Forwarding & Speed Verification
```bash
# Test Port 80 response and pre-compressed Gzip delivery
curl -I -H "Accept-Encoding: gzip" http://127.0.0.1/

# You should see:
# HTTP/1.1 200 OK
# Content-Encoding: gzip
# Cache-Control: public, max-age=3600
```

---

### Free HTTPS / SSL Certificate (Certbot)

If you have a domain name or subdomain pointing to your EC2 Elastic IP (e.g. `trace.example.com`):

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d trace.example.com
```

Certbot will automatically obtain a free Let's Encrypt certificate and update your Nginx configuration. It auto-renews before expiry.

---

## 4. Dual Interface Access

T.R.A.C.E. provides two interfaces:

1. **Mission Control Split-View Console (Primary)**:
   - **URL:** `http://<YOUR_EC2_PUBLIC_IP>/` (or port `8765`)
   - **Features:** High-speed curtain swipe comparison, EMS reference overlays, Change-to-Action cards, Pixel Intelligence Inspector (5-level reasoning), hollow polygon inspection, and 1-click executive / technical PDF dossier generator.

2. **Streamlit GIS Analytical Studio (Alternative)**:
   - **Start:** `streamlit run web/app.py --server.port 8501 --server.address 0.0.0.0`
   - **URL:** `http://<YOUR_EC2_PUBLIC_IP>:8501`
   - **Features:** Interactive Folium map inspection, band threshold adjustment, and live GIS layer exploration.

---

## 5. AWS Cost Optimization Tips

- **Use EC2 Spot Instances:** For hackathons and demos, request a Spot instance instead of On-Demand to save **60–75%** on hourly compute costs.
- **Stop When Inactive:** Remember to click **Stop Instance** in the AWS console when not presenting to pause billing (EBS storage only incurs ~$3/month for 40 GB).
- **Elastic IP Caution:** AWS charges a small fee (~$0.005/hr) for Elastic IPs that are allocated but not attached to a running instance. Release the Elastic IP when terminating the project.

---

## 6. Troubleshooting & FAQs

### Q: Port 8765 or Port 80 is not reachable from my browser.
- Verify your EC2 **Security Group** inbound rules. Ensure Port 80 (and 443) have `0.0.0.0/0` allowed. With Nginx installed, 8765 listens on 127.0.0.1 only, so use port 80.
- Static assets returning 403: re-run `sudo ./setup.sh --install-nginx` (it grants nginx read access to `web/`). Check `sudo tail /var/log/nginx/error.log`.
- Verify the server is running: `curl http://localhost:8765/` or `sudo systemctl status trace`.

### Q: Uploading large GeoTIFF files returns "413 Request Entity Too Large".
- If using Nginx, ensure `client_max_body_size 500M;` is configured in `/etc/nginx/sites-available/trace`.

### Q: How do I enable the AI copilot feature?
- Open `.env` and add your Anthropic API key:
  ```env
  ANTHROPIC_API_KEY=sk-ant-api03-...
  ```
- Restart the server: `sudo systemctl restart trace`. Without an API key, the copilot will automatically fall back to deterministic, offline rule-based reasoning.
