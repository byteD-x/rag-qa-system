import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('operations route guard', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    setActivePinia(createPinia());
    window.history.replaceState({}, '', '/');
  });

  it('redirects users without kb.manage to an actionable forbidden page', async () => {
    localStorage.setItem('access_token', 'token');
    localStorage.setItem(
      'user',
      JSON.stringify({
        id: 'user-1',
        email: 'member@local',
        role: 'kb_editor',
        permissions: ['kb.read', 'kb.write', 'chat.use'],
      }),
    );

    const { default: router } = await import('@/router');
    await router.push('/workspace/kb/operations');

    expect(router.currentRoute.value.fullPath).toBe('/workspace/forbidden?permission=kb.manage&from=/workspace/kb/operations');
  }, 15000);

  it('allows users with kb.manage to enter operations page', async () => {
    localStorage.setItem('access_token', 'token');
    localStorage.setItem(
      'user',
      JSON.stringify({
        id: 'user-2',
        email: 'admin@local',
        role: 'kb_admin',
        permissions: ['kb.read', 'kb.write', 'kb.manage', 'chat.use'],
      }),
    );

    const { default: router } = await import('@/router');
    await router.push('/workspace/kb/operations');

    expect(router.currentRoute.value.fullPath).toBe('/workspace/kb/operations');
  });

  it('redirects the legacy audit deep link to the workspace route', async () => {
    localStorage.setItem('access_token', 'token');
    localStorage.setItem('user', JSON.stringify({ id: 'audit-1', email: 'audit@local', role: 'audit_viewer', permissions: ['audit.read'] }));

    const { default: router } = await import('@/router');
    await router.push('/audit');

    expect(router.currentRoute.value.path).toBe('/workspace/audit');
  });
});
