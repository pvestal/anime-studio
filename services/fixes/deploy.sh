#!/bin/bash
# Deploy anime production system fixes

echo "Deploying anime production fixes..."

# Install required Python packages
echo "Installing dependencies..."
pip3 install redis watchdog websockets psycopg2-binary

# Create anime projects directory
echo "Creating anime projects directory structure..."
mkdir -p /mnt/1TB-storage/anime-projects

# Copy systemd service files
echo "Installing systemd services..."
sudo cp anime-websocket.service /etc/systemd/system/
sudo cp anime-file-organizer.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Start services
echo "Starting services..."
sudo systemctl start anime-websocket.service
sudo systemctl start anime-file-organizer.service

# Enable services for auto-start
sudo systemctl enable anime-websocket.service
sudo systemctl enable anime-file-organizer.service

# Check service status
echo ""
echo "Service Status:"
sudo systemctl status anime-websocket.service --no-pager
sudo systemctl status anime-file-organizer.service --no-pager

echo ""
echo "Deployment complete! Key improvements:"
echo "✅ Redis job queue for non-blocking GPU operations"
echo "✅ WebSocket server on ws://localhost:8765 for real-time progress"
echo "✅ File organizer monitoring /mnt/1TB-storage/ComfyUI/output/"
echo "✅ Fixed job status API implementation ready"
echo ""
echo "Next steps:"
echo "1. Integrate job_status_api_fix.py into anime_api.py"
echo "2. Update frontend to connect to WebSocket for progress"
echo "3. Modify ComfyUI workers to report progress to Redis"
echo ""
echo "Test the job queue:"
echo "python3 /opt/tower-anime-production/services/fixes/job_queue.py"