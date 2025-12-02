#!/bin/bash
# Start WebSocket Progress System for Anime Production

SCRIPT_DIR="/opt/tower-anime-production"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install required packages
echo "Installing/updating required packages..."
pip install -q websockets aiohttp psycopg2-binary

# Check if WebSocket server is already running
WEBSOCKET_PID=$(pgrep -f "websocket_progress_server.py")
if [ ! -z "$WEBSOCKET_PID" ]; then
    echo "WebSocket server already running (PID: $WEBSOCKET_PID)"
    echo "Stopping existing server..."
    kill $WEBSOCKET_PID
    sleep 2
fi

# Check if enhanced progress monitor is running
MONITOR_PID=$(pgrep -f "enhanced_progress_monitor.py")
if [ ! -z "$MONITOR_PID" ]; then
    echo "Enhanced progress monitor already running (PID: $MONITOR_PID)"
    echo "Stopping existing monitor..."
    kill $MONITOR_PID
    sleep 2
fi

echo "Starting WebSocket Progress System..."

# Start the enhanced progress monitor with WebSocket support
echo "Starting enhanced progress monitor on port 8329..."
python3 enhanced_progress_monitor.py monitor &
MONITOR_PID=$!

# Wait a moment for the monitor to start
sleep 3

echo "WebSocket Progress System started successfully!"
echo "  Enhanced Monitor PID: $MONITOR_PID"
echo "  WebSocket Server: ws://127.0.0.1:8329"
echo "  Test UI: http://192.168.50.135:8328/static/progress_test.html"
echo ""
echo "To test the system:"
echo "  1. Open browser to: http://192.168.50.135:8328/static/progress_test.html"
echo "  2. Check WebSocket connection status"
echo "  3. Start an anime generation job to see real-time progress"
echo ""
echo "To stop the system:"
echo "  kill $MONITOR_PID"
echo ""
echo "Logs are available in: $SCRIPT_DIR/logs/"

# Create logs directory if it doesn't exist
mkdir -p logs

# Show initial status
echo "Checking system status..."
sleep 2

if kill -0 $MONITOR_PID 2>/dev/null; then
    echo "✅ Enhanced Progress Monitor is running"
else
    echo "❌ Enhanced Progress Monitor failed to start"
fi

# Test database connection
echo "Testing database connection..."
python3 -c "
import psycopg2
from psycopg2.extras import RealDictCursor
try:
    conn = psycopg2.connect(
        host='192.168.50.135',
        database='anime_production',
        user='patrick',
        password='tower_echo_brain_secret_key_2025',
        cursor_factory=RealDictCursor
    )
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM production_jobs WHERE status IN (\\'processing\\', \\'queued\\', \\'pending\\')')
    result = cursor.fetchone()
    print(f'✅ Database connected. Active jobs: {result[\"count\"] if result else 0}')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'❌ Database connection failed: {e}')
"

echo ""
echo "System startup complete!"