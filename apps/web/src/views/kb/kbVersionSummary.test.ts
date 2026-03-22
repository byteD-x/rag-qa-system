import { describe, expect, it } from 'vitest';

import { buildVersionSummary } from './kbVersionSummary';

describe('kbVersionSummary', () => {
  it('builds compact section summaries from structured sections', () => {
    expect(buildVersionSummary({
      section_count: 4,
      sections: [
        { section_index: 0, section_title: '概览', text_content: '  第一段  内容  ' },
        { section_index: 1, section_title: '发布范围', text_content: '仅适用于总部报销流程。' },
        { section_index: 2, section_title: '', text_content: '' }
      ]
    }, { maxItems: 2, maxChars: 12 })).toEqual({
      items: [
        {
          key: '0:概览',
          title: '概览',
          excerpt: '第一段 内容',
          char_count: 6
        },
        {
          key: '1:发布范围',
          title: '发布范围',
          excerpt: '仅适用于总部报销流程。',
          char_count: 11
        }
      ],
      hidden_section_count: 2,
      total_section_count: 4,
      fallback_excerpt: ''
    });
  });

  it('falls back to full text when section structure is unavailable', () => {
    expect(buildVersionSummary({
      full_text: '   这里是整篇文档的核心摘要。   '
    }, { maxChars: 10 })).toEqual({
      items: [],
      hidden_section_count: 0,
      total_section_count: 0,
      fallback_excerpt: '这里是整篇文档的核心摘要。'
    });
  });
});
