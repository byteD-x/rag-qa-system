# 90 跨页扫描：无障碍与交互规则符合性

扫描范围：`apps/web/src` 下全部 `.vue`（排除 `*.test.ts`）与 `style.css`、`styles/theme-extras.css`、`styles/responsive-enhancements.css`。
方法：静态源码阅读 + WCAG 相对亮度公式计算（比值均由脚本算出，见文末口径）。

## 结论摘要

1. **键盘用户基本无法使用自定义交互容器**：全仓 `tabindex` 只出现 1 次（`apps/web/src/views/kb/KBUploadView.vue:17`），而至少 5 处 `@click` 挂在不可聚焦的 `div/article/img/el-tag/el-icon` 上，键盘完全到不了。
2. **焦点环对比度不合格**：`--shadow-focus` 合成后浅色 1.33:1、深色 1.66:1（`apps/web/src/style.css:53`、`apps/web/src/utils/theme.ts:26`），远低于焦点外观通常要求的 3:1。
3. **深色主题下输入控件读不出字**：`style.css:682,700` 用 `!important` 把输入框底色钉死 `#ffffff`，而深色 `--text-regular` 是 `#cbd5e1` → 1.49:1；另有 5 处硬编码 `#fff`/`#fff5f5` 容器产生 1.02–1.10:1 的不可读文本。
4. **浅色下 12px 灰字压在 `--bg-panel-muted` 上是 4.34:1**，低于 AA 4.5:1，命中全站 el-table 表头及至少 4 个界面。
5. **`prefers-reduced-motion` 的通配符把加载动画也清零**，17 处 `<el-icon class="is-loading">` 在减动效下静止，丢掉"仍在进行"的状态指示。
6. Element Plus 2.13.3 的 dialog/drawer/ElMessage **自带** `role="dialog"`、`aria-modal`、`aria-label`、`role="alert"`，这些不是问题；唯一例外是 `MainLayout.vue:111` 用 `:with-header="false"` 导致 `aria-labelledby` 悬空。

## 唯一用户任务

任意角色的用户（含键盘、读屏、触屏、减动效、高对比度用户）在任一界面下要完成该界面的主任务时，**不必先克服"焦点看不见、控件键盘到不了、文字读不清"这三类障碍**。

## 完成该任务的必要步骤

1. 用 Tab 进入页面并能随时看出焦点落在哪 — **keep**
2. 用键盘到达每一个可点击容器 — **merge**（并入原生语义元素，不新增可见元素）
3. 用键盘触发（Enter / Space）— **keep**
4. 在深色主题下读懂所有输入控件里的文字 — **keep**
5. 在触屏上点中自定义小控件 — **demote**（并入既有触摸目标兜底规则，不新增组件）
6. 在开启减动效时仍能判断"还在加载" — **keep**

## 违规清单

