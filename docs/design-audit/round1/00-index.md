# 第一轮审计 · 索引与全局层

> 范围：`apps/web` 全部 23 个用户可见面（壳层 1 / 认证 4 / 业务 8 / 平台 9 / 共享组件 1 / 跨界面扫描 2）。
> 状态：第一轮只输出结论，**未修改任何源码**。第二轮待 Owner 确认提案后执行。
> 报告：本目录 23 份（21 个界面审计 + 2 个跨界面扫描），全部完成。

## 1. 定量

| 指标 | 数量 |
|---|---|
| 已标注元素 | 897（必要 452 / 可合并 140 / 可下沉 84 / 可删 221） |
| 提案 | 120（删除 56 / 合并 21 / 下沉 9 / 降层级 5 / 加反馈 29） |
| 动效发现 | 133（HIGH 26 / MEDIUM 62 / LOW 45） |
| 存疑条目 | 195（多为「需实际渲染 / 需真机 / 需后端确认」） |

读法：**可删 + 可合并 + 可下沉 = 445 项，占已标注元素的 49.6%**。这些页面的主要问题不是"元素太少"，而是每个页面都在重造同一批零件，并且随手引入了未被定义的样式值。必要元素仍有 452 项，说明大部分界面骨架是合理的，问题是密度与重复，不是方向。

## 2. 全局层（跨界面重复出现，已逐一在 file:line 上核对）

以下 7 条在多个界面独立复现（或跨界面同源），属同一 root cause，按界面逐个改是浪费——应在全局层一次性解决。

### G1 引用了不存在的 CSS 变量（静默失效）
- `var(--blue-400)`：**10 处使用、0 处定义**，分布在 6 个文件（`views/chat/UnifiedChatView.vue:336`、`views/platform/AgentMonitorView.vue:428,517`、`AgentProfileView.vue:247`、`CostDashboardView.vue:205,223,246,252`、`SceneManagerView.vue:200`、`ToolManagerView.vue:247`）。同样的写法在 `apps/web/src/styles/theme-extras.css:200-208` 里另有 4 处。
- `var(--bg-body)`：2 处使用 0 处定义（`views/kb/KBChunkReviewView.vue:265`、`views/platform/PromptTemplateView.vue:259`）。
- `var(--success-color) / --danger-color / --warning-color / --warning-bg`：以 `var(--x, #e6a23c)` 形式硬编码 Element Plus 默认色，6 文件 22 处（`EntryView.vue` 最多）。
- `var(--color-primary)`：**全仓 0 处定义**（实测 `--color-primary:` 在 `apps/web/src` 下无匹配），`views/kb/KBConnectorsView.vue:461` 的 `color-mix()` 因此实际解析为透明。
- `--color-scheme`（`utils/theme.ts:13,39`）：全仓无消费者，真正生效的是 `style.css:2` 写死的 `color-scheme: light`。
- **后果**：这些属性的计算值无效 → 退化为 `unset`/`currentColor`，视觉上表现为"颜色莫名其妙"，且不报错、不被构建发现。

### G2 Theme 亮/暗两套变量不对称
- `utils/theme.ts` 的 `darkThemeVars` 有 23 个键，`lightThemeVars` 只有 18 个：`--blue-500/600/700/50`、`--ink-900` 只在暗色侧定义。
- **后果**：暗→亮切换后，这几个变量残留暗色值（`--blue-600` 被引用 52 次、`--blue-50` 12 次），亮色模式下的图片/背景/边框拿到暗色值。
- 未覆盖的 5 个键：`--success-color`、`--danger-color`、`--warning-color`、`--warning-bg`、`--scrollbar-thumb`。

### G3 装饰性 hover 动效穿透 17+ 界面
- `components/EnhancedEmpty.vue:108,111-113`：纯装饰插图（无交互监听）挂 `transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1)` + `:hover { transform: scale(1.05) rotate(2deg) }`。
- 该组件被 **17 个界面 / 28 个调用点**（实测 `<EnhancedEmpty` 出现次数）渲染：EntryView / AuditView / KBDocumentView / KBConnectorsView / CostDashboardView / AgentMonitorView / MemoryManagerView / ToolManagerView / PromptTemplateView …
- 违反 3 条规则：装饰元素不该动、0.3s 触上限、过冲曲线未被列入允许曲线；且未包 `@media (hover:hover) and (pointer:fine)`。
- **修法（一步覆盖 17+ 界面）**：删 `EnhancedEmpty.vue:108` 的 transition 与 `:111-113` 的 hover 块。

