<template>
  <div class="page-shell chat-page">
    <section class="chat-workspace">
      <!-- 侧边栏 -->
      <ChatSidebar />

      <!-- 主聊天区 -->
      <main class="chat-main">
        <ChatHeader />

        <div ref="messageListRef" class="message-list-container" @scroll="handleScroll">
          <div ref="messageListInnerRef" class="message-list-inner">            <div v-if="!chatStore.messages.length" class="message-empty">
              <div class="welcome-hero">
                <div class="welcome-icon-wrap">
                  <el-icon><Platform /></el-icon>
                </div>
                <h2 class="welcome-title">有什么我可以帮您的？</h2>
                <p class="welcome-subtitle">基于您的知识库提供准确解答</p>
              </div>
              <div class="suggested-grid">
                <button
                  v-for="prompt in suggestedQuestions"
                  :key="prompt"
                  type="button"
                  class="suggest-card"
                  @click="applyPrompt(prompt)"
                >
                  <div class="suggest-icon"><el-icon><ChatLineRound /></el-icon></div>
                  <div class="suggest-text">{{ prompt }}</div>
                </button>
              </div>
            </div>

            <template v-else>
              <transition-group name="chat-fade">
                <ChatMessageItem 
                  v-for="message in chatStore.messages" 
                  :key="message.id" 
                  :message="message" 
                  @show-workflow="openTraceDrawer" 
                />

                <article v-if="chatStore.asking && !chatStore.hasStreamingAssistant" key="typing" class="message-row assistant">
                  <div class="message-avatar">
                    <el-icon><Platform /></el-icon>
                  </div>
                  <div class="message-body">
                    <div class="message-bubble assistant">
                      <div class="typing-indicator">
                        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                        <span class="typing-text">正在检索...</span>
                      </div>
                    </div>
                  </div>
                </article>
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
import { Platform, ChatLineRound } from '@element-plus/icons-vue';

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

let resizeObserver: ResizeObserver | null = null;
let shouldAutoScroll = true;

const suggestedQuestions = [
  '报销审批需要哪些角色签字？',
  '试用期请假流程与正式员工有哪些区别？',
  '跨文档看，客服升级流程有哪些共性要求？'
];

function scrollMessagesToBottom(smooth = true) {
  const target = messageListRef.value;
  if (!target) {
    return;
  }
  target.scrollTo({
    top: target.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto'
  });
}

function handleScroll() {
  const target = messageListRef.value;
  if (!target) return;
  
  // If user scrolls up significantly, disable auto-scroll
  const distanceFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;
  shouldAutoScroll = distanceFromBottom < 150;
}

onMounted(() => {
  if (messageListInnerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (shouldAutoScroll) {
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
});

function handleAsk(question: string) {
  shouldAutoScroll = true;
  chatStore.ask(question, (smooth) => {
    void nextTick().then(() => {
      if (shouldAutoScroll) {
        scrollMessagesToBottom(smooth);
      }
    });
  });
}

function applyPrompt(prompt: string) {
  if (composerRef.value) {
    composerRef.value.setQuestion(prompt);
  }
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

onBeforeUnmount(() => {
  chatStore.stopStreaming();
});
</script>

<style scoped>
.chat-page {
  background: var(--bg-page);
  height: 100vh;
  padding: 0;
  margin: 0;
  display: flex;
}

.chat-workspace {
  display: flex;
  width: 100%;
  height: 100%;
  background: var(--bg-panel);
  overflow: hidden;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-width: 0;
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
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
}

.welcome-title {
  font-size: 24px;
  margin-bottom: 8px;
}

.welcome-subtitle {
  color: var(--text-secondary);
  font-size: 15px;
}

.suggested-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
}

.suggest-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  text-align: left;
  transition: all 0.2s;
  cursor: pointer;
}

.suggest-card:hover {
  border-color: var(--blue-400);
  box-shadow: var(--shadow-sm);
  transform: translateY(-2px);
}

.suggest-icon {
  color: var(--blue-500);
  font-size: 18px;
  margin-top: 2px;
}

.suggest-text {
  font-size: 14px;
  color: var(--text-regular);
  line-height: 1.5;
}

/* Messages */
.message-list-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.message-list-inner {
  max-width: 800px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding-bottom: 40px;
}

/* Typing Indicator (Fallback) */
.message-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--blue-600);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.message-body {
  flex: 1;
  min-width: 0;
  max-width: 85%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 0;
  color: var(--text-muted);
  font-size: 14px;
}
.dot {
  width: 4px;
  height: 4px;
  background: var(--text-muted);
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}
.dot:nth-child(1) { animation-delay: -0.32s; }
.dot:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.typing-text {
  margin-left: 8px;
}

/* Transitions */
.chat-fade-enter-active,
.chat-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.chat-fade-enter-from,
.chat-fade-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
