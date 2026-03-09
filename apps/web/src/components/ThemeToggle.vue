<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <el-button circle :title="currentLabel" class="theme-toggle">
      <transition name="icon-spin" mode="out-in">
        <el-icon :size="20" :key="currentMode" class="theme-icon">
          <component :is="iconComponent" />
        </el-icon>
      </transition>
    </el-button>
    
    <template #dropdown>
      <el-dropdown-menu class="glass-panel">
        <el-dropdown-item
          v-for="option in options"
          :key="option.value"
          :command="option.value"
          :disabled="currentMode === option.value"
          class="theme-menu-item"
        >
          <el-icon :size="18" :color="getIconColor(option.value)">
            <component :is="option.icon" />
          </el-icon>
          <span>{{ option.label }}</span>
          <el-icon v-if="currentMode === option.value" :size="16" color="var(--blue-600)" style="margin-left: auto;">
            <Check />
          </el-icon>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Sunny, Moon, Monitor, Check } from '@element-plus/icons-vue';
import { getTheme, setTheme, type ThemeMode } from '@/utils/theme';

const currentMode = ref<ThemeMode>(getTheme());

const options = [
  {
    value: 'light',
    label: '浅色模式',
    icon: Sunny
  },
  {
    value: 'dark',
    label: '深色模式',
    icon: Moon
  },
  {
    value: 'system',
    label: '跟随系统',
    icon: Monitor
  }
];

const iconComponent = computed(() => {
  if (currentMode.value === 'dark') {
    return Moon;
  }
  if (currentMode.value === 'system') {
    return Monitor;
  }
  return Sunny;
});

const currentLabel = computed(() => {
  const option = options.find(o => o.value === currentMode.value);
  return option?.label || '切换主题';
});

const getIconColor = (mode: string) => {
  if (mode === currentMode.value) {
    return 'var(--blue-600)';
  }
  return 'var(--text-muted)';
};

const handleCommand = (command: ThemeMode) => {
  setTheme(command);
  currentMode.value = command;
};

// 监听主题变化
watch(currentMode, (newMode) => {
  setTheme(newMode);
});
</script>

<style scoped>
.theme-toggle {
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
  color: var(--text-primary);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-toggle:hover {
  border-color: rgba(59, 130, 246, 0.4);
  background: var(--blue-50);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

.theme-toggle:active {
  transform: translateY(0) scale(0.95);
}

.theme-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Icon Spin Transition */
.icon-spin-enter-active,
.icon-spin-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.icon-spin-enter-from {
  opacity: 0;
  transform: rotate(-180deg) scale(0.5);
}

.icon-spin-leave-to {
  opacity: 0;
  transform: rotate(180deg) scale(0.5);
}

.theme-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  transition: background 0.2s ease;
  border-radius: 8px;
  margin: 0 4px;
}

.theme-menu-item:hover {
  background: var(--bg-panel-muted);
}

:deep(.el-dropdown-menu.glass-panel) {
  padding: 8px 0;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}
</style>
