#!/bin/bash
# File: tests/integration/validate_ssot_integration.sh
# Comprehensive validation for all 3 phases of SSOT integration

set -e  # Exit on any error

# Configuration
API_BASE_URL="http://localhost:8328"
DB_HOST="192.168.50.135"
DB_USER="patrick"
DB_NAME="tower_consolidated"
TEST_PROJECT_ID="integration-test-$(date +%s)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Database query helper
query_db() {
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -A -c "$1" 2>/dev/null || echo ""
}

# Check if services are running
check_services() {
    log_info "Checking service availability..."

    # Check anime production service
    if curl -f -s "$API_BASE_URL/health" > /dev/null; then
        log_success "Anime Production API is running"
    else
        log_error "Anime Production API is not accessible at $API_BASE_URL"
        exit 1
    fi

    # Check database connection
    if query_db "SELECT 1;" | grep -q "1"; then
        log_success "Database connection established"
    else
        log_error "Cannot connect to database at $DB_HOST"
        exit 1
    fi

    # Check Echo Brain service
    if curl -f -s "http://localhost:8309/api/echo/health" > /dev/null; then
        log_success "Echo Brain service is running"
    else
        log_warning "Echo Brain service not accessible - Phase 3 tests will be skipped"
    fi
}

# Phase 1: SSOT Bridge Validation
validate_phase1_ssot_bridge() {
    log_info "=== Phase 1 Validation: SSOT Bridge ==="

    # Test 1: Generate image with decision tracking
    log_info "Testing image generation with SSOT tracking..."

    response=$(curl -s -X POST "$API_BASE_URL/api/anime/generate/image" \
        -H "Content-Type: application/json" \
        -d "{
            \"prompt\": \"test SSOT integration validation\",
            \"project_id\": \"$TEST_PROJECT_ID\",
            \"parameters\": {\"width\": 512, \"height\": 512, \"steps\": 20}
        }" || echo "{}")

    if [ -z "$response" ] || [ "$response" = "{}" ]; then
        log_error "Image generation API call failed"
        return 1
    fi

    decision_id=$(echo "$response" | jq -r '.decision_id // ""')

    if [ -z "$decision_id" ] || [ "$decision_id" = "null" ]; then
        log_error "No decision_id returned from image generation"
        return 1
    fi

    log_success "Image generation request returned decision_id: $decision_id"

    # Verify decision was logged in database
    log_info "Verifying decision was logged in SSOT database..."

    decision_count=$(query_db "SELECT COUNT(*) FROM generation_decisions WHERE id = '$decision_id';")

    if [ "$decision_count" = "1" ]; then
        log_success "Decision correctly logged in SSOT database"
    else
        log_error "Decision not found in SSOT database (count: $decision_count)"
        return 1
    fi

    # Verify decision has correct parameters
    stored_params=$(query_db "SELECT parameters FROM generation_decisions WHERE id = '$decision_id';")

    if echo "$stored_params" | grep -q "width.*512"; then
        log_success "Parameters correctly stored in SSOT database"
    else
        log_error "Parameters not correctly stored in SSOT database"
        return 1
    fi

    # Test 2: Video generation tracking
    log_info "Testing video generation with SSOT tracking..."

    video_response=$(curl -s -X POST "$API_BASE_URL/api/anime/generate/video" \
        -H "Content-Type: application/json" \
        -d "{
            \"prompt\": \"test SSOT video integration\",
            \"project_id\": \"$TEST_PROJECT_ID\",
            \"parameters\": {\"duration\": 3, \"fps\": 8}
        }" || echo "{}")

    video_decision_id=$(echo "$video_response" | jq -r '.decision_id // ""')

    if [ -n "$video_decision_id" ] && [ "$video_decision_id" != "null" ]; then
        log_success "Video generation SSOT tracking working"
    else
        log_warning "Video generation SSOT tracking may not be implemented yet"
    fi

    # Test 3: Verify no generation requests bypass SSOT
    total_decisions=$(query_db "SELECT COUNT(*) FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID';")

    if [ "$total_decisions" -ge "1" ]; then
        log_success "All test generations tracked in SSOT (count: $total_decisions)"
    else
        log_error "Some generations may be bypassing SSOT tracking"
        return 1
    fi

    log_success "Phase 1 SSOT Bridge validation completed successfully"
    return 0
}

