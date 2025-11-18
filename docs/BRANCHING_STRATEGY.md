# Anime Production System - Git Branching Strategy & Release Management

## Overview

This document outlines the branching strategy, version control practices, and release management for the Tower Anime Production System redesign. This strategy is designed to support coordinated development across multiple services while ensuring production stability.

## Branch Structure

### Main Branches

#### `main`
- **Purpose**: Production-ready code
- **Protection**: Protected branch with required status checks
- **Deployment**: Automatic deployment to production via CI/CD
- **Merges**: Only from `development` via pull requests
- **Tagging**: All releases tagged with semantic versioning

#### `development`
- **Purpose**: Integration branch for completed features
- **Protection**: Protected branch with required status checks
- **Deployment**: Automatic deployment to staging environment
- **Merges**: From feature branches via pull requests
- **Testing**: Full integration test suite runs on every commit

### Feature Branches

#### `feature/*`
- **Naming**: `feature/anime-system-redesign`, `feature/improved-generation-pipeline`
- **Purpose**: Development of specific features or major changes
- **Base**: Created from `development`
- **Merge**: Into `development` via pull request
- **Lifespan**: Short-lived (ideally < 2 weeks)

#### `hotfix/*`
- **Naming**: `hotfix/critical-generation-bug`, `hotfix/database-connection-issue`
- **Purpose**: Critical production fixes
- **Base**: Created from `main`
- **Merge**: Into both `main` and `development`
- **Deployment**: Emergency deployment process

#### `release/*`
- **Naming**: `release/v2.1.0`
- **Purpose**: Release preparation and stabilization
- **Base**: Created from `development`
- **Merge**: Into `main` and back-merge to `development`
- **Activities**: Final testing, documentation updates, version bumping

## Workflow Process

### Feature Development

```bash
# 1. Create feature branch from development
git checkout development
git pull origin development
git checkout -b feature/anime-system-redesign

# 2. Develop and commit changes
git add .
git commit -m "feat: implement dual-pipeline architecture"

# 3. Push and create pull request
git push origin feature/anime-system-redesign
# Create PR: feature/anime-system-redesign → development
```

### Release Process

```bash
# 1. Create release branch
git checkout development
git pull origin development
git checkout -b release/v2.1.0

# 2. Prepare release (version bump, changelog)
echo "2.1.0" > VERSION
git add VERSION
git commit -m "chore: bump version to 2.1.0"

# 3. Final testing and fixes
# ... make any necessary fixes ...

# 4. Merge to main
git checkout main
git merge --no-ff release/v2.1.0
git tag -a v2.1.0 -m "Release version 2.1.0"

# 5. Back-merge to development
git checkout development
git merge --no-ff release/v2.1.0

# 6. Delete release branch
git branch -d release/v2.1.0
```

### Hotfix Process

```bash
# 1. Create hotfix from main
git checkout main
git pull origin main
git checkout -b hotfix/critical-generation-bug

# 2. Fix the issue
git add .
git commit -m "fix: resolve ComfyUI memory leak causing generation failures"

# 3. Merge to main
git checkout main
git merge --no-ff hotfix/critical-generation-bug
git tag -a v2.0.1 -m "Hotfix version 2.0.1"

# 4. Merge to development
git checkout development
git merge --no-ff hotfix/critical-generation-bug

# 5. Deploy immediately
./scripts/blue_green_deployment.sh deploy
```

## Semantic Versioning

### Version Format: `MAJOR.MINOR.PATCH`

- **MAJOR** (X.0.0): Breaking changes to API or major architecture changes
- **MINOR** (0.X.0): New features, backwards-compatible changes
- **PATCH** (0.0.X): Bug fixes, hotfixes

### Examples:
- `v2.0.0`: Complete system redesign with new dual-pipeline architecture
- `v2.1.0`: Addition of new character consistency engine
- `v2.1.1`: Fix for generation timeout issues

## Commit Message Standards

### Format
```
<type>(<scope>): <description>

<body>

<footer>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic changes)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates

### Scopes
- `api`: API changes
- `ui`: Frontend changes
- `db`: Database changes
- `comfyui`: ComfyUI integration
- `echo`: Echo Brain integration
- `deploy`: Deployment/infrastructure
- `ci`: CI/CD pipeline changes

### Examples
```bash
feat(api): add character consistency validation endpoint

- Implement POST /api/characters/validate endpoint
- Add character similarity scoring algorithm
- Include visual consistency checks

Closes #123
```

```bash
fix(comfyui): resolve memory leak in long-running generations

- Fix improper model cleanup after generation
- Implement proper VRAM monitoring
- Add automatic cleanup for failed jobs

