#!/bin/bash
# Startup script for Nitro Enclave application

set -e

echo "Starting AWS Nitro Enclave Sidecar Application..."
echo "Timestamp: $(date)"

# Environment setup
export PYTHONPATH="/app/src"
export PYTHONUNBUFFERED=1

# Log environment info
echo "Python version: $(python --version)"
echo "Working directory: $(pwd)"
echo "Python path: $PYTHONPATH"

# Function to start sidecar service
start_sidecar() {
    echo "Starting sidecar service..."
    cd /app
    python -m src.sidecar.main &
    SIDECAR_PID=$!
    echo "Sidecar service started with PID: $SIDECAR_PID"
    return $SIDECAR_PID
}

# Function to start demo application
start_demo() {
    echo "Starting demo application..."
    cd /app
    # Wait a bit for sidecar to initialize
    sleep 5
    python -m src.demo_app.main &
    DEMO_PID=$!
    echo "Demo application started with PID: $DEMO_PID"
    return $DEMO_PID
}

# Signal handler for graceful shutdown
cleanup() {
    echo "Shutting down services..."
    if [ ! -z "$SIDECAR_PID" ]; then
        kill $SIDECAR_PID 2>/dev/null || true
    fi
    if [ ! -z "$DEMO_PID" ]; then
        kill $DEMO_PID 2>/dev/null || true
    fi
    echo "Cleanup completed"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Check if running in demo mode
if [ "$DEMO_MODE" = "true" ]; then
    echo "Running in demo mode - starting both sidecar and demo app"
    start_sidecar
    SIDECAR_PID=$!
    
    start_demo
    DEMO_PID=$!
    
    # Wait for both processes
    wait $SIDECAR_PID $DEMO_PID
else
    echo "Running in sidecar-only mode"
    start_sidecar
    SIDECAR_PID=$!
    
    # Wait for sidecar process
    wait $SIDECAR_PID
fi
