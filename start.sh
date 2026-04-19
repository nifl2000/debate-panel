#!/bin/bash
# Start script for DebatePanel
# Checks if frontend/backend are already running and starts them if needed

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
BACKEND_PID=""
FRONTEND_PID=""

check_backend() {
    lsof -i :8000 2>/dev/null | grep LISTEN | awk '{print $2}'
}

check_frontend() {
    lsof -i :5173 2>/dev/null | grep LISTEN | awk '{print $2}'
}

cleanup() {
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Stopping backend (PID $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "Stopping frontend (PID $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT

echo "=== DebatePanel ==="
echo ""

# Check backend
BACKEND_RUNNING=$(check_backend)
if [ -n "$BACKEND_RUNNING" ]; then
    echo "✓ Backend already running (PID: $BACKEND_RUNNING)"
else
    echo "Starting backend..."
    cd "$BACKEND_DIR"
    uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/debatepanel-backend.log 2>&1 &
    BACKEND_PID=$!
    sleep 2

    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Backend started (PID: $BACKEND_PID)"
    else
        echo "✗ Backend failed to start. Check /tmp/debatepanel-backend.log"
        exit 1
    fi
fi

# Check frontend
FRONTEND_RUNNING=$(check_frontend)
if [ -n "$FRONTEND_RUNNING" ]; then
    echo "✓ Frontend already running (PID: $FRONTEND_RUNNING)"
else
    echo "Starting frontend..."
    cd "$FRONTEND_DIR"
    npx vite --host 0.0.0.0 --port 5173 > /tmp/debatepanel-frontend.log 2>&1 &
    FRONTEND_PID=$!
    sleep 2

    if curl -s http://localhost:5173 > /dev/null 2>&1; then
        echo "✓ Frontend started (PID: $FRONTEND_PID)"
    else
        echo "✗ Frontend failed to start. Check /tmp/debatepanel-frontend.log"
        exit 1
    fi
fi

echo ""
echo "=== Ready ==="
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8000"
echo "Sessions: $BACKEND_DIR/sessions/"
echo ""
echo "Press Ctrl+C to stop (only processes started by this script)"
echo ""

# Wait for user interrupt
wait
