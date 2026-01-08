# Anime Production System - CI/CD Pipeline Documentation

## Overview

This document provides comprehensive information about the CI/CD pipeline, version control strategy, and deployment processes for the Tower Anime Production System redesign.

## 🚀 Quick Start

### Prerequisites
- Git repository access to `pvestal/anime-production`
- Self-hosted GitHub Actions runner on Tower (192.168.50.135)
- Access to production environment
- Database credentials for testing

### Basic Workflow
```bash
# 1. Create feature branch
git checkout -b feature/your-feature-name

# 2. Make changes and commit
git add .
git commit -m "feat: your feature description"

# 3. Push and create PR
git push origin feature/your-feature-name
# Create PR via GitHub UI: feature/your-feature-name → development

# 4. After PR approval and merge, automatic deployment to staging
# 5. For production release, merge development → main
```

## 🏗️ Pipeline Architecture

### GitHub Actions Workflows

#### Main CI/CD Pipeline (`.github/workflows/ci.yml`)

**Triggers:**
- Push to `main`, `development`, `feature/*`
- Pull requests to `main`, `development`
- Manual dispatch

**Jobs:**
1. **Code Quality & Security**
   - Code formatting (Black, isort)
   - Linting (Pylint)
   - Security scanning (Bandit, Safety)

2. **Database Migration Testing**
   - PostgreSQL test database setup
   - Migration scripts validation
   - Performance testing

3. **Unit Tests**
   - Python unit tests with pytest
   - Code coverage reporting

4. **Integration Tests**
   - Cross-service communication tests
   - End-to-end workflow validation
   - API endpoint testing

5. **Performance Testing**
   - Load testing with concurrent requests
   - Response time validation
   - Resource usage monitoring

6. **Build & Deploy**
   - Blue-green deployment to staging/production
   - Health checks and validation
   - Automatic rollback on failure

7. **Notifications**
   - Success/failure notifications
   - Integration with Echo Brain logging

### Self-Hosted Runner Requirements

The pipeline runs on Tower's self-hosted GitHub Actions runner with access to:
- Production services and databases
- ComfyUI and Echo Brain integration
- Blue-green deployment environments

## 📁 Directory Structure

```
/opt/tower-anime-production/
├── .github/
│   └── workflows/
│       └── ci.yml                 # Main CI/CD pipeline
├── scripts/
│   ├── blue_green_deployment.sh  # Blue-green deployment script
│   └── validate_deployment.sh    # Deployment validation
├── tests/
│   ├── database/
│   │   └── test_database_migrations.py  # Database testing
│   ├── integration/
│   │   └── test_anime_ecosystem_integration.py  # Integration tests
│   └── unit/                     # Unit tests
├── docs/
│   └── BRANCHING_STRATEGY.md     # Git workflow documentation
└── CICD_README.md               # This file
```

## 🔄 Blue-Green Deployment

### Architecture

**Environments:**
- **Blue**: `/opt/tower-anime-production-blue`
- **Green**: `/opt/tower-anime-production-green`
- **Production**: `/opt/tower-anime-production` (symlink to active environment)

### Deployment Process

1. **Deploy to Inactive Environment**
   ```bash
   ./scripts/blue_green_deployment.sh deploy /path/to/source
   ```

2. **Automatic Steps:**
   - Create deployment backup
   - Deploy code to inactive environment
   - Start service in inactive environment
   - Run health checks and integration tests
   - Switch traffic to new environment
   - Cleanup old environment

3. **Rollback if Needed:**
   ```bash
   ./scripts/blue_green_deployment.sh rollback /opt/anime-backups/backup_path
   ```

### Deployment Ports

- **Production**: `8328` (main service)
- **Blue Environment**: `8329` (testing)
- **Green Environment**: `8330` (testing)

## 🧪 Testing Framework

### Database Migration Testing

**Location**: `tests/database/test_database_migrations.py`

**Features:**
- Isolated test database creation
- Migration validation with test data
- Performance benchmarking
- Data integrity verification
- Automatic cleanup

**Usage:**
```bash
# Run database tests
pytest tests/database/ -v

# Run manually
python tests/database/test_database_migrations.py
```

### Integration Testing

**Location**: `tests/integration/test_anime_ecosystem_integration.py`

**Features:**
- Cross-service communication testing
- End-to-end workflow validation
- Performance and load testing
- Service health monitoring

**Test Scenarios:**
- Service health checks
- Database connectivity
- End-to-end anime generation workflow
- Cross-service communication
- Load performance testing

**Usage:**
```bash
# Run integration tests
pytest tests/integration/ -v

# Run manually for development
python tests/integration/test_anime_ecosystem_integration.py
```

## 🔒 Security & Quality

### Automated Security Scanning

**Tools:**
- **Bandit**: Python security analysis
- **Safety**: Vulnerability scanning
- **Pip-audit**: Dependency vulnerability checking

**Reports**: Generated as artifacts in GitHub Actions

### Code Quality Standards

**Formatting:**
- **Black**: Code formatting
- **isort**: Import organization

**Linting:**
- **Pylint**: Code quality analysis
- Minimum score: 7.0/10

**Testing:**
- Minimum 80% code coverage
- All tests must pass

## 🏷️ Version Control Strategy

### Branch Structure

- **`main`**: Production-ready code
- **`development`**: Integration branch
- **`feature/*`**: Feature development
- **`hotfix/*`**: Critical production fixes
- **`release/*`**: Release preparation

### Commit Standards

