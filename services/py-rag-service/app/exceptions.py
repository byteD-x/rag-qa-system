"""
自定义异常定义模块
用于统一错误处理和日志记录
"""
from typing import Any, Dict, Optional


class RAGServiceError(Exception):
    """RAG 服务基础异常类"""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        detail: Optional[str] = None,
        status_code: int = 500,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.extra_info = extra_info or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式用于 JSON 响应"""
        result = {
            "error": self.message,
            "code": self.code,
        }
        if self.detail:
            result["detail"] = self.detail
        if self.extra_info:
            result.update(self.extra_info)
        return result


class LLMError(RAGServiceError):
    """LLM 调用相关异常"""

    def __init__(
        self,
        message: str = "LLM service error",
        detail: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="LLM_ERROR",
            detail=detail,
            status_code=503,
            extra_info=extra_info,
        )


class RetrievalError(RAGServiceError):
    """检索相关异常"""

    def __init__(
        self,
        message: str = "Retrieval service error",
        detail: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="RETRIEVAL_ERROR",
            detail=detail,
            status_code=503,
            extra_info=extra_info,
        )


class RerankError(RAGServiceError):
    """重排序相关异常"""

    def __init__(
        self,
        message: str = "Rerank service error",
        detail: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="RERANK_ERROR",
            detail=detail,
            status_code=503,
            extra_info=extra_info,
        )


class ValidationError(RAGServiceError):
    """输入验证异常"""

    def __init__(
        self,
        message: str = "Validation error",
        detail: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            detail=detail,
            status_code=400,
            extra_info=extra_info,
        )


class NotFoundError(RAGServiceError):
    """资源未找到异常"""

    def __init__(
        self,
        resource: str = "Resource",
        detail: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=f"{resource} not found",
            code="NOT_FOUND",
            detail=detail,
            status_code=404,
            extra_info=extra_info,
        )


class CacheError(RAGServiceError):
    """缓存相关异常"""

    def __init__(
        self,
        message: str = "Cache service error",
        detail: Optional[str] = None,
        extra_info: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="CACHE_ERROR",
            detail=detail,
            status_code=503,
            extra_info=extra_info,
        )


# 错误码常量
ERR_CODE_INTERNAL = "INTERNAL_ERROR"
ERR_CODE_NOT_FOUND = "NOT_FOUND"
ERR_CODE_INVALID_INPUT = "INVALID_INPUT"
ERR_CODE_UNAUTHORIZED = "UNAUTHORIZED"
ERR_CODE_FORBIDDEN = "FORBIDDEN"
ERR_CODE_CONFLICT = "CONFLICT"
ERR_CODE_SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
ERR_CODE_LLM_ERROR = "LLM_ERROR"
ERR_CODE_RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
ERR_CODE_RERANK_ERROR = "RERANK_ERROR"
ERR_CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
ERR_CODE_CACHE_ERROR = "CACHE_ERROR"
