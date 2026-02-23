# Tower Anime Production - Reorganization Plan

## Current Problem
- 120+ files in root directory
- Test files mixed with production code
- No clear workflow progression
- Multiple overlapping documentation files
- Experimental code cluttering workspace

## Proposed Structure

```
/opt/anime-studio/
├── README.md                    # Main project overview
├── QUICK_START.md              # How to get started
├── requirements.txt            # Dependencies
├── .env                        # Environment config
│
├── production/                 # PRODUCTION WORKFLOWS ONLY
│   ├── workflows/              # Validated production workflows
│   │   ├── ltx_video_2b.py    # Proven 121-frame workflow
│   │   ├── animatediff_16.py  # Proven 16-frame workflow
│   │   └── database_ssot.py   # Database workflow loader
│   ├── pipeline/              # Story-to-video pipeline
│   │   ├── story_to_image.py  # Gate 1: Story → Image
│   │   ├── image_to_video.py  # Gate 2: Image → Video
│   │   └── video_pipeline.py  # Complete pipeline
│   └── validation/            # Quality gates
│       ├── image_validator.py # Image quality checks
│       └── video_validator.py # Video quality checks
│
├── api/                       # FastAPI service (existing)
│   ├── main.py               # Main API entry
│   ├── routers/              # API routes
│   └── services/             # Business logic
│
├── database/                  # Database management (existing)
│   ├── migrations/           # Schema changes
│   └── workflows/            # SSOT workflow storage
│
├── docs/                     # CONSOLIDATED DOCUMENTATION
│   ├── WORKING_SOLUTIONS.md  # What actually works
│   ├── FAILED_ATTEMPTS.md    # What doesn't work (why)
│   ├── SETUP_GUIDE.md        # Installation/setup
│   └── TROUBLESHOOTING.md    # Common issues
│
├── development/              # DEVELOPMENT & TESTING
│   ├── experiments/          # New feature testing
│   ├── tests/                # Unit/integration tests
│   └── benchmarks/           # Performance testing
│
└── archive/                  # OLD/DEPRECATED FILES
    ├── failed_experiments/   # Non-working code
    └── legacy/               # Old implementations
```

## Migration Strategy

### Phase 1: Create Structure (Immediate)
1. Create new directory structure
2. Move working workflows to production/
3. Archive failed experiments

### Phase 2: Document Gates (Next)
1. Create story-to-image pipeline with validation
2. Create image-to-video pipeline with validation
3. Document quality gates between steps

### Phase 3: Clean Production Pipeline (Final)
1. Remove all experimental files from root
2. Create clear entry points for each workflow
3. Document exactly what works and what doesn't

## Success Criteria
- Clear separation of working vs experimental code
- Story-to-video pipeline with validation gates
- New team member can understand structure in 5 minutes
- Zero confusion about what actually works