import { describe, expect, it } from 'vitest';

import { createApiProxy, KB_REBUILD_PROXY_CONTEXT } from './vite.proxy';

describe('vite dev proxy allowlist', () => {
  it('allows the fixed knowledge-base rebuild endpoint without opening delete or wildcard paths', () => {
    const proxy: Record<string, unknown> = createApiProxy('http://localhost:8080');
    const rebuildMatcher = new RegExp(KB_REBUILD_PROXY_CONTEXT);

    expect(proxy[KB_REBUILD_PROXY_CONTEXT]).toEqual({
      target: 'http://localhost:8080',
      changeOrigin: true,
    });
    expect(rebuildMatcher.test('/api/knowledge_base/rebuild')).toBe(true);
    expect(rebuildMatcher.test('/api/knowledge_base/rebuild?dry_run=true')).toBe(true);
    expect(rebuildMatcher.test('/api/knowledge_base/delete')).toBe(false);
    expect(rebuildMatcher.test('/api/knowledge_base/rebuild/delete')).toBe(false);
    expect(rebuildMatcher.test('/api/knowledge_base/rebuild-extra')).toBe(false);
    expect(proxy['/api/knowledge_base/delete']).toBeUndefined();
    expect(proxy['/api/knowledge_base/*']).toBeUndefined();
  });

  it('keeps the existing gateway v1 proxy target unchanged', () => {
    const proxy: Record<string, unknown> = createApiProxy('http://localhost:8080');

    expect(proxy['/api/v1']).toEqual({
      target: 'http://localhost:8080',
      changeOrigin: true,
    });
  });
});
