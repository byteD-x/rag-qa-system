# 01 工作台外壳（侧边栏 + 顶栏 + 页面过渡 + 应用入口）

## 唯一用户任务

已登录的内部成员（平台管理员 / 知识库管理员 / 知识库编辑者 / 知识库只读 / 审计查看者，角色枚举见 apps/web/src/store/auth.ts:38-47）在登录后进入工作台的场景下，要在最短路径内到达他有权限使用的那个功能页，并随时确认自己当前在哪一页。

## 完成该任务的必要步骤

1. 登录后落到默认首页 `/workspace/entry`（apps/web/src/views/LoginView.vue:140-141；从深链进入则回跳原页，apps/web/src/router/index.ts:383-385）→ **keep**
2. 读顶栏标题确认落点（apps/web/src/layouts/MainLayout.vue:92）→ **merge**（同屏另有同值副本两处：apps/web/src/layouts/MainLayout.vue:19、apps/web/src/layouts/MainLayout.vue:83-91）
3. 在侧栏 11 项主导航 + 1 项审计日志里找到目标功能（apps/web/src/layouts/MainLayout.vue:23-54，数据与权限 apps/web/src/layouts/MainLayout.vue:209-301）→ **keep**（另有 12 条已注册路由完全没有入口，见提案 5）
4. 点击导航项，等内容交换（apps/web/src/layouts/MainLayout.vue:101-107）→ **drop**（`mode="out-in"` 使旧页先淡出 250ms，期间内容区空白且无任何加载指示）
5. 进入深层路由（如 `/workspace/kb/documents/:id`）后确认侧栏高亮（apps/web/src/layouts/MainLayout.vue:303-306）→ **merge**（无匹配项时兜底高亮「业务总览」，是错的）
6. 需要时切换主题（apps/web/src/layouts/MainLayout.vue:96-98 → apps/web/src/components/ThemeToggle.vue:1-31）→ **keep**（罕见频次，可保留浮层动效）
7. 视口 <1100px 时用顶栏按钮打开抽屉再选导航（apps/web/src/layouts/MainLayout.vue:78-80、apps/web/src/layouts/MainLayout.vue:697-724）→ **keep**
8. 结束时退出登录（apps/web/src/layouts/MainLayout.vue:66-69，处理逻辑 apps/web/src/layouts/MainLayout.vue:327-331）→ **keep**

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| skip-link「跳到主内容」 | apps/web/src/layouts/MainLayout.vue:3 | 必要 | 键盘用户跳过 12 项侧栏导航的唯一入口（样式 apps/web/src/style.css:164-180） |
| 侧栏品牌块（logo + 产品名） | apps/web/src/layouts/MainLayout.vue:7-15 | 必要 | 唯一标识当前系统；位置由侧栏固定宽度决定（apps/web/src/layouts/MainLayout.vue:343-354） |
| 品牌副标题「企业知识中台」 | apps/web/src/layouts/MainLayout.vue:12 | 可删 | 与紧邻的 h2「RAG-QA 2.0」（apps/web/src/layouts/MainLayout.vue:13）表达同一件事，抽屉内还复制一次（apps/web/src/layouts/MainLayout.vue:125） |
| 「当前页」块 | apps/web/src/layouts/MainLayout.vue:17-20 | 可删 | 与顶栏 h1（apps/web/src/layouts/MainLayout.vue:92）、面包屑尾项（apps/web/src/layouts/MainLayout.vue:83-91）同值同屏出现三次 |
| 主导航列表（11 项） | apps/web/src/layouts/MainLayout.vue:23-38 | 必要 | 唯一全局导航；导航数据 apps/web/src/layouts/MainLayout.vue:209-265，权限过滤 apps/web/src/layouts/MainLayout.vue:267-289 |
| 导航分隔线 | apps/web/src/layouts/MainLayout.vue:39 | 可删 | 只分隔一个成员（审计日志 apps/web/src/layouts/MainLayout.vue:40-54），分类不含信息量 |
| 审计日志导航项（次级样式） | apps/web/src/layouts/MainLayout.vue:40-54 | 可合并 | 与主列表同构，却为单条目引入一套次级层级（样式 apps/web/src/layouts/MainLayout.vue:482-488）；入口不能删，它是 audit.read 用户的唯一入口（apps/web/src/layouts/MainLayout.vue:291-295） |
| 账号卡（头像 + 邮箱 + 角色） | apps/web/src/layouts/MainLayout.vue:58-64 | 必要 | 退出前的身份确认；数据来源 apps/web/src/store/auth.ts:34-47 |
| 退出登录按钮 | apps/web/src/layouts/MainLayout.vue:66-69 | 必要 | 唯一会话出口（apps/web/src/layouts/MainLayout.vue:327-331） |
| 移动端导航按钮 | apps/web/src/layouts/MainLayout.vue:78-80 | 必要 | <1100px 侧栏 `display:none`（apps/web/src/layouts/MainLayout.vue:697-724）后唯一入口 |
| 面包屑行 | apps/web/src/layouts/MainLayout.vue:83-91 | 可合并 | 尾项恒等于顶栏 h1；整行不可点击（apps/web/src/layouts/MainLayout.vue:84-90 是纯 span），祖先链只在深度≥3 时有信息量（apps/web/src/router/index.ts:169、apps/web/src/router/index.ts:180） |
| 顶栏 h1 页面标题 | apps/web/src/layouts/MainLayout.vue:92 | 必要 | 页面唯一权威标题，也是 document.title 的来源（apps/web/src/router/index.ts:403-406） |
| 主题切换按钮 + 三选项菜单 | apps/web/src/layouts/MainLayout.vue:96-98 | 必要 | 顶栏唯一全局偏好；含「跟随系统」（apps/web/src/components/ThemeToggle.vue:40-56） |
| 内容容器 main + router-view | apps/web/src/layouts/MainLayout.vue:101-107 | 必要 | 所有工作台页面的挂载点，也是 skip-link 的目标（apps/web/src/layouts/MainLayout.vue:3） |
| 页面切换过渡 `page` | apps/web/src/layouts/MainLayout.vue:103 | 可删 | `mode="out-in"` 串行两段 250ms，离开阶段无任何内容（apps/web/src/styles/theme-extras.css:131-144） |
| 抽屉品牌块（复制） | apps/web/src/layouts/MainLayout.vue:120-128 | 可合并 | 与 apps/web/src/layouts/MainLayout.vue:7-15 同构，两处维护 |
| 抽屉导航列表 | apps/web/src/layouts/MainLayout.vue:130-163 | 可合并 | 与 apps/web/src/layouts/MainLayout.vue:22-55 完全重复，漏改会造成移动端与桌面端导航不一致 |
| 抽屉账号卡 + 退出登录 | apps/web/src/layouts/MainLayout.vue:165-178 | 可合并 | 与 apps/web/src/layouts/MainLayout.vue:57-70 重复 |
| 抽屉容器 | apps/web/src/layouts/MainLayout.vue:111-118 | 必要 | <1100px 唯一导航容器；路由变化自动关闭（apps/web/src/layouts/MainLayout.vue:316-321） |
| 抽屉 class 钩子 `mobile-drawer` | apps/web/src/layouts/MainLayout.vue:117 | 可删 | 全仓无对应样式规则（仅模板自身与 apps/web/src/layouts/MainLayout.vue:627-632 的 `.drawer-content`） |
| el-config-provider 包装 | apps/web/src/App.vue:2 | 可删 | 未传任何 prop，locale/size/zIndex 全是默认值，等价于不加 |
| 顶层 fade-transform 过渡 | apps/web/src/App.vue:4 | 可删 | 只在登录↔工作台换壳时触发；0.35s + 16px 位移 + scale(0.98)（apps/web/src/style.css:485-498） |
| initTheme 主题初始化 | apps/web/src/main.ts:9、apps/web/src/main.ts:19 | 必要 | 深色变量与 data-theme 的唯一入口（apps/web/src/utils/theme.ts:97-108） |
| initShortcuts 快捷键监听 | apps/web/src/main.ts:10、apps/web/src/main.ts:20 | 可删 | 只装了一个 keydown 监听（apps/web/src/utils/shortcuts.ts:133-137），注册函数 registerCommonShortcuts / useShortcuts（apps/web/src/utils/shortcuts.ts:142、apps/web/src/utils/shortcuts.ts:197）全仓无调用，等于零快捷键 |
| elementComponents 全量注册 | apps/web/src/main.ts:13、apps/web/src/main.ts:27-31 | 必要 | apps/web/src/App.vue:2 的 `<el-config-provider>` 依赖它（apps/web/src/element-plus-components.ts:11、apps/web/src/element-plus-components.ts:64） |
| EnhancedEmpty 全局注册 | apps/web/src/main.ts:14、apps/web/src/main.ts:33 | 可删 | 18 处使用全部本地 import（如 apps/web/src/views/EntryView.vue:340、apps/web/src/views/AuditView.vue:83） |
| ThemeToggle 全局注册 | apps/web/src/main.ts:15、apps/web/src/main.ts:34 | 可删 | 唯一使用点已本地 import（apps/web/src/layouts/MainLayout.vue:202） |
| v-loading 指令注册 | apps/web/src/main.ts:12、apps/web/src/main.ts:25 | 必要 | 3 处使用：apps/web/src/views/platform/AgentOrchestrationView.vue:33、apps/web/src/views/platform/ApiKeyManagerView.vue:30、apps/web/src/views/platform/WebhookManagerView.vue:12；但这 3 页当前无任何入口（见提案 5） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/layouts/MainLayout.vue:92 与 apps/web/src/components/PageHeaderCompact.vue:4 | 少一次判断 | 24 个视图各自渲染一个 `<h1>`（apps/web/src/views/EntryView.vue:4、apps/web/src/views/AuditView.vue:3、apps/web/src/views/kb/KBGovernanceView.vue:3 等），外壳顶栏又渲染一个（apps/web/src/layouts/MainLayout.vue:92），同屏两个一级标题；其中 6 组名称还不一致：apps/web/src/router/index.ts:189「Agent 工作台」vs apps/web/src/views/platform/AgentProfileView.vue:3「Agent 智能体市场」，apps/web/src/router/index.ts:200 vs apps/web/src/views/platform/PromptTemplateView.vue:3，apps/web/src/router/index.ts:135 vs apps/web/src/views/kb/KBOperationsView.vue:3，apps/web/src/router/index.ts:146 vs apps/web/src/views/kb/RetrievalDebuggerView.vue:3，apps/web/src/router/index.ts:124 vs apps/web/src/views/kb/KBConnectorsView.vue:3，apps/web/src/router/index.ts:310 vs apps/web/src/router/index.ts:312。风险：PageHeaderCompact 的 title 在 3 处承担「当前对象名」（apps/web/src/views/kb/KBUploadView.vue:3、apps/web/src/views/kb/KBDocumentView.vue:3、apps/web/src/views/kb/KBChunkReviewView.vue:3），不能直接删 prop，需改挂到已有 subtitle（apps/web/src/components/PageHeaderCompact.vue:5-7）；改动落在被 24 个界面共用的组件上，超出本界面范围，需与各界面负责人协调；无测试断言该 h1（apps/web/src/components/PageHeaderCompact.test.ts:7-16 只断言 subtitle），回归不会被自动发现 |
| 删除 | apps/web/src/layouts/MainLayout.vue:303-306 | 少一次判断 | `activeNavPath` 在未匹配到任何导航项时兜底返回 `/workspace/entry`（该值是字面量而非「无匹配」），凡是路径不以任一导航项开头的路由都会把「业务总览」错高亮成当前页：文档详情与切片管理（apps/web/src/router/index.ts:162、apps/web/src/router/index.ts:173，入口见 apps/web/src/views/kb/KBGovernanceView.vue:814、apps/web/src/views/kb/KBUploadView.vue:637、apps/web/src/views/kb/KBOperationsView.vue:112）、无权限页（apps/web/src/router/index.ts:65）、以及 12 条未入导航的 platform/* 路由（apps/web/src/router/index.ts:216-347）。风险：需要为这些深层路由声明所属导航项（在 apps/web/src/router/index.ts 补 meta 或改匹配规则），漏声明的后果是「无高亮」而非「错高亮」；若同时执行提案 5，需要维护的映射只剩下文档详情/切片管理/无权限 3 条；apps/web/src 下不存在覆盖 MainLayout 的测试，只能人工回归 |
| 删除 | apps/web/src/layouts/MainLayout.vue:103 与 apps/web/src/styles/theme-extras.css:131-144 | 少一次判断 | 每次工作台内导航先播旧页 250ms 淡出（内容区空白、无加载指示）再播新页 250ms 淡入，规则要求数十次/天的切换「极简或砍掉」。风险：失去页面切换的连续性提示，长列表页可能出现内容突然整屏替换的观感（靠 h1 标题变化补偿）；需人工回归 30+ 路由；若产品坚持保留过渡，退路是删掉 `mode="out-in"` 并只留 opacity（≤150ms），不要用 spinner 补偿 |
| 删除 | apps/web/src/layouts/MainLayout.vue:17-20 与 apps/web/src/layouts/MainLayout.vue:83-91 | 少一次判断 | routeTitle 同屏出现三次（apps/web/src/layouts/MainLayout.vue:19 侧栏「当前页」、apps/web/src/layouts/MainLayout.vue:89 面包屑尾项、apps/web/src/layouts/MainLayout.vue:92 顶栏 h1），且面包屑整行不可点击、无法用于跳转（apps/web/src/layouts/MainLayout.vue:84-90）。风险：深度≥3 的页面（apps/web/src/router/index.ts:169、apps/web/src/router/index.ts:180）会失去「所属分区」的文字线索，需要侧栏高亮准确来补偿，因此提案 2 必须先落地；删除后侧栏顶部少一块内容，纵向节奏只能靠 apps/web/src/layouts/MainLayout.vue:356-363 的 `gap:16px` 维持；相关 scoped 样式需连带删除（apps/web/src/layouts/MainLayout.vue:418-438、apps/web/src/layouts/MainLayout.vue:586-608） |
| 删除 | apps/web/src/router/index.ts:216-347 | 少一次判断 | 12 条已注册路由全仓零入口：`platform/monitor`、`platform/tools`、`platform/memory`、`platform/cost`、`platform/scenes`、`platform/cache`、`platform/apikeys`、`platform/webhooks`、`platform/pii`、`platform/market`、`platform/experiments`、`platform/orchestration`。模板与脚本中不存在任何指向它们的 `router.push` / `router-link`（仓库内检索这些路径无命中），侧栏 12 项里也没有它们（apps/web/src/layouts/MainLayout.vue:209-301），其中 3 页还是 v-loading 指令的唯一使用点。风险：这些页面实现完整（如 apps/web/src/views/platform/AgentMonitorView.vue、apps/web/src/views/platform/CostDashboardView.vue），删路由等于让能力下线，属产品决策；若已有外部收藏或文档分享这些 URL，删除会 404；替代方案是补 1 个聚合入口，但新增元素必须偿还——偿还对象即本表第 4 条的「当前页」块与面包屑行 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 可打断性 | apps/web/src/layouts/MainLayout.vue:103 | 工作台内每次路由切换都跑 `mode="out-in"`：先 250ms 旧页淡出（内容区空白、无加载指示），再 250ms 新页淡入；这是数十次/天的操作，规则要求极简或砍掉，且离开阶段是纯等待 | 删除该过渡，或去掉 `mode="out-in"` 只留单段 opacity（≤150ms）；不要新增 spinner/骨架补偿 |
| HIGH | 缓动与时长 / 一致性与 token | apps/web/src/styles/theme-extras.css:133 | `transition: opacity 0.25s ease, transform 0.25s ease`：使用了被规则禁止的 CSS 预设曲线 `ease`，并给内容整块引入 6px 位移；时长与曲线都没走 `--transition-*` token（apps/web/src/style.css:1-84） | 删位移；若保留则曲线改 `cubic-bezier(0.23,1,0.32,1)`、时长 ≤200ms，并引用现有 transition token |
| MEDIUM | 缓动与时长 / 性能 | apps/web/src/style.css:485-498（由 apps/web/src/App.vue:4 触发） | 换壳过渡 0.35s 超出「UI 动效一律 <300ms」，入场同时位移 16px 与 scale(0.98)；触发点是登录↔工作台，属罕见频次，优先级低于页面过渡 | 只保留 opacity（≤200ms，曲线 0.23,1,0.32,1），去掉 16px 位移与缩放；不要动布局属性 |
| MEDIUM | 物理性与原点 / 目的与频次 | apps/web/src/components/ThemeToggle.vue:117-130 | icon-spin 入场从 `rotate(-180deg) scale(0.5)` 起（低于入场下限 scale(0.95)），时长 0.3s（未 <300ms），且 `mode="out-in"`（apps/web/src/components/ThemeToggle.vue:4）让一次换图标跑两段约 600ms；旋转与缩放不携带任何空间或状态信息，主题状态已由图标本身与菜单勾选（apps/web/src/components/ThemeToggle.vue:24-26）表达 | 删除旋转与缩放，只保留 opacity 交叉淡入（≤150ms）；或整段删除，图标直接切换 |
| MEDIUM | 缓动与时长 | apps/web/src/components/ThemeToggle.vue:96、apps/web/src/components/ThemeToggle.vue:106-108 | `.theme-toggle` 用 `transition: all 0.3s`，而 `:active` 是按压反馈，规则要求 100-160ms；按下后按钮要 300ms 才落到 scale(0.95)，手感滞后 | 拆分为 `transform 120ms` + `background/border-color var(--transition-fast)`，去掉 `transition: all` |
| LOW | 一致性与 token | apps/web/src/components/ThemeToggle.vue:96、apps/web/src/components/ThemeToggle.vue:119 | 曲线用 `cubic-bezier(0.4,0,0.2,1)`（Material 标准曲线），与项目要求的进入曲线 `cubic-bezier(0.23,1,0.32,1)` 不一致，属非预设但非本系统 token 的第三套曲线 | 统一到规则指定的进入曲线；若确要两套，必须写进 token（本次不新增 token，则统一为一套） |
| LOW | 无障碍 / 一致性与 token | apps/web/src/styles/responsive-enhancements.css:43-53 与 apps/web/src/components/ThemeToggle.vue:99-104 | 触屏兜底规则只覆盖 `.surface-card/.session-item/.nav-item` 的 hover 位移，漏掉 `.theme-toggle`（apps/web/src/components/ThemeToggle.vue:102 的 `translateY(-2px)`），触屏上主题按钮会粘在位移态；根因是 hover 位移未包在 `@media (hover:hover) and (pointer:fine)` 内（本界面特例） | 把 `.theme-toggle:hover` 的位移包进 `@media (hover:hover) and (pointer:fine)`，或直接把 hover 位移降级为纯颜色变化（少一次判断成本为零） |
| LOW | 一致性与 token | apps/web/src/style.css:164-180（元素在 apps/web/src/layouts/MainLayout.vue:3） | skip-link 用 `transform 0.22s ease`：预设曲线 + 非 token 时长；它是键盘用户进入工作台的第一个可聚焦元素 | 时长与曲线换成现有 token（`--transition-fast` 150ms 等）；隐藏方式保持 transform 可以，但不要用 `ease` 预设 |

## 存疑

- 「页面标题归外壳还是归页面」是产品取舍：两条路径都只保留一个 h1——删视图层 h1（apps/web/src/components/PageHeaderCompact.vue:4）或删外壳 h1（apps/web/src/layouts/MainLayout.vue:92）。若后者，需确认顶栏只剩面包屑 + 主题按钮后信息是否够用（apps/web/src/layouts/MainLayout.vue:83-98）。
- `/` 重定向到 `/workspace/chat`（apps/web/src/router/index.ts:6-8），而 chat 需要 `chat.use`（apps/web/src/router/index.ts:79）；登录后的默认落点却是 `/workspace/entry`（apps/web/src/views/LoginView.vue:140-141，entry 无权限要求 apps/web/src/router/index.ts:54-63）。是否存在无 `chat.use` 的账号取决于后端权限映射（角色枚举 apps/web/src/store/auth.ts:38-47，映射不在本仓库）：若存在，直接访问裸域名的用户首屏就会撞 `/workspace/forbidden`（apps/web/src/router/index.ts:394-400）。验证方法：用 kb_viewer 或 audit_viewer 账号访问 `/`。
- 移动抽屉无可见关闭控件（apps/web/src/layouts/MainLayout.vue:111-118，`:with-header="false"`），只能点遮罩或 Esc；且点击「当前页」对应项时 `route.fullPath` 不变，关闭抽屉的 watch（apps/web/src/layouts/MainLayout.vue:316-321）不触发，抽屉会留在原地。需在移动视口真机验证这两点。
- 宽度规则互相矛盾：`.workspace-main-frame` 是 `width: min(100%, 1540px)`（apps/web/src/layouts/MainLayout.vue:541），而 apps/web/src/styles/responsive-enhancements.css:221-223 在 `min-width: 1920px` 下写 `max-width: 1800px !important`——`max-width` 不会放大 `width`，1800px 从未生效。需产品确认目标最大宽度（1540 还是 1800）后二选一。
- 顶栏 `position: sticky` + `z-index: 6`（apps/web/src/layouts/MainLayout.vue:547-553）在 `.workspace-main-frame`/`.workspace-content` 都是 `overflow: hidden`（apps/web/src/layouts/MainLayout.vue:536-545、apps/web/src/layouts/MainLayout.vue:617-625）的情况下不参与滚动，属空转；删除前需确认没有子界面依赖这个层叠上下文。
- 深色模式的原生外观未跟随：`--color-scheme` 只被写成 CSS 变量（apps/web/src/utils/theme.ts:13、apps/web/src/utils/theme.ts:39），全仓没有 `var(--color-scheme)` 使用；真正生效的是写死的 `color-scheme: light`（apps/web/src/style.css:2）。深色模式下侧栏滚动区（apps/web/src/layouts/MainLayout.vue:361 的 `overflow: auto`）与原生控件仍是浅色。需在深色模式渲染确认。
- 本界面没有任何自动化测试兜底：apps/web/src 下不存在覆盖 MainLayout / App.vue / main.ts 的测试文件（现有测试集中在 views、components、api 与 element-plus-components.test.ts），上述所有改动只能人工回归。
- skip-link 的目标 `<main id="workspace-main-content">`（apps/web/src/layouts/MainLayout.vue:101）没有 `tabindex="-1"`，部分浏览器不把焦点落到主内容，键盘用户按 Tab 可能从链接自身继续。需 Chrome/Firefox/Safari 键盘实测。
