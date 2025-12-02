#!/bin/bash
"""
Startup Script for Redis Queue System
Starts the Redis-based job queue to replace broken ComfyUI queue
"""

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PYTHON_EXEC="$VENV_DIR/bin/python"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

echo_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Redis is running
check_redis() {
    if redis-cli ping >/dev/null 2>&1; then
        echo_success "Redis is running"
        return 0
    else
        echo_error "Redis is not running"
        echo_status "Starting Redis..."
        sudo systemctl start redis-server || sudo systemctl start redis
        sleep 2
        if redis-cli ping >/dev/null 2>&1; then
            echo_success "Redis started successfully"
            return 0
        else
            echo_error "Failed to start Redis"
            return 1
        fi
    fi
}

# Function to check if virtual environment exists
check_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        echo_error "Virtual environment not found at $VENV_DIR"
        echo_status "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        echo_success "Virtual environment created"
    fi

    if [ ! -f "$PYTHON_EXEC" ]; then
        echo_error "Python executable not found in virtual environment"
        return 1
    fi

    echo_success "Virtual environment ready"
    return 0
}

# Function to install dependencies
install_dependencies() {
    echo_status "Installing/updating dependencies..."

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"

    # Required packages
    pip install --upgrade pip
    pip install redis aioredis psycopg2-binary websockets fastapi uvicorn aiohttp psutil

    echo_success "Dependencies installed"
}

# Function to test the Redis queue
test_queue() {
    echo_status "Testing Redis queue system..."

    cd "$SCRIPT_DIR"
    if $PYTHON_EXEC redis_job_queue.py; then
        echo_success "Redis queue test passed"
        return 0
    else
        echo_error "Redis queue test failed"
        return 1
    fi
}

# Function to start the system
start_system() {
    local WORKERS=${1:-2}
    local WEBSOCKET_PORT=${2:-8329}

    echo_status "Starting Redis Queue System..."
    echo_status "Workers: $WORKERS"
    echo_status "WebSocket Port: $WEBSOCKET_PORT"

    cd "$SCRIPT_DIR"

    # Start in background if --daemon flag is provided
    if [[ "$*" == *"--daemon"* ]]; then
        echo_status "Starting as daemon..."
        nohup $PYTHON_EXEC redis_queue_manager.py --workers $WORKERS --websocket-port $WEBSOCKET_PORT --daemon > redis_queue.log 2>&1 &
        PID=$!
        echo "$PID" > redis_queue.pid
        echo_success "Redis Queue System started as daemon (PID: $PID)"
        echo_status "Log file: $SCRIPT_DIR/redis_queue.log"
        echo_status "PID file: $SCRIPT_DIR/redis_queue.pid"
    else
        echo_status "Starting in foreground..."
        $PYTHON_EXEC redis_queue_manager.py --workers $WORKERS --websocket-port $WEBSOCKET_PORT
    fi
}

# Function to stop the system
stop_system() {
    echo_status "Stopping Redis Queue System..."

    # Check for PID file
    if [ -f "$SCRIPT_DIR/redis_queue.pid" ]; then
        PID=$(cat "$SCRIPT_DIR/redis_queue.pid")
        if ps -p $PID > /dev/null 2>&1; then
            echo_status "Stopping daemon (PID: $PID)..."
            kill -TERM $PID
            sleep 5
            if ps -p $PID > /dev/null 2>&1; then
                echo_warning "Process still running, force killing..."
                kill -KILL $PID
            fi
        fi
        rm -f "$SCRIPT_DIR/redis_queue.pid"
    fi

    # Kill any remaining processes
    pkill -f "redis_queue_manager.py" || true
    pkill -f "job_worker.py" || true

    echo_success "Redis Queue System stopped"
}

# Function to show status
show_status() {
    echo_status "Redis Queue System Status"
    echo "=================================="

    # Check Redis
    if redis-cli ping >/dev/null 2>&1; then
        echo_success "Redis: Running"
    else
        echo_error "Redis: Not running"
    fi

    # Check daemon process
    if [ -f "$SCRIPT_DIR/redis_queue.pid" ]; then
        PID=$(cat "$SCRIPT_DIR/redis_queue.pid")
        if ps -p $PID > /dev/null 2>&1; then
            echo_success "Queue Manager: Running (PID: $PID)"
        else
            echo_error "Queue Manager: Not running (stale PID file)"
            rm -f "$SCRIPT_DIR/redis_queue.pid"
        fi
    else
        echo_warning "Queue Manager: Not running"
    fi

    # Check WebSocket port
    if netstat -tuln 2>/dev/null | grep -q ":8329 "; then
        echo_success "WebSocket Server: Running (port 8329)"
    else
        echo_warning "WebSocket Server: Not running"
    fi

    # Get live status if system is running
    cd "$SCRIPT_DIR"
    if $PYTHON_EXEC redis_queue_manager.py --status 2>/dev/null; then
        echo_success "Live status retrieved"
    else
        echo_warning "Could not retrieve live status"
    fi
}

# Function to create systemd service
create_service() {
    echo_status "Creating systemd service..."

    cd "$SCRIPT_DIR"
    if $PYTHON_EXEC redis_queue_manager.py --create-service; then
        echo_success "Systemd service created"
        echo_status "Enable with: sudo systemctl enable tower-anime-redis-queue"
        echo_status "Start with: sudo systemctl start tower-anime-redis-queue"
    else
        echo_error "Failed to create systemd service"
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start [workers] [port]  Start the Redis queue system"
    echo "  stop                    Stop the Redis queue system"
    echo "  restart [workers] [port] Restart the Redis queue system"
    echo "  status                  Show system status"
    echo "  test                    Test the Redis queue system"
    echo "  install                 Install dependencies"
    echo "  create-service          Create systemd service"
    echo "  daemon [workers] [port] Start as daemon"
    echo ""
    echo "Examples:"
    echo "  $0 start                # Start with 2 workers on port 8329"
    echo "  $0 start 4              # Start with 4 workers"
    echo "  $0 start 4 8330         # Start with 4 workers on port 8330"
    echo "  $0 daemon 3             # Start daemon with 3 workers"
    echo "  $0 status               # Show current status"
}

# Main script logic
case "${1:-start}" in
    "start")
        check_redis || exit 1
        check_venv || exit 1
        start_system "${2:-2}" "${3:-8329}"
        ;;
    "stop")
        stop_system
        ;;
    "restart")
        stop_system
        sleep 2
        check_redis || exit 1
        check_venv || exit 1
        start_system "${2:-2}" "${3:-8329}"
        ;;
    "status")
        show_status
        ;;
    "test")
        check_redis || exit 1
        check_venv || exit 1
        test_queue
        ;;
    "install")
        check_venv || exit 1
        install_dependencies
        ;;
    "create-service")
        check_venv || exit 1
        create_service
        ;;
    "daemon")
        check_redis || exit 1
        check_venv || exit 1
        start_system "${2:-2}" "${3:-8329}" --daemon
        ;;
    "help"|"--help"|"-h")
        show_usage
        ;;
    *)
        echo_error "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac