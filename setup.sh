#!/usr/bin/env bash
# ==============================================================================
# 🛰️ T.R.A.C.E. (Terrain Analysis & Change Evaluation) Automated Setup Script
# Works on: Ubuntu/Debian (AWS EC2), Amazon Linux 2023, RHEL, and macOS
# ==============================================================================

set -eo pipefail

# Text formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_banner()  {
    echo -e "${BOLD}${BLUE}======================================================================${NC}"
    echo -e "${BOLD}${BLUE}  🛰️ $1${NC}"
    echo -e "${BOLD}${BLUE}======================================================================${NC}"
}

# Resolve root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FORCE_CPU=false
SKIP_SYS_DEPS=false
SKIP_MODEL_CHECK=false
REBUILD_FRONTEND=false
INSTALL_SERVICE=false
INSTALL_NGINX=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --cpu-only)
            FORCE_CPU=true
            shift
            ;;
        --skip-sys-deps)
            SKIP_SYS_DEPS=true
            shift
            ;;
        --skip-model-check)
            SKIP_MODEL_CHECK=true
            shift
            ;;
        --rebuild-frontend)
            REBUILD_FRONTEND=true
            shift
            ;;
        --install-service)
            INSTALL_SERVICE=true
            shift
            ;;
        --install-nginx)
            INSTALL_NGINX=true
            shift
            ;;
        -h|--help)
            echo "Usage: ./setup.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --cpu-only          Force CPU PyTorch installation (recommended for t3.xlarge / c5.xlarge)"
            echo "  --skip-sys-deps     Skip installing OS system packages with apt/dnf"
            echo "  --skip-model-check  Skip verifying checkpoint weights"
            echo "  --rebuild-frontend  Rebuild web/scenes.json and web/index.html console assets"
            echo "  --install-service   Configure & enable systemd service (trace.service) on Linux EC2"
            echo "  --install-nginx     Configure Nginx reverse proxy (Port 80 -> 8765) on Linux EC2"
            echo "  -h, --help          Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Run ./setup.sh --help for usage."
            exit 1
            ;;
    esac
done

log_banner "T.R.A.C.E. Satellite Change Intelligence Engine Setup"

# ------------------------------------------------------------------------------
# Storage Optimization: Disable cache storage to prevent disk exhaustion on EC2
# ------------------------------------------------------------------------------
export PIP_NO_CACHE_DIR=1
export PIP_DISABLE_PIP_VERSION_CHECK=1

get_disk_space() {
    if command -v df &>/dev/null; then
        df -h . | awk 'NR==2 {print $4 " free (" $5 " used of " $2 ")"}'
    else
        echo "unknown"
    fi
}

log_info "Storage Optimization: Disabled pip cache storage (PIP_NO_CACHE_DIR=1)."
log_info "Available disk space: $(get_disk_space)"

# ------------------------------------------------------------------------------
# 1. OS & Architecture Detection
# ------------------------------------------------------------------------------
log_info "Detecting Operating System and Architecture..."
OS_TYPE="$(uname -s)"
ARCH_TYPE="$(uname -m)"

case "$OS_TYPE" in
    Linux*)
        if [ -f /etc/os-release ]; then
            # shellcheck source=/dev/null
            . /etc/os-release
            DISTRO=$ID
            VERSION_ID=${VERSION_ID:-"unknown"}
        else
            DISTRO="linux-generic"
            VERSION_ID="unknown"
        fi
        log_info "Detected Linux ($DISTRO $VERSION_ID) on $ARCH_TYPE"
        ;;
    Darwin*)
        DISTRO="macos"
        log_info "Detected macOS on $ARCH_TYPE"
        ;;
    *)
        DISTRO="unknown"
        log_warn "Unrecognized OS: $OS_TYPE. Attempting generic installation."
        ;;
esac

