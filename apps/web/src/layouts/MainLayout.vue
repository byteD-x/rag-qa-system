<template>
  <div class="workspace-shell">
    <a class="skip-link" href="#workspace-main-content">跳到主内容</a>

    <aside class="workspace-sidebar">
      <div class="sidebar-scroll">
        <div class="brand-block">
          <div class="brand-mark">
            <el-icon :size="22"><Platform /></el-icon>
          </div>
          <div class="brand-copy">
            <span class="brand-kicker">企业知识中台</span>
            <h2>RAG-QA 2.0</h2>
          </div>
        </div>

        <div class="sidebar-focus">
          <span class="sidebar-focus-label">当前页</span>
          <span class="sidebar-focus-title">{{ routeTitle }}</span>
        </div>

        <nav class="nav-stack" aria-label="主导航">
          <button
            v-for="item in navItemsPrimaryFiltered"
            :key="item.path"
            type="button"
            class="nav-item"
            :class="{ active: activeNavPath === item.path }"
            :aria-current="activeNavPath === item.path ? 'page' : undefined"
            @click="navigate(item.path)"
          >
            <span class="nav-icon">
              <el-icon><component :is="item.icon" /></el-icon>
            </span>
            <span class="nav-copy">
              <strong>{{ item.label }}</strong>
            </span>
          </button>
          <div v-if="auditNavItem" class="nav-divider" role="separator" />
          <button
            v-if="auditNavItem"
            type="button"
            class="nav-item nav-item--secondary"
            :class="{ active: activeNavPath === auditNavItem.path }"
            :aria-current="activeNavPath === auditNavItem.path ? 'page' : undefined"
            @click="navigate(auditNavItem.path)"
          >
            <span class="nav-icon">
              <el-icon><component :is="auditNavItem.icon" /></el-icon>
            </span>
            <span class="nav-copy">
              <strong>{{ auditNavItem.label }}</strong>
            </span>
          </button>
        </nav>

        <div class="sidebar-bottom">
          <div class="profile-card">
            <el-avatar :size="42" class="profile-avatar">{{ userInitial }}</el-avatar>
            <div class="profile-copy">
              <strong>{{ authStore.user?.email || 'member@local' }}</strong>
              <span>{{ userRole }}</span>
            </div>
          </div>

          <el-button plain class="logout-button" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出登录
          </el-button>
        </div>
      </div>
    </aside>

    <div class="workspace-main">
      <div class="workspace-main-frame">
        <header class="workspace-topbar">
          <div class="topbar-leading">
            <el-button circle class="mobile-nav-button" @click="mobileDrawerVisible = true">
              <el-icon><Grid /></el-icon>
            </el-button>

            <div class="topbar-copy">
              <div class="breadcrumb-row" aria-label="当前位置">
                <span
                  v-for="(item, index) in breadcrumbs"
                  :key="`${item}-${index}`"
                  class="breadcrumb-item"
                >
                  {{ item }}
                </span>
              </div>
              <h1>{{ routeTitle }}</h1>
            </div>
          </div>
          
          <div class="topbar-actions">
            <ThemeToggle />
          </div>
        </header>

        <main id="workspace-main-content" class="workspace-content">
          <router-view v-slot="{ Component }">
            <transition name="page" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </main>
      </div>
    </div>

    <el-drawer
      v-model="mobileDrawerVisible"
      direction="ltr"
      size="320px"
      :with-header="false"
      append-to-body
      class="mobile-drawer"
    >
      <div class="drawer-content">
        <div class="brand-block compact">
          <div class="brand-mark">
            <el-icon :size="22"><Platform /></el-icon>
          </div>
          <div class="brand-copy">
            <span class="brand-kicker">企业知识中台</span>
            <h2>RAG-QA 2.0</h2>
          </div>
        </div>

        <nav class="nav-stack" aria-label="移动端导航">
          <button
            v-for="item in navItemsPrimaryFiltered"
            :key="`${item.path}-mobile`"
            type="button"
            class="nav-item"
            :class="{ active: activeNavPath === item.path }"
            :aria-current="activeNavPath === item.path ? 'page' : undefined"
            @click="navigate(item.path)"
          >
            <span class="nav-icon">
              <el-icon><component :is="item.icon" /></el-icon>
            </span>
            <span class="nav-copy">
              <strong>{{ item.label }}</strong>
            </span>
          </button>
          <div v-if="auditNavItem" class="nav-divider" role="separator" />
          <button
            v-if="auditNavItem"
            type="button"
            class="nav-item nav-item--secondary"
            :class="{ active: activeNavPath === auditNavItem.path }"
            :aria-current="activeNavPath === auditNavItem.path ? 'page' : undefined"
            @click="navigate(auditNavItem.path)"
          >
            <span class="nav-icon">
              <el-icon><component :is="auditNavItem.icon" /></el-icon>
            </span>
            <span class="nav-copy">
              <strong>{{ auditNavItem.label }}</strong>
            </span>
          </button>
        </nav>

        <div class="sidebar-bottom">
          <div class="profile-card">
            <el-avatar :size="42" class="profile-avatar">{{ userInitial }}</el-avatar>
            <div class="profile-copy">
              <strong>{{ authStore.user?.email || 'member@local' }}</strong>
              <span>{{ userRole }}</span>
            </div>
          </div>

          <el-button plain class="logout-button" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出登录
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/store/auth';
import {
  ChatDotRound,
  Files,
  Grid,
  Platform,
  SwitchButton,
  Tickets,
  Link,
  Aim,
  User as Robot,
  EditPen
} from '@element-plus/icons-vue';
import ThemeToggle from '@/components/ThemeToggle.vue';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const mobileDrawerVisible = ref(false);

