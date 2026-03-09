/**
 * 移动端手势管理工具
 * 支持滑动、双击、长按等手势
 */

export interface GestureConfig {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  onSwipeUp?: () => void;
  onSwipeDown?: () => void;
  onDoubleTap?: (event: TouchEvent) => void;
  onLongPress?: (event: TouchEvent) => void;
  swipeThreshold?: number;
  longPressDuration?: number;
}

class GestureManager {
  private touchStartX = 0;
  private touchStartY = 0;
  private touchStartTime = 0;
  private longPressTimer: number | null = null;
  private lastTapTime = 0;
  private lastTapPosition = { x: 0, y: 0 };

  /**
   * 绑定到手势到元素
   */
  bind(element: HTMLElement, config: GestureConfig) {
    const {
      swipeThreshold = 50,
      longPressDuration = 500
    } = config;

    element.addEventListener('touchstart', (e) => {
      this.handleTouchStart(e, config, longPressDuration);
    }, { passive: true });

    element.addEventListener('touchmove', (e) => {
      this.handleTouchMove(e);
    }, { passive: true });

    element.addEventListener('touchend', (e) => {
      this.handleTouchEnd(e, config, swipeThreshold);
    }, { passive: true });
  }

  /**
   * 处理触摸开始
   */
  private handleTouchStart(
    event: TouchEvent,
    config: GestureConfig,
    longPressDuration: number
  ) {
    const touch = event.touches[0];
    if (!touch) return;

    this.touchStartX = touch.clientX;
    this.touchStartY = touch.clientY;
    this.touchStartTime = Date.now();

    // 长按检测
    if (config.onLongPress) {
      this.longPressTimer = window.setTimeout(() => {
        if (this.longPressTimer) {
          config.onLongPress?.(event);
          this.longPressTimer = null;
        }
      }, longPressDuration);
    }
  }

  /**
   * 处理触摸移动
   */
  private handleTouchMove(_event: TouchEvent) {
    // 移动时取消长按
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
      this.longPressTimer = null;
    }
  }

  /**
   * 处理触摸结束
   */
  private handleTouchEnd(
    event: TouchEvent,
    config: GestureConfig,
    swipeThreshold: number
  ) {
    // 取消长按
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
      this.longPressTimer = null;
    }

    const touch = event.changedTouches[0];
    if (!touch) return;

    const endX = touch.clientX;
    const endY = touch.clientY;
    const endTime = Date.now();

    const diffX = endX - this.touchStartX;
    const diffY = endY - this.touchStartY;
    const diffTime = endTime - this.touchStartTime;

    // 双击检测
    if (diffTime < 200 && Math.abs(diffX) < 10 && Math.abs(diffY) < 10) {
      const timeSinceLastTap = endTime - this.lastTapTime;
      
      if (timeSinceLastTap < 300 &&
          Math.abs(endX - this.lastTapPosition.x) < 30 &&
          Math.abs(endY - this.lastTapPosition.y) < 30) {
        config.onDoubleTap?.(event);
        this.lastTapTime = 0;
        return;
      }
      
      this.lastTapTime = endTime;
      this.lastTapPosition = { x: endX, y: endY };
    }

    // 滑动检测
    if (Math.abs(diffX) > swipeThreshold || Math.abs(diffY) > swipeThreshold) {
      if (Math.abs(diffX) > Math.abs(diffY)) {
        // 水平滑动
        if (diffX > 0) {
          config.onSwipeRight?.();
        } else {
          config.onSwipeLeft?.();
        }
      } else {
        // 垂直滑动
        if (diffY > 0) {
          config.onSwipeDown?.();
        } else {
          config.onSwipeUp?.();
        }
      }
    }
  }

  /**
   * 解绑手势
   */
  unbind(_element: HTMLElement) {
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
      this.longPressTimer = null;
    }
  }
}

export const gestureManager = new GestureManager();

/**
 * Vue 3 组合式 API Hook
 */
export function useGestures() {
  return {
    bind: gestureManager.bind.bind(gestureManager),
    unbind: gestureManager.unbind.bind(gestureManager)
  };
}

/**
 * 指令方式绑定滑动事件
 */
export const vSwipe = {
  mounted(el: HTMLElement, binding: any) {
    const handlers = binding.value || {};
    
    gestureManager.bind(el, {
      onSwipeLeft: handlers.left,
      onSwipeRight: handlers.right,
      onSwipeUp: handlers.up,
      onSwipeDown: handlers.down,
      onDoubleTap: handlers.doubleTap,
      onLongPress: handlers.longPress
    });
  },
  
  beforeUnmount(el: HTMLElement) {
    gestureManager.unbind(el);
  }
};
