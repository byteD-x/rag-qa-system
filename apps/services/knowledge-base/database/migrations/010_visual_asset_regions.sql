CREATE TABLE IF NOT EXISTS kb_visual_asset_regions (
    id UUID PRIMARY KEY,
    asset_id UUID NOT NULL REFERENCES kb_visual_assets(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    region_index INTEGER NOT NULL,
    page_number INTEGER NULL,
    region_label TEXT NOT NULL DEFAULT '',
    layout_hints_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    bbox_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NULL,
    summary TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asset_id, region_index)
);

CREATE INDEX IF NOT EXISTS idx_kb_visual_asset_regions_asset
    ON kb_visual_asset_regions(asset_id, region_index ASC);

CREATE INDEX IF NOT EXISTS idx_kb_visual_asset_regions_document
    ON kb_visual_asset_regions(document_id, page_number ASC, region_index ASC);
