CREATE TABLE IF NOT EXISTS provider_billing_records (
    id UUID PRIMARY KEY,
    external_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    route_key TEXT NOT NULL DEFAULT '',
    prompt_key TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'CNY',
    billed_cost_cents BIGINT NOT NULL DEFAULT 0,
    input_tokens BIGINT NOT NULL DEFAULT 0,
    output_tokens BIGINT NOT NULL DEFAULT 0,
    billed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    imported_by_user_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT provider_billing_cost_non_negative CHECK (billed_cost_cents >= 0),
    CONSTRAINT provider_billing_input_tokens_non_negative CHECK (input_tokens >= 0),
    CONSTRAINT provider_billing_output_tokens_non_negative CHECK (output_tokens >= 0)
);

CREATE INDEX IF NOT EXISTS idx_provider_billing_records_user_billed
    ON provider_billing_records(user_id, billed_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_billing_records_tenant_billed
    ON provider_billing_records(tenant_id, billed_at DESC);

CREATE INDEX IF NOT EXISTS idx_provider_billing_records_provider_billed
    ON provider_billing_records(provider, billed_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_billing_records_provider_external_unique
    ON provider_billing_records(provider, external_id)
    WHERE external_id <> '';
