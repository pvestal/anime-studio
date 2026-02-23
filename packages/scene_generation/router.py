"""Scene generation router — aggregates sub-module routers.

Sub-modules:
  - scene_crud.py: CRUD for scenes and shots, audio, generation
  - scene_comparison.py: Video A/B engine comparison
  - scene_review.py: Video review, QC, engine stats

Route ordering: static routes (/scenes/motion-presets, /scenes/video-compare, etc.)
come BEFORE dynamic routes (/scenes/{scene_id}) via sub-router include order.
"""

import logging

from fastapi import APIRouter

from .framepack import router as framepack_router
from .ltx_video import router as ltx_router
from .wan_video import router as wan_router

# Import sub-module routers
from .scene_comparison import router as comparison_router
from .scene_review import router as review_router
from .scene_crud import router as crud_router

logger = logging.getLogger(__name__)

router = APIRouter()

# Include engine-specific routers first
router.include_router(framepack_router)
router.include_router(ltx_router)
router.include_router(wan_router)

# Static routes must come before dynamic {scene_id} routes.
# scene_comparison and scene_review have static /scenes/* routes.
# scene_crud has both static and dynamic routes (ordered correctly within).
router.include_router(comparison_router)
router.include_router(review_router)
router.include_router(crud_router)
