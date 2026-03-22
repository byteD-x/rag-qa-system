import type { KBChatFocusHint } from '@/views/chat/chatRoutePresets';

function normalizeId(value: unknown): string {
  return String(value || '').trim();
}

function normalizeLabel(value: unknown, fallback: string): string {
  return normalizeId(value) || fallback;
}

function compareDocumentIds(primaryDocumentId: string, compareDocumentId: string): string[] {
  return [primaryDocumentId, compareDocumentId].filter((item, index, items) => item && items.indexOf(item) === index);
}

export function buildSingleVersionFocus(options: {
  documentId: string;
  versionLabel?: string;
  versionFamilyKey?: string;
  fileName?: string;
}): KBChatFocusHint {
  const documentId = normalizeId(options.documentId);
  const versionLabel = normalizeLabel(options.versionLabel, '当前版本');
  return {
    kind: 'single_version',
    document_ids: documentId ? [documentId] : [],
    primary_document_id: documentId,
    version_label: versionLabel,
    version_family_key: normalizeId(options.versionFamilyKey),
    display_text: normalizeLabel(options.fileName, versionLabel)
  };
}

export function buildCompareVersionsFocus(options: {
  primaryDocumentId: string;
  compareDocumentId: string;
  primaryVersionLabel?: string;
  compareVersionLabel?: string;
  versionFamilyKey?: string;
  assetId?: string;
  regionId?: string;
  regionLabel?: string;
  pageNumber?: number | null;
}): KBChatFocusHint {
  const primaryDocumentId = normalizeId(options.primaryDocumentId);
  const compareDocumentId = normalizeId(options.compareDocumentId);
  const primaryVersionLabel = normalizeLabel(options.primaryVersionLabel, '当前版本');
  const compareVersionLabel = normalizeLabel(options.compareVersionLabel, '对比版本');
  const pageNumber = Number(options.pageNumber);
  const pageLabel = Number.isFinite(pageNumber) && pageNumber > 0 ? `第 ${pageNumber} 页` : '';
  const regionLabel = normalizeId(options.regionLabel);
  const visualDisplay = [pageLabel, regionLabel].filter(Boolean).join(' / ');
  const displayText = visualDisplay
    ? `${primaryVersionLabel} vs ${compareVersionLabel} / ${visualDisplay}`
    : `${primaryVersionLabel} vs ${compareVersionLabel}`;
  return {
    kind: 'compare_versions',
    document_ids: compareDocumentIds(primaryDocumentId, compareDocumentId),
    primary_document_id: primaryDocumentId,
    compare_document_ids: compareDocumentIds(primaryDocumentId, compareDocumentId),
    version_labels: [primaryVersionLabel, compareVersionLabel],
    version_family_key: normalizeId(options.versionFamilyKey),
    ...(normalizeId(options.assetId) ? { asset_id: normalizeId(options.assetId) } : {}),
    ...(normalizeId(options.regionId) ? { region_id: normalizeId(options.regionId) } : {}),
    ...(regionLabel ? { region_label: regionLabel } : {}),
    ...(Number.isFinite(pageNumber) && pageNumber > 0 ? { page_number: pageNumber } : {}),
    display_text: displayText
  };
}

export function buildVisualFocus(options: {
  documentId: string;
  assetId: string;
  regionId?: string;
  regionLabel?: string;
  pageNumber?: number | null;
  versionLabel?: string;
}): KBChatFocusHint {
  const pageNumber = Number(options.pageNumber);
  const pageLabel = Number.isFinite(pageNumber) && pageNumber > 0 ? `第 ${pageNumber} 页` : '';
  const regionLabel = normalizeId(options.regionLabel);
  const versionLabel = normalizeId(options.versionLabel);
  const parts = [versionLabel, pageLabel, regionLabel].filter(Boolean);
  const documentId = normalizeId(options.documentId);
  return {
    kind: 'visual_region',
    document_ids: documentId ? [documentId] : [],
    primary_document_id: documentId,
    asset_id: normalizeId(options.assetId),
    region_id: normalizeId(options.regionId),
    region_label: regionLabel,
    page_number: Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber : undefined,
    version_label: versionLabel,
    display_text: parts.join(' / ') || '截图区域'
  };
}
