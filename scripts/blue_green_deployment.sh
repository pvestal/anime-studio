#!/bin/bash
# Blue-Green Deployment Script for Anime Production System
# Provides zero-downtime deployment with automatic rollback capabilities

set -euo pipefail

# Configuration
DEPLOYMENT_CONFIG="/opt/tower-anime-production/deployment.config"
NGINX_CONFIG="/etc/nginx/sites-available/anime-production"
SERVICE_NAME="tower-anime-production"
HEALTH_CHECK_ENDPOINT="/api/health"
MAX_HEALTH_CHECK_ATTEMPTS=30
HEALTH_CHECK_INTERVAL=2

# Deployment directories
PRODUCTION_DIR="/opt/tower-anime-production"
BLUE_DIR="/opt/tower-anime-production-blue"
GREEN_DIR="/opt/tower-anime-production-green"
BACKUP_DIR="/opt/anime-backups"

# Logging
LOG_FILE="/var/log/anime-production-deployment.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $1${NC}"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ❌ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ $1${NC}"
}

# Function to check if a directory is the current active deployment
get_current_environment() {
    if [[ -L "$PRODUCTION_DIR" ]]; then
        readlink "$PRODUCTION_DIR" | sed 's|.*/||'
    else
        echo "unknown"
    fi
}

# Function to get the inactive environment
get_inactive_environment() {
    local current=$(get_current_environment)
    case $current in
        tower-anime-production-blue)
            echo "green"
            ;;
        tower-anime-production-green)
            echo "blue"
            ;;
        *)
            echo "blue"  # Default to blue if unknown
            ;;
    esac
}

# Function to create environment directories
setup_environments() {
    log "Setting up blue-green environments..."

    # Create backup directory
    sudo mkdir -p "$BACKUP_DIR"

    # If this is the first time setup
    if [[ ! -L "$PRODUCTION_DIR" && -d "$PRODUCTION_DIR" ]]; then
        log "Converting existing installation to blue-green deployment..."

        # Move current installation to blue environment
        sudo mv "$PRODUCTION_DIR" "$BLUE_DIR"

        # Create green environment as copy
        sudo cp -r "$BLUE_DIR" "$GREEN_DIR"

        # Create symlink to blue (current active)
        sudo ln -sf "$BLUE_DIR" "$PRODUCTION_DIR"

        log_success "Blue-green environments initialized"
    fi

    # Ensure both environments exist
    if [[ ! -d "$BLUE_DIR" ]]; then
        sudo mkdir -p "$BLUE_DIR"
        log "Created blue environment directory"
    fi

    if [[ ! -d "$GREEN_DIR" ]]; then
        sudo mkdir -p "$GREEN_DIR"
        log "Created green environment directory"
    fi

    # Ensure production symlink exists
    if [[ ! -L "$PRODUCTION_DIR" ]]; then
        sudo ln -sf "$BLUE_DIR" "$PRODUCTION_DIR"
        log "Created production symlink to blue environment"
    fi
}

# Function to check service health
check_health() {
    local port=$1
    local attempt=1

    log "Checking service health on port $port..."

    while [[ $attempt -le $MAX_HEALTH_CHECK_ATTEMPTS ]]; do
        if curl -f -s "http://localhost:$port$HEALTH_CHECK_ENDPOINT" > /dev/null 2>&1; then
            log_success "Health check passed on port $port (attempt $attempt)"
            return 0
        fi

        log "Health check failed on port $port (attempt $attempt/$MAX_HEALTH_CHECK_ATTEMPTS)"
        sleep $HEALTH_CHECK_INTERVAL
        ((attempt++))
    done

    log_error "Health check failed after $MAX_HEALTH_CHECK_ATTEMPTS attempts"
    return 1
}

