# 前端产品级功能快速指南

## 📦 新增组件

### 1. SkeletonLoader - 骨架屏组件

```vue
<template>
  <!-- 文本骨架屏 -->
  <SkeletonLoader variant="text" :width="200" :height="20" />
  
  <!-- 圆形头像 -->
  <SkeletonLoader variant="circular" :size="40" />
  
  <!-- 卡片 -->
  <SkeletonLoader variant="card" />
  
  <!-- 列表（5 项） -->
  <SkeletonLoader variant="list" :count="5" />
  
  <!-- 聊天对话 -->
  <SkeletonLoader variant="chat" />
</template>
```

**可用变体：**
- `text` - 文本
- `circular` - 圆形
- `rect` - 矩形
- `rounded` - 圆角
- `card` - 卡片
- `list` - 列表
- `table` - 表格
- `chat` - 聊天

### 2. EnhancedEmpty - 增强空状态

```vue
<template>
  <EnhancedEmpty
    variant="document"
    title="暂无文档"
    description="上传文档到知识库以开始问答"
  >
    <template #actions>
      <el-button type="primary" @click="goUpload">上传文档</el-button>
    </template>
    
    <template #tips>
      <strong>支持格式：</strong>
      <ul>
        <li>TXT / PDF / DOCX</li>
      </ul>
    </template>
  </EnhancedEmpty>
</template>
```

**可用变体：**
- `document` - 文档为空
- `folder` - 知识库为空
- `chat` - 聊天为空
- `search` - 搜索无结果
- `upload` - 等待上传
- `question` - 帮助提示
- `success` - 成功状态
- `default` - 默认

### 3. ErrorBoundary - 错误边界

```vue
<template>
  <ErrorBoundary
    title="加载失败"
    error-message="无法加载数据，请检查网络连接"
    :show-retry="true"
    :max-retries="3"
    :retry-delay="1000"
    @retry="loadData"
    @reset="handleReset"
  >
    <div>{{ data }}</div>
    
    <template #actions>
      <el-button plain @click="goBack">返回</el-button>
    </template>
  </ErrorBoundary>
</template>
```

**Props：**
- `title` - 错误标题
- `error-message` - 错误描述
- `error-details` - 错误详情
- `show-retry` - 显示重试按钮
- `retry-text` - 重试按钮文本
- `reset-text` - 返回按钮文本
- `show-details` - 显示详情
- `retry-delay` - 重试延迟
- `max-retries` - 最大重试次数

### 4. ThemeToggle - 主题切换

```vue
<template>
  <div class="topbar">
    <ThemeToggle />
  </div>
</template>

<script setup>
import { ThemeToggle } from '@/components/ThemeToggle'
</script>
```

**主题模式：**
- `light` - 浅色模式
- `dark` - 深色模式
- `system` - 跟随系统

## 🎨 动画类

### 页面过渡
```vue
<transition name="fade-transform" mode="out-in">
  <component :is="Component" />
</transition>
```

### 滑入动画
```vue
<transition name="slide-in-right">
  <div>内容</div>
</transition>
```

### 缩放动画
```vue
<transition name="scale-in">
  <div>内容</div>
</transition>
```

### 淡入淡出
```vue
<transition name="fade">
  <div>内容</div>
</transition>
```

### 交错动画
```vue
<div class="stagger-item" v-for="item in items" :key="item.id">
  {{ item.name }}
</div>
```

### 加载动画
```vue
<div class="animate-pulse">加载中...</div>
<div class="animate-spin">旋转中...</div>
<div class="animate-bounce">跳动中...</div>
<div class="shimmer">闪烁效果</div>
```

## 🎯 响应式工具类

### 自定义滚动条
```vue
<div class="custom-scrollbar">
  <!-- 内容 -->
</div>
```

### 触摸滚动
```vue
<div class="touch-scroll">
  <!-- 内容 -->
</div>
```

## 🌓 主题工具

### JavaScript API

```typescript
import { 
  setTheme, 
  getTheme, 
  toggleTheme,
  getThemeIcon,
  getThemeLabel,
  initTheme,
  type ThemeMode
} from '@/utils/theme'

// 设置主题
setTheme('dark')

// 获取当前主题
const current = getTheme()

// 切换主题
const next = toggleTheme()

// 获取主题图标
const icon = getThemeIcon('dark') // 返回 'Moon'

// 获取主题标签
const label = getThemeLabel('dark') // 返回 '深色模式'

// 初始化主题（在 main.ts 中已调用）
initTheme()
```

## 📱 响应式断点

```css
/* 移动端：< 768px */
@media (max-width: 768px) { }

/* 平板：769px - 1280px */
@media (min-width: 769px) and (max-width: 1280px) { }

/* 桌面端：> 1280px */
@media (min-width: 1281px) { }

/* 大屏幕：> 1920px */
@media (min-width: 1920px) { }
```

## ♿ 可访问性

### ARIA 标签
```vue
<nav aria-label="主导航">
  <button aria-current="page">当前页面</button>
</nav>
```

