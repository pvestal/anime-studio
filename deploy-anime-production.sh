#!/bin/bash
# Tower Anime Production Service Deployment Script
# Follows Tower production deployment patterns

set -e

SERVICE_NAME="tower-anime-production"
SOURCE_DIR="/home/patrick/Documents/Tower/services/anime-production"
PROD_DIR="/opt/tower-anime-production"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "🎬 Deploying Tower Anime Production Service..."

# Stop existing service if running
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "⏹️  Stopping existing service..."
    sudo systemctl stop $SERVICE_NAME
fi

# Remove old broken service
if systemctl is-enabled --quiet tower-anime; then
    echo "🗑️  Removing broken tower-anime service..."
    sudo systemctl stop tower-anime 2>/dev/null || true
    sudo systemctl disable tower-anime 2>/dev/null || true
fi

# Create production directory
echo "📁 Creating production directory..."
sudo mkdir -p $PROD_DIR
sudo chown patrick:patrick $PROD_DIR

# Copy source files
echo "📋 Copying service files..."
cp -r $SOURCE_DIR/* $PROD_DIR/
sudo chown -R patrick:patrick $PROD_DIR

# Setup virtual environment
echo "🐍 Setting up Python environment..."
cd $PROD_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service file
echo "⚙️  Creating systemd service..."
sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Tower Anime Production Service
After=network.target postgresql.service

[Service]
Type=simple
User=patrick
Group=patrick
WorkingDirectory=$PROD_DIR
Environment=PATH=$PROD_DIR/venv/bin
Environment=PYTHONPATH=$PROD_DIR
ExecStart=$PROD_DIR/venv/bin/python api/main.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
echo "🔄 Configuring systemd..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

# Create database schema
echo "🗄️  Setting up database schema..."
source $PROD_DIR/venv/bin/activate
python -c "
from api.main import Base, engine
Base.metadata.create_all(bind=engine)
print('Database schema created successfully')
"

# Add nginx configuration
echo "🌐 Updating nginx configuration..."
NGINX_CONFIG="/etc/nginx/sites-available/tower.conf"

# Check if anime-production location already exists
if ! grep -q "location /anime" $NGINX_CONFIG 2>/dev/null; then
    # Add location block before the closing brace
    sudo sed -i '/^}$/i \
    # Tower Anime Production Service\
    location /anime {\
        proxy_pass http://127.0.0.1:8300;\
        proxy_set_header Host $host;\
        proxy_set_header X-Real-IP $remote_addr;\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\
        proxy_set_header X-Forwarded-Proto $scheme;\
    }\
' $NGINX_CONFIG

    echo "📝 Added nginx location block for anime production"
    sudo nginx -t && sudo systemctl reload nginx
else
    echo "📝 Nginx configuration already includes anime production"
fi

# Start service
echo "🚀 Starting service..."
sudo systemctl start $SERVICE_NAME

# Check service status
sleep 3
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "✅ Service started successfully!"
    echo "🌐 Service available at: https://***REMOVED***/anime"
    echo "📊 API docs: https://***REMOVED***/anime/docs"
else
    echo "❌ Service failed to start. Checking logs..."
    sudo journalctl -u $SERVICE_NAME -n 20 --no-pager
    exit 1
fi

# Test API endpoint
echo "🧪 Testing API endpoint..."
if curl -f http://localhost:8300/health > /dev/null 2>&1; then
    echo "✅ API health check passed"
else
    echo "⚠️  API health check failed - service may still be starting"
fi

echo "🎉 Tower Anime Production Service deployment complete!"
echo ""
echo "📋 Service Information:"
echo "   Name: $SERVICE_NAME"
echo "   Location: $PROD_DIR"
echo "   Port: 8300"
echo "   Status: $(systemctl is-active $SERVICE_NAME)"
echo ""
echo "💡 Useful commands:"
echo "   sudo systemctl status $SERVICE_NAME"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo "   curl http://localhost:8300/health"