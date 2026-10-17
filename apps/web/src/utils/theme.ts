/**
 * 主题切换工具
 * 支持浅色/深色模式切换
 */

export type ThemeMode = 'light' | 'dark' | 'system';

const THEME_STORAGE_KEY = 'rag-qa-theme-mode';

// 深色模式 CSS 变量（与浅色风格一致的克制调性）
const darkThemeVars = {
  '--color-scheme': 'dark',
  '--bg-page': '#0c1222',
  '--bg-panel': '#131b2e',
  '--bg-panel-muted': '#1a2438',
  '--text-primary': '#f1f5f9',
  '--text-regular': '#cbd5e1',
  '--text-secondary': '#94a3b8',
  '--text-muted': '#94a3b8',
  '--border-color': 'rgba(148, 163, 184, 0.1)',
  '--border-strong': 'rgba(148, 163, 184, 0.18)',
  '--border-subtle': 'rgba(148, 163, 184, 0.06)',
  '--shadow-sm': '0 1px 2px rgba(0, 0, 0, 0.2)',
  '--shadow-md': '0 4px 12px rgba(0, 0, 0, 0.25)',
  '--shadow-lg': '0 8px 24px rgba(0, 0, 0, 0.3)',
  '--shadow-focus': '0 0 0 2px var(--blue-600)',
  '--blue-500': '#60a5fa',
  '--blue-600': '#3b82f6',
  '--blue-700': '#2563eb',
  '--blue-50': 'rgba(59, 130, 246, 0.12)',
  '--ink-900': '#f1f5f9',
  '--scrollbar-thumb': 'rgba(148, 163, 184, 0.35)',
  '--scrollbar-thumb-hover': 'rgba(148, 163, 184, 0.5)',
  '--el-fill-color-blank': '#131b2e',
  '--el-bg-color-overlay': '#1a2438',
  '--el-border-color-light': 'rgba(148, 163, 184, 0.06)',
  '--text-info-strong': '#93c5fd',
  '--text-success-status': '#4ade80',
  '--text-warning-heading': '#fbbf24',
  '--text-warning-body': '#fbbf24',
  '--text-warning-status': '#fbbf24',
  '--text-warning-banner': '#fbbf24',
  '--text-danger-heading': '#f87171',
  '--text-danger-body': '#f87171',
  '--text-danger-status': '#f87171',
  '--text-on-primary': '#ffffff',
  '--border-info': 'rgba(96, 165, 250, 0.55)',
  '--border-info-soft': 'rgba(96, 165, 250, 0.4)',
  '--border-info-subtle': 'rgba(96, 165, 250, 0.28)',
  '--bg-warning-subtle': 'rgba(230, 162, 60, 0.14)',
  '--bg-media-canvas': '#0f172a',
};

// 浅色模式 CSS 变量（Linear / Vercel 风格）
const lightThemeVars = {
  '--color-scheme': 'light',
  '--bg-page': '#f8fafc',
  '--bg-panel': '#ffffff',
  '--bg-panel-muted': '#f1f5f9',
  '--text-primary': '#0f172a',
  '--text-regular': '#334155',
  '--text-secondary': '#64748b',
  '--text-muted': '#64748b',
  '--border-color': 'rgba(15, 23, 42, 0.08)',
  '--border-strong': 'rgba(15, 23, 42, 0.16)',
  '--border-subtle': 'rgba(15, 23, 42, 0.05)',
  '--shadow-sm': '0 1px 2px rgba(0, 0, 0, 0.04)',
  '--shadow-md': '0 4px 12px rgba(0, 0, 0, 0.06)',
  '--shadow-lg': '0 8px 24px rgba(0, 0, 0, 0.08)',
  '--shadow-focus': '0 0 0 2px var(--blue-600)',
  '--blue-500': '#3b82f6',
  '--blue-600': '#2563eb',
  '--blue-700': '#1d4ed8',
  '--blue-50': '#eff6ff',
  '--ink-900': '#0f172a',
  '--scrollbar-thumb': 'rgba(126, 142, 161, 0.58)',
  '--scrollbar-thumb-hover': 'rgba(95, 112, 132, 0.72)',
  '--el-fill-color-blank': '#ffffff',
  '--el-bg-color-overlay': '#ffffff',
  '--el-border-color-light': 'rgba(15, 23, 42, 0.06)',
  '--text-info-strong': '#275dad',
  '--text-success-status': '#2f7d1f',
  '--text-warning-heading': '#92400e',
  '--text-warning-body': '#b45309',
  '--text-warning-status': '#b26a07',
  '--text-warning-banner': '#8a5800',
  '--text-danger-heading': '#991b1b',
  '--text-danger-body': '#b91c1c',
  '--text-danger-status': '#c03838',
  '--text-on-primary': '#ffffff',
  '--border-info': '#8bb6ff',
  '--border-info-soft': '#bfd7ff',
  '--border-info-subtle': '#d9e5fb',
  '--bg-warning-subtle': '#fff7ed',
  '--bg-media-canvas': '#0f172a',
};

/**
 * 应用主题变量
 */
function applyThemeVars(vars: Record<string, string>) {
  const root = document.documentElement;
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value);
  }
}

/**
 * 获取系统主题偏好
 */
function getSystemTheme(): ThemeMode {
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
}

/**
 * 设置主题模式
 */
export function setTheme(mode: ThemeMode) {
  localStorage.setItem(THEME_STORAGE_KEY, mode);
  applyTheme(mode);
}

/**
 * 获取当前主题模式
 */
export function getTheme(): ThemeMode {
  return (localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode) || 'system';
}

/**
 * 应用主题
 */
function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  
  if (mode === 'system') {
    const systemMode = getSystemTheme();
    applyThemeVars(systemMode === 'dark' ? darkThemeVars : lightThemeVars);
    root.setAttribute('data-theme', systemMode);
  } else {
    applyThemeVars(mode === 'dark' ? darkThemeVars : lightThemeVars);
    root.setAttribute('data-theme', mode);
  }
}

/**
 * 监听系统主题变化
 */
function watchSystemTheme(callback: (mode: ThemeMode) => void) {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  
  const handler = (e: MediaQueryListEvent) => {
    callback(e.matches ? 'dark' : 'light');
  };
  
  mediaQuery.addEventListener('change', handler);
  
  return () => {
    mediaQuery.removeEventListener('change', handler);
  };
}

/**
 * 初始化主题
 */
export function initTheme() {
  const savedTheme = getTheme();
  applyTheme(savedTheme);
  
  // 监听系统主题变化
  if (savedTheme === 'system') {
    watchSystemTheme(() => {
      applyTheme('system');
    });
  }
}

/**
 * 切换主题
 */
export function toggleTheme() {
  const current = getTheme();
  const next: ThemeMode = current === 'light' ? 'dark' : 'light';
  setTheme(next);
  return next;
}

/**
 * 获取主题图标
 */
export function getThemeIcon(mode?: ThemeMode): string {
  const theme = mode || getTheme();
  
  if (theme === 'dark') {
    return 'Sunny';
  }
  return 'Moon';
}

/**
 * 获取主题标签
 */
export function getThemeLabel(mode?: ThemeMode): string {
  const theme = mode || getTheme();
  
  switch (theme) {
    case 'light':
      return '浅色模式';
    case 'dark':
      return '深色模式';
    case 'system':
      return '跟随系统';
    default:
      return '浅色模式';
  }
}
