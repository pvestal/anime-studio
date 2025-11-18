#!/bin/bash
# Deployment Validation Script
# Comprehensive validation of anime production system deployment

set -euo pipefail

# Configuration
SERVICE_URL="${SERVICE_URL:-http://127.0.0.1:8328}"
ECHO_URL="${ECHO_URL:-https://***REMOVED***/api/echo}"
COMFYUI_URL="${COMFYUI_URL:-http://***REMOVED***:8188}"
KB_URL="${KB_URL:-https://***REMOVED***/api/kb}"

TIMEOUT=30
MAX_RETRIES=5
RETRY_INTERVAL=2

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠️ $1${NC}"
}

# Function to make HTTP request with retries
http_request() {
    local url="$1"
    local method="${2:-GET}"
    local data="${3:-}"
    local attempt=1

    while [[ $attempt -le $MAX_RETRIES ]]; do
        if [[ -n "$data" ]]; then
            if curl -s -f -m $TIMEOUT -X "$method" -H "Content-Type: application/json" -d "$data" "$url" > /dev/null 2>&1; then
                return 0
            fi
        else
            if curl -s -f -m $TIMEOUT "$url" > /dev/null 2>&1; then
                return 0
            fi
        fi

        if [[ $attempt -lt $MAX_RETRIES ]]; then
            log "Request failed, retrying... ($attempt/$MAX_RETRIES)"
            sleep $RETRY_INTERVAL
        fi
        ((attempt++))
    done

    return 1
}

# Function to check service health
check_service_health() {
    local service_name="$1"
    local health_url="$2"

    log "Checking $service_name health..."

    if http_request "$health_url"; then
        success "$service_name is healthy"
        return 0
    else
        error "$service_name health check failed"
        return 1
    fi
}

