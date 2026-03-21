from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


ALLOWED_KB_FILE_TYPES = {"txt", "pdf", "docx", "png", "jpg", "jpeg"}
ALLOWED_CONNECTOR_TYPES = {
    "local_directory",
    "notion",
    "feishu_document",
    "dingtalk_document",
    "web_crawler",
    "sql_query",
}
ALLOWED_DOCUMENT_VERSION_STATUSES = {"active", "draft", "superseded", "archived"}
ALLOWED_DOCUMENT_REVIEW_STATUSES = {"review_pending", "approved", "rejected"}


def _normalize_optional_text(value: str | None, *, field_name: str, allow_blank: bool = False) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized and not allow_blank:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class CreateBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=120)


class UpdateBaseRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=120)


class CreateUploadRequest(BaseModel):
    base_id: str
    file_name: str = Field(min_length=1, max_length=255)
    file_type: str = Field(min_length=1, max_length=16)
    size_bytes: int = Field(gt=0)
    category: str = Field(default="", max_length=120)
    version_family_key: str | None = Field(default=None, max_length=160)
    version_label: str | None = Field(default=None, max_length=64)
    version_number: int | None = Field(default=None, ge=1, le=100000)
    version_status: str | None = Field(default=None, max_length=32)
    is_current_version: bool | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    supersedes_document_id: str | None = Field(default=None, max_length=64)

    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, value: str) -> str:
        normalized = value.lower().lstrip(".").strip()
        if normalized not in ALLOWED_KB_FILE_TYPES:
            raise ValueError(f"unsupported kb file type: {normalized}")
        return normalized

    @field_validator("version_family_key")
    @classmethod
    def normalize_version_family_key(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="version_family_key")

    @field_validator("version_label")
    @classmethod
    def normalize_version_label(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="version_label")

    @field_validator("version_status")
    @classmethod
    def validate_version_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(_normalize_optional_text(value, field_name="version_status") or "").lower()
        if normalized not in ALLOWED_DOCUMENT_VERSION_STATUSES:
            raise ValueError(f"unsupported version status: {normalized}")
        return normalized

    @field_validator("supersedes_document_id")
    @classmethod
    def normalize_supersedes_document_id(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="supersedes_document_id")

    @model_validator(mode="after")
    def validate_version_window(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be greater than or equal to effective_from")
        if self.is_current_version and self.version_status and self.version_status != "active":
            raise ValueError("current version must use active status")
        return self


class PresignPartsRequest(BaseModel):
    part_numbers: list[int] = Field(min_length=1, max_length=1000)


class UploadPartItem(BaseModel):
    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1, max_length=256)
    size_bytes: int = Field(default=0, ge=0)


class CompleteUploadRequest(BaseModel):
    parts: list[UploadPartItem] = Field(default_factory=list)
    content_hash: str = Field(default="", max_length=128)


class RetrieveRequest(BaseModel):
    base_id: str
    question: str = Field(min_length=1, max_length=12000)
    document_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=20)


class RetrievalDebugRequest(RetrieveRequest):
    pass


class KBQueryRequest(BaseModel):
    base_id: str
    question: str = Field(min_length=1, max_length=12000)
    document_ids: list[str] = Field(default_factory=list)
    debug: bool = False


class UpdateDocumentRequest(BaseModel):
    file_name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=120)
    version_family_key: str | None = Field(default=None, max_length=160)
    version_label: str | None = Field(default=None, max_length=64)
    version_number: int | None = Field(default=None, ge=1, le=100000)
    version_status: str | None = Field(default=None, max_length=32)
    is_current_version: bool | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    supersedes_document_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=128)
    review_status: str | None = Field(default=None, max_length=32)
    reviewer_note: str | None = Field(default=None, max_length=1000)

    @field_validator("version_family_key")
    @classmethod
    def normalize_optional_version_family_key(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="version_family_key")

    @field_validator("version_label")
    @classmethod
    def normalize_optional_version_label(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="version_label")

    @field_validator("version_status")
    @classmethod
    def validate_optional_version_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(_normalize_optional_text(value, field_name="version_status") or "").lower()
        if normalized not in ALLOWED_DOCUMENT_VERSION_STATUSES:
            raise ValueError(f"unsupported version status: {normalized}")
        return normalized

    @field_validator("supersedes_document_id")
    @classmethod
    def normalize_optional_supersedes_document_id(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="supersedes_document_id")

    @field_validator("owner_user_id")
    @classmethod
    def normalize_optional_owner_user_id(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="owner_user_id", allow_blank=True)

    @field_validator("review_status")
    @classmethod
    def validate_optional_review_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            return ""
        if normalized not in ALLOWED_DOCUMENT_REVIEW_STATUSES:
            raise ValueError(f"unsupported review status: {normalized}")
        return normalized

    @field_validator("reviewer_note")
    @classmethod
    def normalize_optional_reviewer_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def validate_document_version_window(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be greater than or equal to effective_from")
        if self.is_current_version and self.version_status and self.version_status != "active":
            raise ValueError("current version must use active status")
        return self


class BatchUpdateDocumentsRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=200)
    patch: UpdateDocumentRequest
    task_id: str | None = Field(default=None, max_length=64)
    retry_of_task_id: str | None = Field(default=None, max_length=64)

    @field_validator("document_ids")
    @classmethod
    def normalize_document_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            document_id = str(item or "").strip()
            if not document_id:
                raise ValueError("document_ids must not contain blank values")
            if document_id not in normalized:
                normalized.append(document_id)
        return normalized

    @model_validator(mode="after")
    def validate_patch_has_changes(self):
        if not self.patch.model_dump(exclude_none=True):
            raise ValueError("patch must contain at least one field")
        return self

    @field_validator("task_id", "retry_of_task_id")
    @classmethod
    def normalize_task_ids(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value, field_name="task_id")


