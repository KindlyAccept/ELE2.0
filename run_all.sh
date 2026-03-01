#!/usr/bin/env bash

cd "$(dirname "$0")"

source .venv/bin/activate

export PYTHONUNBUFFERED=1
export EMOTION_ROBOT_CONFIG="${EMOTION_ROBOT_CONFIG:-./config.yaml}"

HAILO_OLLAMA_PORT=11434
HAILO_OLLAMA_URL="http://localhost:${HAILO_OLLAMA_PORT}"

# Store PIDs
PIDS=()
HAILO_OLLAMA_PID=""

# Cleanup function - kills all child processes
cleanup() {
    echo ""
    echo "Stopping all services..."

    # Kill stored PIDs
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null
        fi
    done

    sleep 1

    # Force kill if still running
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
    done

    # Also kill by pattern to catch any stragglers
    pkill -9 -f "hailo-ollama" 2>/dev/null || true
    pkill -9 -f "python3 main.py" 2>/dev/null || true
    pkill -9 -f "python3 -m uvicorn app.main:app" 2>/dev/null || true
    pkill -9 -f "vite" 2>/dev/null || true
    pkill -9 -f "node.*web_monitor" 2>/dev/null || true

    echo "All services stopped."
    exit 0
}

# Trap all exit signals
trap cleanup INT TERM EXIT

# Stop any previous runs first
echo "Cleaning up previous processes..."
pkill -9 -f "hailo-ollama" 2>/dev/null || true
pkill -9 -f "python3 main.py" 2>/dev/null || true
pkill -9 -f "python3 -m uvicorn app.main:app" 2>/dev/null || true
pkill -9 -f "vite" 2>/dev/null || true
pkill -9 -f "node.*web_monitor" 2>/dev/null || true
sleep 2

# --- Step 1: Start hailo-ollama ---
echo "[run_all] Starting hailo-ollama (port ${HAILO_OLLAMA_PORT})..."
hailo-ollama serve &
HAILO_OLLAMA_PID=$!
PIDS+=($HAILO_OLLAMA_PID)
echo "[run_all] hailo-ollama started (PID: ${HAILO_OLLAMA_PID})"

# Wait until hailo-ollama is ready (poll /api/version, max 60s)
echo "[run_all] Waiting for hailo-ollama to become ready..."
MAX_WAIT=60
ELAPSED=0
until curl -sf "${HAILO_OLLAMA_URL}/api/version" > /dev/null 2>&1; do
    if ! kill -0 "$HAILO_OLLAMA_PID" 2>/dev/null; then
        echo "ERROR: hailo-ollama process exited unexpectedly."
        exit 1
    fi
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "ERROR: hailo-ollama did not become ready within ${MAX_WAIT}s."
        exit 1
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done
echo "[run_all] hailo-ollama ready (${ELAPSED}s)"

# --- Step 2: Start web monitor backend ---
echo "[run_all] Starting backend..."
cd web_monitor/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log &
PIDS+=($!)
echo "[run_all] Backend started (PID: ${PIDS[-1]})"
cd ../..

# --- Step 3: Start web monitor frontend ---
echo "[run_all] Starting frontend..."
cd web_monitor/frontend
npm run dev &
PIDS+=($!)
echo "[run_all] Frontend started (PID: ${PIDS[-1]})"
cd ../..

echo ""
echo "============================================"
echo "All background services started!"
echo "  - hailo-ollama: ${HAILO_OLLAMA_URL} (PID ${PIDS[0]})"
echo "  - Backend:      http://0.0.0.0:8000  (PID ${PIDS[1]})"
echo "  - Frontend:     http://0.0.0.0:5173  (PID ${PIDS[2]})"
echo ""
echo "Starting robot (foreground, text input enabled)..."
echo "Press Ctrl+C to stop all services."
echo "============================================"
echo ""

# --- Step 4: Run main robot in foreground so stdin (text input) works ---
python3 main.py
