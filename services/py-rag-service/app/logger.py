"""
结构化日志配置模块
使用 JSON 格式输出，支持 ELK/Prometheus 集成
"""
import logging
import sys
from typing import Any, Dict, List, Optional


def setup_logger(
    name: str,
    level: str = "INFO",
    service_name: str = "py-rag-service",
) -> logging.Logger:
    """
    设置结构化日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        service_name: 服务名称

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))

        formatter = StructuredJsonFormatter(service_name=service_name)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


class StructuredJsonFormatter(logging.Formatter):
    """
    JSON 格式化的日志 Formatter
    输出格式:
    {
        "timestamp": "2026-03-05T12:34:56.789Z",
        "level": "INFO",
        "service": "py-rag-service",
        "logger": "py-rag-service.app.main",
        "message": "请求处理完成",
        "request_id": "xxx-xxx-xxx",
        "duration_ms": 123.45,
        "extra_field1": "value1"
    }
    """

    def __init__(self, service_name: str = "py-rag-service"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id") and record.request_id:
            log_data["request_id"] = record.request_id

        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms

        if hasattr(record, "query_id") and record.query_id:
            log_data["query_id"] = record.query_id

        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]) if record.exc_info[1] else "",
                "traceback": self.formatException(record.exc_info),
            }

        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        if hasattr(record, "retrieval_stats"):
            log_data["retrieval_stats"] = record.retrieval_stats

        if hasattr(record, "intent_info"):
            log_data["intent_info"] = record.intent_info

        if hasattr(record, "cache_info"):
            log_data["cache_info"] = record.cache_info

        return json.dumps(log_data, ensure_ascii=False)
