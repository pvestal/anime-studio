# Git Branching Strategy - Tower Anime Production System

## Overview
This document outlines the branching strategy and version control best practices for the Tower Anime Production System, with special considerations for Echo Brain integration and timeline branching features.

## Branch Types

### 🌟 Main Branch
- **Branch**: `main`
- **Purpose**: Production-ready code
- **Protection**:
  - Requires pull request reviews
  - Status checks must pass
  - No direct pushes allowed
- **Deployment**: Automatically deploys to production

### 🔧 Development Branch
- **Branch**: `development`
- **Purpose**: Integration testing and staging
- **Merge Source**: Feature branches
- **Deployment**: Staging environment

### 🚀 Feature Branches
- **Naming**: `feature/description-of-feature`
- **Examples**:
  - `feature/echo-brain-timeline-integration`
  - `feature/character-lora-system`
  - `feature/comfyui-workflow-optimization`
- **Lifetime**: Created for specific features, deleted after merge
- **Base**: Created from `development` or `main`

### 🐛 Hotfix Branches
- **Naming**: `hotfix/critical-issue-description`
- **Purpose**: Critical production fixes
- **Base**: Created from `main`
- **Merge**: Directly to `main` and back-merge to `development`

### 🧪 Experimental Branches
- **Naming**: `experiment/research-area`
- **Purpose**: Research and proof-of-concept work
- **Examples**:
  - `experiment/new-ai-model-testing`
  - `experiment/performance-optimization`
- **Lifecycle**: May be long-lived, archived when research concludes

## Echo Brain Integration Specific Branches

### Timeline Feature Branches
- **Naming**: `timeline/feature-or-storyline`
- **Purpose**: Anime timeline-specific development
- **Examples**:
  - `timeline/cyberpunk-goblin-slayer`
  - `timeline/character-evolution-system`
- **Integration**: Merge through Echo Brain validation pipeline

### AI Model Update Branches
- **Naming**: `models/model-update-description`
- **Purpose**: AI model integration and LoRA updates
- **Examples**:
  - `models/mei-character-lora-v2`
  - `models/combat-animation-enhancement`

## Commit Message Standards

### Format
```
type(scope): description

body (optional)

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation only
- **style**: Formatting, no code change
- **refactor**: Code restructuring
- **test**: Adding or modifying tests
- **chore**: Maintenance tasks

### Scopes (Optional)
- **echo**: Echo Brain integration
- **timeline**: Timeline branching system
- **api**: API endpoints
- **ui**: User interface
- **db**: Database changes
- **comfyui**: ComfyUI workflows

### Examples
```
feat(echo): Add timeline branching with database persistence

fix(api): Resolve hardcoded database credentials security issue

docs(timeline): Add comprehensive integration architecture guide
```

## Pull Request Workflow

### 1. Feature Development
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Regular commits during development
git add .
git commit -m "feat(scope): description"

# Push and create PR
git push -u origin feature/your-feature-name
```

### 2. Pull Request Requirements
- **Title**: Clear description of changes
- **Description**:
  - Summary of changes
  - Testing performed
  - Breaking changes (if any)
  - Screenshots (for UI changes)
- **Reviewers**: At least one other team member
- **Labels**: Appropriate labels (feature, bug, enhancement)

### 3. Review Process
- Code review by team members
- Automated tests must pass
- Security checks must pass
- Documentation updated if needed

### 4. Merge Strategy
- **Squash and merge** for feature branches
- **Rebase and merge** for critical fixes
- **Merge commit** for major releases

## Echo Brain Integration Workflow

### Timeline Branch Development
```bash
# Create timeline-specific branch
git checkout -b timeline/new-storyline

# Work with Echo Brain integration
git add services/echo_*.py
git commit -m "feat(echo): Add timeline integration services"

# Test integration
python test_echo_pipeline.py
python validate_integration.py

# Push for Echo Brain validation
git push -u origin timeline/new-storyline
```

### Validation Pipeline
1. **Local Testing**: Run integration test suite
2. **Echo Brain Validation**: AI-assisted code review
3. **Timeline Consistency Check**: Database schema validation
4. **ComfyUI Workflow Testing**: Generation pipeline verification
5. **Manual Review**: Human review of changes

## Release Management

### Version Numbering
- **Major**: `X.0.0` - Breaking changes, major features
- **Minor**: `X.Y.0` - New features, backward compatible
- **Patch**: `X.Y.Z` - Bug fixes, small improvements

### Release Process
1. **Feature Freeze**: No new features in `development`
2. **Release Branch**: `release/vX.Y.Z` created from `development`
3. **Final Testing**: Integration and regression tests
4. **Merge to Main**: Release branch merged to `main`
5. **Tag Release**: Create version tag with changelog
6. **Deploy**: Automated deployment to production

### Current Version
- **v2.0.0**: Echo Brain Timeline Integration (Current)
- **v1.5.0**: Basic Anime Generation System
- **v1.0.0**: Initial Release

## Best Practices

### Do's ✅
- Keep feature branches focused and small
- Write clear, descriptive commit messages
- Test locally before pushing
- Update documentation with code changes
- Use meaningful branch names
- Rebase feature branches before merging

### Don'ts ❌
- Direct commits to `main` branch
- Large, unfocused commits
- Pushing broken code
- Skipping code reviews
- Leaving stale branches
- Committing secrets or credentials

## Emergency Procedures

### Production Hotfix
```bash
# Create hotfix from main
git checkout main
git checkout -b hotfix/critical-security-fix

# Make fix and commit
git add .
git commit -m "fix(security): patch database vulnerability"

# Push and create urgent PR
git push -u origin hotfix/critical-security-fix
# Create PR with "URGENT" label
```

### Rollback Procedure
```bash
# Identify last good commit
git log --oneline main

# Create rollback branch
git checkout -b rollback/revert-broken-feature

# Revert problematic commits
git revert <commit-hash>

# Deploy rollback
git push -u origin rollback/revert-broken-feature
```

## Tools and Automation

### Pre-commit Hooks
- Security credential scanning
- Code formatting (Black, Prettier)
- Linting (ESLint, Pylint)
- Test execution

### CI/CD Pipeline
- **GitHub Actions**: Automated testing and deployment
- **Security Scanning**: SAST and dependency checks
- **Quality Gates**: Code coverage and complexity analysis
- **Deployment**: Automated staging and production deployment

---

## Integration Points

### Echo Brain System
- **Repository**: `/opt/tower-echo-brain`
- **Integration**: JSON-based API communication
- **Validation**: AI-assisted code review pipeline

### ComfyUI Workflows
- **Directory**: `workflows/comfyui/`
- **Validation**: Automated workflow testing
- **Versioning**: Workflow JSON files in git

### Database Schema
- **Migrations**: `sql/` directory
- **Versioning**: Database migration tracking
- **Rollback**: Migration rollback procedures

---

**Last Updated**: 2026-01-02
**Version**: 2.0.0
**Status**: ✅ Active and Enforced