# 21 共享组件（页头/空状态/筛选栏/引用列表/文档事件/主题切换）

审计范围：apps/web/src/components/{PageHeaderCompact,EnhancedEmpty,FilterBarSticky,CitationList,DocumentEvents,ThemeToggle}.vue，跨页复用（无独立路由）。只读审计，未修改任何源码文件。

## 唯一用户任务

任一角色的用户 在 进入某个工作台页面并阅读一条问答回答 的场景下，要 一眼确认"这是哪一页、这一页现在能做什么"，并当场核对回答所依据的来源是否可信。

## 完成该任务的必要步骤

1. 确认"我在哪一页" — merge（同屏最多 3 处同值：侧栏「当前页」apps/web/src/layouts/MainLayout.vue:17-20、顶栏 h1 :92、页头 h1 apps/web/src/components/PageHeaderCompact.vue:4；已由 docs/design-audit/round1/01-shell.md 提案登记，本报告不重复提案）
2. 找到本页唯一主操作（页头 actions 槽）— keep
3. （有筛选项的页面）调整筛选条件，并在长列表滚动时保持可达 — keep
4. 无数据时判断"是真的没有 / 还是加载失败"，并知道下一步点哪里 — keep（但空态高度被 5 个调用点各自用 !important 改写，见元素清单，本报告未单列提案）
5. 在回答下方核对引用来源 — merge（默认折叠 + meta 行静默截断 + 摘要数字徽章，见提案 1、3、5）
6. 打开来源原文 — keep
7. 查看文档处理事件的时间线状态 — merge（同一状态被 icon / 流程词 / tag 表达三次，见提案 2）
8. 需要时切换主题 — keep

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页头标题 `<h1>` | apps/web/src/components/PageHeaderCompact.vue:4 | 可删 | 25 处调用里 13 处与 route.meta.title 完全同值（AuditView.vue:3 vs router/index.ts:354、ApiKeyManagerView.vue:3 vs :288 等），6 处是同义改写（KBConnectorsView.vue:3「多源数据同步」vs router/index.ts:124「多源同步」），只有 6 处承载文档/知识库名（KBDocumentView.vue:3 等） |
| 页头副标题（prop + 槽） | apps/web/src/components/PageHeaderCompact.vue:5-7, :49-57 | 可删 | 21 处调用里 19 处是页面自述文案（16 处静态 subtitle，如 AgentMonitorView.vue:3、ModelProviderView.vue:5、AbExperimentView.vue:3；3 处 #subtitle 槽，如 InterviewView.vue:4）；承载状态的只有 AuditView.vue:5-7（计数）与 KBOperationsView.vue:6（生成时间，与同槽位的自述句混排） |
| actions 槽 | apps/web/src/components/PageHeaderCompact.vue:9-11 | 必要 | 25 处调用中的唯一操作入口（EntryView.vue:5-16、KBOperationsView.vue:8-28） |
| `min-height: var(--page-header-compact, 56px)` | apps/web/src/components/PageHeaderCompact.vue:30 | 可删 | 单行标题的自然高度约 54px（:29 padding 14/16 + :42 字号 1.125rem×行高 1.3），min-height 只补约 1.6px；一旦有副标题（:49-57 margin-top 6px + 12px 行）就涨到约 78px，「compact 56px」的契约在 19 个页面上失效 |
| `margin-bottom: -1px` | apps/web/src/components/PageHeaderCompact.vue:33 | 可删 | 父级 `.page-shell` 是 `gap: 24px` 的 flex 列（apps/web/src/style.css:182-191），-1px 只把间距从 24 变成 23px，永远无法与下一条 border 合并 |
| 页头 border-bottom | apps/web/src/components/PageHeaderCompact.vue:32 | 可删 | 与筛选栏的 border-bottom 在同一视野内并存两条平行细线（AuditView 页面） |
| 72px 装饰插画容器 | apps/web/src/components/EnhancedEmpty.vue:99-113 | 可删 | 纯装饰、无交互监听；含 :93 的 24px 外边距共占约 96px 纵向空间，是空屏上最重的元素 |
| 基础内边距 `56px 28px` | apps/web/src/components/EnhancedEmpty.vue:88 | 可删 | 被 5 个调用点用 `!important` 覆写成 4 个不同值：EntryView.vue:656（32/16）、AuditView.vue:182（48/24）、DocumentEvents.vue:132（32/20）、KBDocumentView.vue:1322（32/20）、KBUploadView.vue:834（40/20） |
| `variant` 8 值枚举 | apps/web/src/components/EnhancedEmpty.vue:42, :52-61 | 可删 | 全仓只出现 document/folder/chat/search/default；upload/question/success 零引用；8 个值里 5 个图标同色 --blue-600（:69-75） |
| `imageSize` prop | apps/web/src/components/EnhancedEmpty.vue:45, :65 | 可删 | 零调用（唯一读点是 :65 自己） |
| `tips` 槽 + `.empty-tips` 样式 | apps/web/src/components/EnhancedEmpty.vue:21-23, :146-174 | 可删 | 零调用（含 :156-174 的 :deep 规则，共约 29 行死 CSS） |
| `illustration` 槽 | apps/web/src/components/EnhancedEmpty.vue:4 | 可删 | 零调用 |
| `.empty-title` 用 --text-h2 + 600 | apps/web/src/components/EnhancedEmpty.vue:122-128 | 可下沉 | 与页面标题同字号同字重（apps/web/src/components/PageHeaderCompact.vue:42），空状态标题与页面标题平级，空屏上没有主角 |
| sticky 容器 | apps/web/src/components/FilterBarSticky.vue:13-18 | 必要 | 审计页 6 个筛选条件 + 2 个按钮在长表格滚动时保持可达（AuditView.vue:11-31） |
| `backdrop-filter: blur(8px)` + 85% 半透明底 | apps/web/src/components/FilterBarSticky.vue:24-28 | 可删 | 底色已 85% 不透明（:25）；模糊只作用于滚过的那 15% 透出内容，却常驻一个合成层 |
| 筛选栏 border-bottom | apps/web/src/components/FilterBarSticky.vue:22 | 可删 | 与页头 border-bottom（PageHeaderCompact.vue:32）重复；两者间距被 `gap:24px` 固定，无法用叠边技巧合并 |
| `z-index: 5` | apps/web/src/components/FilterBarSticky.vue:16 | 必要 | 需要盖住表格固定列与滚动内容，且低于顶栏的 6（apps/web/src/layouts/MainLayout.vue:551） |
| 组件本体（仅 1 处调用） | apps/web/src/components/FilterBarSticky.vue:1-30（唯一调用 AuditView.vue:11） | 可合并 | 单调用点的透传容器；可与页头 actions 同排成一条工具条，或直接并入 AuditView 的页面样式 |
| 折叠容器默认收起 | apps/web/src/components/CitationList.vue:121 | 可合并 | `activeNames = ref([])`；引用是问答可核查性的本体，展开需 1 次点击；而正文角标与卡片之间没有任何联动（apps/web/src/views/chat/components/ChatMessageItem.vue:141-145 仅处理代码复制） |
| 摘要 3 个数字徽章 + `...` | apps/web/src/components/CitationList.vue:11-16, :231-251 | 可删 | 徽章内容是 `i + 1`（1、2、3），不是文档名或页码，与同行「N 个引用来源」表达同一信息 |
| `title` prop | apps/web/src/components/CitationList.vue:117 | 可删 | 唯一调用点只传 citations 与 mode（apps/web/src/views/chat/components/ChatMessageItem.vue:38） |
| meta 标签行（9 项，nowrap + ellipsis） | apps/web/src/components/CitationList.vue:26-39, :308-318 | 可合并 | 语料类型/版本标签/生效状态/证据类型/页码/区域/置信度挤在一行且 `overflow: hidden`；能看到哪几个字段取决于字符串长度，被截断的部分无 title、不可展开、不换行 |
| 「置信度 x%」标签 | apps/web/src/components/CitationList.vue:38 | 可合并 | 与 :64-75 的「相关性 %」条重复回答"这次匹配有多好"，但两数来源与量纲不同，用户需要自己判断信哪个 |
| 相关性条 + 百分比 | apps/web/src/components/CitationList.vue:64-75, :423-439 | 可删 | 与上一条二选一即可；宽度过渡 0.5s 见动效表 |
| 卡片序号 `.source-index` | apps/web/src/components/CitationList.vue:23, :278-290 | 必要 | 与答案正文角标对应的唯一映射；去掉后 9 个标签里再无"这是第几条来源" |
| 生效/失效时间线 | apps/web/src/components/CitationList.vue:58-61 | 必要 | 版本时效性是知识库答案可信度的关键约束 |
| 44×44 原文链接 | apps/web/src/components/CitationList.vue:41-50, :338-349 | 必要 | 每张卡唯一的"查看原文"入口（hover 描边失效见动效表） |
| 引号伪元素装饰 | apps/web/src/components/CitationList.vue:400-409 | 可删 | 28px serif 引号叠在引文左上角，与引文内容重复，且 `opacity: .5` 让它在浅色底上只留下脏点 |
| 折叠容器 hover 描边 | apps/web/src/components/CitationList.vue:181-183 | 可删 | 容器本身不可点击，反馈指向错误对象 |
| 4px / 3px 硬编码圆角 | apps/web/src/components/CitationList.vue:237, :285, :334, :366 | 可删 | 跳出 --radius-xs(6)/sm(8)/md(12)/lg(14) 刻度（apps/web/src/style.css:41-44），卡片细节比全站其余部分更尖 |
| 事件头（h3 + 描述 + N 条） | apps/web/src/components/DocumentEvents.vue:3-7 | 可删 | KBDocumentView.vue:388 的外层 collapse 已渲染同串「处理事件」（docs/design-audit/round1/12-kb-document.md 已登记该重复）；KBUploadView.vue:216 传空文案后只剩一个孤立的「N 条」 |
| `description` prop | apps/web/src/components/DocumentEvents.vue:5, :80 | 可删 | 两个调用点都传空字符串（KBUploadView.vue:216、KBDocumentView.vue:389） |
| 状态三重表达 | apps/web/src/components/DocumentEvents.vue:30-35 | 可合并 | 同一状态同时用 icon（:30）+ 流程词 `<strong>`（:33）+ el-tag（:35）表达；failed 时两处文案完全相同（:92 vs apps/web/src/utils/status.ts:16），uploaded 同样（:85 vs :9），ready 时变成两个不同词「流程完成」/「可问答」（:92 vs :15） |
| 事件时间戳 | apps/web/src/components/DocumentEvents.vue:21, :179-184 | 必要 | 定位一条处理事件的唯一时间线索 |
| 事件卡边框容器 `.event-card` | apps/web/src/components/DocumentEvents.vue:186-191 | 可下沉 | 时间线轴 + 卡片边框 + 详情框（:230）三层容器叠在一条事件上，可用间距/对齐替代其中一层 |
| 详情 JSON 折叠 | apps/web/src/components/DocumentEvents.vue:39-50, :264-274 | 可下沉 | 面向实现者的原始 payload；.event-details 只有 `overflow:auto` 没有 max-height，展开后卡片高度等于 JSON 全文高度 |
| `#0f172a` 硬编码代码块底 | apps/web/src/components/DocumentEvents.vue:268-269 | 可删 | 浅色主题下全站唯一的深色块，未走任何 token；同类硬编码状态色还有 :105-106、:223（#10b981/#ef4444）与 CitationList.vue:437-439 |
| `:type` 与 `:color` 同时传 | apps/web/src/components/DocumentEvents.vue:23-25 | 可删 | `getTimelineNodeColor`（:104-109）已覆盖 type 的取色，二者取一 |
| 触发按钮（图标 + title） | apps/web/src/components/ThemeToggle.vue:3 | 必要 | 主题唯一入口；无 aria-label，靠 `:title` 充当可访问名 |
| 三选项菜单（含「跟随系统」） | apps/web/src/components/ThemeToggle.vue:13-27 | 必要 | 全局唯一偏好设置，docs/design-audit/round1/01-shell.md:34 已确认为必要 |
| 当前项三重标记（disabled + Check + 蓝图标） | apps/web/src/components/ThemeToggle.vue:17, :20, :24 | 可合并 | 同一状态由三个信号表达（禁用态、勾选图标、图标色 :73-78），保留 Check 即可 |
| `handleCommand` 内的 setTheme | apps/web/src/components/ThemeToggle.vue:81 | 可删 | 随后的 `watch(currentMode)`（:86-88）会再调一次 setTheme，一次选择写两遍 localStorage 与 `:root` 变量（apps/web/src/utils/theme.ts:82-85） |
| icon-spin 过渡参数 | apps/web/src/components/ThemeToggle.vue:117-130 | 可删 | 180° 旋转 + scale(0.5) 入场，表达不了 light↔dark 的方向（01-shell.md:68 已按组件级登记） |
| `:deep(.el-dropdown-menu.glass-panel)` | apps/web/src/components/ThemeToggle.vue:146-151 | 可删 | 下拉默认被 teleport 到 body（element-plus ^2.13.3，未传 teleported/append-to-body），作用域祖先不存在，规则疑似零匹配 → 存疑 |
| hover 四重反馈 | apps/web/src/components/ThemeToggle.vue:99-104 | 可合并 | 位移 + 阴影 + 底色 + 描边同时变化，四次改动表达同一个"可点" |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 合并 | apps/web/src/components/CitationList.vue:26-39, :308-318 | 少一次判断 | meta 行把 9 个字段塞进一行 `white-space: nowrap` + `text-overflow: ellipsis`（:308-318），末尾的「置信度/页码/区域」能不能看见取决于前面字符串的长度——同一条回答里，用户看到的字段集合会随机变化，且被截断的部分没有 title 可查、不能换行。收敛为 3 类（版本 / 位置 / 分数）并允许 `flex-wrap`，同时与 :64-75 的相关性条二选一，行高换来的空间由删除摘要徽章（提案 3）偿还。风险：换行后每张卡高 1–2 行，一屏可见来源数下降；「置信度」与「相关性」语义不同（前者是引用自评，后者来自 `evidence_path.relevance`），保留哪一个必须由后端确认是否同源，选错会让用户拿到不再单调可比的数字；`Math.min/Math.max` 的宽度钳制（:69）在换行后需重新确认不会挤出卡片 |
| 合并 | apps/web/src/components/DocumentEvents.vue:30-35 | 少一次判断 | 一个事件的状态被写三遍：图标、流程词、状态 tag。failed 与 uploaded 时流程词与 tag 渲染的是同一串字（:92 与 apps/web/src/utils/status.ts:16；:85 与 :9），ready 时却变成两个词「流程完成」/「可问答」——用户需要判断这两个词是不是一回事，而它恰好是「文档能不能开始问答」这个最关键的状态。保留 el-tag（唯一经过 statusMeta 收敛、且被其它页面共用）或保留图标 + 流程词。风险：statusMeta 也被 KBDocumentView/KBUploadView 的其它位置复用，改 tag 文案会外溢；若选择保留 STAGE_LABELS，则要接受它与全局状态词表出现两套词汇（需要在 utils/status.ts 里对齐，改动跨 3 个文件） |
| 删除 | apps/web/src/components/CitationList.vue:11-16, :231-251 | 少一次判断 | 摘要行右侧固定渲染 3 个 20px 徽章，内容只是 `i + 1`（1、2、3）和一个 `...`：它们看起来是"来源头像/缩略预览"，实际不携带任何文档信息，与同一行左侧的「N 个引用来源」完全重复；折叠态下这 3 个数字也无法与任何具体内容对应。风险：头部行会只剩「图标 + N 个引用来源 + 展开箭头」，在窄容器（`.citation-grid` 最小列宽 280px，:256）里视觉上更空，需要确认折叠态的点击热区仍然明显；删除后若产品希望折叠态展示来源线索，只能靠文档名（需要后端在 citations 里稳定提供，当前 `section_title` 可能为空，:25） |
| 删除 | apps/web/src/components/PageHeaderCompact.vue:5-7, :49-57（19 个静态文案调用点，如 AgentMonitorView.vue:3、AbExperimentView.vue:3、ToolManagerView.vue:3、ModelProviderView.vue:5） | 少一次判断 | 页头副标题承载的是"这一页是干什么的"自述文案，与侧栏高亮项、顶栏面包屑表达同一件事，却占掉页头约 24px 高度（56px → 约 78px），把首屏内容整体下压；用户读完标题还要读第二行才知道能不能跳过。删除后页头只剩「标题（已由外壳承担）+ 操作」。风险：KB 类页面用同一槽位显示当前对象名（KBChunkReviewView.vue:3 文件名、KBDocumentView.vue:3 文档名、KBUploadView.vue:3 知识库名），这三处不能删，否则失去"我在操作哪个对象"；如果保留 prop 只删文案，会留下"有时有副标题有时没有"的不一致，需要按页面类型写进约定；功能说明文案要迁到文档或首次进入引导，否则新用户失去唯一的"这页能做什么"提示 |
| 删除 | apps/web/src/components/CitationList.vue:121（配合 apps/web/src/views/chat/components/ChatMessageItem.vue:141-145） | 少一步 | 引用是回答可核查性的本体，但 `activeNames` 初值是空数组（:121）→ 每条回答都必须先点一次「N 个引用来源」才能看到任何一个来源；同时正文里的角标与来源卡片之间没有任何点击联动（ChatMessageItem.vue:141-145 只处理代码复制按钮），核对一条来源的完整路径是"展开 → 目视按序号找卡片 → 点 44px 链接"。改为默认展开（或来源数 ≤3 时默认展开）后，核对动作少一步；新增的高度由删除摘要徽章（提案 3）与装饰插画偿还，净增 0 元素。风险：来源多、回答长时每条消息高度显著增加，长会话滚动变长，需要限制默认展开条数（例如展开前 3 条 + "查看其余 N 条"），否则"引用"从可选项变成必读项；这属于产品对"证据是否必读"的取舍，若产品有意弱化引用，应保持现状并只保留提案 1、3；另需确认默认展开后 el-collapse 的 aria-expanded / 键盘路径仍正确（现由 el-collapse 管理，会随 v-model 初值变化） |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 物理性与原点 | apps/web/src/components/EnhancedEmpty.vue:108-113 | 装饰插画容器（:99-109 内无任何交互监听）挂 `:hover` 做 `scale(1.05) rotate(2deg)`：300ms、回弹过冲曲线 `cubic-bezier(0.34, 1.56, 0.64, 1)`，既不属于允许的四类理由，又对非可点元素给出可点错觉。该组件在 16 个视图被引用（本报告所属组件即为归属方），docs/design-audit/round1/{03,07,11,12,13,15,16} 已各自登记过实例，此处给出组件层结论 | 删除 `:108` 的 transition 与 `:111-113` 的 hover 规则；空态是静态占位，不需要等价替代物 |
| HIGH | 一致性与 token | apps/web/src/components/CitationList.vue:351-355 | `.source-link:hover` 同时改 color / border-color / background（:348 声明了 3 个 0.2s 过渡），但 `border-color: var(--blue-200)`（:353）引用的变量全仓无定义（apps/web/src/style.css:17-20 与 apps/web/src/utils/theme.ts:27-30 只定义 blue-50/500/600/700）→ 该声明在计算值阶段失效，hover 时只有文字与底色变化，描边退回继承色，恰好是"原文链接"这个唯一外部入口的反馈不一致 | 删除该声明（三个信号里留两个即可），或改用已定义 token（--border-strong / --blue-500）；同类未定义变量（--blue-400/--blue-100/--green-400/--red-400-500-600）还散布在 8 个视图，见返回摘要 systemic_candidates |
| HIGH | 性能 / 缓动与时长 | apps/web/src/components/CitationList.vue:431-435 | `.relevance-fill { transition: width 0.5s ease }`：动画属性是 `width`（布局属性，规则禁止），时长 500ms 超过 300ms 上限，缓动用的是被禁的 `ease` 预设；而宽度是渲染时由 `:style`（:69）一次性写入的静态值，卡片挂载后再无变更 → 这是一条几乎永不触发的死过渡，一旦触发（流式追加引用导致同卡重算）就是整列卡片同时重排 | 删除该 transition；若确实需要在数据到达时有反馈，用 `opacity` 或条内 `scaleX`（transform）替代，时长 ≤200ms |
| MEDIUM | 物理性与原点 / 可打断性 | apps/web/src/components/ThemeToggle.vue:117-130, :4 | icon-spin 入场从 `rotate(-180deg) scale(0.5)` 起（低于入场下限 scale(0.95)），出场到 `rotate(180deg) scale(0.5)`，配 `mode="out-in"` 后一次换图标跑两段约 600ms；旋转方向由 enter/leave 决定，不编码 light→dark 或 dark→light，不构成空间一致性 | 删除旋转与缩放，只保留 opacity 交叉淡入（≤150ms）；或整段删除，图标直接切换 |
| MEDIUM | 性能 / 一致性 | apps/web/src/components/DocumentEvents.vue:264-274 | `.event-details` 只有 `overflow: auto`（:267）而无 max-height，高度约束不存在时 auto 不产生滚动条，展开后卡片高度 = JSON 全文高度；它又与 el-collapse 的展开动画叠加在同一条时间线上，长 payload 会把后续事件推出视口。同类未 token 化：`:228` 硬编码 `border-radius: 12px`（应为 --radius-md） | 给 `.event-details` 加 `max-height` + 滚动，或把详情收进抽屉；圆角改用 --radius-md |
| MEDIUM | 一致性与 token | apps/web/src/components/CitationList.vue:237, :285, :334, :366 | 卡片内部的圆角硬编码为 4px（徽章 :237、序号 :285）、3px（meta 标签 :334），都低于圆角刻度的最小档 --radius-xs 6px；缩略图另用 8px 而非 --radius-sm。同一张卡里出现 3/4/8px 三种未入册的圆角，与全站 6/8/12/14 的刻度不一致 | 收敛到 --radius-xs / --radius-sm 两档；与提案 1（meta 行重构）同一处改动 |
| LOW | 无障碍 / 状态指示 | apps/web/src/components/ThemeToggle.vue:3, :17, :24 | 触发按钮没有 aria-label，只有 `:title="currentLabel"` 充当可访问名（读屏可用但不稳定，且 tooltip 依赖指针悬停）；菜单里"当前主题"同时用 `disabled`、Check 图标、图标色三种方式表达 | 补 aria-label="主题：{currentLabel}"；状态指示只留 Check 一种 |
| LOW | 缺失的机会 | apps/web/src/components/CitationList.vue:121, :3-18 | 展开/收起属于"偶尔"频次，允许一次正常动效；当前完全交给 el-collapse 默认高度过渡，没有任何方向或原点提示（浮层/披露的原点应对齐触发点，模态框除外）。反过来看：若采纳提案 5 让引用默认展开，这条动效需求自然消失 | 维持现状即可，不要为此新增动效；若要动，只做 ≤200ms 的 opacity，不做位移 |