### G4 `prefers-reduced-motion` 全局清零把 spinner 也冻住了
- `style.css:806-815` 用通配符 `*` 把 `animation-duration: 0.01ms !important` 应用到所有元素，包含 Element Plus 的 `.is-loading` 旋转。
- 全仓 17 处手写 `<el-icon class="is-loading">` 加载块（`RetrievalDebuggerView.vue:50`、`EntryView.vue:22`、`KBDocumentView.vue:25,336`、`AgentMonitorView.vue:49,97`、`CostDashboardView.vue:39`、`ModelProviderView.vue:139`、`ToolManagerView.vue:40`、`ChatTraceDrawer.vue:98` 等）。
- **后果**：减动效用户看到的是"卡住的图标"，比不做减动效更糟——这是把可访问性偏好实现成了功能缺陷。
- 另：17 处 `transition: all`（含 `style.css:658,682,700`）同样被通配符清零，过渡被整体移除而非替换。

### G5 同一批零件在各界面各写一遍
| 零件 | 复制情况 | 样张 |
|---|---|---|
| 手写加载块 | 15 个文件逐份复制，无延迟显示/最短显示策略 | `RetrievalDebuggerView.vue:50`、`EntryView.vue:22`、`ChatTraceDrawer.vue:98` |
| 指标数字块 | 13 处 / 12 个文件，命名各异、字号 22-32px 各不相同 | `KBGovernanceView.vue:919(28px)`、`CostDashboardView.vue:206-207(22/26px)`、`AbExperimentView.vue:193(24px)`、`ToolManagerView.vue:207(24px)` |
| 基础卡片容器 | 约 19 个界面各写一遍 border+radius+bg+padding | `KBOperationsView.vue:404-412`、`EntryView.vue:470`、`CitationList.vue:260`、`CostDashboardView.vue:219` |
| 空状态 | 共享组件 `EnhancedEmpty` 已覆盖 17 个界面，仍有 4 个界面自建 | 自建：`KBOperationsView.vue:89,123,172,210`、`EntryView.vue:74,114,204,222,235,247`、`KBGovernanceView.vue:218`、`AgentProfileView.vue:46` |
| 裸 JSON 调试块 | 8 处把后端原始结构 `JSON.stringify` 直接进 `<pre>`，类名各自为政 | `AuditView.vue:73`、`KBGovernanceView.vue:447`、`KBOperationsView.vue:222`、`DocumentEvents.vue:47`、`ChatTraceDrawer.vue:81,84,87`、`KBDocumentView.vue:242`、`InstructionMarketView.vue:61` |
| 失败提示 | 请求层拦截器统一 toast ＋ 各视图 catch 再弹一次，同一次失败两条文案 | `api/request.ts:151-161`；实例 `InterviewView.vue:125` |

**注（数字为我实测，非审计员转述）**：`apps/web/src` 下 331 条 `font-size` 声明中 **266 条是裸 `px` 值**（未走 4 级 `--text-*` 刻度；其中 `views/` 单独统计为 259 条 / 238 条裸值）；硬编码六位十六进制色值分布在 **18 个 `.vue` 文件、共 102 处**，形成 `#f5f9ff / #275dad / #ecfdf5 / #059669` 这类与 token 并行的第二套色板。

### G6 导航：路由有、入口无、高亮错
- `router/index.ts:216-347` 注册了 12 条 `platform/*` 路由（monitor、tools、memory、cost、scenes、cache、apikeys、webhooks、pii、market、experiments、orchestration），侧栏 12 项里**没有它们**——页面实现完整但零用户入口。
- `MainLayout.vue:303-306`：`activeNavPath` 精确匹配失败即兜底返回 `/workspace/entry`，导致文档详情、切片管理、无权限页以及上述 12 条路由全部把「业务总览」错高亮成当前页。
- 同屏双 `h1`：`MainLayout.vue:92`（顶栏）与 `PageHeaderCompact.vue:4`（**25 个调用点全部渲染标题**，实测），其中 6 组名称还不一致。

