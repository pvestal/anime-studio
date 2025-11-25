#!/bin/bash
# Start the progress monitoring service

cd /opt/tower-anime-production

echo "Starting ComfyUI Progress Monitor..."
echo "This service will monitor all active anime generation jobs"
echo "Press Ctrl+C to stop"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the monitor
python3 progress_monitor.py