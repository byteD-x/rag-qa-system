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
  '--text-muted': '#64748b',
  '--border-color': 'rgba(148, 163, 184, 0.1)',
  '--border-strong': 'rgba(148, 163, 184, 0.18)',
  '--border-subtle': 'rgba(148, 163, 184, 0.06)',
  '--shadow-sm': '0 1px 2px rgba(0, 0, 0, 0.2)',
  '--shadow-md': '0 4px 12px rgba(0, 0, 0, 0.25)',
  '--shadow-lg': '0 8px 24px rgba(0, 0, 0, 0.3)',
  '--shadow-focus': '0 0 0 2px rgba(59, 130, 246, 0.35)',
  '--blue-500': '#60a5fa',
  '--blue-600': '#3b82f6',
  '--blue-700': '#2563eb',
  '--blue-50': 'rgba(59, 130, 246, 0.12)',
  '--ink-900': '#f1f5f9',
  '--el-fill-color-blank': '#131b2e',
  '--el-bg-color-overlay': '#1a2438',
  '--el-border-color-light': 'rgba(148, 163, 184, 0.06)'
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
  '--text-muted': '#94a3b8',
  '--border-color': 'rgba(15, 23, 42, 0.08)',
  '--border-strong': 'rgba(15, 23, 42, 0.16)',
  '--border-subtle': 'rgba(15, 23, 42, 0.05)',
  '--shadow-sm': '0 1px 2px rgba(0, 0, 0, 0.04)',
  '--shadow-md': '0 4px 12px rgba(0, 0, 0, 0.06)',
  '--shadow-lg': '0 8px 24px rgba(0, 0, 0, 0.08)',
  '--shadow-focus': '0 0 0 2px rgba(37, 99, 235, 0.2)',
  '--el-fill-color-blank': '#ffffff',
  '--el-bg-color-overlay': '#ffffff',
  '--el-border-color-light': 'rgba(15, 23, 42, 0.06)'
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
