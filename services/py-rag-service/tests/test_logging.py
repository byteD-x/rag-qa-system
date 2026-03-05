"""
测试结构化日志功能
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.logger import setup_logger

logger = setup_logger(name="test", level="DEBUG", service_name="test-service")

print("Testing structured logging...")
print("=" * 60)

logger.debug("This is a debug message")
logger.info("This is an info message")
logger.warning("This is a warning message")
logger.error("This is an error message")

try:
    raise ValueError("Test exception")
except Exception as exc:
    logger.error(
        "Exception occurred",
        extra={
            "extra_fields": {
                "test_field": "test_value",
                "another_field": 123,
            }
        },
        exc_info=True,
    )

print("=" * 60)
print("Check the output above - each line should be valid JSON")