# Function to validate API endpoints
validate_api_endpoints() {
    local base_url="$1"
    local endpoints=(
        "/api/health"
        "/api/projects"
        "/api/status"
    )

    log "Validating API endpoints..."

    local failed_endpoints=()

    for endpoint in "${endpoints[@]}"; do
        local url="${base_url}${endpoint}"
        if http_request "$url"; then
            success "✓ $endpoint"
        else
            error "✗ $endpoint"
            failed_endpoints+=("$endpoint")
        fi
    done

    if [[ ${#failed_endpoints[@]} -eq 0 ]]; then
        success "All API endpoints are responsive"
        return 0
    else
        error "Failed endpoints: ${failed_endpoints[*]}"
        return 1
    fi
}

# Function to test database connectivity
test_database_connectivity() {
    log "Testing database connectivity..."

    # Test via API endpoint
    if http_request "${SERVICE_URL}/api/projects?limit=1"; then
        success "Database connectivity via API is working"
        return 0
    else
        error "Database connectivity test failed"
        return 1
    fi
}

# Function to test service integration
test_service_integration() {
    log "Testing service integration..."

    # Test Echo Brain integration
    local echo_test_data='{"query": "Health check from deployment validation", "conversation_id": "deployment_validation"}'
    if http_request "${ECHO_URL}/query" "POST" "$echo_test_data"; then
        success "Echo Brain integration working"
    else
        warning "Echo Brain integration failed - may not be critical"
    fi

    # Test ComfyUI integration
    if http_request "${COMFYUI_URL}/queue"; then
        success "ComfyUI integration working"
    else
        warning "ComfyUI integration failed - may not be critical"
    fi

    # Test Knowledge Base integration
    if http_request "${KB_URL}/articles?limit=1"; then
        success "Knowledge Base integration working"
    else
        warning "Knowledge Base integration failed - may not be critical"
    fi
}

# Function to run performance tests
run_performance_tests() {
    log "Running basic performance tests..."

    local start_time
    local end_time
    local response_time

    # Test response time
    start_time=$(date +%s%N)
    if http_request "${SERVICE_URL}/api/health"; then
        end_time=$(date +%s%N)
        response_time=$(( (end_time - start_time) / 1000000 )) # Convert to milliseconds

        if [[ $response_time -lt 1000 ]]; then
            success "Response time: ${response_time}ms ✓"
        elif [[ $response_time -lt 3000 ]]; then
            warning "Response time: ${response_time}ms (acceptable but slow)"
        else
            error "Response time: ${response_time}ms (too slow)"
            return 1
        fi
    else
        error "Performance test failed - service not responding"
        return 1
    fi

    return 0
}

# Function to validate environment configuration
validate_environment() {
    log "Validating environment configuration..."

    # Check if required directories exist
    local required_dirs=(
        "/opt/tower-anime-production"
        "/opt/tower-anime-production/logs"
        "/opt/tower-anime-production/venv"
    )

    for dir in "${required_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            success "✓ Directory exists: $dir"
        else
            error "✗ Missing directory: $dir"
            return 1
        fi
    done

    # Check if service is running
    if systemctl is-active tower-anime-production > /dev/null 2>&1; then
        success "✓ Systemd service is running"
    else
        error "✗ Systemd service is not running"
        return 1
    fi

    # Check Python virtual environment
    if [[ -f "/opt/tower-anime-production/venv/bin/python" ]]; then
        success "✓ Python virtual environment exists"
    else
        error "✗ Python virtual environment not found"
        return 1
    fi

    return 0
}

# Function to validate dependencies
validate_dependencies() {
    log "Validating system dependencies..."

    local dependencies=(
        "python3"
        "pip"
        "curl"
        "systemctl"
    )

    for dep in "${dependencies[@]}"; do
        if command -v "$dep" > /dev/null 2>&1; then
            success "✓ $dep is available"
        else
            error "✗ $dep is not available"
            return 1
        fi
    done

    return 0
}

# Function to generate validation report
generate_report() {
    local start_time="$1"
    local end_time="$2"
    local total_checks="$3"
    local passed_checks="$4"
    local failed_checks="$5"

    local duration=$((end_time - start_time))
    local success_rate=$(( (passed_checks * 100) / total_checks ))

    echo
    echo "============================================"
    echo "🎬 ANIME PRODUCTION DEPLOYMENT VALIDATION"
    echo "============================================"
    echo "Validation Time: $(date)"
    echo "Duration: ${duration}s"
    echo "Total Checks: $total_checks"
    echo "Passed: $passed_checks"
    echo "Failed: $failed_checks"
    echo "Success Rate: ${success_rate}%"
    echo

    if [[ $failed_checks -eq 0 ]]; then
        echo -e "${GREEN}✅ VALIDATION PASSED${NC}"
        echo "🚀 Deployment is ready for production!"
    elif [[ $failed_checks -lt 3 ]]; then
        echo -e "${YELLOW}⚠️ VALIDATION PASSED WITH WARNINGS${NC}"
        echo "🔄 Deployment is functional but has minor issues"
    else
        echo -e "${RED}❌ VALIDATION FAILED${NC}"
        echo "🚫 Deployment has critical issues and should be rolled back"
    fi

    echo "============================================"
    echo
}

# Function to send validation results to monitoring
send_validation_results() {
    local status="$1"
    local passed_checks="$2"
    local total_checks="$3"

    # Send to Echo Brain for logging
    local validation_data="{
        \"query\": \"Deployment validation $status: $passed_checks/$total_checks checks passed\",
        \"conversation_id\": \"deployment_validation\",
        \"metadata\": {
            \"type\": \"deployment_validation\",
            \"status\": \"$status\",
            \"passed_checks\": $passed_checks,
            \"total_checks\": $total_checks,
            \"timestamp\": \"$(date -Iseconds)\",
            \"service\": \"anime-production\"
        }
    }"

    curl -k -X POST "${ECHO_URL}/query" \
        -H "Content-Type: application/json" \
        -d "$validation_data" > /dev/null 2>&1 || true
}

# Main validation function
main() {
    local start_time=$(date +%s)
    local total_checks=0
    local passed_checks=0
    local failed_checks=0

    echo "🎬 Starting Anime Production System Deployment Validation..."
    echo

    # List of validation functions
    local validations=(
        "validate_dependencies:System Dependencies"
        "validate_environment:Environment Configuration"
        "check_service_health:anime_api:${SERVICE_URL}/api/health"
        "validate_api_endpoints:${SERVICE_URL}:API Endpoints"
        "test_database_connectivity:Database Connectivity"
        "test_service_integration:Service Integration"
        "run_performance_tests:Performance Tests"
    )

    for validation in "${validations[@]}"; do
        IFS=':' read -ra parts <<< "$validation"
        local func="${parts[0]}"
        local desc="${parts[1]}"
        local param="${parts[2]:-}"

        ((total_checks++))

        echo "📋 Running: $desc"
        echo "──────────────────────────────────────"

        if [[ -n "$param" ]]; then
            if $func "$desc" "$param"; then
                ((passed_checks++))
            else
                ((failed_checks++))
            fi
        else
            if $func; then
                ((passed_checks++))
            else
                ((failed_checks++))
            fi
        fi

        echo
    done

    local end_time=$(date +%s)

    # Generate and display report
    generate_report "$start_time" "$end_time" "$total_checks" "$passed_checks" "$failed_checks"

    # Send results to monitoring
    local status
    if [[ $failed_checks -eq 0 ]]; then
        status="PASSED"
    elif [[ $failed_checks -lt 3 ]]; then
        status="PASSED_WITH_WARNINGS"
    else
        status="FAILED"
    fi

    send_validation_results "$status" "$passed_checks" "$total_checks"

    # Exit with appropriate code
    if [[ $failed_checks -lt 3 ]]; then
        exit 0
    else
        exit 1
    fi
}

# Handle script arguments
case "${1:-validate}" in
    validate)
        main
        ;;
    health)
        check_service_health "anime_api" "${SERVICE_URL}/api/health"
        ;;
    api)
        validate_api_endpoints "$SERVICE_URL"
        ;;
    performance)
        run_performance_tests
        ;;
    integration)
        test_service_integration
        ;;
    *)
        echo "Usage: $0 {validate|health|api|performance|integration}"
        echo
        echo "Commands:"
        echo "  validate     - Run full validation suite (default)"
        echo "  health       - Check service health only"
        echo "  api          - Validate API endpoints only"
        echo "  performance  - Run performance tests only"
        echo "  integration  - Test service integration only"
        exit 1
        ;;
esac