class UpdateChunkRequest(BaseModel):
    text_content: str | None = Field(default=None, min_length=1, max_length=40000)
    disabled: bool | None = None
    disabled_reason: str = Field(default="", max_length=240)
    manual_note: str = Field(default="", max_length=1000)

    @field_validator("text_content")
    @classmethod
    def normalize_text_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("text_content must not be blank")
        return normalized

    @field_validator("disabled_reason", "manual_note")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return value.strip()


class SplitChunkRequest(BaseModel):
    parts: list[str] = Field(min_length=2, max_length=16)

    @field_validator("parts")
    @classmethod
    def validate_parts(cls, value: list[str]) -> list[str]:
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if len(normalized) < 2:
            raise ValueError("parts must contain at least two non-empty text blocks")
        return normalized


class MergeChunksRequest(BaseModel):
    chunk_ids: list[str] = Field(min_length=2, max_length=16)
    separator: str = Field(default="\n\n", max_length=16)

    @field_validator("chunk_ids")
    @classmethod
    def validate_chunk_ids(cls, value: list[str]) -> list[str]:
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if len(normalized) < 2:
            raise ValueError("chunk_ids must contain at least two items")
        return list(dict.fromkeys(normalized))


class LocalDirectorySyncRequest(BaseModel):
    base_id: str
    source_path: str = Field(min_length=1, max_length=1024)
    category: str = Field(default="", max_length=120)
    recursive: bool = True
    delete_missing: bool = True
    dry_run: bool = False
    max_files: int | None = Field(default=None, ge=1, le=5000)


class NotionSyncRequest(BaseModel):
    base_id: str
    page_ids: list[str] = Field(min_length=1, max_length=64)
    category: str = Field(default="", max_length=120)
    delete_missing: bool = True
    dry_run: bool = False
    max_pages: int | None = Field(default=None, ge=1, le=256)

    @field_validator("page_ids")
    @classmethod
    def validate_page_ids(cls, value: list[str]) -> list[str]:
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if not normalized:
            raise ValueError("page_ids must not be empty")
        return normalized


class ConnectorScheduleRequest(BaseModel):
    enabled: bool = False
    interval_minutes: int | None = Field(default=None, ge=15, le=10080)

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.enabled and self.interval_minutes is None:
            raise ValueError("interval_minutes is required when schedule.enabled is true")
        return self


class CreateConnectorRequest(BaseModel):
    base_id: str
    name: str = Field(min_length=1, max_length=120)
    connector_type: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    schedule: ConnectorScheduleRequest = Field(default_factory=ConnectorScheduleRequest)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("connector_type")
    @classmethod
    def validate_connector_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_CONNECTOR_TYPES:
            raise ValueError(f"unsupported connector type: {normalized}")
        return normalized


class UpdateConnectorRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict[str, Any] | None = None
    schedule: ConnectorScheduleRequest | None = None
    status: str | None = Field(default=None, max_length=32)

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"active", "paused"}:
            raise ValueError(f"unsupported connector status: {normalized}")
        return normalized


class RunConnectorRequest(BaseModel):
    dry_run: bool = False
    limit: int | None = Field(default=None, ge=1, le=64)


class KBAnalyticsDashboardResponse(BaseModel):
    view: str = Field(description="Analytics scope. personal only includes the caller's KB resources; admin includes all visible resources.")
    days: int = Field(description="Rolling window in days for funnel and latency metrics.", ge=1, le=90)
    funnel: dict[str, Any] = Field(description="Core KB funnel metrics for knowledge-base creation, document upload, and document ready transitions.")
    ingest_health: dict[str, Any] = Field(description="Current ingest health snapshot, status distributions, and upload-to-ready latency statistics.")
    data_quality: dict[str, Any] = Field(description="Unsupported or degraded KB analytics fields. Empty arrays mean full support for the current payload.")


