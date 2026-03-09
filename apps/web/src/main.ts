import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import './style.css'
import './styles/responsive-enhancements.css'
import './styles/theme-extras.css'
import { initTheme } from '@/utils/theme'
import { initShortcuts } from '@/utils/shortcuts'
import { installRipplePlugin } from '@/directives/ripple'
import {
  ElAlert,
  ElAside,
  ElAvatar,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCollapse,
  ElCollapseItem,
  ElConfigProvider,
  ElContainer,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElLink,
  ElLoadingDirective,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPopover,
  ElProgress,
  ElInputNumber,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSlider,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  ElUpload
} from 'element-plus'
import 'element-plus/dist/index.css'

// 导入自定义组件
import SkeletonLoader from './components/SkeletonLoader.vue'
import EnhancedEmpty from './components/EnhancedEmpty.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import ThemeToggle from './components/ThemeToggle.vue'

const app = createApp(App)
const pinia = createPinia()
const elementComponents = [
  ElAlert,
  ElAside,
  ElAvatar,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCollapse,
  ElCollapseItem,
  ElConfigProvider,
  ElContainer,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDrawer,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElLink,
  ElMain,
  ElMenu,
  ElMenuItem,
  ElOption,
  ElPopover,
  ElProgress,
  ElInputNumber,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSlider,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTimeline,
  ElTimelineItem,
  ElUpload
]

// 初始化主题
initTheme()

// 初始化全局快捷键
initShortcuts()

// 安装波纹效果插件
installRipplePlugin(app)

app.use(pinia)
app.use(router)
app.directive('loading', ElLoadingDirective)

for (const component of elementComponents) {
  if (component.name) {
    app.component(component.name, component)
  }
}

// 注册全局自定义组件
app.component('SkeletonLoader', SkeletonLoader)
app.component('EnhancedEmpty', EnhancedEmpty)
app.component('ErrorBoundary', ErrorBoundary)
app.component('ThemeToggle', ThemeToggle)

app.mount('#app')
