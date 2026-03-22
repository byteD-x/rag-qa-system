export interface BuildKbChatRouteQueryOptions {
  baseId: string;
  documentId: string;
  compareDocumentId?: string;
  question?: string;
  focusHint?: KBChatFocusHint;
}

export interface KBChatFocusHint {
  kind?: string;
  document_ids?: string[];
  primary_document_id?: string;
  compare_document_ids?: string[];
  version_labels?: string[];
  version_label?: string;
  version_family_key?: string;
  asset_id?: string;
  region_id?: string;
  region_label?: string;
  page_number?: number | null;
  display_text?: string;
}

export interface ResolvedKbRoutePreset {
  scope: {
    mode: 'single';
    corpus_ids: string[];
    document_ids: string[];
  };
  question: string;
  focusHint?: KBChatFocusHint;
}

function normalizeId(value: unknown): string {
  return String(value || '').trim();
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => normalizeId(item))
    .filter((item, index, items) => item && items.indexOf(item) === index);
}

function normalizeFocusHint(value: unknown): KBChatFocusHint | undefined {
  if (!value || typeof value !== 'object') {
    return undefined;
  }
  const payload = value as Record<string, unknown>;
  const focusHint: KBChatFocusHint = {};
  const kind = normalizeId(payload.kind);
  const documentIds = normalizeStringArray(payload.document_ids);
  const primaryDocumentId = normalizeId(payload.primary_document_id);
  const compareDocumentIds = normalizeStringArray(payload.compare_document_ids);
  const versionLabels = normalizeStringArray(payload.version_labels);
  const versionLabel = normalizeId(payload.version_label);
  const versionFamilyKey = normalizeId(payload.version_family_key);
  const assetId = normalizeId(payload.asset_id);
  const regionId = normalizeId(payload.region_id);
  const regionLabel = normalizeId(payload.region_label);
  const displayText = normalizeId(payload.display_text);

  if (kind) {
    focusHint.kind = kind;
  }
  if (documentIds.length) {
    focusHint.document_ids = documentIds;
  }
  if (primaryDocumentId) {
    focusHint.primary_document_id = primaryDocumentId;
  }
  if (compareDocumentIds.length) {
    focusHint.compare_document_ids = compareDocumentIds;
  }
  if (versionLabels.length) {
    focusHint.version_labels = versionLabels;
  }
  if (versionLabel) {
    focusHint.version_label = versionLabel;
  }
  if (versionFamilyKey) {
    focusHint.version_family_key = versionFamilyKey;
  }
  if (assetId) {
    focusHint.asset_id = assetId;
  }
  if (regionId) {
    focusHint.region_id = regionId;
  }
  if (regionLabel) {
    focusHint.region_label = regionLabel;
  }
  if (displayText) {
    focusHint.display_text = displayText;
  }
  const pageNumber = Number(payload.page_number);
  if (Number.isFinite(pageNumber) && pageNumber > 0) {
    focusHint.page_number = pageNumber;
  }
  const hasValue = Object.values(focusHint).some((item) => {
    if (Array.isArray(item)) {
      return item.length > 0;
    }
    return item !== undefined && item !== null && item !== '';
  });
  return hasValue ? focusHint : undefined;
}

function serializeFocusHint(value: KBChatFocusHint | undefined): string {
  const focusHint = normalizeFocusHint(value);
  return focusHint ? JSON.stringify(focusHint) : '';
}

function parseFocusHint(value: unknown): KBChatFocusHint | undefined {
  const raw = normalizeId(value);
  if (!raw) {
    return undefined;
  }
  try {
    return normalizeFocusHint(JSON.parse(raw));
  } catch {
    return undefined;
  }
}

export function buildKbChatRouteQuery(options: BuildKbChatRouteQueryOptions): Record<string, string> {
  const baseId = normalizeId(options.baseId);
  const documentId = normalizeId(options.documentId);
  const compareDocumentId = normalizeId(options.compareDocumentId);
  const hasCompareDocument = Boolean(compareDocumentId && compareDocumentId !== documentId);
  const serializedFocusHint = serializeFocusHint(options.focusHint);
  const question = normalizeId(options.question);

  return {
    preset: 'kb',
    baseId,
    documentId,
    ...(hasCompareDocument ? { compareDocumentId } : {}),
    ...(serializedFocusHint ? { focusHint: serializedFocusHint } : {}),
    question: question || (
      hasCompareDocument
        ? `请先比较当前版本与 ${compareDocumentId} 的正文差异，再回答我的问题。`
        : serializedFocusHint
          ? '请结合当前焦点内容回答我的问题。'
          : '请基于当前版本回答我的问题。'
    )
  };
}

export function resolveKbRoutePreset(query: Record<string, unknown>): ResolvedKbRoutePreset | null {
  const preset = normalizeId(query.preset);
  const baseId = normalizeId(query.baseId);
  const documentId = normalizeId(query.documentId);
  const compareDocumentId = normalizeId(query.compareDocumentId);
  const question = normalizeId(query.question);
  const focusHint = parseFocusHint(query.focusHint);
  if (preset !== 'kb' || !baseId) {
    return null;
  }
  const documentIds = [documentId, compareDocumentId].filter((item, index, items) => item && items.indexOf(item) === index);
  return {
    scope: {
      mode: 'single',
      corpus_ids: [`kb:${baseId}`],
      document_ids: documentIds
    },
    question,
    focusHint
  };
}
