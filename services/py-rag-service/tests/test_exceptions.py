"""
测试异常处理功能
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.exceptions import (
    RAGServiceError,
    LLMError,
    RetrievalError,
    ValidationError,
    NotFoundError,
)

print("Testing exception handling...")
print("=" * 60)

# Test 1: Basic RAGServiceError
try:
    raise RAGServiceError(
        message="Test error",
        code="TEST_ERROR",
        detail="Detailed information",
        status_code=500,
        extra_info={"field1": "value1"},
    )
except RAGServiceError as e:
    print(f"✓ RAGServiceError: {e.to_dict()}")

# Test 2: LLMError
try:
    raise LLMError(
        message="LLM service unavailable",
        detail="Connection timeout",
    )
except LLMError as e:
    print(f"✓ LLMError: {e.to_dict()}")
    assert e.status_code == 503
    assert e.code == "LLM_ERROR"

# Test 3: ValidationError
try:
    raise ValidationError(
        message="Invalid input format",
        detail="Field 'question' is required",
    )
except ValidationError as e:
    print(f"✓ ValidationError: {e.to_dict()}")
    assert e.status_code == 400
    assert e.code == "VALIDATION_ERROR"

# Test 4: NotFoundError
try:
    raise NotFoundError(
        resource="Document",
        detail="Document ID not found",
    )
except NotFoundError as e:
    print(f"✓ NotFoundError: {e.to_dict()}")
    assert e.status_code == 404
    assert e.code == "NOT_FOUND"

# Test 5: RetrievalError
try:
    raise RetrievalError(
        message="Qdrant connection failed",
        detail="Host unreachable",
    )
except RetrievalError as e:
    print(f"✓ RetrievalError: {e.to_dict()}")
    assert e.status_code == 503

print("=" * 60)
print("All exception tests passed!")
