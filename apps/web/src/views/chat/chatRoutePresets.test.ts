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

  it('resolves kb route preset and de-duplicates document ids', () => {
    const result = resolveKbRoutePreset({
      preset: 'kb',
      baseId: 'base-1',
      documentId: 'doc-current',
      compareDocumentId: 'doc-current',
      question: '请回答'
    });

    expect(result).toEqual({
      scope: {
        mode: 'single',
        corpus_ids: ['kb:base-1'],
        document_ids: ['doc-current']
      },
      question: '请回答'
    });
  });
});
