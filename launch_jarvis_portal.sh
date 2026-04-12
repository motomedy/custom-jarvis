#!/bin/bash
# Unified launcher for JARVIS portal (backend + frontend + browser)

# Load port from .env or default to 8340
if [ -f .env ]; then
  export $(grep JARVIS_PORT .env | xargs)
fi
PORT=${JARVIS_PORT:-8340}

# Start backend (assumes main.py or run_jarvis.sh)
if [ -f run_jarvis.sh ]; then
  ./run_jarvis.sh &
else
  python3 main.py &
fi
BACKEND_PID=$!

# Start frontend (assumes frontend/ with npm)
if [ -d frontend ]; then
  cd frontend
  if [ -f package.json ]; then
    npm run dev &
    FRONTEND_PID=$!
  fi
  cd ..
fi

# Wait a few seconds for servers to start
sleep 5

# Open browser to portal
open "http://localhost:$PORT"

# Wait for backend/frontend to exit
wait $BACKEND_PID
if [ ! -z "$FRONTEND_PID" ]; then
  wait $FRONTEND_PID
fi
