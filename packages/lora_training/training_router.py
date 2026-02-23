"""Training sub-router -- delegates to training_jobs + training_variants sub-modules.

All original exports remain available from this module via re-export.
"""

import logging

from fastapi import APIRouter

from .training_variants import (
    variant_router,
    VariantRequest,
    RegenerateBody,
    CompareRequest,
    SceneTrainingRequest,
    generate_variant,
    regenerate_character,
    regenerate_compare,
    compare_status,
    generate_training_for_scenes,
    _extract_pose_hints,
)
from .training_jobs import (
    jobs_router,
    start_training,
    get_training_jobs_endpoint,
    get_training_job,
    get_training_log,
    cancel_training_job,
    delete_training_job,
    clear_finished_jobs,
    retry_training_job,
    invalidate_training_job,
    reconcile_training_jobs_endpoint,
    list_trained_loras,
    delete_trained_lora,
    gap_analysis,
    get_feedback,
    clear_feedback,
)

logger = logging.getLogger(__name__)

# Main router: includes both sub-routers
training_router = APIRouter()
training_router.include_router(variant_router)
training_router.include_router(jobs_router)

# Keep backward compatibility
__all__ = [
    "training_router",
    "start_training",
    "VariantRequest",
    "RegenerateBody",
    "CompareRequest",
    "SceneTrainingRequest",
]
