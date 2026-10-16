# 07 知识库治理（上传与文档列表）

审计范围：`apps/web/src/views/kb/KBUploadView.vue`、`apps/web/src/api/kb.ts`
路由：`/workspace/kb/upload`（`apps/web/src/router/index.ts:97-106`，`requiresPermission: 'kb.read'`）
依赖组件（仅在与本界面相关处取证）：`components/PageHeaderCompact.vue`、`components/DocumentEvents.vue`、`components/EnhancedEmpty.vue`、`utils/multipartUpload.ts`、`utils/status.ts`

## 唯一用户任务

知识库管理员/知识库创建者在「已有一个知识库、要往里面补文档」的场景下，要**选文件→上传→确认这份文档什么时候能问答**。

（推论依据：本页 `kb.read` 即可进入 `router/index.ts:101`，但所有写操作都被 `canWrite` 收窄 `KBUploadView.vue:395-398`，其中写权限等价于「自己是这个库的创建者或管理员」`KBUploadView.vue:389-394`。因此本页真实用户是库的属主，不是泛化的「任何人」。）

## 完成该任务的必要步骤

1. 进入页面，等 `listKnowledgeBases` + `listKBTypes` + `listKBJobPositions` 三个请求（`KBUploadView.vue:674-684`）→ **keep**
2. 在左栏选中目标知识库 —— 若 URL 带 `baseId` 则自动选中，否则默认取第一个库（`KBUploadView.vue:410-416`）→ **keep**（默认选第一个库是静默的，用户不确认就上传会落到错误的库，这是误操作风险，见提案 5）
3. 读取/填写「文档分类」等元数据（`KBUploadView.vue:44-120`）→ **demote**（全部可选，`api/kb.ts:451-464` 中对应字段均为可选）
4. 选文件：拖拽或点击 dropzone（`KBUploadView.vue:122-143`）→ **keep**
5. 点「开始上传」（`KBUploadView.vue:160-168`）→ **keep**（这是本页唯一的主任务按钮，必须唯一、必须最重）
6. 从右侧「文档列表」里找到刚上传的那条，读状态标签（`KBUploadView.vue:186-196`）→ **keep**
7. 判断「能不能问答了」：状态未到 `ready` 时（`utils/status.ts:6-17` 中 `parsing` / `enhancing` 均为 warning）需要展开「处理事件」看进程（`KBUploadView.vue:211-218`）→ **keep**，但事件面板默认折叠 `eventsCollapse = ref<string[]>([])` `KBUploadView.vue:330`

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 头部「问答」按钮 | apps/web/src/views/kb/KBUploadView.vue:5 | 可删 | 路由到 `/workspace/chat`，与「上传文档」目标无关；且本页 `requiresPermission: 'kb.read'`，`/workspace/chat` 需要 `chat.use`（router/index.ts:79），无 chat.use 的用户点它会被守卫弹到 `/workspace/forbidden`（router/index.ts:394-400），是本页唯一未做权限判断的头部动作 |
| 头部「上传」按钮 | apps/web/src/views/kb/KBUploadView.vue:6 | 可删 | 与 dropzone 调用同一个 `pickFiles`（KBUploadView.vue:127、KBUploadView.vue:436） |
| 头部「新建」按钮 | apps/web/src/views/kb/KBUploadView.vue:7 | 可删（或下沉） | 新建知识库是本页任务的前置条件而非步骤；`canManageBase` 门控（KBUploadView.vue:7） |
| 知识库选择器 | apps/web/src/views/kb/KBUploadView.vue:20-32 | 必要 | 决定上传目标；`selectedBaseId` 是 `handleUpload` 的硬门控（KBUploadView.vue:163） |
| 「编辑」按钮 | apps/web/src/views/kb/KBUploadView.vue:33-40 | 可下沉 | 编辑知识库元数据与上传文档无关，`openBaseDrawer('edit')`（KBUploadView.vue:37） |
| 文档分类输入 | apps/web/src/views/kb/KBUploadView.vue:45-51 | 可合并 | 可选字段（api/kb.ts:451）；与「内容类型」同属文档级元数据 |
| 内容类型输入 | apps/web/src/views/kb/KBUploadView.vue:52-54 | 可合并 | 可选字段（api/kb.ts:461） |
| 题型输入 | apps/web/src/views/kb/KBUploadView.vue:55-57 | 可下沉 | 可选字段（api/kb.ts:462），语义偏面试题库 |
| 难度输入 | apps/web/src/views/kb/KBUploadView.vue:58-60 | 可下沉 | 可选字段（api/kb.ts:463），语义偏面试题库 |
| 标签输入 | apps/web/src/views/kb/KBUploadView.vue:61-63 | 可合并 | 可选字段（api/kb.ts:464），逗号分隔解析（KBUploadView.vue:599） |
| 版本治理分组 | apps/web/src/views/kb/KBUploadView.vue:64-119 | 可下沉 | 全组可选（api/kb.ts:451-459） |
| 版本家族 Key | apps/web/src/views/kb/KBUploadView.vue:65-71 | 可合并 | 见上 |
| 版本标签 | apps/web/src/views/kb/KBUploadView.vue:72-78 | 可合并 | 见上 |
| 版本号 | apps/web/src/views/kb/KBUploadView.vue:79-81 | 可合并 | 见上 |
| 版本状态 | apps/web/src/views/kb/KBUploadView.vue:82-89 | 可合并 | 默认 `'active'`（KBUploadView.vue:348） |
| 设为当前版本开关 | apps/web/src/views/kb/KBUploadView.vue:90-92 | 可合并 | 默认 `true`（KBUploadView.vue:349） |
| 生效开始 | apps/web/src/views/kb/KBUploadView.vue:93-102 | 可合并 | 见上 |
| 生效结束 | apps/web/src/views/kb/KBUploadView.vue:103-112 | 可合并 | 见上 |
| 替代旧文档 ID | apps/web/src/views/kb/KBUploadView.vue:113-119 | 可删 | 要求用户手填一个文档 UUID，而文档列表只渲染 `doc.file_name`（KBUploadView.vue:192），界面上根本看不到 ID；该版本治理能力在另建连接器界面已有（KBConnectorsView.vue:124-129） |
| 拖拽/上传区 | apps/web/src/views/kb/KBUploadView.vue:122-135 | 必要 | 唯一包含拖拽入口的元素 |
| 格式提示文案 | apps/web/src/views/kb/KBUploadView.vue:134 | 可删 | 与 `accept` 不一致，见动效/存疑 |
| 文件选择 input | apps/web/src/views/kb/KBUploadView.vue:136-143 | 必要 | `pickFiles` 的目标（KBUploadView.vue:436） |
| 已选文件列表 | apps/web/src/views/kb/KBUploadView.vue:145-158 | 必要 | 上传前的唯一确认面 |
| 「开始上传」按钮 | apps/web/src/views/kb/KBUploadView.vue:160-168 | 必要 | 本页主任务动作 |
| 文档计数 | apps/web/src/views/kb/KBUploadView.vue:175 | 可删 | `latestDocuments.length`（KBUploadView.vue:175），后端全量返回不翻页（kb_base_routes.py:645-649），计数恒等于列表长度 |
| 空文档态 | apps/web/src/views/kb/KBUploadView.vue:178-184 | 必要 | 冷启动可辨识（EnhancedEmpty variant="document"） |
| 文档行打开按钮 | apps/web/src/views/kb/KBUploadView.vue:191-196 | 必要 | 进入 `/workspace/kb/documents/:id`（KBUploadView.vue:637） |
| 文档状态标签 | apps/web/src/views/kb/KBUploadView.vue:193-195 | 必要 | 唯一的状态指示（statusMeta，utils/status.ts:19-25） |
| 版本建议卡片 | apps/web/src/views/kb/KBUploadView.vue:197-202 | 可删 | 只读建议，无任何按钮把它填回左侧版本表单；同样的建议在 KBConnectorsView.vue:124-129 有完整形态 |
| 「提问」按钮 | apps/web/src/views/kb/KBUploadView.vue:204 | 可下沉 | 生成后任务，与上传无关；无 `chat.use` 判断，同头部「问答」 |
| 「删除」按钮 | apps/web/src/views/kb/KBUploadView.vue:205 | 必要 | 有二次确认（KBUploadView.vue:648-656），误操作已被拦 |
| 处理事件折叠面板 | apps/web/src/views/kb/KBUploadView.vue:211-218 | 必要 | 唯一能看到解析/索引进程的地方；默认折叠（KBUploadView.vue:330） |
| 知识库抽屉（新建/编辑） | apps/web/src/views/kb/KBUploadView.vue:222-280 | 必要 | 首次使用的入口 |
| 抽屉「删除知识库」 | apps/web/src/views/kb/KBUploadView.vue:270-277 | 必要 | 有二次确认（KBUploadView.vue:533-537） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/views/kb/KBUploadView.vue:5-6 | 少一次判断 | 头部失去「上传」入口后，只能从 dropzone 或底部按钮起手；对习惯点头部的主用户是新增一次学习。另：`问答` 按钮删掉后，无 `chat.use` 的用户不再被弹到 forbidden 页（router/index.ts:394-400），但该跳转本身在别处仍存在 |
| 删除 | apps/web/src/views/kb/KBUploadView.vue:113-119 | 少一步 | 「替代旧文档 ID」是版本治理的合法能力，删掉后该路径只能走批量更新接口（api/kb.ts:135）或连接器（KBConnectorsView.vue:124-129）；若后端强依赖 `supersedes_document_id` 表达版本链，此能力在本界面将不可达 |
| 下沉 | apps/web/src/views/kb/KBUploadView.vue:64-119 | 少一次判断 | 版本字段默认折叠后，需要用它们的少数用户多一次展开；且折叠期间用户不知道有这些字段，可能上传出「无版本家族」的文档，把成本推到下游治理视图 |
| 删除 | apps/web/src/views/kb/KBUploadView.vue:197-202 | 少一次判断 | 删掉建议卡片后，建议数据仍来自 `doc.stats_json.version_assist`，本页不再展示，用户若要采纳需切到连接器界面；若该卡片是「版本治理」产品的核心卖点，删除会削弱它 |
| 加反馈 | apps/web/src/views/kb/KBUploadView.vue:145-158 | 少一次误操作 | 需要新增每文件状态文案（这违反默认删除），且上传中重复渲染是性能代价；实现上还要区分「上传失败」与「已上传待索引」两种状态，否则文案会误导 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 缓动与时长 | apps/web/src/components/EnhancedEmpty.vue:108-113 | 空态插图挂在 `:hover` 上做 `scale(1.05) rotate(2deg)`，300ms，`cubic-bezier(0.34, 1.56, 0.64, 1)`（带过冲）。这是纯装饰插图，不是可点元素（EnhancedEmpty.vue:99-109 内无交互监听），却给出可交互的错觉 | 删除该 hover 变换；`:hover` 位移改挂触发点本身（现状连触发点都没对齐）。若确实要保留，须进 `@media (hover: hover) and (pointer: fine)` 且去掉过冲曲线 |
| MEDIUM | 性能 / 一致性与 token | apps/web/src/views/kb/KBUploadView.vue:745、852 | `transition` 落到了 `background`（dropzone 与 doc-item 都是 `border-color, background`），而 hover 目标色是实色变量（KBUploadView.vue:753-756、855-858），触发的是可动画属性而非合成层属性 | 只保留 `border-color` 的过渡；如需背景反馈改用 `box-shadow` 或不做过渡 |
| LOW | 缺失的机会 | apps/web/src/views/kb/KBUploadView.vue:152-156 | `el-progress` 在轮询（KBUploadView.vue:569，2s 一次）下没有明确的插值过渡；上传完成瞬间 `uploadProgress` 被清空（KBUploadView.vue:629），百分比从 100 直接消失，进度条整条消失而无过渡 | 只加 `opacity` 过渡（KBUploadView.vue:629），不要动宽高；进度条本身的插值交给组件默认值 |
| LOW | 无障碍 / 一致性与 token | apps/web/src/views/kb/KBUploadView.vue:753、855 | 两处 `:hover` 样式的选择器都未包在 `@media (hover: hover) and (pointer: fine)` 内 | 全局范围已有此问题（见已知清单），此处只作为本界面内的实例记录；修复应与全局同一批进行 |

