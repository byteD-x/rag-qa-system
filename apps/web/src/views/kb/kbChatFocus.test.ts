import { describe, expect, it } from 'vitest';

import { buildCompareVersionsFocus, buildSingleVersionFocus, buildVisualFocus } from './kbChatFocus';

describe('kbChatFocus', () => {
  it('builds single-version focus payload', () => {
    expect(buildSingleVersionFocus({
      documentId: 'doc-1',
      versionLabel: 'v3',
      versionFamilyKey: 'expense-policy',
      fileName: 'Expense Policy'
    })).toEqual({
      kind: 'single_version',
      document_ids: ['doc-1'],
      primary_document_id: 'doc-1',
      version_label: 'v3',
      version_family_key: 'expense-policy',
      display_text: 'Expense Policy'
    });
  });

  it('builds compare-versions focus payload', () => {
    expect(buildCompareVersionsFocus({
      primaryDocumentId: 'doc-2',
      compareDocumentId: 'doc-1',
      primaryVersionLabel: 'v2',
      compareVersionLabel: 'v1',
      versionFamilyKey: 'expense-policy'
    })).toEqual({
      kind: 'compare_versions',
      document_ids: ['doc-2', 'doc-1'],
      primary_document_id: 'doc-2',
      compare_document_ids: ['doc-2', 'doc-1'],
      version_labels: ['v2', 'v1'],
      version_family_key: 'expense-policy',
      display_text: 'v2 vs v1'
    });
  });

  it('builds compare-versions focus payload with visual context', () => {
    expect(buildCompareVersionsFocus({
      primaryDocumentId: 'doc-2',
      compareDocumentId: 'doc-1',
      primaryVersionLabel: 'v2',
      compareVersionLabel: 'v1',
      versionFamilyKey: 'expense-policy',
      assetId: 'asset-9',
      regionId: 'region-3',
      regionLabel: '红框配置',
      pageNumber: 3
    })).toEqual({
      kind: 'compare_versions',
      document_ids: ['doc-2', 'doc-1'],
      primary_document_id: 'doc-2',
      compare_document_ids: ['doc-2', 'doc-1'],
      version_labels: ['v2', 'v1'],
      version_family_key: 'expense-policy',
      asset_id: 'asset-9',
      region_id: 'region-3',
      region_label: '红框配置',
      page_number: 3,
      display_text: 'v2 vs v1 / 第 3 页 / 红框配置'
    });
  });

  it('builds visual focus payload', () => {
    expect(buildVisualFocus({
      documentId: 'doc-1',
      assetId: 'asset-1',
      regionId: 'region-1',
      regionLabel: '红框配置',
      pageNumber: 3,
      versionLabel: 'v2'
    })).toEqual({
      kind: 'visual_region',
      document_ids: ['doc-1'],
      primary_document_id: 'doc-1',
      asset_id: 'asset-1',
      region_id: 'region-1',
      region_label: '红框配置',
      page_number: 3,
      version_label: 'v2',
      display_text: 'v2 / 第 3 页 / 红框配置'
    });
  });
});
