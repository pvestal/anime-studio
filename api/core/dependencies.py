"""
Shared dependencies for Tower Anime Production API
"""

import sys
import logging
from typing import Dict, Optional

# Fix Python path for imports
sys.path.insert(0, '/opt/anime-studio')
sys.path.append('/opt/anime-studio/pipeline')
sys.path.append('/opt/anime-studio/quality')
sys.path.append('/opt/anime-studio/services')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import integrated pipeline
try:
    from test_pipeline_simple import SimplifiedAnimePipeline
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    logger.warning("Simplified anime pipeline not available")

# Import Echo Brain service
try:
    from echo_brain_integration import echo_brain_service
    ECHO_BRAIN_AVAILABLE = True
except ImportError:
    logger.warning("Echo Brain service not available")
    ECHO_BRAIN_AVAILABLE = False


def get_pipeline():
    """Get the anime pipeline instance"""
    if not PIPELINE_AVAILABLE:
        raise RuntimeError("Anime pipeline is not available")
    return SimplifiedAnimePipeline()


def get_echo_brain():
    """Get the echo brain service instance"""
    if not ECHO_BRAIN_AVAILABLE:
        raise RuntimeError("Echo Brain service is not available")
    return echo_brain_service