const navItemsPrimary = [
  {
    path: '/workspace/entry',
    label: '业务总览',
    icon: Grid
  },
  {
    path: '/workspace/chat',
    label: '统一问答',
    icon: ChatDotRound
  },
  {
    path: '/workspace/platform/agents',
    label: 'Agent 工作台',
    icon: Robot
  },
  {
    path: '/workspace/platform/prompts',
    label: 'Prompt 库',
    icon: EditPen
  },
  {
    path: '/workspace/kb/upload',
    label: '知识库治理',
    icon: Files
  },
  {
    path: '/workspace/kb/connectors',
    label: '多源同步',
    icon: Link
  },
  {
    path: '/workspace/kb/debugger',
    label: '检索测试',
    icon: Aim
  }
];

const navItemsPrimaryFiltered = computed(() =>
  navItemsPrimary.filter((item) => {
    if (
      item.path === '/workspace/chat' ||
      item.path === '/workspace/platform/agents' ||
      item.path === '/workspace/platform/prompts'
    ) {
      return authStore.hasPermission('chat.use');
    }
    if (item.path === '/workspace/kb/upload') return authStore.hasPermission('kb.read');
    if (item.path === '/workspace/kb/connectors' || item.path === '/workspace/kb/debugger') {
      return authStore.hasPermission('kb.manage');
    }
    return true;
  })
);

const auditNavItem = computed(() =>
  authStore.hasPermission('audit.read')
    ? { path: '/workspace/audit', label: '审计日志', icon: Tickets }
    : null
);

const navItemsFiltered = computed(() => {
  const items = [...navItemsPrimaryFiltered.value];
  if (auditNavItem.value) items.push(auditNavItem.value);
  return items;
});

const activeNavPath = computed(() => {
  const current = navItemsFiltered.value.find((item) => route.path.startsWith(item.path));
  return current?.path || '/workspace/entry';
});

const routeTitle = computed(() => String(route.meta.title || 'RAG-QA 工作台'));
const breadcrumbs = computed(() => {
  const raw = (route.meta as { breadcrumb?: unknown }).breadcrumb;
  return Array.isArray(raw) && raw.length ? raw.map((item) => String(item)) : ['工作台', routeTitle.value];
});
const userRole = computed(() => authStore.roleLabel());
const userInitial = computed(() => (authStore.user?.email || '?').charAt(0).toUpperCase());

watch(
  () => route.fullPath,
  () => {
    mobileDrawerVisible.value = false;
  }
);

const navigate = (path: string) => {
  router.push(path);
};

const handleLogout = () => {
  authStore.logout();
  mobileDrawerVisible.value = false;
  router.push('/login');
};
</script>

<style scoped>
.workspace-shell {
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
}

.workspace-sidebar {
  position: sticky;
  top: 0;
  flex: 0 0 280px;
  width: 280px;
  height: 100vh;
  padding: 16px;
  background: var(--bg-panel);
  border-right: 1px solid var(--border-color);
  z-index: 10;
}

