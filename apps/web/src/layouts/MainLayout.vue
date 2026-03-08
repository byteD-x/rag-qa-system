<template>
  <el-container class="main-layout">
    <el-aside width="280px" class="app-sidebar">
      <div class="sidebar-header">
        <div class="logo-circle-mini">
          <el-icon :size="20"><Platform /></el-icon>
        </div>
        <div>
          <h2>RAG-QA 2.0</h2>
          <p>统一 QA / 极速上传 / 证据优先</p>
        </div>
      </div>

      <div class="sidebar-menu-container">
        <el-menu :default-active="$route.path" router class="app-menu">
          <el-menu-item index="/workspace/chat" class="menu-item-custom">
            <el-icon><ChatDotRound /></el-icon>
            <template #title>统一 QA</template>
          </el-menu-item>
          <el-menu-item index="/workspace/entry" class="menu-item-custom">
            <el-icon><Grid /></el-icon>
            <template #title>概览</template>
          </el-menu-item>
          <el-menu-item index="/workspace/kb/upload" class="menu-item-custom">
            <el-icon><Files /></el-icon>
            <template #title>企业文档上传</template>
          </el-menu-item>
        </el-menu>
      </div>

      <div class="sidebar-footer">
        <div class="mode-summary">
          <span class="mode-label">当前工作区</span>
          <strong>{{ currentMode }}</strong>
        </div>
        <el-dropdown trigger="click" @command="handleCommand" placement="top-start" class="user-dropdown">
          <div class="user-profile">
            <el-avatar :size="38" class="user-avatar">{{ userInitial }}</el-avatar>
            <div class="user-info">
              <span class="user-name">{{ authStore.user?.email || 'member@local' }}</span>
              <span class="user-role">{{ authStore.isAdmin() ? '管理员' : '成员' }}</span>
            </div>
            <el-icon class="dropdown-icon"><MoreFilled /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">
                <el-icon><SwitchButton /></el-icon>
                退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-aside>

    <el-container class="main-content-wrapper">
      <el-main class="app-main">
        <router-view v-slot="{ Component }">
          <transition name="fade-transform" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/store/auth';
import {
  ChatDotRound,
  Files,
  Grid,
  MoreFilled,
  Platform,
  SwitchButton
} from '@element-plus/icons-vue';

const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();

const userInitial = computed(() => {
  const email = authStore.user?.email || '?';
  return email.charAt(0).toUpperCase();
});

const currentMode = computed(() => {
  if (route.path.includes('/workspace/chat')) {
    return '统一 QA';
  }
  if (route.path.includes('/workspace/kb/')) {
    return '企业文档链路';
  }
  return '概览';
});

const handleCommand = (command: string) => {
  if (command === 'logout') {
    authStore.logout();
    router.push('/login');
  }
};
</script>

<style scoped>
.main-layout {
  height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.12), transparent 30%),
    radial-gradient(circle at bottom right, rgba(15, 118, 110, 0.14), transparent 35%),
    var(--bg-base);
}

.app-sidebar {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 250, 252, 0.98));
  border-right: 1px solid var(--border-color-light);
  display: flex;
  flex-direction: column;
  box-shadow: 8px 0 32px rgba(15, 23, 42, 0.05);
  z-index: 10;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 22px 20px 18px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.logo-circle-mini {
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #0f766e);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.28);
}

.sidebar-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.sidebar-header p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.sidebar-menu-container {
  flex: 1;
  padding: 18px 14px;
  overflow-y: auto;
}

.app-menu {
  border-right: none;
  background: transparent;
}

.menu-item-custom {
  height: 50px;
  line-height: 50px;
  margin-bottom: 8px;
  border-radius: 14px;
  color: var(--text-regular);
  transition: all 0.22s ease;
}

.menu-item-custom:hover {
  background: rgba(59, 130, 246, 0.08);
  color: var(--text-primary);
  transform: translateX(3px);
}

.menu-item-custom.is-active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.12), rgba(15, 118, 110, 0.1));
  color: #1d4ed8;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.08);
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid var(--border-color-light);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.9));
}

.mode-summary {
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.03);
}

.mode-label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.user-dropdown {
  width: 100%;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 14px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.22s ease;
}

.user-profile:hover {
  background: rgba(255, 255, 255, 0.72);
  border-color: var(--border-color-light);
}

.user-avatar {
  background: linear-gradient(135deg, #2563eb, #0f766e);
  color: #fff;
  font-weight: 700;
}

.user-info {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  font-size: 12px;
  color: var(--text-secondary);
}

.dropdown-icon {
  color: var(--text-secondary);
}

.main-content-wrapper {
  min-width: 0;
}

.app-main {
  height: 100vh;
  overflow-y: auto;
  padding: 24px;
}

.fade-transform-enter-active,
.fade-transform-leave-active {
  transition: all 0.2s ease;
}

.fade-transform-enter-from,
.fade-transform-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 960px) {
  .app-sidebar {
    width: 240px !important;
  }

  .app-main {
    padding: 18px;
  }
}

@media (max-width: 760px) {
  .main-layout {
    flex-direction: column;
    height: auto;
    min-height: 100vh;
  }

  .app-sidebar {
    width: 100% !important;
  }

  .app-main {
    height: auto;
  }
}
</style>
