from typing import Any, Optional


class ClawZepException(Exception):
    """基础异常"""
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: Optional[Any] = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


# 向后兼容别名
YonZepException = ClawZepException


class NotFoundError(ClawZepException):
    status_code = 404
    error_code = "NOT_FOUND"


class UnauthorizedError(ClawZepException):
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(ClawZepException):
    status_code = 403
    error_code = "FORBIDDEN"


class ValidationError(ClawZepException):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ConflictError(ClawZepException):
    status_code = 409
    error_code = "CONFLICT"


class TenantQuotaExceededError(ClawZepException):
    status_code = 429
    error_code = "TENANT_QUOTA_EXCEEDED"


class ProjectNotFoundError(NotFoundError):
    error_code = "PROJECT_NOT_FOUND"


class TenantNotFoundError(NotFoundError):
    error_code = "TENANT_NOT_FOUND"


class GraphOperationError(ClawZepException):
    status_code = 500
    error_code = "GRAPH_OPERATION_ERROR"


class VectorOperationError(ClawZepException):
    status_code = 500
    error_code = "VECTOR_OPERATION_ERROR"


class TemporalConflictError(ConflictError):
    error_code = "TEMPORAL_CONFLICT"


class MemoryTreeError(ClawZepException):
    status_code = 500
    error_code = "MEMORY_TREE_ERROR"


class RateLimitExceededError(ClawZepException):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class RetrievalError(ClawZepException):
    status_code = 500
    error_code = "RETRIEVAL_ERROR"
