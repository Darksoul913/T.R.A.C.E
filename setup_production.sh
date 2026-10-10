#!/usr/bin/env bash
# ==============================================================================
# 🛰️ T.R.A.C.E. Production Deployment: Nginx (Port 80 -> 127.0.0.1:8765) & Systemd Daemon
# Thin wrapper so production uses the same, single nginx/systemd setup path as setup.sh.
# ==============================================================================

exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/setup.sh" --skip-sys-deps --skip-model-check --install-service --install-nginx "$@"