## 存疑

- 头部「上传」按钮删掉后，主用户是否真的会转向 dropzone？需要真机观察首次进入时的点击分布（建议埋点：`pickFiles` 的调用来源）。
- `supersedes_document_id`（apps/web/src/views/kb/KBUploadView.vue:595）在后端是否被用于强校验或版本链推导？本次只读了前端与 KB 服务的列表接口（kb_base_routes.py:645-649），未追版本链写入路径，无法判断删除该输入框会不会断链。
- `allowed_departments` 在 `createKBUpload` 的入参里存在（api/kb.ts:460），但本页从不传。需要人确认这是「本页缺失的能力」还是「故意留给其他入口」。
- 上传失败后重试时 `uploadProgress` 不会被重置（KBUploadView.vue:617-635 无 catch 分支），真实表现取决于请求层是否显示 error toast（request.ts:128 显示 `ElMessage.error`）；需要真机复现一次「第 2 个文件失败」的路径来确认残留态。
- `fileFingerprint` 用 `name:size:lastModified` 作 key（KBUploadView.vue:387）；同一进度表在并发上传两个同名同长文件时是否会串进度，需要实际构造数据验证。
- `el-progress` 是否内建 percentage 过渡（element-plus 版本相关）需在浏览器 DevTools 中确认，本次未能确认。
- 文档列表全量渲染无虚拟滚动（KBUploadView.vue:186-208），在文档数很大时的滚动性能需要真机测量。
