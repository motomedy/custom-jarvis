#!/bin/bash
# Supervisor script to auto-restart JARVIS backend if it crashes
LOGFILE="jarvis_backend.log"
PORT=${JARVIS_PORT:-8340}

while true; do
  echo "[Supervisor] Starting backend at $(date)" | tee -a "$LOGFILE"
  source .venv/bin/activate
  export JARVIS_MODE=web
  python3 main.py >> "$LOGFILE" 2>&1
  EXIT_CODE=$?
  echo "[Supervisor] Backend exited with code $EXIT_CODE at $(date)" | tee -a "$LOGFILE"
  echo "[Supervisor] Restarting in 2 seconds..." | tee -a "$LOGFILE"
  sleep 2
done