.sidebar-scroll {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow: auto;
  padding-right: 4px;
}

.brand-block {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding-bottom: 16px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
}

.brand-block.compact {
  margin-bottom: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-sm);
  background: var(--blue-600);
  color: #fff;
  flex-shrink: 0;
}

.brand-copy {
  min-width: 0;
}

.brand-kicker {
  display: inline-flex;
  margin-bottom: 2px;
  color: var(--text-muted);
  font-size: var(--text-caption, 0.75rem);
  font-weight: 500;
  letter-spacing: 0.03em;
}

.brand-copy h2 {
  font-size: var(--text-h2, 1.125rem);
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.brand-copy p {
  margin-top: 8px;
  color: var(--text-secondary);
  line-height: 1.65;
}

.sidebar-focus {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
}

.sidebar-focus-label {
  display: block;
  font-size: var(--text-caption, 0.75rem);
  color: var(--text-muted);
  margin-bottom: 4px;
  font-weight: 500;
}

.sidebar-focus-title {
  font-size: var(--text-body, 0.9375rem);
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.nav-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 12px 10px 10px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  text-align: left;
  transition: background var(--transition-base), color var(--transition-base);
  color: var(--text-primary);
  position: relative;
}

.nav-item:hover {
  background: var(--bg-panel-muted);
}

.nav-item.active {
  background: var(--blue-50);
  color: var(--blue-700);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: var(--blue-600);
  border-radius: 0 2px 2px 0;
}

.nav-item--secondary .nav-icon {
  color: var(--text-muted);
}

.nav-item--secondary.active .nav-icon {
  color: var(--blue-600);
}

.nav-divider {
  height: 1px;
  margin: 8px 0;
  background: var(--border-color);
}

.nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--text-secondary);
}

.nav-item.active .nav-icon {
  color: var(--blue-600);
}

.nav-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.nav-copy strong {
  color: inherit;
  font-size: 14px;
  font-weight: 500;
}

.mobile-nav-button {
  display: none;
}

.workspace-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workspace-main-frame {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  width: min(100%, 1540px);
  margin: 0 auto;
  padding: 18px 20px 24px;
  overflow: hidden;
}

.workspace-topbar {
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 6;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 14px 16px 16px 12px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-color);
}


.topbar-leading {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  flex: 1 1 0%;
  min-width: 0;
  overflow: visible;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  align-self: center;
}

.topbar-copy {
  min-width: 0;
  flex: 1 1 auto;
  overflow: visible;
  padding-right: 12px;
}

.breadcrumb-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  margin-bottom: 4px;
}

.breadcrumb-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: var(--text-caption, 0.75rem);
  font-weight: 500;
  white-space: nowrap;
}

.breadcrumb-item:not(:last-child)::after {
  content: '/';
  color: var(--border-strong);
  margin-left: 4px;
}

.topbar-leading h1 {
  font-size: var(--text-h2, 1.125rem);
  font-weight: 600;
  line-height: 1.3;
  letter-spacing: -0.02em;
}

.workspace-content {
  flex: 1;
  min-width: 0;
  padding: 18px 0 4px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-content {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  gap: 18px;
}

.sidebar-bottom {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
  margin-top: 8px;
}

.profile-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
}

.profile-avatar {
  background: var(--blue-600);
  color: #fff;
  font-weight: 500;
}

.profile-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.profile-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.profile-copy span {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 13px;
}

.logout-button {
  justify-content: center;
  gap: 8px;
}

@media (max-width: 1280px) {
  .workspace-sidebar {
    flex-basis: 260px;
    width: 260px;
  }

  .workspace-main-frame {
    padding-inline: 18px;
  }
}

@media (max-width: 1100px) {
  .workspace-shell {
    display: block;
  }

  .workspace-sidebar {
    display: none;
  }

  .workspace-main-frame {
    width: min(100%, 1024px);
    padding: 16px;
  }

  .workspace-topbar {
    padding: 18px 20px 20px 18px;
  }

  .mobile-nav-button {
    display: inline-flex;
  }
}

@media (max-width: 768px) {
  .workspace-main-frame {
    padding: 12px;
  }

  .workspace-topbar {
    flex-direction: column;
    gap: 12px;
    padding: 12px 16px 12px 12px;
  }
}
</style>
