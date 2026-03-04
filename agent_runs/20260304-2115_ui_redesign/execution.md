# Execution Plan

## 1) 目标与交付物
- Goal: 重构 RAG-QA 系统前端界面（Vue 3 + Element Plus），提升美观度与交互体验（清爽、高对比度、动画流畅、高质感）。
- Deliverables: 
  1. 重构的登录页 (AuthLayout, LoginView)
  2. 重构的主布局及侧边栏 (MainLayout, ChatSidebar)
  3. 重构的聊天核心界面 (ChatInputArea, ChatMessageList, RagMessageRenderer)
  4. 重构的文档管理界面 (Dashboard 相关视图, DocumentUploader, CreateCorpusModal)
  5. 全局样式及动画优化 (style.css, Element Plus 主题定制)
- Out of scope: 后端 API 修改、非界面的核心业务逻辑重构、新增系统主要业务流程。

## 2) 输入/依赖/约束
- Inputs: 现有的 `src/views`, `src/components`, `src/layouts` 相关 Vue 组件。
- Dependencies: Vue 3, Element Plus 基础环境。
- Constraints: 遵循 "No Fake Progress" 原则，每完成一个 Task 记录真实修改与证据，代码注使用中文。
- Assumptions (显式列出): 
  1. 前端目前已实现可用业务逻辑并与后端连通，重构期间不对基础 API Request 进行改变。
  2. 系统允许定制/重置部分 Element Plus 样式以符合现代化高质感要求。

## 3) 方法（How）
- Approach:
  1. **全局样式/主题构建**：在 `style.css` 内统一定义设计系统变量（亮色主题、冷灰主色调、鲜明高对比色、舒适圆角阴影配置），并使用 CSS 原生动画提升组件切换过渡。
  2. **布局框架升级**：用现代 Dashboard 版式重构 `MainLayout`，侧边栏增加悬浮微交互，提升层次感。
  3. **聊天体验改造**：重构 `RagMessageRenderer`，采用细腻的对话气泡，区分 User/Bot 外观，打磨 `ChatInputArea` 以及列表滚动体验。
  4. **知识库管理美化**：优化 Dashboard 卡片呈现模式与表单 `CreateCorpusModal` 和上传控件的形态。
- Key decisions:
  - 核心风格走向：“极简现代风 + 微拟物阴影 / 毛玻璃修饰”；强化不同图层层级的对比度。
- Quality checks (验证闭环):
  - 本地尝试执行构建验证框架稳定性。
  - 用户本地运行环境验证 UI 不阻塞业务及报错。

## 4) 风险
- R1: 原有在 DOM 元素上挂载的 ref 或第三方插件在结构改变时可能受影响或失效。
- R2: Element Plus 组件的默认内联样式可能会抗拒 CSS 覆写，需要合理利用 `:deep` 样式穿透。

## 5) 验收（DoD）
- D1: 核心页面完成 UI 设计升级（涉及颜色、排版及过渡微交互）。
- D2: 整体前端交互顺畅，不引发白屏或其他业务逻辑崩溃（即 JS 与路由正常运行）。

## 6) 变更记录
- [2026-03-04 22:42] change: 建立基础 UI 重构执行计划。
