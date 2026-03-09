/**
 * 点击波纹效果指令
 * 为按钮和可点击元素添加 Material Design 风格的波纹反馈
 */

interface RippleInstance {
  element: HTMLElement;
  x: number;
  y: number;
  size: number;
}

class RippleManager {
  private ripples: Map<HTMLElement, RippleInstance> = new Map();

  createRipple(event: MouseEvent | TouchEvent, element: HTMLElement) {
    // 移除旧的波纹
    this.removeRipple(element);

    const rect = element.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    
    let clientX: number;
    let clientY: number;

    if ('touches' in event && event.touches.length > 0) {
      const touch = event.touches[0];
      if (touch) {
        clientX = touch.clientX;
        clientY = touch.clientY;
      } else {
        return;
      }
    } else if ('clientX' in event) {
      clientX = event.clientX;
      clientY = event.clientY;
    } else {
      return;
    }

    const x = clientX - rect.left - size / 2;
    const y = clientY - rect.top - size / 2;

    const ripple = document.createElement('span');
    ripple.className = 'ripple-effect';
    ripple.style.width = `${size}px`;
    ripple.style.height = `${size}px`;
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;

    // 确保元素有相对定位
    if (getComputedStyle(element).position === 'static') {
      element.style.position = 'relative';
    }

    // 阻止溢出
    element.style.overflow = 'hidden';

    element.appendChild(ripple);

    this.ripples.set(element, {
      element: ripple,
      x,
      y,
      size
    });

    // 动画结束后移除
    setTimeout(() => {
      this.removeRipple(element);
    }, 600);
  }

  removeRipple(element: HTMLElement) {
    const rippleData = this.ripples.get(element);
    if (rippleData && rippleData.element.parentNode === element) {
      rippleData.element.remove();
      this.ripples.delete(element);
    }
  }
}

const rippleManager = new RippleManager();

// 波纹效果样式
const style = document.createElement('style');
style.textContent = `
  .ripple-effect {
    position: absolute;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.4);
    transform: scale(0);
    animation: ripple-animation 0.6s ease-out;
    pointer-events: none;
    user-select: none;
  }

  @keyframes ripple-animation {
    to {
      transform: scale(4);
      opacity: 0;
    }
  }

  [data-ripple] {
    position: relative;
    overflow: hidden;
  }
`;
document.head.appendChild(style);

export const vRipple = {
  mounted(el: HTMLElement) {
    el.addEventListener('mousedown', (e) => {
      // 右键点击不触发
      if ((e as MouseEvent).button !== 0) return;
      rippleManager.createRipple(e, el);
    });

    el.addEventListener('touchstart', (e) => {
      rippleManager.createRipple(e, el);
    });

    el.setAttribute('data-ripple', 'true');
  },

  beforeUnmount(el: HTMLElement) {
    rippleManager.removeRipple(el);
  }
};

/**
 * Vue 3 插件安装函数
 */
export function installRipplePlugin(app: any) {
  app.directive('ripple', vRipple);
}

export default vRipple;