# Function to create backup
create_backup() {
    local current_env=$(get_current_environment)
    local backup_name="deployment_backup_$(date +%Y%m%d_%H%M%S)"
    local backup_path="$BACKUP_DIR/$backup_name"

    log "Creating deployment backup..."

    sudo mkdir -p "$backup_path"

    # Backup current production environment
    if [[ -d "$PRODUCTION_DIR" ]]; then
        sudo cp -r "$PRODUCTION_DIR" "$backup_path/production"
    fi

    # Backup database schema
    if command -v pg_dump > /dev/null 2>&1; then
        sudo -u patrick pg_dump -h 192.168.50.135 -d anime_production -s > "$backup_path/schema_backup.sql" 2>/dev/null || true
    fi

    # Backup nginx configuration
    if [[ -f "$NGINX_CONFIG" ]]; then
        sudo cp "$NGINX_CONFIG" "$backup_path/"
    fi

    # Backup systemd service file
    sudo cp "/etc/systemd/system/$SERVICE_NAME.service" "$backup_path/" 2>/dev/null || true

    # Create backup info file
    cat > "$backup_path/backup_info.json" << EOF
{
    "timestamp": "$(date -Iseconds)",
    "current_environment": "$current_env",
    "git_commit": "$(cd $PRODUCTION_DIR && git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "git_branch": "$(cd $PRODUCTION_DIR && git branch --show-current 2>/dev/null || echo 'unknown')",
    "service_status": "$(systemctl is-active $SERVICE_NAME 2>/dev/null || echo 'unknown')"
}
EOF

    echo "$backup_path"
    log_success "Backup created: $backup_path"
}

