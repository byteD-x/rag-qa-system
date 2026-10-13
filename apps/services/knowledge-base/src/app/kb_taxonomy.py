from __future__ import annotations

from typing import Any

from shared.api_errors import raise_api_error


def _display_path(path: str) -> str:
    return path or "metadata"


def _validate_value(value: Any, schema: dict[str, Any], *, path: str) -> None:
    """Validate the portable JSON-Schema subset used by knowledge-base types.

    The registry is intentionally extensible, so unknown schema keywords are
    ignored.  This keeps type registration forward-compatible while enforcing
    the common object/array/scalar constraints without adding a new dependency.
    """
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} must be an object")
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            key_name = str(key)
            if key_name not in value or value[key_name] in (None, ""):
                raise_api_error(400, "kb_metadata_required", f"{_display_path(f'{path}.{key_name}')} is required")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - {str(key) for key in properties})
            if unknown:
                raise_api_error(400, "kb_metadata_unknown_field", f"unsupported metadata field: {', '.join(unknown)}")
        for key, child_schema in properties.items():
            if key in value and isinstance(child_schema, dict):
                _validate_value(value[key], child_schema, path=f"{path}.{key}" if path else str(key))
        return

    if expected == "array":
        if not isinstance(value, list):
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} must be an array")
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} has too few items")
        if isinstance(max_items, int) and len(value) > max_items:
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} has too many items")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_value(item, item_schema, path=f"{path}[{index}]")
        return

    valid_types = {
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected in valid_types and not valid_types[expected](value):
        raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} must be {expected}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} must be one of the configured values")
    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} is too short")
        if isinstance(max_length, int) and len(value) > max_length:
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} is too long")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} is below the minimum")
        if isinstance(maximum, (int, float)) and value > maximum:
            raise_api_error(400, "kb_metadata_invalid", f"{_display_path(path)} is above the maximum")


def validate_type_schema(schema: dict[str, Any]) -> None:
    if not isinstance(schema, dict):
        raise_api_error(400, "kb_type_schema_invalid", "knowledge base type schema must be an object")
    if schema and schema.get("type") not in (None, "object"):
        raise_api_error(400, "kb_type_schema_invalid", "knowledge base type schema root must be an object")
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise_api_error(400, "kb_type_schema_invalid", "knowledge base type schema properties must be an object")
    required = schema.get("required")
    if required is not None and not isinstance(required, list):
        raise_api_error(400, "kb_type_schema_invalid", "knowledge base type schema required must be an array")


def validate_base_metadata(*, schemas: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    """Apply every selected type's schema to the shared base metadata object."""
    for schema in schemas:
        if not schema:
            continue
        validate_type_schema(schema)
        _validate_value(metadata, schema, path="metadata")
