from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
KB_SRC = ROOT / "apps/services/knowledge-base/src"
PY_PACKAGES = ROOT / "packages/python"
for candidate in (KB_SRC, PY_PACKAGES):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from app import kb_resource_store
from app.kb_resource_store import serialize_visual_asset
from app.kb_schemas import CreateUploadRequest
from app.kb_version_assist import build_version_assist
from app.vision import extract_visual_assets


def test_create_upload_request_accepts_image_file_types() -> None:
    payload = CreateUploadRequest(
        base_id="base-1",
        file_name="screen.png",
        file_type="png",
        size_bytes=128,
        category="ops",
    )
    assert payload.file_type == "png"


def test_extract_visual_assets_supports_standalone_image(tmp_path: Path) -> None:
    image_path = tmp_path / "screen.png"
    Image.new("RGB", (120, 80), color=(255, 255, 255)).save(image_path)

    assets = extract_visual_assets(image_path, "png")

    assert len(assets) == 1
    assert assets[0].source_kind == "standalone"
    assert assets[0].page_number == 1
    assert assets[0].mime_type in {"image/png", "image/jpeg"}
    assert assets[0].width == 120
    assert assets[0].height == 80


def test_serialize_visual_asset_uses_thumbnail_route(monkeypatch) -> None:
    def fake_presign(storage_key: str, *, expires_in: int = 0) -> str:
        return f"https://example.test/{storage_key}"

    monkeypatch.setattr(kb_resource_store.storage, "presign_get_object", fake_presign)
    payload = serialize_visual_asset(
        {
            "id": "asset-1",
            "storage_key": "visual/original.png",
            "thumbnail_key": "visual/thumb.jpg",
        }
    )

    assert payload["asset_id"] == "asset-1"
    assert payload["thumbnail_url"] == "/api/v1/kb/visual-assets/asset-1/thumbnail"
    assert payload["image_url"] == "https://example.test/visual/original.png"


def test_build_version_assist_marks_high_confidence_continuous_version_for_auto_apply() -> None:
    result = build_version_assist(
        candidate={
            "file_name": "expense-policy-v3.pdf",
            "relative_path": "policies/expense-policy-v3.pdf",
            "source_uri": "notion://expense-policy",
            "source_updated_at": None,
            "source_metadata": {"page_title": "Expense Policy v3"},
        },
        existing_documents=[
            {
                "id": "doc-v2",
                "file_name": "expense-policy-v2.pdf",
                "source_uri": "notion://expense-policy",
                "source_metadata_json": {"relative_path": "policies/expense-policy-v2.pdf"},
                "version_family_key": "expense-policy",
                "version_number": 2,
                "updated_at": None,
            }
        ],
    )

    assert result["suggested_version_family_key"] == "expense-policy"
    assert result["suggested_supersedes_document_id"] == "doc-v2"
    assert result["suggested_version_label"] == "v3"
    assert result["auto_apply"] is True


def test_build_version_assist_respects_manual_version_metadata() -> None:
    result = build_version_assist(
        candidate={
            "file_name": "expense-policy-v4.pdf",
            "relative_path": "policies/expense-policy-v4.pdf",
            "source_uri": "notion://expense-policy",
            "source_updated_at": None,
            "source_metadata": {"page_title": "Expense Policy v4"},
        },
        existing_documents=[
            {
                "id": "doc-v3",
                "file_name": "expense-policy-v3.pdf",
                "source_uri": "notion://expense-policy",
                "source_metadata_json": {"relative_path": "policies/expense-policy-v3.pdf"},
                "version_family_key": "expense-policy",
                "version_number": 3,
                "updated_at": None,
            }
        ],
        explicit_version_family_key="expense-policy",
        explicit_version_label="v4",
    )

    assert result == {}