## 存疑

- **`:deep(.el-dropdown-menu.glass-panel)` 是否真的生效**：apps/web/src/components/ThemeToggle.vue:146-151 用 `:deep()` 修饰 teleport 到 body 的下拉菜单，需要存在带 `data-v-*` 的祖先元素；element-plus 版本为 ^2.13.3（apps/web/package.json:16）且未传 `teleported`/`append-to-body`（全仓仅 MainLayout 的 drawer 用了 append-to-body），默认 teleport 到 body 后该祖先不存在 → 规则疑似零匹配。菜单实际外观由全局 `.glass-panel` 提供（apps/web/src/styles/theme-extras.css:8-12，带 `!important`），所以肉眼难以发现。验证方法：devtools 选中下拉菜单，看 Computed 里的 border-radius/padding 是否来自 scoped 规则；或临时传 `:teleported="false"` 对比。
- **`.source-link:hover` 描边失效后的实际表现**：`var(--blue-200)` 未定义会让 `border-color` 变成 invalid at computed-value time（回退为继承）。父级 `.source-card`（apps/web/src/components/CitationList.vue:260-267）设了 `border: 1px solid var(--border-color)`，因此推断它继承到的是近透明描边。我未在浏览器确认，需实测确认 hover 时描边是否真的"无变化"（若浏览器回退成 currentColor 则会变蓝，结论需改写）。
- **两条平行细线的实际观感**：apps/web/src/components/PageHeaderCompact.vue:32-33 的 `margin-bottom:-1px` 与父级 `gap:24px`（apps/web/src/style.css:182-191）、以及 FilterBarSticky.vue:22 的 border-bottom，三者叠加后的真实间距与视觉权重我无法从 CSS 推导到像素级确定（flex gap 与负 margin 的相互作用、是否有其它兄弟节点）。验证方法：打开 /workspace/audit（审计日志），量页头底边与筛选栏底边的实际距离并截图确认是否读作"两条线"。
- **sticky 与顶栏的层叠关系**：FilterBarSticky.vue:16 `z-index: 5` 位于 `.workspace-topbar`（apps/web/src/layouts/MainLayout.vue:549-559，`z-index: 6`，同为 sticky）之下，二者是否在同一个层叠上下文、滚动时是否会出现筛选栏钻进顶栏底边的情况，需要真机滚动验证；`.page-shell` 自身 `overflow-y:auto`（apps/web/src/style.css:189）使滚动容器是页面内层而非窗口，sticky 的参照系需实际渲染确认。
- **引用默认收起是否为产品决策**：apps/web/src/components/CitationList.vue:121 与 apps/web/src/views/chat/components/ChatMessageItem.vue:141-145 共同导致"正文角标 → 来源卡片"没有联动，用户必须手动点击展开再按序号查找。我把它写成提案 5（默认展开，收益"少一步"），但它取决于产品是否认为引用属于必读证据：若认为长回答的阅读节奏更重要，则应保持现状，仅保留提案 1、3。验证方法：找 3 条真实回答（来源数 1/5/10+）走一遍核对流程，量出"展开→找卡片"的耗时与误点率。
- **DocumentEvents 的 v-for key 是否唯一**：apps/web/src/components/DocumentEvents.vue:20 用 `${item.created_at}-${item.stage}` 作 key，若同一文档在同一秒内产生两条同 stage 事件（例如重试），key 会重复并触发 Vue 的重复 key 告警与渲染错位。需要后端事件流样本确认是否存在同 stage 同秒记录。
- **`.event-details` 的 JSON 体量**：我看不到真实 `details_json` 的大小（DocumentEvents.vue:39 只在存在时渲染），因此"展开后把后续事件推出视口"的影响面未量化；验证方法：取一份真实的 kb 文档事件响应，量 JSON 字符数与渲染高度。
- **`--text-h1`（1.375rem）在本轮全部 6 个组件里都未被使用**：apps/web/src/style.css:32 定义的字号目前只被 LoginView.vue:159 使用，页面标题一律是 `--text-h2`（PageHeaderCompact.vue:42）。这属于"共享页头该不该升到 h1 档"的全局取舍，我没有把它作为提案（会引入新的层级约定），需要设计口径确认。
- **本轮未覆盖的相邻文件**：apps/web/src/styles/theme-extras.css 与 responsive-enhancements.css 对 el-* 组件有 17 处 `!important` 尺寸覆盖（如 theme-extras.css:102-107 的表格内边距），会直接影响本文档事件/引用列表里 el-table / el-collapse 的观感；它们不属于本界面的 6 个文件，仅在此登记为跨界面模式。
