#!/usr/bin/env bash
# ==============================================================================
# 🛰️ T.R.A.C.E. Server Runner
# Terrain Analysis & Change Evaluation Platform
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults
PORT="${PORT:-8765}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"
RELOAD=false

# Text formatting
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
NC="\033[0m"

# Parse command line flags
while [[ $# -gt 0 ]]; do
    case $1 in
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --host|-h)
            HOST="$2"
            shift 2
            ;;
        --workers|-w)
            WORKERS="$2"
            shift 2
            ;;
        --reload|-r)
            RELOAD=true
            shift
            ;;
        --help)
            echo "Usage: ./run_server.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --port, -p PORT       Port to listen on (default: 8765)"
            echo "  --host, -h HOST       Host address to bind to (default: 0.0.0.0)"
            echo "  --workers, -w NUM     Number of worker processes (default: 1)"
            echo "  --reload, -r          Enable auto-reload on code change (development)"
            echo "  --help                Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            echo "Usage: ./run_server.sh [--port PORT] [--host HOST] [--workers N] [--reload]"
            exit 1
            ;;
    esac
done

# Load .env file if it exists
if [ -f ".env" ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' .env | xargs -0 2>/dev/null || true)
fi

# Ensure headless matplotlib config directory exists
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib_config}"
mkdir -p "$MPLCONFIGDIR"

# Activate virtual environment if present
if [ -d ".venv" ]; then
    # shellcheck source=/dev/null
    source .venv/bin/activate
fi

export PORT="$PORT"
export HOST="$HOST"

echo -e "${BOLD}${BLUE}======================================================================${NC}"
echo -e "${BOLD}${BLUE}  🛰️ Starting T.R.A.C.E. Satellite Change Intelligence Server${NC}"
echo -e "${BOLD}${BLUE}======================================================================${NC}"
echo -e "  --> Host    : ${GREEN}${HOST}${NC}"
echo -e "  --> Port    : ${GREEN}${PORT}${NC}"
echo -e "  --> Workers : ${GREEN}${WORKERS}${NC}"
echo -e "  --> Web UI  : ${BLUE}http://${HOST}:${PORT}${NC}"
echo -e "======================================================================"
echo ""

if [ "$RELOAD" = true ]; then
    exec uvicorn src.server.app:app --host "$HOST" --port "$PORT" --reload
else
    exec uvicorn src.server.app:app --host "$HOST" --port "$PORT" --workers "$WORKERS"
fi
