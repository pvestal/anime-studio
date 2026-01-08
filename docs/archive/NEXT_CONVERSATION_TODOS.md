# Next Conversation TODOs - Make Personal Anime System Usable

## Context for Next Claude Session
**Achievement**: 93% character consistency with ControlNet + IPAdapter working
**Problem**: System is proof-of-concept, not usable for personal daily creative work
**Goal**: Build simple CLI tool for personal anime character generation

## Priority 1 TODOs (Must Have)

### 1. Create Simple CLI Interface
```bash
# Target commands:
anime-gen --character sakura --pose "sitting" --output ~/anime/
anime-gen --character-sheet "pink hair anime girl" --name yuki
anime-gen --variations sakura 5
```
- [ ] Create `anime-gen` command-line tool
- [ ] Wrap working ControlNet + IPAdapter workflow
- [ ] Add argument parsing and validation
- [ ] Implement basic error handling

### 2. Character Library System
- [ ] Create `~/.anime-characters/` directory structure
- [ ] Character storage: reference image + metadata
- [ ] Character listing and management commands
- [ ] Import existing sakura reference into library

### 3. Automatic Output Organization
- [ ] Create dated output folders: `~/anime-output/2024-12-04/`
- [ ] Filename convention: `character_pose_timestamp.png`
- [ ] Symlink recent outputs to `~/anime-output/latest/`
- [ ] Clean up ComfyUI output folder integration

## Priority 2 TODOs (Should Have)

### 4. Pose Library System
- [ ] Extract common poses from existing images
- [ ] Text-to-pose mapping: "sitting" → pose skeleton
- [ ] Pose variation system (slight random changes)
- [ ] Fallback pose if text-to-pose fails

### 5. Batch Generation
- [ ] Generate multiple variations in one command
- [ ] Progress bar for batch operations
- [ ] Parallel generation if possible
- [ ] Batch consistency measurement

### 6. Configuration System
- [ ] Create `~/.anime-config.yaml` for settings
- [ ] Model paths and parameters
- [ ] Default output settings
- [ ] Personal preferences

## Priority 3 TODOs (Nice to Have)

### 7. Quality Control
- [ ] Auto-measure consistency and reject <90%
- [ ] Basic face detection validation
- [ ] Aesthetic scoring integration
- [ ] Manual quality rating system

### 8. Performance Improvements
- [ ] Optimize generation speed (<8 seconds target)
- [ ] Better VRAM management
- [ ] ComfyUI health monitoring and restart
- [ ] Queue system for multiple requests

### 9. User Experience Polish
- [ ] Better error messages
- [ ] Generation previews/thumbnails
- [ ] Recent generations browser
- [ ] Favorite poses and variations

## Implementation Notes

### Key Working Components to Preserve:
- ControlNet + IPAdapter workflow from `test_actual_fix.py` (93% consistency)
- OpenPose extraction from `test_openpose_simple.py`
- CLIP similarity measurement

### File Locations:
- Working workflows: `/opt/tower-anime-production/test_actual_fix.py`
- ComfyUI: `/mnt/1TB-storage/ComfyUI/`
- Character references: Currently `sakura_reference_424242_00001_.png`

### Technical Constraints:
- ComfyUI API at `http://localhost:8188`
- NVIDIA GPU only setup (RTX 3060)
- Python environment at `/opt/tower-anime-production/venv/`

## Success Metrics for Next Session:
1. **Can run**: `anime-gen sakura "standing"` and get output
2. **Can manage**: Create/list/use multiple characters
3. **Can batch**: Generate 5 variations with one command
4. **Organized output**: Files go to dated folders with good names

## Critical: Start with CLI Interface
Don't get distracted by optimization. Focus on making the proven 93% consistency system **actually usable** for daily creative work.

The technical hard part (character consistency) is solved. Now solve the usability hard part.