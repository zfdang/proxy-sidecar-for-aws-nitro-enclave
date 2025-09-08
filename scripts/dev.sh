#!/bin/bash
# Development and testing script for the sidecar proxy

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Start development environment
start_dev() {
    log_info "Starting development environment..."
    
    cd "$PROJECT_ROOT"
    
    # Create logs directory
    mkdir -p logs
    
    # Start with docker-compose
    docker-compose -f docker/docker-compose.yml up -d
    
    log_info "Development environment started"
    log_info "Host proxy available at: http://localhost:8080"
    log_info "Health check: http://localhost:8080/health"
}

# Stop development environment
stop_dev() {
    log_info "Stopping development environment..."
    
    cd "$PROJECT_ROOT"
    docker-compose -f docker/docker-compose.yml down
    
    log_info "Development environment stopped"
}

# Run tests
run_tests() {
    log_info "Running tests..."
    
    cd "$PROJECT_ROOT"
    
    # Start test environment
    log_info "Starting test environment..."
    docker-compose -f docker/docker-compose.yml up -d host-proxy
    
    # Wait for services to be ready
    sleep 10
    
    # Run demo application as test
    log_info "Running demo application tests..."
    docker run --rm \
        --network host \
        -e PROXY_URL=http://localhost:8080 \
        nitro-enclave-sidecar-client:latest
    
    # Cleanup
    docker-compose -f docker/docker-compose.yml down
    
    log_info "Tests completed"
}

# Show logs
show_logs() {
    local service=${1:-}
    
    cd "$PROJECT_ROOT"
    
    if [ -z "$service" ]; then
        docker-compose -f docker/docker-compose.yml logs -f
    else
        docker-compose -f docker/docker-compose.yml logs -f "$service"
    fi
}

# Clean up development artifacts
clean_dev() {
    log_info "Cleaning development artifacts..."
    
    cd "$PROJECT_ROOT"
    
    # Stop and remove containers
    docker-compose -f docker/docker-compose.yml down -v --remove-orphans
    
    # Remove built images
    docker rmi nitro-enclave-sidecar:latest 2>/dev/null || true
    docker rmi nitro-enclave-sidecar-host:latest 2>/dev/null || true
    docker rmi nitro-enclave-sidecar-client:latest 2>/dev/null || true
    
    # Clean logs
    rm -rf logs/*
    
    log_info "Development cleanup completed"
}

# Install development dependencies
install_deps() {
    log_info "Installing development dependencies..."
    
    if command -v python3 &> /dev/null; then
        pip3 install -r "$PROJECT_ROOT/requirements.txt"
        log_info "Python dependencies installed"
    else
        log_warn "Python3 not found. Please install manually."
    fi
}

# Run in local mode (without Docker)
run_local() {
    log_info "Running in local development mode..."
    
    cd "$PROJECT_ROOT"
    
    # Set Python path
    export PYTHONPATH="$PROJECT_ROOT/src"
    
    # Start host proxy in background
    log_info "Starting host proxy..."
    python3 -m src.host_proxy.main &
    PROXY_PID=$!
    
    # Wait a bit for proxy to start
    sleep 3
    
    # Function to cleanup on exit
    cleanup() {
        log_info "Stopping local services..."
        kill $PROXY_PID 2>/dev/null || true
        exit 0
    }
    
    trap cleanup SIGTERM SIGINT
    
    # Run demo application
    log_info "Running demo application..."
    python3 -m src.demo_app.main
    
    cleanup
}

# Show status
show_status() {
    log_info "Development environment status:"
    
    cd "$PROJECT_ROOT"
    
    # Check Docker containers
    if docker-compose -f docker/docker-compose.yml ps | grep -q "Up"; then
        log_info "Docker services running:"
        docker-compose -f docker/docker-compose.yml ps
    else
        log_warn "No Docker services running"
    fi
    
    # Check local services
    if netstat -tln 2>/dev/null | grep -q ":8080"; then
        log_info "Service running on port 8080"
    else
        log_warn "No service running on port 8080"
    fi
}

# Show help
show_help() {
    echo "Development script for AWS Nitro Enclave Sidecar Proxy"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  start       Start development environment with Docker"
    echo "  stop        Stop development environment"
    echo "  restart     Restart development environment"
    echo "  test        Run tests"
    echo "  logs        Show logs (optionally specify service)"
    echo "  clean       Clean up development artifacts"
    echo "  deps        Install development dependencies"
    echo "  local       Run in local development mode"
    echo "  status      Show development environment status"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start"
    echo "  $0 logs host-proxy"
    echo "  $0 test"
}

# Main command handling
case "${1:-help}" in
    "start")
        start_dev
        ;;
    "stop")
        stop_dev
        ;;
    "restart")
        stop_dev
        sleep 2
        start_dev
        ;;
    "test")
        run_tests
        ;;
    "logs")
        show_logs "$2"
        ;;
    "clean")
        clean_dev
        ;;
    "deps")
        install_deps
        ;;
    "local")
        run_local
        ;;
    "status")
        show_status
        ;;
    "help"|"")
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