# ------------------------------------------------------------------------------
# 2. Install System Dependencies (Linux)
# ------------------------------------------------------------------------------
if [ "$SKIP_SYS_DEPS" = false ]; then
    if [ "$DISTRO" = "ubuntu" ] || [ "$DISTRO" = "debian" ]; then
        log_info "Checking/installing Ubuntu/Debian system dependencies..."
        SUDO=""
        if [ "$EUID" -ne 0 ]; then
            if command -v sudo &>/dev/null; then
                SUDO="sudo"
            else
                log_warn "Running non-root without sudo. Skipping apt package installation."
            fi
        fi

        if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
            $SUDO apt-get update -y
            $SUDO apt-get install -y \
                python3 \
                python3-venv \
                python3-pip \
                python3-dev \
                build-essential \
                libgdal-dev \
                gdal-bin \
                libgeos-dev \
                libproj-dev \
                curl \
                git \
                htop
            log_info "Purging apt cache to reclaim disk space..."
            $SUDO apt-get clean
            $SUDO rm -rf /var/lib/apt/lists/* 2>/dev/null || true
            log_success "System libraries installed successfully via apt (cache cleared)."
        fi
    elif [ "$DISTRO" = "amzn" ] || [ "$DISTRO" = "rhel" ] || [ "$DISTRO" = "centos" ] || [ "$DISTRO" = "fedora" ]; then
        log_info "Checking/installing Amazon Linux / RHEL system dependencies..."
        SUDO=""
        if [ "$EUID" -ne 0 ]; then
            if command -v sudo &>/dev/null; then
                SUDO="sudo"
            else
                log_warn "Running non-root without sudo. Skipping dnf package installation."
            fi
        fi

        if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
            $SUDO dnf install -y \
                python3 \
                python3-devel \
                python3-pip \
                gcc \
                gcc-c++ \
                make \
                curl \
                git \
                htop
            log_info "Purging dnf cache to reclaim disk space..."
            $SUDO dnf clean all 2>/dev/null || true
            log_success "System libraries installed successfully via dnf (cache cleared)."
        fi
    fi
else
    log_info "Skipping system packages (--skip-sys-deps)."
fi

# ------------------------------------------------------------------------------
# 3. Python 3 Validation
# ------------------------------------------------------------------------------
log_info "Checking Python 3 installation..."
PY_CMD=""
if [ -x ".venv/bin/python3" ]; then
    PY_CMD=".venv/bin/python3"
elif command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif [ -x "/usr/bin/python3" ]; then
    PY_CMD="/usr/bin/python3"
else
    log_error "Python 3 is not installed or not on PATH. Please install Python 3.10+."
    exit 1
fi

PY_VERSION=$($PY_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_info "Found Python version: $PY_VERSION ($PY_CMD)"

# Ensure Python version is >= 3.10
PY_MAJOR=$($PY_CMD -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PY_CMD -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    log_error "T.R.A.C.E. requires Python 3.10 or newer (detected $PY_VERSION)."
    exit 1
fi

# ------------------------------------------------------------------------------
# 4. Virtual Environment Creation (.venv)
# ------------------------------------------------------------------------------
if [ ! -d ".venv" ]; then
    log_info "Creating Python virtual environment at .venv..."
    $PY_CMD -m venv .venv
    log_success "Created virtual environment."
else
    log_info "Existing virtual environment found at .venv."
fi

# Activate virtual environment
log_info "Activating virtual environment..."
# shellcheck source=/dev/null
source .venv/bin/activate

# Purge any stale pip cache and temp wheels from prior runs
log_info "Purging stale pip caches to maximize available disk storage..."
pip cache purge --quiet 2>/dev/null || true
rm -rf ~/.cache/pip /tmp/pip-* /tmp/pip-ephem-wheel-cache-* /tmp/pip-req-build-* 2>/dev/null || true

log_info "Upgrading pip, setuptools, and wheel (without caching wheels)..."
pip install --no-cache-dir --upgrade pip setuptools wheel --quiet 2>/dev/null || log_warn "Could not upgrade pip/setuptools/wheel (offline or network restricted). Proceeding with current versions."

# ------------------------------------------------------------------------------
# 5. Hardware Acceleration & PyTorch Installation
# ------------------------------------------------------------------------------
log_info "Checking compute acceleration (NVIDIA GPU / CUDA / Apple Silicon)..."
HAS_CUDA=false
if [ "$FORCE_CPU" = false ] && command -v nvidia-smi &>/dev/null; then
    if nvidia-smi &>/dev/null; then
        HAS_CUDA=true
        GPU_NAME=$(nvidia-smi --query-gpu=gpu_name --format=csv,noheader | head -n 1)
        log_success "Detected NVIDIA GPU: $GPU_NAME"
    fi
fi

if python3 -c "import torch" &>/dev/null; then
    TORCH_VER=$(python3 -c "import torch; print(torch.__version__)")
    log_info "PyTorch already installed ($TORCH_VER). Skipping re-download."
else
    if [ "$HAS_CUDA" = true ]; then
        log_info "Installing PyTorch with CUDA 12.1 acceleration (streamed without wheel caching)..."
        pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121
    elif [ "$OS_TYPE" = "Darwin" ]; then
        log_info "Installing PyTorch for macOS (Apple Silicon MPS / CPU, without wheel caching)..."
        pip install --no-cache-dir torch torchvision
    else
        log_info "Installing PyTorch for Linux CPU (streamed without wheel caching, optimized for EC2)..."
        pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
    fi
fi

# ------------------------------------------------------------------------------
# 6. Install Python Dependencies
# ------------------------------------------------------------------------------
log_info "Installing geospatial, machine learning, and web dependencies from requirements.txt (no-cache-dir)..."
pip install --no-cache-dir -r requirements.txt || log_warn "pip install reported warnings or network limits. Verifying modules during sanity check..."

# Final purge of any temp files created during build
log_info "Cleaning up temporary build and pip files..."
pip cache purge --quiet 2>/dev/null || true
rm -rf ~/.cache/pip /tmp/pip-* /tmp/pip-ephem-wheel-cache-* /tmp/pip-req-build-* 2>/dev/null || true
log_info "Storage status after packages: $(get_disk_space)"

# ------------------------------------------------------------------------------
# 7. Environment Configuration (.env)
# ------------------------------------------------------------------------------
if [ ! -f ".env" ]; then
    if [ -f "config/.env.template" ]; then
        log_info "Initializing .env from config/.env.template..."
        cp config/.env.template .env
    else
        log_info "Generating default .env configuration..."
        cat << 'EOF' > .env
# T.R.A.C.E. Environment Configuration
HOST=0.0.0.0
PORT=8765
TRACE_COPILOT_MODEL=claude-opus-5-5
ANTHROPIC_API_KEY=
MPLCONFIGDIR=/tmp/matplotlib_config
EOF
    fi
    log_success "Created .env configuration file."
else
    log_info "Existing .env configuration found."
fi

# Ensure headless matplotlib config cache directory exists
mkdir -p /tmp/matplotlib_config

# ------------------------------------------------------------------------------
# 8. Checkpoint & Pre-trained Model Verification
# ------------------------------------------------------------------------------
if [ "$SKIP_MODEL_CHECK" = false ]; then
    log_info "Verifying pre-trained model checkpoints in checkpoints/..."

    # Check Track A: BIT LEVIR Pretrained Weights (~60 MB)
    CHECKPOINT_BIT="checkpoints/BIT_LEVIR_best.pt"
    if [ -f "$CHECKPOINT_BIT" ]; then
        CHECKPOINT_SIZE=$(wc -c < "$CHECKPOINT_BIT" 2>/dev/null || echo 0)
        if [ "$CHECKPOINT_SIZE" -gt 10000000 ]; then
            log_success "Track A BIT checkpoint verified (~$(( CHECKPOINT_SIZE / 1024 / 1024 )) MB)."
        else
            log_warn "Checkpoint $CHECKPOINT_BIT exists but is under 10MB. It might be a git-lfs pointer."
        fi
    else
        log_warn "Track A checkpoint not found at $CHECKPOINT_BIT."
    fi

    # Check Track B: Sentinel-2 MLP Weights (~241 KB)
    CHECKPOINT_S2="checkpoints/s2_track_b.pt"
    if [ -f "$CHECKPOINT_S2" ]; then
        log_success "Track B Sentinel-2 checkpoint verified ($CHECKPOINT_S2)."
    else
        log_warn "Track B checkpoint not found at $CHECKPOINT_S2. Training quick model..."
        python -m src.models.track_b || log_warn "Track B training skipped. Run: python -m src.models.track_b"
    fi
else
    log_info "Skipping model checkpoint verification (--skip-model-check)."
fi

# ------------------------------------------------------------------------------
# 9. Frontend & Data Assets Verification
# ------------------------------------------------------------------------------
if [ "$REBUILD_FRONTEND" = true ]; then
    log_info "Rebuilding frontend scenes and static bundles..."
    python scripts/build_scenes.py
    python scripts/build_full_app.py
    log_success "Frontend assets rebuilt."
else
    if [ -f "web/index.html" ] && [ -f "web/scenes.json" ]; then
        INDEX_SIZE=$(wc -c < "web/index.html" 2>/dev/null || echo 0)
        log_success "Frontend console ready in web/index.html (~$(( INDEX_SIZE / 1024 )) KB + web/a/ assets)."
    else
        log_warn "web/index.html or web/scenes.json missing. Building now..."
        python scripts/build_scenes.py
        python scripts/build_full_app.py
        log_success "Built web/index.html and web/scenes.json successfully."
    fi
fi

# Pre-compress frontend assets with gzip -9 for instant Nginx & browser delivery
log_info "Pre-compressing frontend assets with gzip -9 for high-speed delivery..."
gzip -kf -9 web/index.html 2>/dev/null || true
gzip -kf -9 web/scenes.json 2>/dev/null || true

# ------------------------------------------------------------------------------
# 10. System Sanity Check
# ------------------------------------------------------------------------------
log_info "Running system sanity check..."
python3 - << 'EOF'
import sys
import torch

print(f"  --> Python: {sys.version.split()[0]}")
print(f"  --> PyTorch: {torch.__version__}")
if torch.cuda.is_available():
    print(f"  --> Compute Backend: CUDA ({torch.cuda.get_device_name(0)})")
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    print("  --> Compute Backend: Apple Silicon Metal (MPS)")
else:
    print("  --> Compute Backend: CPU")

try:
    from src.models.bit_model import load_bit_model, BitemporalTransformer
    from src.models import track_b
    from src.data.geotiff_processor import GeoTIFFProcessor
    from src.geospatial.vectorizer import GeospatialVectorizer
    from src.pipeline.change_engine import ChangeEngine
    from src.server.app import app
    print("  --> Core Modules: BIT, Track B, GeoTIFFProcessor, Vectorizer, ChangeEngine, FastAPI app loaded OK.")
except Exception as e:
    print(f"  [!] Import Error: {e}")
    sys.exit(1)

# Verify checkpoint loading if files exist
import os
if os.path.exists("checkpoints/BIT_LEVIR_best.pt"):
    try:
        load_bit_model("checkpoints/BIT_LEVIR_best.pt", device="cpu")
        print("  --> Pre-trained BIT Weights: Loaded & Verified OK.")
    except Exception as e:
        print(f"  [!] BIT Weights Error: {e}")

if os.path.exists("checkpoints/s2_track_b.pt"):
    try:
        track_b.load()
        print("  --> Pre-trained Track B Weights: Loaded & Verified OK.")
    except Exception as e:
        print(f"  [!] Track B Weights Error: {e}")
EOF

log_success "Sanity check passed!"

# ------------------------------------------------------------------------------
# 11. Optional EC2 Production Configuration (Systemd & Nginx)
# ------------------------------------------------------------------------------
CURRENT_USER="${SUDO_USER:-$(id -un)}"

# Behind Nginx the app only needs to listen on loopback (port 8765 stays private); without it, bind publicly.
BIND_HOST="0.0.0.0"
[ "$INSTALL_NGINX" = true ] && BIND_HOST="127.0.0.1"

if [ "$INSTALL_SERVICE" = true ]; then
    log_info "Configuring systemd service with 5-second automatic crash restart..."
    SERVICE_FILE="/etc/systemd/system/trace.service"

    SUDO=""
    if [ "$EUID" -ne 0 ] && command -v sudo &>/dev/null; then
        SUDO="sudo"
    fi

    TEMP_SERVICE=$(mktemp)
    cat << EOF > "$TEMP_SERVICE"
[Unit]
Description=T.R.A.C.E. Bi-Temporal Satellite Change Intelligence Engine
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=-${SCRIPT_DIR}/.env
# One worker: upload/process/status share in-memory session state (_JOB_STATUS, _ACTIVE_SESSIONS), so
# requests split across workers fail with "Session not found". Pipelines already run in background threads.
ExecStart=${SCRIPT_DIR}/.venv/bin/uvicorn src.server.app:app --host ${BIND_HOST} --port 8765 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
Restart=always
RestartSec=5
RestartPreventExitStatus=
KillMode=mixed
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

    if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
        $SUDO cp "$TEMP_SERVICE" "$SERVICE_FILE"
        rm -f "$TEMP_SERVICE"
        $SUDO chmod 644 "$SERVICE_FILE"
        $SUDO systemctl daemon-reload
        $SUDO systemctl enable trace.service
        $SUDO systemctl restart trace.service
        log_success "Installed and enabled auto-restarting systemd service: $SERVICE_FILE"
        log_info "Daemon status: sudo systemctl status trace"
    else
        log_warn "Root or sudo required to install systemd service. Template saved at config/trace.service.template."
    fi
fi

if [ "$INSTALL_NGINX" = true ]; then
    log_info "Configuring Nginx reverse proxy (Port 80 -> Port 8765)..."
    SUDO=""
    if [ "$EUID" -ne 0 ] && command -v sudo &>/dev/null; then
        SUDO="sudo"
    fi

    if [ -n "$SUDO" ] || [ "$EUID" -eq 0 ]; then
        if ! command -v nginx &>/dev/null; then
            log_info "Installing Nginx..."
            if [ "$DISTRO" = "ubuntu" ] || [ "$DISTRO" = "debian" ]; then
                $SUDO apt-get install -y nginx
            else
                $SUDO dnf install -y nginx
            fi
        fi

        TEMP_NGINX=$(mktemp)
        sed "s|__REPO_PATH__|${SCRIPT_DIR}|g" config/nginx_trace.conf.template > "$TEMP_NGINX"

        if [ -d "/etc/nginx/sites-available" ]; then
            $SUDO cp "$TEMP_NGINX" /etc/nginx/sites-available/trace
            $SUDO ln -sf /etc/nginx/sites-available/trace /etc/nginx/sites-enabled/trace
            $SUDO rm -f /etc/nginx/sites-enabled/default
        elif [ -d "/etc/nginx/conf.d" ]; then
            $SUDO cp "$TEMP_NGINX" /etc/nginx/conf.d/trace.conf
            $SUDO rm -f /etc/nginx/conf.d/default.conf
            # Amazon Linux / RHEL ship a port-80 default_server inside nginx.conf itself, which makes
            # `nginx -t` fail with "duplicate default server". Drop that flag so trace.conf owns port 80.
            $SUDO sed -i.bak -E 's/(listen[^;]*) default_server;/\1;/' /etc/nginx/nginx.conf
        fi
        $SUDO chmod 644 /etc/nginx/sites-available/trace /etc/nginx/conf.d/trace.conf 2>/dev/null || true
        rm -f "$TEMP_NGINX"

        # Nginx serves web/ straight from disk, but EC2 home dirs are 700/750, so the nginx user gets
        # 403 on every static asset. Grant traverse (x) on each parent dir and read on web/ only.
        D="$SCRIPT_DIR"
        while [ "$D" != "/" ]; do $SUDO chmod o+x "$D"; D="$(dirname "$D")"; done
        $SUDO chmod -R o+rX "$SCRIPT_DIR/web"

        # SELinux (enforcing on RHEL): allow proxying to 8765 and reading web/ from a home directory
        if command -v getenforce &>/dev/null && [ "$(getenforce)" = "Enforcing" ]; then
            $SUDO setsebool -P httpd_can_network_connect 1
            $SUDO chcon -R -t httpd_sys_content_t "$SCRIPT_DIR/web"
        fi

        if $SUDO nginx -t; then
            $SUDO systemctl enable nginx
            $SUDO systemctl restart nginx
            sleep 2
            # Verify the whole path: page from disk, a hashed asset from disk, and an API call proxied to 8765
            ASSET=$(ls web/a/*.jpeg 2>/dev/null | head -1)
            for URL in "/" ${ASSET:+"/static/${ASSET#web/}"} "/api/health"; do
                CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1${URL}" || echo 000)
                if [ "$CODE" = "200" ]; then
                    log_success "Port 80 ${URL} -> HTTP 200"
                else
                    log_warn "Port 80 ${URL} -> HTTP ${CODE} (logs: sudo tail /var/log/nginx/error.log; sudo journalctl -u trace -n 30)"
                fi
            done
            log_success "Nginx reverse proxy active: Port 80 forwards to 127.0.0.1:8765 with gzip_static enabled."
        else
            log_warn "Nginx configuration syntax check failed. Please review /etc/nginx/."
        fi
    else
        log_warn "Root or sudo required to configure Nginx."
    fi
fi

# ------------------------------------------------------------------------------
# 12. Completion & Next Steps
# ------------------------------------------------------------------------------
echo ""
log_banner "Setup Complete! How to Run T.R.A.C.E."
echo ""
echo -e "1. ${BOLD}Start the FastAPI Web & Intelligence Server:${NC}"
echo -e "   source .venv/bin/activate"
echo -e "   uvicorn src.server.app:app --host 0.0.0.0 --port 8765"
echo -e "   ${GREEN}Or simply run:${NC} ./run_server.sh"
if [ "$INSTALL_NGINX" = true ]; then
echo -e "   ${BLUE}Access UI at:${NC} http://<YOUR_EC2_PUBLIC_IP>/ (Nginx on port 80; 8765 is loopback-only)"
else
echo -e "   ${BLUE}Access UI at:${NC} http://<YOUR_EC2_PUBLIC_IP>:8765 (or http://localhost:8765)"
echo -e "   ${BLUE}Production:${NC} sudo ./setup.sh --install-service --install-nginx  (serves on port 80)"
fi
echo ""
echo -e "2. ${BOLD}Run Alternative Streamlit GIS Console:${NC}"
echo -e "   streamlit run web/app.py --server.port 8501 --server.address 0.0.0.0"
echo -e "   ${BLUE}Access UI at:${NC} http://<YOUR_EC2_PUBLIC_IP>:8501"
echo ""
echo -e "3. ${BOLD}Run Verification Self-Checks & Tests:${NC}"
echo -e "   python tests/test_synthetic.py"
echo -e "   python -m src.geospatial.events"
echo ""
echo -e "4. ${BOLD}Run Full Quantitative Benchmark Evaluation:${NC}"
echo -e "   python src/models/evaluate.py"
echo ""
if [ "$INSTALL_SERVICE" = true ]; then
echo -e "5. ${BOLD}Systemd Service Management:${NC}"
echo -e "   sudo systemctl start trace"
echo -e "   sudo systemctl status trace"
echo -e "   sudo journalctl -u trace -f"
echo ""
fi
echo -e "${BOLD}AWS Deployment Guide:${NC} See ${GREEN}AWS_EC2_DEPLOYMENT_GUIDE.md${NC} for complete AWS instructions."
echo ""
