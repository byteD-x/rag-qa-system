import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import './style.css'
import './styles/responsive-enhancements.css'
import './styles/theme-extras.css'
import { initTheme } from '@/utils/theme'
import { initShortcuts } from '@/utils/shortcuts'
import { installRipplePlugin } from '@/directives/ripple'
import { ElLoadingDirective } from 'element-plus'
import { elementComponents } from './element-plus-components'
import EnhancedEmpty from './components/EnhancedEmpty.vue'
import ThemeToggle from './components/ThemeToggle.vue'

const app = createApp(App)
const pinia = createPinia()
initTheme()
initShortcuts()
installRipplePlugin(app)

app.use(pinia)
app.use(router)
app.directive('loading', ElLoadingDirective)

for (const component of elementComponents) {
  if (component.name) {
    app.component(component.name, component)
  }
}

app.component('EnhancedEmpty', EnhancedEmpty)
app.component('ThemeToggle', ThemeToggle)

app.mount('#app')