Fixes #456
```

## Pull Request Process

### Required Checks
- ✅ All CI tests pass
- ✅ Code review approval (minimum 1 reviewer)
- ✅ Integration tests pass
- ✅ Security scan passes
- ✅ No merge conflicts
- ✅ Documentation updated (if applicable)

### PR Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (non-breaking change fixing an issue)
- [ ] New feature (non-breaking change adding functionality)
- [ ] Breaking change (fix or feature causing existing functionality to change)
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or breaking changes documented)

## Related Issues
Closes #123
```

## Service Coordination Strategy

### Multi-Repository Management

#### Core Services Repositories:
- `pvestal/anime-production` (Main API)
- `pvestal/tower-echo-brain` (AI Integration)
- `pvestal/tower-auth` (Authentication)
- `pvestal/tower-dashboard` (Frontend)

#### Coordinated Release Process:
1. **Feature Development**: Each service develops features independently
2. **Integration Testing**: Cross-service testing in staging environment
3. **Coordinated Tagging**: All services tagged with same version when released together
4. **Deployment Orchestration**: Blue-green deployment across all services

#### Dependency Management:
```bash
# Tag all services with coordinated release
git tag -a v2.1.0-ecosystem -m "Coordinated release v2.1.0"

# Deploy all services together
./scripts/deploy_ecosystem.sh v2.1.0-ecosystem
```

## CI/CD Integration

### Automated Processes

#### On Push to Feature Branch:
- ✅ Code quality checks
- ✅ Unit tests
- ✅ Security scan
- ✅ Basic integration tests

#### On Pull Request:
- ✅ Full test suite
- ✅ Integration tests with staging services
- ✅ Performance tests
- ✅ Database migration tests

#### On Merge to Development:
- ✅ Deploy to staging environment
- ✅ Full integration test suite
- ✅ End-to-end workflow testing

#### On Merge to Main:
- ✅ Production deployment via blue-green strategy
- ✅ Post-deployment health checks
- ✅ Rollback on failure
- ✅ Notification to team

### Branch Protection Rules

#### Main Branch:
- Require pull request reviews (1 reviewer minimum)
- Require status checks to pass
- Require branches to be up to date before merging
- Restrict pushes to users with admin permissions
- Require signed commits (optional)

#### Development Branch:
- Require pull request reviews (1 reviewer minimum)
- Require status checks to pass
- Require branches to be up to date before merging

## Emergency Procedures

### Critical Production Issue
1. **Immediate Response**: Create hotfix branch from main
2. **Quick Fix**: Implement minimal fix for critical issue
3. **Fast-Track Review**: Expedited review process
4. **Emergency Deployment**: Skip staging, deploy directly to production
5. **Post-Incident**: Full retrospective and permanent fix

### Rollback Procedures
```bash
# Automatic rollback via blue-green deployment
./scripts/blue_green_deployment.sh rollback /opt/anime-backups/deployment_backup_YYYYMMDD_HHMMSS

# Manual rollback to specific version
git checkout main
git reset --hard v2.0.1
./scripts/blue_green_deployment.sh deploy
```

## Monitoring and Metrics

### Git Metrics
- Pull request velocity
- Time from feature start to production
- Hotfix frequency
- Rollback frequency

### Deployment Metrics
- Deployment success rate
- Deployment duration
- Time to recovery (MTTR)
- Mean time between failures (MTBF)

### Automation Tools
- **GitHub Actions**: CI/CD pipeline automation
- **Echo Brain**: Deployment notifications and monitoring
- **Blue-Green Script**: Zero-downtime deployments

## Best Practices

### Development
1. **Small, Focused Commits**: Each commit should represent a logical unit of work
2. **Regular Rebasing**: Keep feature branches up to date with development
3. **Descriptive Messages**: Clear, descriptive commit messages
4. **Test Coverage**: Maintain high test coverage for all changes
5. **Documentation**: Update documentation with code changes

### Code Review
1. **Review for Logic**: Check algorithm correctness and edge cases
2. **Review for Security**: Look for potential security vulnerabilities
3. **Review for Performance**: Consider performance implications
4. **Review for Maintainability**: Ensure code is readable and maintainable

### Deployment
1. **Staging First**: Always test in staging environment first
2. **Gradual Rollout**: Use blue-green deployment for zero downtime
3. **Monitor Closely**: Watch metrics during and after deployment
4. **Ready to Rollback**: Always have rollback plan ready

## Team Workflow

### Daily Development
- Pull latest changes from development before starting work
- Create feature branches for all changes
- Commit frequently with clear messages
- Push daily and create draft PRs for visibility

### Weekly Process
- Review and merge completed features
- Plan releases and coordinate dependencies
- Review metrics and improve processes
- Update documentation and technical debt

### Release Cycle
- **2-week sprints** for feature development
- **Monthly releases** to production (or as needed)
- **Quarterly major releases** for significant changes
- **Immediate hotfixes** for critical issues

This branching strategy ensures stable production deployments while enabling rapid development and coordinated releases across the anime production ecosystem.