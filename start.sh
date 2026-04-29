#!/bin/bash
# Start script for DebatePanel
# Checks if frontend/backend are already running and starts them if needed

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
BACKEND_PID=""
FRONTEND_PID=""
STARTED_BACKEND=false
STARTED_FRONTEND=false

check_backend() {
    lsof -i :8000 2>/dev/null | grep LISTEN | awk '{print $2}'
}

check_frontend() {
    lsof -i :5173 2>/dev/null | grep LISTEN | awk '{print $2}'
}

kill_by_pid() {
    local pid=$1
    local name=$2
    if [ -z "$pid" ]; then
        return
    fi
    echo "Stopping $name (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    for i in $(seq 1 10); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "$name did not shut down gracefully, forcing..."
        kill -9 "$pid" 2>/dev/null || true
    fi
}

prompt_kill() {
    local pid=$1
    local name=$2
    if [ -z "$pid" ]; then
        return 0
    fi
    echo ""
    read -rp "$name is already running (PID: $pid). Stop it? [Y/n] " answer
    answer=$(echo "$answer" | tr '[:upper:]' '[:lower:]')
    if [ "$answer" = "n" ] || [ "$answer" = "no" ]; then
        return 1
    fi
    kill_by_pid "$pid" "$name"
    return 0
}

cleanup() {
    echo ""
    echo "Shutting down..."
    if [ "$STARTED_BACKEND" = true ] && [ -n "$BACKEND_PID" ]; then
        kill_by_pid "$BACKEND_PID" "Backend"
    fi
    if [ "$STARTED_FRONTEND" = true ] && [ -n "$FRONTEND_PID" ]; then
        kill_by_pid "$FRONTEND_PID" "Frontend"
    fi
    echo "Done."
    exit 0
}

trap cleanup INT TERM

wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=15
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        if lsof -i :$port 2>/dev/null | grep -q LISTEN; then
            return 0
        fi
        sleep 0.5
        elapsed=$((elapsed + 1))
    done
    echo "✗ $name failed to start within ${max_wait}s"
    return 1
}

echo "=== DebatePanel ==="
echo ""

# Check backend
BACKEND_RUNNING=$(check_backend)
if [ -n "$BACKEND_RUNNING" ]; then
    if prompt_kill "$BACKEND_RUNNING" "Backend"; then
        sleep 1
        echo "Starting backend..."
        (cd "$BACKEND_DIR" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/debatepanel-backend.log 2>&1) &
        BACKEND_PID=$!
        STARTED_BACKEND=true

        if wait_for_port 8000 "Backend"; then
            echo "✓ Backend started (PID: $BACKEND_PID)"
        else
            echo "✗ Backend failed to start. Check /tmp/debatepanel-backend.log"
            exit 1
        fi
    else
        echo "Using existing backend (PID: $BACKEND_RUNNING)"
    fi
else
    echo "Starting backend..."
    (cd "$BACKEND_DIR" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/debatepanel-backend.log 2>&1) &
    BACKEND_PID=$!
    STARTED_BACKEND=true

    if wait_for_port 8000 "Backend"; then
        echo "✓ Backend started (PID: $BACKEND_PID)"
    else
        echo "✗ Backend failed to start. Check /tmp/debatepanel-backend.log"
        exit 1
    fi
fi

# Check frontend
FRONTEND_RUNNING=$(check_frontend)
if [ -n "$FRONTEND_RUNNING" ]; then
    if prompt_kill "$FRONTEND_RUNNING" "Frontend"; then
        sleep 1
        echo "Starting frontend..."
        (cd "$FRONTEND_DIR" && exec npx vite --host 0.0.0.0 --port 5173 >> /tmp/debatepanel-frontend.log 2>&1) &
        FRONTEND_PID=$!
        STARTED_FRONTEND=true

        if wait_for_port 5173 "Frontend"; then
            echo "✓ Frontend started (PID: $FRONTEND_PID)"
        else
            echo "✗ Frontend failed to start. Check /tmp/debatepanel-frontend.log"
            exit 1
        fi
    else
        echo "Using existing frontend (PID: $FRONTEND_RUNNING)"
    fi
else
    echo "Starting frontend..."
    (cd "$FRONTEND_DIR" && exec npx vite --host 0.0.0.0 --port 5173 >> /tmp/debatepanel-frontend.log 2>&1) &
    FRONTEND_PID=$!
    STARTED_FRONTEND=true

    if wait_for_port 5173 "Frontend"; then
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

# Wait for user interrupt - use a loop that responds to signals
while true; do
    # Check if either process died unexpectedly
    if [ "$STARTED_BACKEND" = true ] && [ -n "$BACKEND_PID" ] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "⚠ Backend process died unexpectedly"
        STARTED_BACKEND=false
    fi
    if [ "$STARTED_FRONTEND" = true ] && [ -n "$FRONTEND_PID" ] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "⚠ Frontend process died unexpectedly"
        STARTED_FRONTEND=false
    fi
    sleep 1
done
