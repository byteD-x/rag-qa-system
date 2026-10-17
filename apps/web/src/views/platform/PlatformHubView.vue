<template>
  <div class="page-shell">
    <PageHeaderCompact title="平台管理" />

    <section v-for="group in visibleGroups" :key="group.title" class="hub-group">
      <h2 class="hub-group__title">{{ group.title }}</h2>
      <ul class="hub-group__list">
        <li v-for="item in group.items" :key="item.path">
          <router-link class="hub-link" :to="item.path">
            <span class="hub-link__label">{{ item.label }}</span>
            <span class="hub-link__hint">{{ item.hint }}</span>
          </router-link>
        </li>
      </ul>
    </section>

    <EnhancedEmpty
      v-if="!visibleGroups.length"
      variant="question"
      title="暂无可访问的平台能力"
      description="当前账号没有平台配置相关权限，请联系管理员开通。"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { useAuthStore } from '@/store/auth';

const authStore = useAuthStore();

interface HubItem {
  path: string;
  label: string;
  hint: string;
  permission: string;
}

const groups: { title: string; items: HubItem[] }[] = [
  {
    title: '运行观测',
    items: [
      { path: '/workspace/platform/monitor', label: 'Agent 监控', hint: '任务拆解与工具调用链路', permission: 'chat.use' },
      { path: '/workspace/platform/cost', label: '成本分析', hint: '调用成本与 Token 消耗', permission: 'chat.use' },
      { path: '/workspace/platform/cache', label: '缓存管理', hint: '语义缓存与命中策略', permission: 'chat.use' }
    ]
  },
  {
    title: 'Agent 能力',
    items: [
      { path: '/workspace/platform/tools', label: '工具管理', hint: '工具注册、启停与 MCP 接入', permission: 'chat.use' },
      { path: '/workspace/platform/memory', label: '记忆管理', hint: '长期记忆与用户偏好', permission: 'chat.use' },
      { path: '/workspace/platform/scenes', label: '场景模板', hint: '多场景 Agent 行为配置', permission: 'chat.use' },
      { path: '/workspace/platform/market', label: '指令模板市场', hint: '指令模板导入与评价', permission: 'chat.use' },
      { path: '/workspace/platform/orchestration', label: 'Agent 协作编排', hint: '多 Agent 执行计划与 DAG', permission: 'chat.use' }
    ]
  },
  {
    title: '安全与实验',
    items: [
      { path: '/workspace/platform/apikeys', label: 'API Key 管理', hint: '创建、轮换与配额', permission: 'kb.manage' },
      { path: '/workspace/platform/webhooks', label: 'Webhook 管理', hint: '事件回调地址注册', permission: 'kb.manage' },
      { path: '/workspace/platform/pii', label: 'PII 脱敏配置', hint: '身份信息检测与脱敏', permission: 'kb.manage' },
      { path: '/workspace/platform/experiments', label: 'A/B 实验', hint: 'Prompt / 模型对比实验', permission: 'kb.manage' }
    ]
  }
];

const visibleGroups = computed(() =>
  groups
    .map((group) => ({
      title: group.title,
      items: group.items.filter((item) => authStore.hasPermission(item.permission))
    }))
    .filter((group) => group.items.length > 0)
);
</script>

<style scoped>
.hub-group {
  margin-bottom: var(--section-gap, 24px);
}

.hub-group__title {
  margin: 0 0 10px;
  font-size: var(--text-caption, 0.75rem);
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.hub-group__list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.hub-link {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel);
  text-decoration: none;
}

.hub-link__label {
  color: var(--text-primary);
  font-size: var(--text-body, 0.9375rem);
  font-weight: 500;
}

.hub-link__hint {
  color: var(--text-muted);
  font-size: var(--text-caption, 0.75rem);
}
</style>