| 规则 | 位置 | 证据 | 影响 | 修复方向 |
|---|---|---|---|---|
| 键盘可达 | apps/web/src/views/kb/KBDocumentView.vue:302 | `<article v-for="region ..." @click="focusVisualRegion(...)">`，无 `role`/`tabindex`/键盘事件 | 键盘用户无法选中截图区域，无法完成跨版本视觉对比 | 改为 `<button>`；区域已带 `:id`，可直接承接原 `@click` |
| 键盘可达 | apps/web/src/views/kb/KBDocumentView.vue:290 | `<img class="visual-thumb" @click="focusVisualAsset(...)">`，`img` 不可聚焦 | 同上，缩略图点击选中有鼠标专属 | 外面套 `<button>`，`img` 保留作内容 |
| 键盘可达 | apps/web/src/views/platform/AgentMonitorView.vue:61-67 | `<div class="run-card" @click="selectRun(run)">`，无 `role`/`tabindex` | 键盘用户无法打开任一运行详情 | 改 `<button class="run-card">`，`.run-card` 现有样式（:418-425）不依赖标签名 |
| 键盘可达 | apps/web/src/views/platform/SceneManagerView.vue:9-18 | `<el-tag ... @click="activeTag = activeTag === tag ? '' : tag">`；el-tag 根节点无 `tabindex`/`role`（node_modules/element-plus/es/components/tag/src/tag.vue2.mjs 只有 close 按钮的 aria-label） | 标签筛选是纯键盘不可达，只能靠"清除筛选"按钮（:19）迂回 | 改用 `<el-check-tag>` 或原生 `<button>`；`:19` 的"清除筛选"可随之删除 |
| 键盘可达 | apps/web/src/views/platform/PromptTemplateView.vue:44 | `<el-icon :color="..." @click="toggleFav(tpl)" style="cursor: pointer; font-size: 18px;">`，渲染为 `<i>` | 收藏模板键盘不可达，且无 aria-label（读屏只听到"图片"） | 换成 `<button>` 并给 `aria-label="收藏模板"/"取消收藏"` + `aria-pressed` |
| 焦点可见 | apps/web/src/style.css:53（浅）/ apps/web/src/utils/theme.ts:26（深） | `--shadow-focus: 0 0 0 2px rgba(37,99,235,.2)`；合成色 `#D3E0FB` vs `#fff` = **1.33:1**；深色 `#213F74` vs `#131b2e` = **1.66:1**。应用点 apps/web/src/style.css:130-137 | 全站键盘用户看不出焦点位置，是最高频的可用性障碍 | token 改为实心高对比（如 `0 0 0 2px var(--blue-600)`，5.17:1），浅/深两处同时改 |
| 焦点可见 | apps/web/src/styles/responsive-enhancements.css:286-292 ↔ apps/web/src/style.css:130-137 | 两套并存实现：前者 `outline: 2px solid var(--blue-600) !important`（合格），后者 `box-shadow`（1.33:1）。自定义原生 `<button>` 只命中后者 | 同一页面内 EP 组件与自定义按钮的焦点样式不一致，且后者不可见 | 合并为一处；保留 `!important` 的 outline 方案，删除 box-shadow 方案 |
| 对比度 | apps/web/src/style.css:682,700 + :69 + apps/web/src/utils/theme.ts:17 | `.el-input__wrapper/.el-select__wrapper/.el-textarea__inner { background: #ffffff !important }`，无 `[data-theme='dark']` 覆盖（theme-extras.css:83-89 只覆盖 dialog/message/notification）；`--el-text-color-regular: var(--text-regular)`，深色下为 `#cbd5e1` → **1.49:1** | 深色模式下**全站每个表单输入都读不出字**，影响面最大 | 底色改 `var(--bg-panel)`；若必须压 EP 默认色，加 `[data-theme='dark']` 覆盖 |
| 对比度 | apps/web/src/views/chat/components/ChatComposer.vue:68,77 | `.composer-inner { background: #fff }` + `.modern-input :deep(.el-textarea__inner) { background: transparent !important }` → 深色 **1.49:1** | 产品核心输入框在深色下不可读 | 底色改 `var(--bg-panel)` |
| 对比度 | apps/web/src/views/chat/components/ChatSidebar.vue:123,126 | `.new-chat-btn { background: #fff; color: var(--text-primary) }`；深色 `--text-primary: #f1f5f9` → **1.10:1** | "新建对话"按钮文字隐形 | 底色改 `var(--bg-panel)` |
| 对比度 | apps/web/src/views/chat/components/ChatInterruptCard.vue:142,152 | `.interrupt-option { background: #fff }` + `.interrupt-option__label { color: var(--text-primary) }` → 深色 **1.10:1** | 澄清选项标题隐形，而这是必须作答的阻断式卡片 | 底色改 `var(--bg-panel)` |
| 对比度 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:203,214,206,207,211,215,216 | `.trace-section { background: #f9f9fb }`、`.trace-summary-card { background: #fff }`，其内文字用 `--text-muted`/`--text-secondary`（深色 `#94a3b8`）→ on `#fff` **2.56:1**、on `#f9f9fb` **2.44:1** | 轨迹抽屉元信息深色下不可读 | 底色改 `var(--bg-panel)`/`var(--bg-panel-muted)` |
| 对比度 | apps/web/src/views/platform/CostDashboardView.vue:229,236 | `.health-card.circuit-open { background: #fff5f5 }` + `.hm-val { color: var(--text-primary) }` → 深色 **1.02:1** | 熔断告警卡上的指标数字完全不可见——恰好是最需要看到的告警态 | 底色改 `var(--bg-panel)` + 红色边框/左侧色条 |
| 对比度 | apps/web/src/styles/theme-extras.css:94,99,100 | `.el-table th.el-table__cell { color: var(--text-secondary); font-size: var(--text-caption) }` 且 `--el-table-header-bg-color: var(--bg-panel-muted)`；EP 规则 `.el-table th.el-table__cell{background-color:var(--el-table-header-bg-color)}` → `#64748b` on `#f1f5f9` = **4.34:1** < 4.5:1 | 全站所有 el-table 表头小字低于 AA | 表头底色改 `var(--bg-panel)`，或表头色改 `--text-regular`(#475569) |
| 对比度 | apps/web/src/views/platform/SceneManagerView.vue:209 | 单条规则自证：`.scene-prompt-preview { font-size: 12px; color: var(--text-muted); background: var(--bg-panel-muted) }` = **4.34:1** | 场景 Prompt 预览读不清 | 底色改 `var(--bg-panel)` |
| 对比度 | apps/web/src/views/LoginView.vue:250-255（底 :231） | `.demo-email { font-size: var(--text-caption); color: var(--text-muted) }` 位于 `.demo-btn { background: var(--bg-panel-muted) }` = **4.34:1** | 登录页演示账号邮箱读不清，而这是登录必经路径 | 该行改 `--text-regular`，或 `.demo-btn` 底色改 `var(--bg-panel)` |
| 对比度 | apps/web/src/views/platform/MemoryManagerView.vue:91（表 :68） | 内联 `style="font-size: 11px; color: var(--text-muted)"`；表格 `stripe`，条带行底色由 theme-extras.css:110-112 设为 `--bg-panel-muted` = **4.34:1** 且仅 11px | 置信度百分比读不清 | 去掉内联样式，沿用单元格默认色/字号 |
| 对比度 | apps/web/src/views/platform/AgentMonitorView.vue:612 | `.reflection-suggestions strong { color: var(--blue-500); font-size: 13px }` → `#3b82f6` on `#fff` = **3.68:1** < 4.5:1 | 反思建议标题低于 AA | 改 `--blue-600`（5.17:1）或 `--blue-700` |
| 对比度 | apps/web/src/views/chat/components/ChatMessageItem.vue:419-430 | `.feedback-btn { color: var(--text-muted); opacity: 0.6 }` → 合成 `#A2ACB9` on `#fff` = **2.30:1**（文本需 4.5、非文本需 3） | 反馈图标静息态几乎看不见，用户找不到评价入口 | 删掉 `opacity: 0.6`，或静息色用 `--text-regular` |
| 对比度 | apps/web/src/views/chat/components/ChatHeader.vue:212,229-233 | `.action-chip { font-size: 12px }` + `.action-chip.is-agent { color: #059669; background: #ecfdf5 }` = **3.58:1** < 4.5:1 | Agent 模式标识文字低于 AA | 文字改 `#047857` 或去掉彩色底 |
| 字号 | apps/web/src/views/platform/CostDashboardView.vue:233,237,244,254 | `.hm-label`(11px)、`.hm-lbl`(**10px**)、`.scene-pct`(11px)、`.daily-label`(**9px**) 均为硬编码 px，未用既有 `--text-caption`(0.75rem/12px)；比对白底 4.76:1 数值合格但字号低于可读下限 | 图表轴标签实际读不出 | 统一改 `var(--text-caption)`；9px 的 `.daily-label` 还应去掉 `transform: rotate(-45deg)` |
| 点击区 | apps/web/src/views/chat/components/ChatMessageItem.vue:407-417 | `.text-action-btn { padding: 0; font-size: 12px }`，`display:flex` 内含 1em 图标 → 高约 **16px**，小于 WCAG 2.2 AA 2.5.8 的 24×24 | 触屏/低精度指针点不中"轨迹"按钮 | 加 `padding: 6px 8px`（增至 ≈28px） |
| 点击区 | apps/web/src/views/chat/components/ChatHeader.vue:204-216 / apps/web/src/views/kb/KBDocumentView.vue:1256-1265 / apps/web/src/views/kb/KBOperationsView.vue:434-443 | `.action-chip`(6+6+2+≈17 ≈ **28-31px**)、`.smart-ask-preset`(8+8+2+≈16 ≈ **32-34px**)、`.toolbar-button`/`.link-button`(8+8+2+≈16 ≈ **33-36px**) 均 < 44px；触摸目标兜底 responsive-enhancements.css:33-40 只覆盖 `.el-button/.el-menu-item/.el-select/.el-input__wrapper`，**漏掉这些自定义类** | 触屏上偏小但可用（≥24px 过 AA 2.5.8） | 把上述类名并入 responsive-enhancements.css:35-40 的 `min-height: 44px` 列表 |
| 语义与标注 | apps/web/src/views/platform/PiiConfigView.vue:34 | `<el-switch v-model="pt.enabled" />` 在普通 `<div class="pii-type-row">`(:32) 内，非 `el-form-item`；`pt.label` 是兄弟 `span`(:35) 无关联 → `role="switch"` 无可访问名称 | 读屏只播报"开关，已选中"，不知是哪个 PII 类型 | 包一层 `<el-form-item :label="pt.label">` |
| 语义与标注 | apps/web/src/views/platform/ToolManagerView.vue:66 | `<el-switch v-model="tool.enabled" ... />` 在 `.tool-header` div(:53) 内，仅兄弟 `el-tag`(:60-62) 显示状态，无名称关联 | 读屏不知在开关哪个工具 | 同上报 `<el-form-item :label="tool.name">` 或加 `aria-label` |
| 语义与标注 | apps/web/src/views/kb/KBOperationsView.vue:9,13 | 两个原生 `<select v-model="viewMode">` / `<select v-model.number="days">` 均无 `<label>`、无 `aria-label` | 读屏播报"组合框"，不知选的是范围还是天数 | 两个 select 各加 `aria-label`（"数据范围"/"统计天数"） |
| 语义与标注 | apps/web/src/views/kb/KBChunkReviewView.vue:78 | `<el-button type="danger" plain icon="Delete" @click="splitParts.splice(i, 1)" />` 自闭合，无 `aria-label`/`title` | 读屏播报成无名按钮，删除拆分片段时无法确认 | 加 `aria-label="删除该片段"` |
| 语义与标注 | apps/web/src/layouts/MainLayout.vue:111-118 | `<el-drawer :with-header="false" ...>` 且无 `title` → EP 渲染 `aria-labelledby="<titleId>"`（node_modules/element-plus/es/components/drawer/src/drawer.vue2.mjs:114），而带该 id 的 `<span>` 位于 `v-if="withHeader"` 分支内（同文件 :140、:153-154）→ 悬空引用 | 移动端主导航抽屉无可访问名称 | 补 `title="导航"` 或加 `aria-label="主导航"`（`:115` 的 `with-header:false` 是为了视觉，不必改） |
| prefers-reduced-motion | apps/web/src/style.css:806-815 | 通配符 `animation-duration: .01ms !important; animation-iteration-count: 1 !important` 连带清零 `.el-icon.is-loading { animation: rotating 2s linear infinite }`（node_modules/element-plus/theme-chalk/index.css）→ 17 处加载图标静止：EntryView.vue:22、KBDocumentView.vue:25/336、KBConnectorsView.vue:11、KBChunkReviewView.vue:12、AgentMonitorView.vue:49/97、ChatTraceDrawer.vue:98、AgentProfileView.vue:11、CacheManagerView.vue:38、CostDashboardView.vue:39、MemoryManagerView.vue:56、RetrievalDebuggerView.vue:50、ModelProviderView.vue:139、PromptTemplateView.vue:11、ToolManagerView.vue:40、SceneManagerView.vue:23 | 减动效用户失去"仍在进行"的状态指示（有文字兜底处影响小，纯图标处影响大） | 改为显式白名单，保留 `animation`（旋转可降速），只禁 `transition` 位移与缩放 |
| prefers-contrast | apps/web/src/styles/responsive-enhancements.css:263-277 | `@media (prefers-contrast: high)` 只把 `--border-color/--border-strong` 硬编码成 `rgba(0,0,0,.5/.6)`，深色面板 `#131b2e` 上边框几乎不可见；且完全没动文字色 | 请求高对比的用户拿不到任何文字对比改善，深色下反而丢边框 | 改为 `currentColor` 或按 `[data-theme]` 分色；同时补文字色覆盖 |
| 无效声明 | apps/web/src/views/kb/KBChunkReviewView.vue:265 / apps/web/src/views/platform/PromptTemplateView.vue:259 | `background: var(--bg-body)`；`--bg-body` 在 style.css:1-84、utils/theme.ts、theme-extras.css:1-5、responsive-enhancements.css 中均未定义 | 声明无效，禁用切片的底色与默认态一致，"已禁用"缺少视觉区分 | 删除该行改用 `var(--bg-panel-muted)` |
| 无效 token | apps/web/src/utils/theme.ts:12,39 | 写入 `--color-scheme: 'dark'/'light'`，但全仓无消费者；`color-scheme` 由 apps/web/src/style.css:2 硬编码 `light` | 深色模式下原生控件（KBOperationsView.vue:9,13 的 select 下拉、滚动条）仍按浅色渲染 | 删除该 token，或在 style.css 加 `color-scheme: var(--color-scheme, light)` |
| 假可供性 | apps/web/src/views/platform/CostDashboardView.vue:138,252,253 | `<div class="daily-bar" :title="formatCost(d.cost)" />` **无 `@click`**，但样式给了 `cursor: pointer` 与 `.daily-bar:hover { background: var(--blue-600) }` | 鼠标指针和 hover 高亮都在承诺可点，实际无响应，白耗一次点击 | 删除 `cursor: pointer` 与 `:hover` 规则 |

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 自定义可点击容器（div/article/img） | apps/web/src/views/kb/KBDocumentView.vue:290,302；apps/web/src/views/platform/AgentMonitorView.vue:61 | 必要 | 承载版本对比、运行详情等真实动作，不能删；缺 role/tabindex/键盘事件 |
| `el-tag` 当筛选器 | apps/web/src/views/platform/SceneManagerView.vue:9 | 必要 | 筛选能力必要，但 el-tag 不可聚焦；改用可聚焦的等价物即可，:19 的"清除筛选"可一并去掉 |
| `el-icon` 当按钮 | apps/web/src/views/platform/PromptTemplateView.vue:44 | 必要 | 收藏动作必要；换成 `<button>`，无需新增元素 |
| 图表轴/元信息小字 | apps/web/src/views/platform/CostDashboardView.vue:233,237,244,254 | 可下沉 | 统一沉到 `--text-caption`，不再硬编码 9/10/11px |
| 自定义交互类家族 | `.action-chip`(ChatHeader.vue:204)、`.text-action-btn`(ChatMessageItem.vue:407)、`.smart-ask-preset`(KBDocumentView.vue:1256)、`.toolbar-button`/`.link-button`(KBOperationsView.vue:434)、`.recent-item`(EntryView.vue:622)、`.suggest-card`(UnifiedChatView.vue:322)、`.run-card`(AgentMonitorView.vue:418) | 可合并 | 各自重实现可交互态；缺统一的键盘/触摸目标/焦点基类，5+ 文件重复同一问题 |
| 硬编码浅色容器 | ChatComposer.vue:68、ChatSidebar.vue:123、ChatInterruptCard.vue:142、ChatTraceDrawer.vue:203,214、CostDashboardView.vue:229、style.css:682,700 | 可合并 | 8 处同类写法，统一改 `var(--bg-panel)` 一处规则即可覆盖 |
| `.el-icon.is-loading` 加载指示 | 17 处，见违规清单末段 | 可合并 | 统一为同一个加载组件/类，才能一处修好减动效行为 |
| `--color-scheme` token | apps/web/src/utils/theme.ts:12,39 | 可删 | 零消费者 |
| `--bg-body` 声明 | apps/web/src/views/kb/KBChunkReviewView.vue:265；apps/web/src/views/platform/PromptTemplateView.vue:259 | 可删 | 变量未定义，声明无效 |
| `.daily-bar` 的 cursor/hover | apps/web/src/views/platform/CostDashboardView.vue:252,253 | 可删 | 无点击处理，纯假可供性 |
| `--shadow-focus` 上的 `rgba(...)` 低透明度 | apps/web/src/style.css:53；apps/web/src/utils/theme.ts:26 | 可删 | 该 token 的存在使焦点环停在 1.33:1，直接删掉改用实心色 |

## 提案（≤5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 下沉 | apps/web/src/style.css:53 + apps/web/src/utils/theme.ts:26 | 少一次误操作 | 焦点环改实心 `var(--blue-600)`（1.33:1 → 5.17:1）。代价：浅/深两处 token 必须同时改，且所有原生按钮、链接、input 的焦点外观会明显变重，需视觉回归一遍；另外 `responsive-enhancements.css:286-292` 的 outline 方案要一并合并，否则两套并存继续分叉 |
| 下沉 | apps/web/src/style.css:682,700 | 少一次误操作 | 删掉 `background:#ffffff !important` 改 `var(--bg-panel)`。代价：这两条 `!important` 原本是为了压 Element Plus 默认底色，改动后会与 EP 的 `--el-fill-color-blank` 交互，需确认浅色下输入框仍是纯白（否则浅色观感回退）；且影响全站每个表单 |
| 删除 | apps/web/src/style.css:806-815 | 少一次判断 | 通配符减动效改为显式白名单，保留加载旋转。代价：必须逐个列出要禁的过渡属性，遗漏项会继续动；同时要确认保留 `animation` 不会让 `el-loading` 的 `scale(1.2)`（responsive-enhancements.css:299-301）在减动效下产生位移感 |
| 合并 | apps/web/src/styles/responsive-enhancements.css:33-40 | 少一次误操作 | 把 `.action-chip`/`.text-action-btn`/`.smart-ask-preset`/`.toolbar-button`/`.link-button` 并入触摸目标 `min-height: 44px` 列表。代价：移动端工具栏与聊天头部纵向变高，首屏可见内容减少；`.text-action-btn` 从 16px 涨到 44px 后消息尾部间距会明显变大，需要重新排版 |
| 删除 | apps/web/src/views/platform/CostDashboardView.vue:252,253 + :254 | 少一次误操作 | 删掉 `.daily-bar` 的 `cursor:pointer` 与 `:hover`，并把 `.daily-label` 的 9px + `rotate(-45deg)` 改成 `var(--text-caption)` 水平排布。代价：柱状图失去 hover 高亮的可探索感，且水平标签在 14 根柱子下可能重叠，需要减少展示天数或改用稀疏刻度 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| HIGH | 无障碍 | apps/web/src/style.css:812 | `animation-iteration-count: 1 !important` 连带停掉 `.el-icon.is-loading` 的 `rotating` 关键帧，17 处加载指示器在减动效下静止，丢掉"仍在进行"这一状态指示 | 改为显式白名单；旋转类动画保留（可降速至 3s），只对 `transition` 的位移/缩放做清零 |
| MEDIUM | 性能 / 缓动与时长 | apps/web/src/views/platform/CostDashboardView.vue:223 | `transition: width 0.5s` 动布局属性 `width`，且 500ms 超过 UI 动效 <300ms 上限；同类 :246 `.scene-bar { transition: width 0.5s }`、:252 `.daily-bar { transition: height 0.3s }`，三者都未用 `--transition-*` token | 改 `transform: scaleX()` + `transform-origin: left`，时长落到 200ms，用 `--transition-base` |
| MEDIUM | 一致性与 token / 可打断性 | apps/web/src/styles/theme-extras.css:133 | `.page-enter-active { transition: opacity 0.25s ease, transform 0.25s ease }` 使用 CSS 预设曲线 `ease`（规则明令禁止预设曲线）；`apps/web/src/style.css:175` 的 `.skip-link { transition: transform 0.22s ease }` 同一问题；两者都绕过了 `--transition-*` token | 改用 `--transition-smooth` 或 `cubic-bezier(0.23,1,0.32,1)` |
| MEDIUM | 物理性与原点 | apps/web/src/views/kb/KBDocumentView.vue:1264,1268 | `.smart-ask-preset` 的 transition 同时含 `transform`，`:hover` 用 `translateY(-1px)` 位移；该位移未包在 `@media (hover:hover) and (pointer:fine)` 内，触屏会粘滞残留 | 位移规则包进 `@media (hover:hover) and (pointer:fine)`；transition 收敛为 `transform`+`border-color` |

## 存疑

- **焦点环的判定等级**：1.33:1 一定不合格，但"焦点指示器属不属于 AA 的 1.4.11 非文本对比度"存在解释分歧；WCAG 2.2 中明确要求 3:1 的是 2.4.13 Focus Appearance（AAA）。需要产品确认守到 AA 还是 AAA，再决定改动幅度。
- **深色模式的承诺范围**：V8–V13 全部只在用户切到深色时成立。若产品只承诺浅色为正式主题，这 6 条可整体降级。需要人确认主题支持策略。
- **行高的实际取值**：`.action-chip`(≈28-31px)、`.smart-ask-preset`(≈32-34px)、`.toolbar-button`(≈33-36px)、`.text-action-btn`(≈16px) 的高度是按 `padding + border + font-size` 估算，实际取决于继承的 `line-height`。需在浏览器 DevTools 量取确认后再决定是否必须提到 44px。
- **`--bg-panel-muted` 作为实际渲染底色**：el-table 表头（theme-extras.css:94）与条带行的 `4.34:1` 是按变量值推算；`--el-table-header-bg-color` 在深色模式下没有对应覆盖，深色实测底色需浏览器取色确认。
- **`MainLayout.vue:111` 抽屉的可访问名称**：静态阅读显示 `aria-labelledby` 悬空，但需用 NVDA/VoiceOver 实测确认 Element Plus 是否在别处补了 `aria-label`。
- **减动效静止后的影响程度**：取决于每处加载图标旁边有没有文字兜底。`KBOperationsView.vue:31` 有文字，多数 `:size="32"` 的纯图标处没有——需逐处确认后再定优先级。
- **`.daily-bar` 是否真无点击**：`:138` 模板确无 `@click`，但父层或全局事件委托可能有；需运行时点击验证。
- **`.el-loading-spinner { transform: scale(1.2) }`（responsive-enhancements.css:299-301）在减动效下的残留**：`transition-duration:.01ms` 不影响静态 `transform`，该 `scale` 会一直生效。是否属预期需要确认。
- **未覆盖项**：`*.test.ts` 按任务要求排除；`apps/web/src/directives/ripple.ts` 零使用与 `style.css:182-483` 装饰类零使用属全局已确认问题，未重复报告。
- **本报告未运行构建或浏览器渲染**，全部结论来自静态阅读；行号基于当前工作区版本（`element-plus@^2.13.3`、`vue@^3.5.25`）。

### 对比度计算口径

WCAG 2.x 相对亮度公式，sRGB 线性化后取 `0.2126R + 0.7152G + 0.0722B`，比值 = `(L_hi + 0.05) / (L_lo + 0.05)`。
半透明色按 alpha 合成到背景后再计算。关键结果：

| 前景 | 背景 | 比值 | AA 4.5:1 |
|---|---|---|---|
| `--slate-600` #64748b | `--bg-panel` #ffffff | 4.76 | 通过 |
| #64748b | `--bg-page` #f8fafc | 4.55 | 勉强通过 |
| #64748b | `--bg-panel-muted` #f1f5f9 | **4.34** | **不通过** |
| #64748b | `#f5f9ff` | 4.50 | 临界 |
| `--slate-500` #94a3b8 | #ffffff | **2.56** | **不通过** |
| #94a3b8 | `#f9f9fb` | **2.44** | **不通过** |
| #94a3b8（深色 `--text-muted`） | 深色 `--bg-panel` #131b2e | 6.69 | 通过 |
| 深色 `--text-regular` #cbd5e1 | #ffffff | **1.49** | **不通过** |
| 深色 `--text-primary` #f1f5f9 | #ffffff | **1.10** | **不通过** |
| 深色 `--text-primary` #f1f5f9 | `#fff5f5` | **1.02** | **不通过** |
| `--blue-500` #3b82f6 | #ffffff | **3.68** | **不通过** |
| `--blue-600` #2563eb | #ffffff | 5.17 | 通过 |
| #059669 | #ecfdf5 | **3.58** | **不通过** |
| #275dad | #f5f9ff | 6.11 | 通过 |
| #64748b @ opacity .6 合成 #A2ACB9 | #ffffff | **2.30** | **不通过** |
| `--shadow-focus` 合成 #D3E0FB | #ffffff | **1.33** | 远低于 3:1 |
| 深色 `--shadow-focus` 合成 #213F74 | #131b2e | **1.66** | 远低于 3:1 |
| #92400e | #fffbeb | 6.84 | 通过（安全告警） |
| #b45309 | #fffbeb | 4.84 | 通过（安全告警） |
