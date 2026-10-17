<template>
  <div class="page-shell chat-page">
    <section class="chat-workspace" :class="{ 'show-sidebar': showSidebar }">
      <!-- 侧边栏 -->
      <ChatSidebar ref="sidebarRef" :open="showSidebar" @close="closeSidebar" />

      <!-- 主聊天区 -->
      <main class="chat-main">
        <ChatHeader ref="chatHeaderRef" @toggle-sidebar="openSidebar" />

        <div class="chat-status-live-region" role="status" aria-live="polite" aria-atomic="true">
          {{ liveStatus }}
        </div>

        <div ref="messageListRef" class="message-list-container" @scroll="handleScroll">
          <div ref="messageListInnerRef" class="message-list-inner">            <div v-if="!chatStore.messages.length" class="message-empty">
              <div class="welcome-hero">
                <div class="welcome-icon-wrap">
                  <el-icon><Platform /></el-icon>
                </div>
                <h2 class="welcome-title">有什么我可以帮您的？</h2>
                <p class="welcome-subtitle">基于您的知识库提供准确解答</p>
              </div>
            </div>

            <template v-else>
              <!-- 切换会话时整列表重挂载，不走 enter/leave 动画 -->
              <transition-group :key="chatStore.activeSessionId || 'draft'" name="chat-fade">
                <ChatMessageItem 
                  v-for="message in chatStore.messages" 
                  :key="message.id" 
                  :message="message" 
                  @show-workflow="openTraceDrawer" 
                />
              </transition-group>
            </template>
          </div>
        </div>

        <ChatComposer ref="composerRef" @ask="handleAsk" />
      </main>

      <ChatTraceDrawer ref="traceDrawerRef" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, nextTick, watch } from 'vue';
import { useRoute } from 'vue-router';
import { Platform } from '@element-plus/icons-vue';

import ChatSidebar from './components/ChatSidebar.vue';
import ChatHeader from './components/ChatHeader.vue';
import ChatMessageItem from './components/ChatMessageItem.vue';
import ChatComposer from './components/ChatComposer.vue';
import ChatTraceDrawer from './components/ChatTraceDrawer.vue';

import { useChatStore } from '@/store/chat';
import { resolveKbRoutePreset } from './chatRoutePresets';

const route = useRoute();
const chatStore = useChatStore();

const messageListRef = ref<HTMLElement | null>(null);
const messageListInnerRef = ref<HTMLElement | null>(null);
const composerRef = ref<InstanceType<typeof ChatComposer> | null>(null);
const traceDrawerRef = ref<InstanceType<typeof ChatTraceDrawer> | null>(null);
const sidebarRef = ref<InstanceType<typeof ChatSidebar> | null>(null);
const chatHeaderRef = ref<InstanceType<typeof ChatHeader> | null>(null);
const showSidebar = ref(true);
const liveStatus = ref('');

let resizeObserver: ResizeObserver | null = null;
let shouldAutoScroll = true;
let smoothScrollTimer: number | null = null;
let isSmoothScrolling = false;

function prefersReducedMotion() {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// 滚动只保留一种行为：结果到达时平滑滚动一次；减少动效偏好下一律瞬时。
function scrollMessagesToBottom(smooth = true) {
  const target = messageListRef.value;
  if (!target) {
    return;
  }
  const useSmooth = smooth && !prefersReducedMotion();
  target.scrollTo({
    top: target.scrollHeight,
    behavior: useSmooth ? 'smooth' : 'auto'
  });
  if (!useSmooth) {
    isSmoothScrolling = false;
    return;
  }
  isSmoothScrolling = true;
  if (smoothScrollTimer !== null) {
    window.clearTimeout(smoothScrollTimer);
  }
  smoothScrollTimer = window.setTimeout(() => {
    isSmoothScrolling = false;
  }, 400);
}

function handleScroll() {
  const target = messageListRef.value;
  if (!target) return;
  
  // If user scrolls up significantly, disable auto-scroll
  const distanceFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
  shouldAutoScroll = distanceFromBottom < 150;
}

onMounted(() => {
  if (window.innerWidth <= 768) {
    showSidebar.value = false;
  }
  if (messageListInnerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (shouldAutoScroll && !isSmoothScrolling) {
        scrollMessagesToBottom(false);
      }
    });
    resizeObserver.observe(messageListInnerRef.value);
  }
});

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
  }
  if (smoothScrollTimer !== null) {
    window.clearTimeout(smoothScrollTimer);
    smoothScrollTimer = null;
  }
});

