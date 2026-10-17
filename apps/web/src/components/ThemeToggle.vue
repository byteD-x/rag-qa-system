<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <el-button circle :title="currentLabel" :aria-label="'主题：' + currentLabel" class="theme-toggle">
      <el-icon :size="20" class="theme-icon">
        <component :is="iconComponent" />
      </el-icon>
    </el-button>
    
    <template #dropdown>
      <el-dropdown-menu class="glass-panel">
        <el-dropdown-item
          v-for="option in options"
          :key="option.value"
          :command="option.value"
          class="theme-menu-item"
        >
          <el-icon :size="18" color="var(--text-muted)">
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
  transition: transform var(--transition-fast), background-color var(--transition-fast), border-color var(--transition-fast);
}

@media (hover: hover) and (pointer: fine) {
  .theme-toggle:hover {
    border-color: color-mix(in srgb, var(--blue-500) 40%, transparent);
    background: var(--blue-50);
    box-shadow: var(--shadow-sm);
    transform: translateY(-2px);
  }
}

.theme-toggle:active {
  transform: translateY(0) scale(0.95);
}

.theme-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.theme-menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  transition: background-color var(--transition-fast);
  border-radius: var(--radius-sm);
  margin: 0 4px;
}

.theme-menu-item:hover {
  background: var(--bg-panel-muted);
}

:deep(.el-dropdown-menu.glass-panel) {
  padding: 8px 0;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}
</style>