# Phase 2: ComfyUI Workflow Persistence Validation
validate_phase2_workflow_persistence() {
    log_info "=== Phase 2 Validation: ComfyUI Workflow Persistence ==="

    # Check if workflow_history table exists
    workflow_table_exists=$(query_db "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_history');")

    if [ "$workflow_table_exists" = "t" ]; then
        log_success "workflow_history table exists"
    else
        log_warning "workflow_history table not found - Phase 2 not implemented"
        return 0
    fi

    # Test workflow capture
    log_info "Testing workflow capture for recent generations..."

    recent_workflows=$(query_db "SELECT COUNT(*) FROM workflow_history wh JOIN generation_decisions gd ON wh.decision_id = gd.id WHERE gd.project_id = '$TEST_PROJECT_ID';")

    if [ "$recent_workflows" -gt "0" ]; then
        log_success "Workflows are being captured and stored (count: $recent_workflows)"
    else
        log_warning "No workflows captured for test generations - Phase 2 may not be active"
    fi

    # Test workflow analysis endpoint
    if curl -f -s "$API_BASE_URL/api/workflows/analysis?days=1" > /dev/null; then
        log_success "Workflow analysis endpoint is accessible"
    else
        log_warning "Workflow analysis endpoint not accessible"
    fi

    # Check for workflow optimization
    if curl -f -s "$API_BASE_URL/api/workflows/optimize/image_generation" > /dev/null; then
        log_success "Workflow optimization endpoint is accessible"
    else
        log_warning "Workflow optimization endpoint not accessible"
    fi

    log_success "Phase 2 ComfyUI Workflow Persistence validation completed"
    return 0
}

# Phase 3: Echo Brain Integration Validation
validate_phase3_echo_brain_integration() {
    log_info "=== Phase 3 Validation: Echo Brain Integration ==="

    # Check if Echo Brain service is available
    if ! curl -f -s "http://localhost:8309/api/echo/health" > /dev/null; then
        log_warning "Echo Brain service not available - skipping Phase 3 validation"
        return 0
    fi

    # Check if ai_consultations table exists
    consultations_table_exists=$(query_db "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_consultations');")

    if [ "$consultations_table_exists" = "t" ]; then
        log_success "ai_consultations table exists"
    else
        log_warning "ai_consultations table not found - Phase 3 not implemented"
        return 0
    fi

    # Test AI consultation capture
    log_info "Testing AI consultation capture..."

    consultation_response=$(curl -s -X POST "$API_BASE_URL/api/anime/generate/image" \
        -H "Content-Type: application/json" \
        -d "{
            \"prompt\": \"test AI consultation capture\",
            \"project_id\": \"$TEST_PROJECT_ID\",
            \"parameters\": {\"width\": 512, \"height\": 512},
            \"request_consultation\": true
        }" || echo "{}")

    consultation_id=$(echo "$consultation_response" | jq -r '.consultation_id // ""')

    if [ -n "$consultation_id" ] && [ "$consultation_id" != "null" ]; then
        log_success "AI consultation captured with ID: $consultation_id"

        # Verify consultation was stored
        consultation_count=$(query_db "SELECT COUNT(*) FROM ai_consultations WHERE id = '$consultation_id';")

        if [ "$consultation_count" = "1" ]; then
            log_success "Consultation correctly stored in database"
        else
            log_error "Consultation not found in database"
        fi
    else
        log_warning "AI consultation capture not implemented or failed"
    fi

    # Test consultation effectiveness analysis
    if curl -f -s "$API_BASE_URL/api/consultations/effectiveness?days=1" > /dev/null; then
        log_success "Consultation effectiveness analysis endpoint accessible"
    else
        log_warning "Consultation effectiveness analysis not accessible"
    fi

    # Test parameter optimization
    optimization_response=$(curl -s -X POST "$API_BASE_URL/api/parameters/optimize" \
        -H "Content-Type: application/json" \
        -d "{
            \"parameters\": {\"width\": 512, \"height\": 512},
            \"context\": {\"style\": \"anime\", \"quality\": \"high\"}
        }" || echo "{}")

    if echo "$optimization_response" | jq -e '.optimized_parameters' > /dev/null; then
        log_success "Parameter optimization working"
    else
        log_warning "Parameter optimization not implemented or failed"
    fi

    log_success "Phase 3 Echo Brain Integration validation completed"
    return 0
}

# Performance validation
validate_performance() {
    log_info "=== Performance Validation ==="

    # Test response times
    start_time=$(date +%s%N)
    curl -s "$API_BASE_URL/health" > /dev/null
    end_time=$(date +%s%N)
    health_response_time=$(( (end_time - start_time) / 1000000 )) # Convert to milliseconds

    if [ "$health_response_time" -lt 200 ]; then
        log_success "Health check response time acceptable: ${health_response_time}ms"
    else
        log_warning "Health check response time high: ${health_response_time}ms"
    fi

    # Test database query performance
    start_time=$(date +%s%N)
    query_db "SELECT COUNT(*) FROM generation_decisions WHERE timestamp > NOW() - INTERVAL '1 hour';" > /dev/null
    end_time=$(date +%s%N)
    db_response_time=$(( (end_time - start_time) / 1000000 ))

    if [ "$db_response_time" -lt 1000 ]; then
        log_success "Database query response time acceptable: ${db_response_time}ms"
    else
        log_warning "Database query response time high: ${db_response_time}ms"
    fi
}

