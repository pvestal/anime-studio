"""
Echo Brain Creative AI System
A holistic creative assistant for anime production
"""

from .assist import EchoBrainAssistant
from .workflow_orchestrator import CreativeWorkflowOrchestrator
from .routes import router as echo_brain_router

__all__ = [
    'EchoBrainAssistant',
    'CreativeWorkflowOrchestrator',
    'echo_brain_router'
]

__version__ = '1.0.0'