**Format:**
```
<type>(<scope>): <description>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Testing
- `chore`: Maintenance

**Examples:**
```bash
feat(api): add character consistency validation endpoint
fix(comfyui): resolve memory leak in long-running generations
docs(deployment): update blue-green deployment documentation
```

### Release Process

1. **Feature Development** → `development`
2. **Release Branch** → `release/v2.1.0`
3. **Production Release** → `main`
4. **Tagging** → `v2.1.0`

## 🚀 Deployment Commands

### Blue-Green Deployment

```bash
# Deploy from current directory
./scripts/blue_green_deployment.sh deploy

# Deploy from specific directory
./scripts/blue_green_deployment.sh deploy /path/to/source

# Check deployment status
./scripts/blue_green_deployment.sh status

# Rollback to backup
./scripts/blue_green_deployment.sh rollback /opt/anime-backups/backup_path

# Setup blue-green environments (first time)
./scripts/blue_green_deployment.sh setup
```

### Validation

```bash
# Full validation suite
./scripts/validate_deployment.sh validate

# Health check only
./scripts/validate_deployment.sh health

# API validation only
./scripts/validate_deployment.sh api

# Performance tests only
./scripts/validate_deployment.sh performance

# Integration tests only
./scripts/validate_deployment.sh integration
```

## 📊 Monitoring & Metrics

### Deployment Metrics

**Tracked Metrics:**
- Deployment success rate
- Deployment duration
- Rollback frequency
- Test success rate

**Monitoring:**
- Echo Brain integration for notifications
- GitHub Actions artifacts for reports
- System logs for troubleshooting

### Health Checks

**Endpoints:**
- Service health: `/api/health`
- Database connectivity: `/api/projects?limit=1`
- Integration status: Cross-service communication

**Validation:**
- Response time < 1000ms (ideal) / < 3000ms (acceptable)
- Success rate > 90%
- All critical services responsive

## 🔧 Configuration

### Environment Variables

**CI/CD Pipeline:**
- `PYTHON_VERSION`: Python version for testing (default: 3.10)
- `NODE_VERSION`: Node.js version (default: 18)

**Deployment Scripts:**
- `SERVICE_URL`: Service URL for validation (default: http://127.0.0.1:8328)
- `ECHO_URL`: Echo Brain URL (default: https://192.168.50.135/api/echo)
- `COMFYUI_URL`: ComfyUI URL (default: http://192.168.50.135:8188)

### Database Configuration

**Test Database:**
- Host: localhost (during CI)
- Database: anime_test
- User: test_user
- Password: test_password

**Production Database:**
- Host: 192.168.50.135
- Database: anime_production
- User: patrick
- Password: [stored in secrets]

## 🚨 Emergency Procedures

### Critical Production Issue

1. **Create Hotfix:**
   ```bash
   git checkout main
   git checkout -b hotfix/critical-issue-description
   ```

2. **Fix and Deploy:**
   ```bash
   # Make fix
   git add .
   git commit -m "fix: critical issue description"

   # Fast-track merge to main
   git checkout main
   git merge --no-ff hotfix/critical-issue-description

   # Emergency deployment
   ./scripts/blue_green_deployment.sh deploy
   ```

3. **Verify Fix:**
   ```bash
   ./scripts/validate_deployment.sh validate
   ```

### Rollback Procedures

**Automatic Rollback:**
- CI/CD pipeline automatically rolls back on failed health checks
- Blue-green deployment includes rollback capabilities

**Manual Rollback:**
```bash
# List available backups
ls -la /opt/anime-backups/

# Rollback to specific backup
./scripts/blue_green_deployment.sh rollback /opt/anime-backups/deployment_backup_YYYYMMDD_HHMMSS

# Verify rollback success
./scripts/validate_deployment.sh health
```

## 🛠️ Troubleshooting

### Common Issues

**1. CI Tests Failing:**
```bash
# Check test logs in GitHub Actions
# Run tests locally:
pytest tests/ -v --tb=short

# Check specific test:
python tests/integration/test_anime_ecosystem_integration.py
```

**2. Deployment Health Checks Failing:**
```bash
# Check service status
systemctl status tower-anime-production

# Check service logs
journalctl -u tower-anime-production -f

# Manual health check
curl http://127.0.0.1:8328/api/health
```

**3. Database Migration Issues:**
```bash
# Test migrations
python tests/database/test_database_migrations.py

# Check database connectivity
psql -h 192.168.50.135 -U patrick -d anime_production -c "SELECT 1;"
```

### Log Locations

- **Deployment Logs**: `/var/log/anime-production-deployment.log`
- **Service Logs**: `journalctl -u tower-anime-production`
- **CI Artifacts**: GitHub Actions artifacts
- **Validation Reports**: `/tmp/integration_test_results_*.json`

## 📚 Additional Resources

### Documentation

- **Branching Strategy**: `docs/BRANCHING_STRATEGY.md`
- **API Documentation**: `API_DOCUMENTATION.md`
- **Security Guide**: `SECURITY_IMPLEMENTATION_GUIDE.md`

### Scripts

- **Blue-Green Deployment**: `scripts/blue_green_deployment.sh`
- **Deployment Validation**: `scripts/validate_deployment.sh`

### Test Suites

- **Database Tests**: `tests/database/`
- **Integration Tests**: `tests/integration/`
- **Unit Tests**: `tests/unit/`

## 🎯 Best Practices

### Development

1. **Always use feature branches** for development
2. **Write tests** for new features
3. **Update documentation** with code changes
4. **Follow commit message standards**
5. **Test locally** before pushing

### Deployment

1. **Use staging environment** for testing
2. **Monitor metrics** during deployment
3. **Have rollback plan ready**
4. **Validate after deployment**
5. **Document any issues**

### Security

1. **Never commit secrets** to repository
2. **Use environment variables** for configuration
3. **Regular security scans**
4. **Monitor for vulnerabilities**
5. **Follow principle of least privilege**

This CI/CD pipeline ensures reliable, secure, and automated deployment of the anime production system while maintaining high code quality and system stability.