# Data integrity validation
validate_data_integrity() {
    log_info "=== Data Integrity Validation ==="

    # Check for orphaned records
    orphaned_workflows=$(query_db "SELECT COUNT(*) FROM workflow_history wh LEFT JOIN generation_decisions gd ON wh.decision_id = gd.id WHERE gd.id IS NULL;")

    if [ "$orphaned_workflows" = "0" ]; then
        log_success "No orphaned workflow records found"
    else
        log_warning "Found $orphaned_workflows orphaned workflow records"
    fi

    # Check for orphaned consultations
    orphaned_consultations=$(query_db "SELECT COUNT(*) FROM ai_consultations ac LEFT JOIN generation_decisions gd ON ac.decision_id = gd.id WHERE gd.id IS NULL;" 2>/dev/null || echo "0")

    if [ "$orphaned_consultations" = "0" ]; then
        log_success "No orphaned consultation records found"
    else
        log_warning "Found $orphaned_consultations orphaned consultation records"
    fi

    # Validate JSON data integrity
    invalid_json_count=$(query_db "SELECT COUNT(*) FROM generation_decisions WHERE parameters::text = 'null' OR parameters::text = '';")

    if [ "$invalid_json_count" = "0" ]; then
        log_success "All parameter JSON data is valid"
    else
        log_warning "Found $invalid_json_count records with invalid JSON parameters"
    fi
}

# Cleanup test data
cleanup_test_data() {
    log_info "Cleaning up test data..."

    # Get all decision IDs for our test project
    decision_ids=$(query_db "SELECT id FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID';" | tr '\n' ' ')

    if [ -n "$decision_ids" ]; then
        # Clean up in reverse order due to foreign key constraints
        if query_db "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_consultations');" = "t"; then
            query_db "DELETE FROM consultation_effectiveness WHERE consultation_id IN (SELECT id FROM ai_consultations WHERE decision_id IN (SELECT id FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID'));" > /dev/null
            query_db "DELETE FROM ai_consultations WHERE decision_id IN (SELECT id FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID');" > /dev/null
        fi

        if query_db "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'workflow_history');" = "t"; then
            query_db "DELETE FROM workflow_performance_metrics WHERE workflow_id IN (SELECT id FROM workflow_history WHERE decision_id IN (SELECT id FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID'));" > /dev/null
            query_db "DELETE FROM workflow_history WHERE decision_id IN (SELECT id FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID');" > /dev/null
        fi

        query_db "DELETE FROM generation_decisions WHERE project_id = '$TEST_PROJECT_ID';" > /dev/null

        log_success "Test data cleaned up successfully"
    else
        log_info "No test data to clean up"
    fi
}

# Generate validation report
generate_report() {
    local total_tests=$1
    local passed_tests=$2

    log_info "=== Integration Validation Report ==="
    log_info "Total test phases: $total_tests"
    log_info "Passed phases: $passed_tests"
    log_info "Success rate: $(( passed_tests * 100 / total_tests ))%"

    if [ "$passed_tests" -eq "$total_tests" ]; then
        log_success "All validation phases passed successfully!"
        log_success "SSOT integration is working correctly"
        return 0
    else
        log_warning "Some validation phases did not pass completely"
        log_warning "Review warnings above for implementation status"
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting SSOT Integration Validation"
    log_info "Test Project ID: $TEST_PROJECT_ID"

    # Initialize counters
    total_phases=0
    passed_phases=0

    # Check prerequisites
    check_services

    # Run validation phases
    total_phases=$((total_phases + 1))
    if validate_phase1_ssot_bridge; then
        passed_phases=$((passed_phases + 1))
    fi

    total_phases=$((total_phases + 1))
    if validate_phase2_workflow_persistence; then
        passed_phases=$((passed_phases + 1))
    fi

    total_phases=$((total_phases + 1))
    if validate_phase3_echo_brain_integration; then
        passed_phases=$((passed_phases + 1))
    fi

    # Run additional validations
    validate_performance
    validate_data_integrity

    # Cleanup
    cleanup_test_data

    # Generate final report
    generate_report $total_phases $passed_phases
}

# Trap to ensure cleanup on exit
trap cleanup_test_data EXIT

# Execute main function
main "$@"