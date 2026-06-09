from __future__ import annotations

import json

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError

from shared.api_errors import http_exception_response, json_error_response, validation_exception_response
from shared.tracing import reset_trace_id, set_trace_id


def test_http_exception_response_preserves_code_and_trace_id() -> None:
    token = set_trace_id("gateway-test-trace")
    try:
        response = http_exception_response(
            HTTPException(
                status_code=404,
                detail={
                    "detail": "chat session not found",
                    "code": "chat_session_not_found",
                },
            )
        )
    finally:
        reset_trace_id(token)

    payload = json.loads(response.body.decode("utf-8"))
    assert response.status_code == 404
    assert payload["detail"] == "chat session not found"
    assert payload["code"] == "chat_session_not_found"
    assert payload["trace_id"] == "gateway-test-trace"


def test_json_error_response_extra_cannot_override_base_fields() -> None:
    trace_context = set_trace_id("gateway-extra-trace")
    try:
        response = json_error_response(
            status_code=503,
            detail="service is not ready",
            code="service_not_ready",
            errors=[{"loc": ["query"], "msg": "invalid"}],
            extra={
                "detail": "overridden",
                "code": "overridden_code",
                "trace_id": "overridden-trace",
                "errors": [],
                "status": "not_ready",
            },
        )
    finally:
        reset_trace_id(trace_context)

    payload = json.loads(response.body.decode("utf-8"))
    assert payload["detail"] == "service is not ready"
    assert payload["code"] == "service_not_ready"
    assert payload["trace_id"] == "gateway-extra-trace"
    assert payload["errors"] == [{"loc": ["query"], "msg": "invalid"}]
    assert payload["status"] == "not_ready"


def test_validation_exception_response_exposes_error_rows() -> None:
    token = set_trace_id("gateway-validation-trace")
    try:
        response = validation_exception_response(
            RequestValidationError(
                [
                    {
                        "loc": ("body", "scope", "mode"),
                        "msg": "field required",
                        "type": "missing",
                    }
                ]
            )
        )
    finally:
        reset_trace_id(token)

    payload = json.loads(response.body.decode("utf-8"))
    assert response.status_code == 422
    assert payload["code"] == "validation_error"
    assert payload["trace_id"] == "gateway-validation-trace"
    assert payload["errors"][0]["loc"] == ["body", "scope", "mode"]
