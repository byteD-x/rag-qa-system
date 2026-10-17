import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { updateChatSession, listAgentProfiles, listPromptTemplates, listChatMessages, listChatSessions, listWorkflowRuns } = vi.hoisted(() => ({
  updateChatSession: vi.fn(),
  listAgentProfiles: vi.fn(),
  listPromptTemplates: vi.fn(),
  listChatMessages: vi.fn(),
  listChatSessions: vi.fn(),
  listWorkflowRuns: vi.fn()
}));

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() }
}));

vi.mock('@/api/request', () => ({
  createIdempotencyKey: () => 'idem-key',
  isAbortRequestError: () => false,
  isHandledRequestError: () => false
}));

vi.mock('@/api/chat', () => ({
  createChatSession: vi.fn(),
  createChatRunV2: vi.fn(),
  deleteChatSession: vi.fn(),
  defaultChatScope: () => ({
    mode: 'all',
    corpus_ids: [],
    document_ids: [],
    allow_common_knowledge: false
  }),
  getChatRunV2: vi.fn(),
  listChatCorpora: vi.fn(),
  listChatCorpusDocuments: vi.fn(),
  listChatMessages,
  listChatSessions,
  listWorkflowRuns,
  resumeChatRunV2: vi.fn(),
  submitMessageFeedback: vi.fn(),
  updateChatSession
}));

vi.mock('@/api/platform', () => ({
  listAgentProfiles,
  listPromptTemplates
}));

import { useChatStore } from './chat';

describe('chat store scope identity fields', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    updateChatSession.mockReset();
    updateChatSession.mockResolvedValue({});
    listAgentProfiles.mockReset();
    listPromptTemplates.mockReset();
    listAgentProfiles.mockResolvedValue({ items: [{ id: 'p1', name: '财务助手' }] });
    listPromptTemplates.mockResolvedValue({ items: [{ id: 't1', name: '严谨引用' }] });
    listChatMessages.mockReset();
    listChatMessages.mockResolvedValue({ items: [] });
    listChatSessions.mockReset();
    listChatSessions.mockResolvedValue({ items: [] });
    listWorkflowRuns.mockReset();
    listWorkflowRuns.mockResolvedValue({ items: [] });
  });

  it('sends agent_profile_id and prompt_template_id inside the session scope', async () => {
    const store = useChatStore();
    store.activeSessionId = 'session-1';
    store.agentProfileId = 'p1';
    store.promptTemplateId = 't1';

    await store.handleAgentProfileChange();

    expect(updateChatSession).toHaveBeenCalledWith('session-1', {
      scope: expect.objectContaining({
        agent_profile_id: 'p1',
        prompt_template_id: 't1'
      })
    });
  });

  it('restores both fields from a persisted scope and defaults them to empty', () => {
    const store = useChatStore();

    store.applyScope({
      mode: 'single',
      corpus_ids: ['c1'],
      document_ids: [],
      allow_common_knowledge: true,
      agent_profile_id: 'p9',
      prompt_template_id: 't9'
    });
    expect(store.agentProfileId).toBe('p9');
    expect(store.promptTemplateId).toBe('t9');

    store.applyScope(null);
    expect(store.agentProfileId).toBe('');
    expect(store.promptTemplateId).toBe('');
  });

  it('loads the selector options from the platform endpoints', async () => {
    const store = useChatStore();

    await store.loadScopeOptions();

    expect(store.agentProfiles).toEqual([{ id: 'p1', name: '财务助手' }]);
    expect(store.promptTemplates).toEqual([{ id: 't1', name: '严谨引用' }]);
  });

  it('writes the execution mode through the session update endpoint', async () => {
    const store = useChatStore();
    store.activeSessionId = 'session-9';
    store.executionMode = 'agent';

    await store.handleExecutionModeChange();

    expect(updateChatSession).toHaveBeenCalledWith('session-9', { execution_mode: 'agent' });
  });

  it('restores the execution mode from the session scope snapshot', async () => {
    const store = useChatStore();

    await store.selectSession({
      id: 'session-9',
      scope_json: { mode: 'all', corpus_ids: [], document_ids: [], allow_common_knowledge: false, execution_mode: 'agent' }
    });
    expect(store.executionMode).toBe('agent');

    await store.selectSession({ id: 'session-10', scope_json: { mode: 'all' } });
    expect(store.executionMode).toBe('grounded');
  });
});
