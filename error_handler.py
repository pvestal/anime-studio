#!/usr/bin/env python3
'''Enhanced Error Handling for Anime Service'''
import logging
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    LOW = 'low'           # Recoverable, retry
    MEDIUM = 'medium'     # Degraded functionality
    HIGH = 'high'         # Service failure
    CRITICAL = 'critical' # Complete system failure

class ErrorCategory(Enum):
    COMFYUI_CONNECTION = 'comfyui_connection'
    COMFYUI_GENERATION = 'comfyui_generation'
    VRAM_SHORTAGE = 'vram_shortage'
    TIMEOUT = 'timeout'
    FILE_SYSTEM = 'file_system'
    APPLE_MUSIC = 'apple_music'
    QUALITY_ASSESSMENT = 'quality_assessment'
    UNKNOWN = 'unknown'

class AnimeServiceError(Exception):
    '''Base exception for anime service errors'''
    def __init__(
        self, 
        message: str,
        category: ErrorCategory,
        severity: ErrorSeverity,
        generation_id: Optional[str] = None,
        original_error: Optional[Exception] = None,
        recovery_suggestion: Optional[str] = None
    ):
        self.message = message
        self.category = category
        self.severity = severity
        self.generation_id = generation_id
        self.original_error = original_error
        self.recovery_suggestion = recovery_suggestion
        self.timestamp = datetime.now().isoformat()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'error': self.message,
            'category': self.category.value,
            'severity': self.severity.value,
            'generation_id': self.generation_id,
            'timestamp': self.timestamp,
            'recovery_suggestion': self.recovery_suggestion,
            'original_error': str(self.original_error) if self.original_error else None
        }

class ErrorHandler:
    '''Centralized error handling and logging'''
    
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.error_log = log_dir / 'errors.jsonl'
        self.error_stats = {
            'total_errors': 0,
            'by_category': {},
            'by_severity': {}
        }
    
    def handle_error(self, error: AnimeServiceError) -> Dict[str, Any]:
        '''Handle an error and return response'''
        # Log to structured error file
        self._log_error(error)
        
        # Update statistics
        self._update_stats(error)
        
        # Log to standard logger
        log_level = {
            ErrorSeverity.LOW: logging.WARNING,
            ErrorSeverity.MEDIUM: logging.ERROR,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }[error.severity]
        
        logger.log(
            log_level,
            f'[{error.category.value}] {error.message} (ID: {error.generation_id})'
        )
        
        return error.to_dict()
    
    def _log_error(self, error: AnimeServiceError):
        '''Log error to JSON lines file'''
        try:
            with open(self.error_log, 'a') as f:
                f.write(json.dumps(error.to_dict()) + '\n')
        except Exception as e:
            logger.error(f'Failed to log error to file: {e}')
    
    def _update_stats(self, error: AnimeServiceError):
        '''Update error statistics'''
        self.error_stats['total_errors'] += 1
        
        cat = error.category.value
        self.error_stats['by_category'][cat] =             self.error_stats['by_category'].get(cat, 0) + 1
        
        sev = error.severity.value
        self.error_stats['by_severity'][sev] =             self.error_stats['by_severity'].get(sev, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        '''Get error statistics'''
        return self.error_stats

# Specific error types
class ComfyUIConnectionError(AnimeServiceError):
    def __init__(self, generation_id: str, original_error: Exception):
        super().__init__(
            message='ComfyUI service is unreachable',
            category=ErrorCategory.COMFYUI_CONNECTION,
            severity=ErrorSeverity.HIGH,
            generation_id=generation_id,
            original_error=original_error,
            recovery_suggestion='Check if ComfyUI service is running on port 8188'
        )

class VRAMShortageError(AnimeServiceError):
    def __init__(self, generation_id: str, available_gb: float, required_gb: float):
        super().__init__(
            message=f'Insufficient VRAM: {available_gb:.2f}GB available, {required_gb:.2f}GB required',
            category=ErrorCategory.VRAM_SHORTAGE,
            severity=ErrorSeverity.MEDIUM,
            generation_id=generation_id,
            recovery_suggestion='Wait for current generations to complete or reduce resolution'
        )

class GenerationTimeoutError(AnimeServiceError):
    def __init__(self, generation_id: str, timeout_seconds: int):
        super().__init__(
            message=f'Video generation timeout after {timeout_seconds} seconds',
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.MEDIUM,
            generation_id=generation_id,
            original_error=None,
            recovery_suggestion='Try reducing video length or resolution'
        )