function handleAsk(question: string, done?: (accepted: boolean) => void) {
  shouldAutoScroll = true;
  liveStatus.value = '正在检索知识库，请稍候。';
  const accepted = chatStore.ask(question, (smooth) => {
    void nextTick().then(() => {
      if (shouldAutoScroll) {
        scrollMessagesToBottom(smooth);
      }
    });
  });
  done?.(accepted);
}

function openSidebar() {
  showSidebar.value = true;
  void nextTick().then(() => sidebarRef.value?.focusCloseButton());
}

function closeSidebar() {
  showSidebar.value = false;
  void nextTick().then(() => chatHeaderRef.value?.focusSidebarToggle());
}

function openTraceDrawer(workflowInfo: any) {
  if (traceDrawerRef.value) {
    traceDrawerRef.value.show(workflowInfo);
  }
}

async function applyRoutePreset(): Promise<boolean> {
  const preset = resolveKbRoutePreset(route.query as Record<string, unknown>);
  if (!preset) {
    return false;
  }
  chatStore.startDraftSession();
  chatStore.applyScope(preset.scope);
  chatStore.setFocusHint(preset.focusHint || {});
  await chatStore.handleScopeModeChange();
  if (preset.question && composerRef.value) {
    composerRef.value.setQuestion(preset.question);
  }
  return true;
}

onMounted(async () => {
  await chatStore.loadCorpora();
  await chatStore.loadScopeOptions();
  await chatStore.loadSessions();
  const presetApplied = await applyRoutePreset();

  if (!presetApplied && route.query.sessionId) {
    const session = chatStore.sessions.find((item: any) => item.id === route.query.sessionId);
    if (session) {
      await chatStore.selectSession(session);
      return;
    }
  }

  if (!presetApplied && chatStore.sessions.length) {
    await chatStore.selectSession(chatStore.sessions[0]);
  }
});

watch(
  () => route.fullPath,
  async () => {
    const presetApplied = await applyRoutePreset();
    if (presetApplied) {
      await nextTick();
      scrollMessagesToBottom(false);
    }
  }
);

watch(
  () => [chatStore.asking, chatStore.hasStreamingAssistant] as const,
  ([asking, hasStreaming]) => {
    if (asking) {
      liveStatus.value = hasStreaming ? '正在生成回答，请稍候。' : '正在检索知识库，请稍候。';
    } else if (liveStatus.value) {
      liveStatus.value = '回答已完成。';
    }
  }
);

onBeforeUnmount(() => {
  chatStore.stopStreaming();
});
</script>

<style scoped>
.chat-page {
  background: var(--bg-page);
  height: 100%;
  min-height: 0;
  padding: 0;
  margin: 0;
  display: flex;
  overflow: hidden;
}

.chat-workspace {
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0;
  background: var(--bg-panel);
  overflow: hidden;
  position: relative;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
  min-height: 0;
}

.chat-status-live-region {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Welcome Screen */
.welcome-hero {
  text-align: center;
  margin-bottom: 40px;
}

.welcome-icon-wrap {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  background: var(--blue-50);
  color: var(--blue-600);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-h1);
}

.welcome-title {
  font-size: var(--text-h1);
  margin-bottom: 8px;
}

.welcome-subtitle {
  color: var(--text-secondary);
  font-size: var(--text-body);
}

/* Messages */
.message-list-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
}

@media (max-width: 768px) {
  .composer-container {
    padding: 8px 12px calc(8px + env(safe-area-inset-bottom));
  }
}

.message-list-inner {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding-bottom: 40px;
}

/* Transitions */
.chat-fade-enter-active {
  transition: opacity 200ms var(--ease-enter), transform 200ms var(--ease-enter);
}
.chat-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
</style>
