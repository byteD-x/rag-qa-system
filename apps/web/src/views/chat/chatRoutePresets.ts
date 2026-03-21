export interface BuildKbChatRouteQueryOptions {
  baseId: string;
  documentId: string;
  compareDocumentId?: string;
}

export interface ResolvedKbRoutePreset {
  scope: {
    mode: 'single';
    corpus_ids: string[];
    document_ids: string[];
  };
  question: string;
}

function normalizeId(value: unknown): string {
  return String(value || '').trim();
}

export function buildKbChatRouteQuery(options: BuildKbChatRouteQueryOptions): Record<string, string> {
  const baseId = normalizeId(options.baseId);
  const documentId = normalizeId(options.documentId);
  const compareDocumentId = normalizeId(options.compareDocumentId);
  const hasCompareDocument = Boolean(compareDocumentId && compareDocumentId !== documentId);

  return {
    preset: 'kb',
    baseId,
    documentId,
    ...(hasCompareDocument ? { compareDocumentId } : {}),
    question: hasCompareDocument
      ? `请先比较当前版本与 ${compareDocumentId} 的正文差异，再回答我的问题。`
      : '请基于当前版本回答我的问题。'
  };
}

export function resolveKbRoutePreset(query: Record<string, unknown>): ResolvedKbRoutePreset | null {
  const preset = normalizeId(query.preset);
  const baseId = normalizeId(query.baseId);
  const documentId = normalizeId(query.documentId);
  const compareDocumentId = normalizeId(query.compareDocumentId);
  const question = normalizeId(query.question);
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
    question
  };
}
