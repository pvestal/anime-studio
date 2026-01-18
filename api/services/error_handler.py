"""
Comprehensive error handling for Tower Anime Production API
"""
import logging
import traceback
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from psycopg2.errors import UniqueViolation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class APIError(Exception):
    """Base exception for API errors"""
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

class DatabaseError(APIError):
    """Database-related errors"""
    def __init__(self, message: str = "Database operation failed", details: dict = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, details)

class ValidationError(APIError):
    """Input validation errors"""
    def __init__(self, message: str = "Invalid input data", details: dict = None):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY, details)

class AuthenticationError(APIError):
    """Authentication-related errors"""
    def __init__(self, message: str = "Authentication required", details: dict = None):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, details)

class AuthorizationError(APIError):
    """Authorization-related errors"""
    def __init__(self, message: str = "Insufficient permissions", details: dict = None):
        super().__init__(message, status.HTTP_403_FORBIDDEN, details)

class NotFoundError(APIError):
    """Resource not found errors"""
    def __init__(self, message: str = "Resource not found", details: dict = None):
        super().__init__(message, status.HTTP_404_NOT_FOUND, details)

def handle_database_error(error: Exception) -> APIError:
    """Convert database errors to appropriate API errors"""
    logger.error(f"Database error: {error}")

    if isinstance(error, IntegrityError):
        if isinstance(error.orig, UniqueViolation):
            return ValidationError(
                message="Resource already exists",
                details={"type": "unique_violation", "original_error": str(error.orig)}
            )
        return ValidationError(
            message="Data integrity violation",
            details={"type": "integrity_error", "original_error": str(error.orig)}
        )

    if isinstance(error, SQLAlchemyError):
        return DatabaseError(
            message="Database operation failed",
            details={"type": "sqlalchemy_error", "original_error": str(error)}
        )

    return DatabaseError(
        message="Unexpected database error",
        details={"original_error": str(error)}
    )

def log_error(error: Exception, context: dict = None):
    """Log error with context and traceback"""
    context = context or {}
    logger.error(
        f"Error occurred: {error}\n"
        f"Context: {context}\n"
        f"Traceback: {traceback.format_exc()}"
    )

def create_error_response(error: APIError) -> HTTPException:
    """Create FastAPI HTTPException from APIError"""
    return HTTPException(
        status_code=error.status_code,
        detail={
            "message": error.message,
            "details": error.details
        }
    )

def safe_execute(func, error_message: str = "Operation failed", context: dict = None):
    """Safely execute a function with comprehensive error handling"""
    try:
        return func()
    except APIError:
        # Re-raise API errors as-is
        raise
    except SQLAlchemyError as e:
        log_error(e, context)
        api_error = handle_database_error(e)
        raise create_error_response(api_error)
    except Exception as e:
        log_error(e, context)
        api_error = APIError(error_message, details={"original_error": str(e)})
        raise create_error_response(api_error)