### 键盘导航
```vue
<button 
  @keyup.enter="handleAction"
  @keyup.space="handleAction"
>
  操作
</button>
```

### 焦点管理
```vue
<input 
  type="text"
  @focus="handleFocus"
  @blur="handleBlur"
/>
```

## 🎨 CSS 变量

### 颜色
```css
var(--bg-page)          /* 页面背景 */
var(--bg-panel)         /* 卡片背景 */
var(--bg-panel-muted)   /*  muted 卡片背景 */
var(--text-primary)     /* 主文本 */
var(--text-regular)     /* 常规文本 */
var(--text-secondary)   /* 次要文本 */
var(--text-muted)       /* 弱化文本 */
var(--border-color)     /* 边框颜色 */
var(--border-strong)    /* 强边框颜色 */
```

### 阴影
```css
var(--shadow-sm)        /* 小阴影 */
var(--shadow-md)        /* 中阴影 */
var(--shadow-lg)        /* 大阴影 */
var(--shadow-focus)     /* 焦点阴影 */
```

### 圆角
```css
var(--radius-sm)        /* 小圆角：8px */
var(--radius-md)        /* 中圆角：12px */
var(--radius-lg)        /* 大圆角：16px */
```

### 字体
```css
var(--font-heading)     /* 标题字体 */
var(--font-body)        /* 正文字体 */
var(--font-mono)        /* 等宽字体 */
```

## 🚀 性能优化

### 组件懒加载（预留）
```typescript
// router/index.ts
const ChatView = () => import('@/views/chat/UnifiedChatView.vue')
```

### 虚拟滚动（预留）
```vue
<template>
  <!-- 大数据列表使用虚拟滚动 -->
  <div class="virtual-list">
    <div v-for="item in visibleItems" :key="item.id">
      {{ item.name }}
    </div>
  </div>
</template>
```

## 🧪 测试

### Playwright 测试
```bash
# 运行产品级功能测试
npx playwright test tests/product-grade.spec.ts
```

### 测试覆盖
- ✅ 登录页面
- ✅ 导航菜单
- ✅ 主题切换
- ✅ 响应式布局
- ✅ 动画效果
- ✅ 空状态组件
- ✅ 骨架屏组件
- ✅ 错误边界组件

## 📊 构建验证

```bash
# 构建项目
cd apps/web && npm run build

# 编码检查
python scripts/quality/check-encoding.py

# Docker 配置检查
docker compose config --quiet
```

## 💡 最佳实践

### 1. 加载状态
```vue
<template>
  <div>
    <SkeletonLoader v-if="loading" variant="card" />
    <div v-else>{{ data }}</div>
  </div>
</template>
```

### 2. 空状态
```vue
<template>
  <EnhancedEmpty
    v-if="!items.length"
    variant="document"
    title="暂无数据"
  >
    <template #actions>
      <el-button type="primary" @click="loadData">
        加载数据
      </el-button>
    </template>
  </EnhancedEmpty>
  
  <div v-else>
    <!-- 数据列表 -->
  </div>
</template>
```

### 3. 错误处理
```vue
<template>
  <ErrorBoundary
    ref="errorBoundary"
    title="加载失败"
    :show-retry="true"
    @retry="loadData"
  >
    <div>{{ data }}</div>
  </ErrorBoundary>
</template>

<script setup>
const errorBoundary = ref()

const loadData = async () => {
  try {
    data.value = await fetchData()
    errorBoundary.value?.resetError()
  } catch (error) {
    errorBoundary.value?.handleError(error)
  }
}
</script>
```

### 4. 主题感知
```vue
<template>
  <div :class="['component', `theme-${currentTheme}`]">
    内容
  </div>
</template>

<script setup>
import { getTheme } from '@/utils/theme'

const currentTheme = getTheme()
</script>
```

### 5. 响应式设计
```vue
<template>
  <div class="responsive-grid">
    <!-- 自动适配列数 -->
    <div v-for="item in items" :key="item.id" class="grid-item">
      {{ item.name }}
    </div>
  </div>
</template>

<style scoped>
.responsive-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}
</style>
```

## 📚 相关文档

- [FRONTEND_OPTIMIZATION_SUMMARY.md](./FRONTEND_OPTIMIZATION_SUMMARY.md) - 完整优化总结
- [README.md](./README.md) - 项目说明
- [docs/development/dev-scripts.md](./docs/development/dev-scripts.md) - 开发脚本

## 🎯 下一步

### 立即可用
- ✅ 使用骨架屏优化加载体验
- ✅ 使用增强空状态提升引导性
- ✅ 使用错误边界改善容错性
- ✅ 使用主题切换满足个性化需求

### 短期优化
- [ ] 在所有页面添加骨架屏
- [ ] 完善所有空状态场景
- [ ] 添加更多错误恢复场景
- [ ] 优化移动端导航体验

### 中长期优化
- [ ] 实现组件懒加载
- [ ] 添加虚拟滚动
- [ ] 完善深色模式
- [ ] 添加 PWA 支持

---

**更新时间：** 2026-03-08  
**版本：** v2.0  
**状态：** 生产就绪 ✅