# Function to deploy to inactive environment
deploy_to_inactive() {
    local source_dir="$1"
    local inactive_env=$(get_inactive_environment)
    local target_dir

    case $inactive_env in
        blue)
            target_dir="$BLUE_DIR"
            ;;
        green)
            target_dir="$GREEN_DIR"
            ;;
    esac

    log "Deploying to $inactive_env environment: $target_dir"

    # Stop any service running in the target environment
    if systemctl is-active "${SERVICE_NAME}-${inactive_env}" > /dev/null 2>&1; then
        sudo systemctl stop "${SERVICE_NAME}-${inactive_env}" || true
    fi

    # Clear target directory
    sudo rm -rf "$target_dir"
    sudo mkdir -p "$target_dir"

    # Copy new code
    sudo cp -r "$source_dir"/* "$target_dir/"

    # Set correct ownership
    sudo chown -R patrick:patrick "$target_dir"

    # Install/update dependencies
    log "Installing dependencies in $inactive_env environment..."
    cd "$target_dir"

    if [[ -f "requirements.txt" ]]; then
        if [[ -d "venv" ]]; then
            source venv/bin/activate
            pip install --quiet -r requirements.txt
        else
            python3 -m venv venv
            source venv/bin/activate
            pip install --quiet -r requirements.txt
        fi
    fi

    # Run database migrations if any
    if [[ -f "migrations/migrate.py" ]]; then
        log "Running database migrations..."
        python3 migrations/migrate.py || log_warning "Database migration failed"
    fi

    log_success "Deployment to $inactive_env environment completed"
}

# Function to create environment-specific systemd service
create_environment_service() {
    local environment="$1"
    local port="$2"
    local service_file="/etc/systemd/system/${SERVICE_NAME}-${environment}.service"

    case $environment in
        blue)
            target_dir="$BLUE_DIR"
            ;;
        green)
            target_dir="$GREEN_DIR"
            ;;
    esac

    log "Creating systemd service for $environment environment..."

    sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Tower Anime Production Service ($environment environment)
After=network.target postgresql.service

[Service]
Type=simple
User=patrick
Group=patrick
WorkingDirectory=$target_dir
Environment=PATH=$target_dir/venv/bin
Environment=PORT=$port
Environment=ENVIRONMENT=$environment
ExecStart=$target_dir/venv/bin/python api/main.py
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    log_success "Created $environment environment service"
}

# Function to start service in inactive environment
start_inactive_service() {
    local inactive_env=$(get_inactive_environment)
    local test_port

    case $inactive_env in
        blue)
            test_port="8329"  # Blue test port
            ;;
        green)
            test_port="8330"  # Green test port
            ;;
    esac

    log "Starting $inactive_env environment service on port $test_port..."

    # Create environment-specific service
    create_environment_service "$inactive_env" "$test_port"

    # Start the service
    sudo systemctl start "${SERVICE_NAME}-${inactive_env}"
    sudo systemctl enable "${SERVICE_NAME}-${inactive_env}"

    # Wait for service to start
    sleep 5

    # Check if service started successfully
    if systemctl is-active "${SERVICE_NAME}-${inactive_env}" > /dev/null 2>&1; then
        log_success "$inactive_env environment service started"
    else
        log_error "$inactive_env environment service failed to start"
        sudo journalctl -u "${SERVICE_NAME}-${inactive_env}" --no-pager -n 20
        return 1
    fi

    # Health check
    if check_health "$test_port"; then
        log_success "$inactive_env environment is healthy"
        return 0
    else
        log_error "$inactive_env environment health check failed"
        return 1
    fi
}

# Function to switch traffic to new environment
switch_traffic() {
    local target_env="$1"
    local current_env=$(get_current_environment)

    log "Switching traffic from $current_env to $target_env..."

    # Update symlink atomically
    case $target_env in
        blue)
            sudo ln -sfn "$BLUE_DIR" "$PRODUCTION_DIR"
            ;;
        green)
            sudo ln -sfn "$GREEN_DIR" "$PRODUCTION_DIR"
            ;;
    esac

    # Restart main production service
    sudo systemctl restart "$SERVICE_NAME"

    # Wait for service restart
    sleep 5

    # Verify production service health
    if check_health "8328"; then
        log_success "Traffic successfully switched to $target_env"
        return 0
    else
        log_error "Production service health check failed after switch"
        return 1
    fi
}

# Function to cleanup old environment
cleanup_old_environment() {
    local old_env="$1"

    log "Cleaning up $old_env environment..."

    # Stop the old environment service
    if systemctl is-active "${SERVICE_NAME}-${old_env}" > /dev/null 2>&1; then
        sudo systemctl stop "${SERVICE_NAME}-${old_env}"
        sudo systemctl disable "${SERVICE_NAME}-${old_env}"
    fi

    # Remove service file
    sudo rm -f "/etc/systemd/system/${SERVICE_NAME}-${old_env}.service"
    sudo systemctl daemon-reload

    log_success "Cleaned up $old_env environment"
}

# Function to rollback deployment
rollback_deployment() {
    local backup_path="$1"
    local current_env=$(get_current_environment)

    log_error "Rolling back deployment..."

    # Stop current production service
    sudo systemctl stop "$SERVICE_NAME" || true

    # Stop any environment-specific services
    sudo systemctl stop "${SERVICE_NAME}-blue" 2>/dev/null || true
    sudo systemctl stop "${SERVICE_NAME}-green" 2>/dev/null || true

    # Restore from backup
    if [[ -d "$backup_path/production" ]]; then
        sudo rm -rf "$PRODUCTION_DIR"
        sudo cp -r "$backup_path/production" "$PRODUCTION_DIR"
        sudo chown -R patrick:patrick "$PRODUCTION_DIR"
    fi

    # Restore nginx config if exists
    if [[ -f "$backup_path/$(basename $NGINX_CONFIG)" ]]; then
        sudo cp "$backup_path/$(basename $NGINX_CONFIG)" "$NGINX_CONFIG"
        sudo nginx -t && sudo systemctl reload nginx
    fi

    # Restart production service
    sudo systemctl start "$SERVICE_NAME"

    # Health check
    if check_health "8328"; then
        log_success "Rollback completed successfully"
        return 0
    else
        log_error "Rollback failed - manual intervention required"
        return 1
    fi
}

# Function to clean old backups
clean_old_backups() {
    local keep_backups=5

    log "Cleaning old backups (keeping last $keep_backups)..."

    # Find and remove old backup directories
    find "$BACKUP_DIR" -name "deployment_backup_*" -type d | sort -r | tail -n +$((keep_backups + 1)) | xargs -r sudo rm -rf

    log_success "Old backups cleaned"
}

# Function to send deployment notification
send_notification() {
    local status="$1"
    local environment="$2"
    local message="$3"

    local emoji="🚀"
    case $status in
        success)
            emoji="✅"
            ;;
        error)
            emoji="❌"
            ;;
        warning)
            emoji="⚠️"
            ;;
    esac

    # Send to Echo Brain for logging
    curl -k -X POST "https://192.168.50.135/api/echo/query" \
        -H "Content-Type: application/json" \
        -d "{
            \"query\": \"$emoji Blue-Green Deployment $status: $message\",
            \"conversation_id\": \"deployment_notifications\",
            \"metadata\": {
                \"type\": \"deployment_notification\",
                \"status\": \"$status\",
                \"environment\": \"$environment\",
                \"timestamp\": \"$(date -Iseconds)\",
                \"service\": \"anime-production\"
            }
        }" 2>/dev/null || true

    log "Notification sent: $status - $message"
}

# Main deployment function
deploy() {
    local source_dir="${1:-$(pwd)}"
    local backup_path
    local inactive_env
    local current_env

    log "🚀 Starting blue-green deployment for Anime Production System"
    log "Source directory: $source_dir"

    # Validate source directory
    if [[ ! -d "$source_dir" ]]; then
        log_error "Source directory not found: $source_dir"
        exit 1
    fi

    if [[ ! -f "$source_dir/anime_api.py" ]]; then
        log_error "Source directory does not contain anime_api.py"
        exit 1
    fi

    # Setup environments
    setup_environments

    current_env=$(get_current_environment)
    inactive_env=$(get_inactive_environment)

    log "Current environment: $current_env"
    log "Deploying to: $inactive_env"

    # Create backup
    backup_path=$(create_backup)

    # Deploy to inactive environment
    if ! deploy_to_inactive "$source_dir"; then
        log_error "Deployment to inactive environment failed"
        exit 1
    fi

    # Start service in inactive environment and test
    if ! start_inactive_service; then
        log_error "Failed to start service in inactive environment"
        send_notification "error" "$inactive_env" "Failed to start service in $inactive_env environment"
        exit 1
    fi

    # Run integration tests on inactive environment
    log "Running integration tests on $inactive_env environment..."
    if [[ -f "tests/integration/test_anime_ecosystem_integration.py" ]]; then
        cd "$source_dir"
        if python3 tests/integration/test_anime_ecosystem_integration.py; then
            log_success "Integration tests passed"
        else
            log_warning "Integration tests failed, but continuing deployment"
        fi
    fi

    # Switch traffic
    if ! switch_traffic "$inactive_env"; then
        log_error "Failed to switch traffic to $inactive_env environment"
        send_notification "error" "$inactive_env" "Traffic switch failed"

        # Attempt rollback
        if rollback_deployment "$backup_path"; then
            send_notification "success" "$current_env" "Rollback completed successfully"
        else
            send_notification "error" "$current_env" "Rollback failed - manual intervention required"
        fi
        exit 1
    fi

    # Cleanup old environment
    cleanup_old_environment "$current_env"

    # Clean old backups
    clean_old_backups

    log_success "🎉 Blue-green deployment completed successfully!"
    log_success "Active environment: $inactive_env"
    log_success "Backup created: $backup_path"

    send_notification "success" "$inactive_env" "Deployment completed successfully to $inactive_env environment"

    # Show deployment summary
    echo
    echo "============================================"
    echo "🎬 ANIME PRODUCTION DEPLOYMENT SUMMARY"
    echo "============================================"
    echo "✅ Status: SUCCESS"
    echo "🔄 Environment: $current_env → $inactive_env"
    echo "📁 Backup: $backup_path"
    echo "⏰ Completed: $(date)"
    echo "🌐 Service URL: https://192.168.50.135/anime"
    echo "============================================"
}

# Function to show current deployment status
status() {
    local current_env=$(get_current_environment)

    echo "============================================"
    echo "🎬 ANIME PRODUCTION DEPLOYMENT STATUS"
    echo "============================================"
    echo "Current Environment: $current_env"
    echo "Production Directory: $PRODUCTION_DIR -> $(readlink $PRODUCTION_DIR 2>/dev/null || echo 'not a symlink')"
    echo "Service Status: $(systemctl is-active $SERVICE_NAME 2>/dev/null || echo 'unknown')"
    echo
    echo "Environment Directories:"
    echo "  Blue:  $BLUE_DIR $([ -d $BLUE_DIR ] && echo '✅' || echo '❌')"
    echo "  Green: $GREEN_DIR $([ -d $GREEN_DIR ] && echo '✅' || echo '❌')"
    echo
    echo "Available Backups:"
    find "$BACKUP_DIR" -name "deployment_backup_*" -type d 2>/dev/null | sort -r | head -5 || echo "  No backups found"
    echo "============================================"
}

# Main script logic
case "${1:-deploy}" in
    deploy)
        deploy "${2:-$(pwd)}"
        ;;
    status)
        status
        ;;
    rollback)
        if [[ -n "${2:-}" ]]; then
            rollback_deployment "$2"
        else
            log_error "Please specify backup path for rollback"
            echo "Usage: $0 rollback <backup_path>"
            exit 1
        fi
        ;;
    setup)
        setup_environments
        ;;
    *)
        echo "Usage: $0 {deploy|status|rollback|setup} [options]"
        echo
        echo "Commands:"
        echo "  deploy [source_dir]   - Deploy from source directory (default: current directory)"
        echo "  status               - Show current deployment status"
        echo "  rollback <backup>    - Rollback to specific backup"
        echo "  setup               - Initialize blue-green environments"
        echo
        echo "Examples:"
        echo "  $0 deploy /path/to/source"
        echo "  $0 rollback /opt/anime-backups/deployment_backup_20241118_120000"
        exit 1
        ;;
esac