### 附：全局死代码（我自己扫的，非审计员报告）
| 对象 | 规模 | 证据 |
|---|---|---|
| 死 CSS 规则 | **127 条 / 559 行** | `style.css` 66 条/333 行；`styles/responsive-enhancements.css` 60 条/220 行；`styles/theme-extras.css` 1 条/6 行 |
| 装饰类家族 | 零使用 | `style.css:182-483`（`.page-hero/.hero-*/.insight-*/.metric-card/.surface-card/.page-grid-*` 等） |
| 入场动画类 | 零引用 | `.slide-in-*/.scale-in-*/.stagger-item/.shimmer` |
| Tailwind 残留 | 零引用 | `.animate-pulse/.animate-bounce/.animate-spin` |
| `ripple` 指令 | 注册但零使用 | `main.ts:21` + `directives/ripple.ts` |
| Element Plus 注册未用 | 8 / 50 | `el-aside/el-container/el-empty/el-link/el-main/el-menu/el-menu-item/el-upload`；`v-loading` 指令零使用 |
| `!important` | 124 处 | theme-extras 52 / responsive 42 / style.css 19 / 其余零星 |
| 全局 helper 类 | 零使用 | `.custom-form-error`、`mark.highlight` |

### G7 做完了、但用户在 Web 里用不到（产出无处消费）
这是同一个产品级断点，散在三处，应由 Owner 一次裁决：

| 产出 | 现状 | 证据（实测） |
|---|---|---|
| 12 个平台配置页 | 页面完整、路由齐备，但**全仓无任何导航指向它们**（既无 `router-link`、也无 `router.push`、也无 `name:` 跳转） | 这 12 个视图组件名在 `apps/web/src` 下**只出现在 `router/index.ts`** 的 24 行里（12 个 `path` + 12 个 `name`），`path` 区间 `router/index.ts:216-347` |
| Agent 工作台产出的智能体 | 能建、能配，但问答侧不认：`buildScope()` 只发 `mode / corpus_ids / document_ids / allow_common_knowledge` | `apps/web/src/store/chat.ts:62-69`（无 `agent_profile_id`）；Web 端无选择入口，只有 SDK 用得上（`sdk/python/rag_qa_client/client.py:77`） |
| Prompt 库产出的模板 | 同上，`prompt_template_id` 同样未进 scope；且 `applyPromptTemplate` 打向一个不存在的后端路由 | `apps/web/src/store/chat.ts:62-69`；`apps/web/src/api/platform.ts:376` → `POST /platform/prompt-templates/{id}/apply`，全仓（前端 + api-gateway）**仅此一处**出现，无对应路由 |

**判断**：这三处加起来涉及 14 个页面的用户价值。要么补入口把能力接上，要么下线页面——继续维持"页面在、能力不通"是纯负债。

### 附：用户直接可见的文案缺陷（修复成本极低，建议先修）

`views/kb/KBGovernanceView.vue` 的低置信区域列表有 **6 处 GBK 乱码**（文件已是 UTF-8，乱码已固化在源码里，其中 2 处还丢了 1 个字节）：

| 行 | 当前显示 | 应为 |
|---|---|---|
| `:297` | `鍖哄煙` | 区域 |
| `:299` | `椤电爜` | 页码 |
| `:302` | `缃俊搴?` | 置信度 |
| `:304` | `鍧愭爣` | 坐标 |
| `:306` | `鏃犳憳瑕?` | 无摘要 |
| `:308` | `瀹氫綅` | 定位 |

另需确认后端返回的 `region_label` 本身是否已是乱码——若数据源就坏，只改前端文案不够。

## 3. 需单独确认的信息架构变更（不包含在任何提案内）

按规则，信息架构改动必须单独提出、单独确认：

1. **12 条 `platform/*` 路由的入口**：要么补 1 个聚合入口（偿还物 = 侧栏「当前页」块 + 面包屑行），要么下线这 12 页能力。
2. **`PageHeaderCompact` 的 `title` 归属**：删视图层 h1（改 24 个调用点）还是删外壳层 h1（改 1 处，但顶栏只剩面包屑 + 主题按钮）。
3. **`.chat-workspace` 的第三栏**：`responsive-enhancements.css:110-112,201-203,225-227` 为它定义了 grid 列（280/1fr/320、360/1fr/420），但该元素是 flex 容器，声明无效——是恢复常驻轨迹面板，还是删掉这些声明。
4. **`executionMode='agent'` 是否还有用户**：唯一入口 `ChatHeader.vue:102-119`，删除后 Agent 模式从 UI 不可达。
5. **登录后默认落点**：`LoginView.vue:140-141` 落 `/workspace/entry`，而 `/` 重定向到需要 `chat.use` 的 `/workspace/chat`；无 `chat.use` 的账号直接访问裸域名会首屏撞无权限页。

## 4. 第一轮未做的事

- 未启动前端、未跑测试、未渲染任何页面：所有"观感/对比度/折行/滚动"结论都标了待验证。
- 未读后端大部分写入路径：涉及"删掉这个输入框会不会断链"的判断都列进各报告的「存疑」。
- 未修改任何源码、未删任何代码、未动任何配置文件。
