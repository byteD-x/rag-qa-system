import { describe, expect, it } from 'vitest';

import { buildKbChatRouteQuery, resolveKbRoutePreset } from './chatRoutePresets';

describe('chatRoutePresets', () => {
  it('builds compare chat query with compareDocumentId and preset question', () => {
    const result = buildKbChatRouteQuery({
      baseId: 'base-1',
      documentId: 'doc-current',
      compareDocumentId: 'doc-history'
    });

    expect(result).toMatchObject({
      preset: 'kb',
      baseId: 'base-1',
      documentId: 'doc-current',
      compareDocumentId: 'doc-history'
    });
    expect(result.question).toContain('doc-history');
  });

  it('persists structured visual focus hint inside route query', () => {
    const result = buildKbChatRouteQuery({
      baseId: 'base-1',
      documentId: 'doc-current',
      question: '请解释红框里的变化。',
      focusHint: {
        kind: 'visual_region',
        document_ids: ['doc-current'],
        asset_id: 'asset-1',
        region_id: 'region-1',
        display_text: '第 3 页 / 红框配置'
      }
    });

    expect(result.focusHint).toBeTruthy();

    const resolved = resolveKbRoutePreset(result);
    expect(resolved?.focusHint).toEqual({
      kind: 'visual_region',
      document_ids: ['doc-current'],
      asset_id: 'asset-1',
      region_id: 'region-1',
      display_text: '第 3 页 / 红框配置'
    });
  });

  it('persists compare focus hint with visual context inside route query', () => {
    const result = buildKbChatRouteQuery({
      baseId: 'base-1',
      documentId: 'doc-current',
      compareDocumentId: 'doc-history',
      question: '比较两个版本在当前截图区域中的变化。',
      focusHint: {
        kind: 'compare_versions',
        document_ids: ['doc-current', 'doc-history'],
        compare_document_ids: ['doc-current', 'doc-history'],
        primary_document_id: 'doc-current',
        version_labels: ['v3', 'v2'],
        asset_id: 'asset-1',
        region_id: 'region-9',
        region_label: '红框配置',
        page_number: 3,
        display_text: 'v3 vs v2 / 第 3 页 / 红框配置'
      }
    });

    const resolved = resolveKbRoutePreset(result);
    expect(resolved?.focusHint).toEqual({
      kind: 'compare_versions',
      document_ids: ['doc-current', 'doc-history'],
      compare_document_ids: ['doc-current', 'doc-history'],
      primary_document_id: 'doc-current',
      version_labels: ['v3', 'v2'],
      asset_id: 'asset-1',
      region_id: 'region-9',
      region_label: '红框配置',
      page_number: 3,
      display_text: 'v3 vs v2 / 第 3 页 / 红框配置'
    });
  });

  it('resolves kb route preset and de-duplicates document ids', () => {
    const result = resolveKbRoutePreset({
      preset: 'kb',
      baseId: 'base-1',
      documentId: 'doc-current',
      compareDocumentId: 'doc-current',
      question: '请回答。'
    });

    expect(result).toEqual({
      scope: {
        mode: 'single',
        corpus_ids: ['kb:base-1'],
        document_ids: ['doc-current']
      },
      question: '请回答。',
      focusHint: undefined
    });
  });
});