class KBGovernanceDocumentItem(BaseModel):
    document_id: str = Field(description="Document identifier.")
    base_id: str = Field(description="Knowledge base identifier.")
    base_name: str = Field(description="Knowledge base display name.")
    file_name: str = Field(description="Document file name.")
    status: str = Field(description="Document ingest status.")
    enhancement_status: str = Field(description="Visual or enhancement pipeline status.")
    version_family_key: str = Field(description="Document version family key when provided.")
    version_label: str = Field(description="Human readable version label.")
    version_number: int | None = Field(default=None, description="Monotonic version number if present.")
    version_status: str = Field(description="Version governance status.")
    is_current_version: bool = Field(description="Whether the document is marked as the current version.")
    effective_from: datetime | None = Field(default=None, description="Effective window start timestamp.")
    effective_to: datetime | None = Field(default=None, description="Effective window end timestamp.")
    effective_now: bool = Field(description="Whether the version is currently effective.")
    visual_asset_count: int = Field(default=0, ge=0, description="Detected visual asset count from OCR or visual extraction.")
    low_confidence_region_count: int = Field(default=0, ge=0, description="How many stored visual regions are below the governance confidence threshold.")
    low_confidence_asset_id: str = Field(description="Representative asset id for the first low-confidence visual region.")
    low_confidence_region_id: str = Field(description="Representative low-confidence region id for deep links.")
    low_confidence_region_label: str = Field(description="Representative low-confidence region label.")
    low_confidence_region_confidence: float | None = Field(default=None, description="Confidence score of the representative low-confidence region.")
    low_confidence_region_bbox: list[float] = Field(default_factory=list, description="Bounding box of the representative low-confidence region in normalized coordinates.")
    created_at: datetime | None = Field(default=None, description="Document creation timestamp.")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp.")
    owner_user_id: str = Field(description="Responsible owner user id for governance follow-up.")
    review_status: str = Field(description="Review workflow status stored for governance triage.")
    reviewer_note: str = Field(description="Latest reviewer note or rejection reason.")
    reviewed_at: datetime | None = Field(default=None, description="Timestamp of the latest review action.")
    reviewed_by_user_id: str = Field(description="User id of the latest reviewer.")
    reviewed_by_email: str = Field(description="Email of the latest reviewer.")
    reason: str = Field(description="Governance queue reason for surfacing this document.")


class KBGovernanceVersionConflictItem(BaseModel):
    base_id: str = Field(description="Knowledge base identifier.")
    base_name: str = Field(description="Knowledge base display name.")
    version_family_key: str = Field(description="Conflicting version family key.")
    current_version_count: int = Field(ge=0, description="How many documents are marked as current within the family.")
    active_version_count: int = Field(ge=0, description="How many documents are active within the family.")
    total_versions: int = Field(ge=0, description="Total document versions found in the family.")
    latest_version_number: int | None = Field(default=None, description="Highest observed version number in the family.")
    current_document_ids: list[str] = Field(default_factory=list, description="Current-version document ids involved in the conflict.")
    current_labels: list[str] = Field(default_factory=list, description="Current-version labels involved in the conflict.")


class KBGovernanceQueues(BaseModel):
    pending_review: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Draft or scheduled documents waiting for review or publish.")
    approved_ready: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Approved documents waiting to be published or switched current.")
    rejected_documents: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Rejected documents that need author follow-up.")
    expired_documents: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Documents whose effective window has ended.")
    visual_attention: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Documents with visual assets that still require enhancement or remediation.")
    visual_low_confidence: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Documents that contain low-confidence visual regions requiring manual review.")
    missing_version_family: list[KBGovernanceDocumentItem] = Field(default_factory=list, description="Documents with partial version metadata but no version family key.")
    version_conflicts: list[KBGovernanceVersionConflictItem] = Field(default_factory=list, description="Version families that currently have multiple current versions.")


class KBGovernanceSummary(BaseModel):
    pending_review: int = Field(default=0, ge=0)
    approved_ready: int = Field(default=0, ge=0)
    rejected_documents: int = Field(default=0, ge=0)
    expired_documents: int = Field(default=0, ge=0)
    visual_attention: int = Field(default=0, ge=0)
    visual_low_confidence: int = Field(default=0, ge=0)
    missing_version_family: int = Field(default=0, ge=0)
    version_conflicts: int = Field(default=0, ge=0)


class KBAnalyticsGovernanceResponse(BaseModel):
    view: str = Field(description="Governance scope. personal only includes the caller's KB resources; admin includes all visible resources.")
    limit: int = Field(description="Maximum number of records returned per governance queue.", ge=1, le=50)
    generated_at: datetime = Field(description="Payload generation timestamp in UTC.")
    summary: KBGovernanceSummary = Field(description="Top-level governance queue counts for the full result set, not only returned items.")
    queues: KBGovernanceQueues = Field(description="Governance queue samples for operator triage.")
    data_quality: dict[str, Any] = Field(description="Unsupported or degraded governance analytics fields. Empty arrays mean full support for the current payload.")
