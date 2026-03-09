/**
 * 键盘快捷键管理工具
 * 提供全局快捷键注册和取消注册功能
 */

export interface Shortcut {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  handler: (event: KeyboardEvent) => void;
  description?: string;
}

export interface ShortcutConfig {
  [key: string]: Shortcut;
}

class ShortcutManager {
  private shortcuts: Map<string, Shortcut> = new Map();
  private enabled = true;

  /**
   * 注册快捷键
   */
  register(shortcut: Shortcut) {
    const key = this.buildKey(shortcut);
    this.shortcuts.set(key, shortcut);
  }

  /**
   * 取消注册快捷键
   */
  unregister(shortcut: Shortcut) {
    const key = this.buildKey(shortcut);
    this.shortcuts.delete(key);
  }

  /**
   * 启用所有快捷键
   */
  enable() {
    this.enabled = true;
  }

  /**
   * 禁用所有快捷键
   */
  disable() {
    this.enabled = false;
  }

  /**
   * 构建快捷键的唯一标识
   */
  private buildKey(shortcut: Shortcut): string {
    const parts: string[] = [];
    
    if (shortcut.ctrl) parts.push('Ctrl');
    if (shortcut.shift) parts.push('Shift');
    if (shortcut.alt) parts.push('Alt');
    
    parts.push(shortcut.key.toUpperCase());
    
    return parts.join('+');
  }

  /**
   * 解析键盘事件为快捷键标识
   */
  private parseEvent(event: KeyboardEvent): string {
    const parts: string[] = [];
    
    if (event.ctrlKey) parts.push('Ctrl');
    if (event.shiftKey) parts.push('Shift');
    if (event.altKey) parts.push('Alt');
    
    const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;
    parts.push(key);
    
    return parts.join('+');
  }

  /**
   * 处理键盘事件
   */
  handleEvent(event: KeyboardEvent) {
    if (!this.enabled) return;

    // 忽略在输入框中的快捷键（除非是特定组合键）
    const target = event.target as HTMLElement;
    const isInput = target.tagName === 'INPUT' || 
                    target.tagName === 'TEXTAREA' || 
                    (target as any).isContentEditable;
    
    if (isInput && !event.ctrlKey && !event.altKey) {
      return;
    }

    const key = this.parseEvent(event);
    const shortcut = this.shortcuts.get(key);
    
    if (shortcut) {
      event.preventDefault();
      event.stopPropagation();
      shortcut.handler(event);
    }
  }

  /**
   * 获取所有注册的快捷键
   */
  getAll(): Shortcut[] {
    return Array.from(this.shortcuts.values());
  }

  /**
   * 获取快捷键的帮助文本
   */
  getHelpText(): string[] {
    return Array.from(this.shortcuts.values())
      .filter(s => s.description)
      .map(s => `${this.buildKey(s)} - ${s.description}`);
  }
}

// 创建全局快捷键管理器实例
export const shortcutManager = new ShortcutManager();

/**
 * 初始化全局快捷键监听
 */
export function initShortcuts() {
  window.addEventListener('keydown', (event) => {
    shortcutManager.handleEvent(event);
  });
}

/**
 * 注册常用快捷键
 */
export function registerCommonShortcuts(actions: {
  openSearch?: () => void;
  newChat?: () => void;
  uploadFile?: () => void;
  closeDialog?: () => void;
  save?: () => void;
}) {
  if (actions.openSearch) {
    shortcutManager.register({
      key: 'k',
      ctrl: true,
      handler: actions.openSearch,
      description: '打开搜索'
    });
  }

  if (actions.newChat) {
    shortcutManager.register({
      key: 'n',
      ctrl: true,
      handler: actions.newChat,
      description: '新建会话'
    });
  }

  if (actions.uploadFile) {
    shortcutManager.register({
      key: 'u',
      ctrl: true,
      handler: actions.uploadFile,
      description: '上传文件'
    });
  }

  if (actions.closeDialog) {
    shortcutManager.register({
      key: 'Escape',
      handler: actions.closeDialog,
      description: '关闭对话框'
    });
  }

  if (actions.save) {
    shortcutManager.register({
      key: 's',
      ctrl: true,
      handler: actions.save,
      description: '保存'
    });
  }
}

/**
 * Vue 3 组合式 API Hook
 */
export function useShortcuts() {
  return {
    register: shortcutManager.register.bind(shortcutManager),
    unregister: shortcutManager.unregister.bind(shortcutManager),
    enable: shortcutManager.enable.bind(shortcutManager),
    disable: shortcutManager.disable.bind(shortcutManager),
    getHelpText: shortcutManager.getHelpText.bind(shortcutManager)
  };
}
