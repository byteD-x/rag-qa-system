# 10 知识库运维

审计范围：`apps/web/src/views/kb/KBOperationsView.vue`（647 行，单文件视图，样式全在该文件 scoped 块 `:386-647`）
数据层（只读引用）：`apps/web/src/api/kb.ts:326-444`
路由：`/workspace/kb/operations`（`apps/web/src/router/index.ts:130-138`，`requiresPermission: 'kb.manage'`）
入口：侧栏「知识库运维」（`apps/web/src/layouts/MainLayout.vue:255-259`；可见性过滤 `MainLayout.vue:279-286`）
依赖组件：`apps/web/src/components/PageHeaderCompact.vue`、`apps/web/src/utils/time.ts:1-12`
本次为只读审阅，未运行构建、测试或渲染。

## 唯一用户任务

知识库管理员（值班）在怀疑存在 ingest / connector 故障的场景下，要在一屏内确认是否存在需要人工介入的故障项，并当场对具体 job 或连接器触发重试 / 同步。

依据：路由以 `kb.manage` 为门槛（`apps/web/src/router/index.ts:134`）；页面自述「面向知识库管理员的值班视图」（`apps/web/src/views/kb/KBOperationsView.vue:5`）；全页写类操作只有三处——重试 ingest（`:333-347`）、单条同步（`:349-363`）、批量同步（`:365-379`）。

## 完成该任务的必要步骤

1. 进入页面并等一次全量取数 → **keep**（`KBOperationsView.vue:381-383` 只调 `reloadAll`；`:286-293`；全文件无定时器，页面不轮询）
2. 读副标题的「生成时间」确认这批数据的新鲜度 → **keep**（`KBOperationsView.vue:6`、`utils/time.ts:1-12`）
3. 读「服务健康」的聚合状态与依赖检查，确认有没有降级 → **keep**（`KBOperationsView.vue:40-52`、标签映射 `:316-320`）
4. 扫 ingest 三个指标判断有没有活要干 → **merge**（`KBOperationsView.vue:69-82`；三个数字与下方 `:84-141` 两个列表的计数重复表达）
5. 在「可重试任务」里对某条点「重试 ingest」并在确认框上确认 → **keep**（`KBOperationsView.vue:103-111`、`:333-347`）
6. 在「卡住文档」里点「文档详情」跳到该文档 → **keep**（`KBOperationsView.vue:137`、`:295-297`）
7. 在 Connector 卡里对某条点「立即同步」并确认 → **keep**（`KBOperationsView.vue:187-195`、`:349-363`）
8. 批量处理时点顶栏「执行到期连接器」并确认 → **demote**（`KBOperationsView.vue:19-27`、`:365-379`；它只作用于连接器这一块，却占用全页工具栏位，与 ingest 区块并列在页头）
9. 改「个人/管理范围」或「最近 N 天」重取数据 → **keep**（`KBOperationsView.vue:9-17`、`:259-262`；但当前会清空整页，见动效发现第 1 条）
10. 从连接器行点「连接器页」去看那一条 → **drop**（`KBOperationsView.vue:196`；目的地与同卡头 `:150`、侧栏 `MainLayout.vue:251-253` 完全相同，且不带 `connector_id`，到不了那一条）
11. 扫「事故事件流」回溯失败 / 重试 / 降级记录 → **demote**（`KBOperationsView.vue:203-225`；保留事件行，去掉逐条原始 JSON `:222`）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页面标题「知识库运维总览」 | apps/web/src/views/kb/KBOperationsView.vue:3 | 必要 | 全页唯一身份锚点，与侧栏同名条目对应（MainLayout.vue:257） |
| 副标题·「面向知识库管理员的值班视图…」 | apps/web/src/views/kb/KBOperationsView.vue:5 | 可删 | 描述页面自身与受众，不改变任何操作，用户无法据此做判断 |
| 副标题·「生成时间」 | apps/web/src/views/kb/KBOperationsView.vue:6 | 必要 | 页面无轮询（全文件无定时器，仅 :381-383 的 onMounted），新鲜度只能靠它判断 |
| 范围选择器（个人/管理） | apps/web/src/views/kb/KBOperationsView.vue:9-12 | 必要 | 切换数据集：作为 `view` 参数发给后端（api/kb.ts:442，响应含 `view` 字段 api/kb.ts:423-424） |
| 天数选择器（7/14/30） | apps/web/src/views/kb/KBOperationsView.vue:13-17 | 必要 | 切换时间窗口（默认 14，`:256`；参数 api/kb.ts:442） |
| 刷新按钮 | apps/web/src/views/kb/KBOperationsView.vue:18 | 必要 | 无自动刷新，唯一手动取数入口（`:286-293`） |
| 「执行到期连接器」（工具栏主按钮） | apps/web/src/views/kb/KBOperationsView.vue:19-27 | 可下沉 | 只作用于连接器一块（`:371` 传 `limit 10`），却占据全页工具栏最重位置，与 ingest 区块无关 |
| 服务健康卡（聚合状态 + 依赖检查） | apps/web/src/views/kb/KBOperationsView.vue:34-52 | 必要 | 值班的第一判断：服务是否可用 |
| 降级横幅 | apps/web/src/views/kb/KBOperationsView.vue:53-56 | 可合并 | 与 `:40` 的状态 pill 表达同一事实；且只渲染 `item.key`（`:55`），丢掉了同一响应里的 `detail` / `error_type`（api/kb.ts:434-438） |
| 卡片说明段（4 处） | apps/web/src/views/kb/KBOperationsView.vue:38,64,148,207 | 可删 | 实现说明与规则复述：`:38` 写出后端端点名 readyz，`:207` 写事件流的过滤规则，用户不需要 |
| 「去治理页」链接 | apps/web/src/views/kb/KBOperationsView.vue:66 | 可下沉 | 目的地与侧栏 MainLayout.vue:246-249 重复；属卡头的次级出口，不构成主任务 |
| ingest 指标盒 ×3（失败/Dead letter/长卡） | apps/web/src/views/kb/KBOperationsView.vue:69-82 | 可合并 | 与下方 `:84-141` 两个列表头重复表达；`dead_letter_documents` 没有对应列表（api/kb.ts:379-380），删前必须先给它落点 |
| 「可重试任务」小节 | apps/web/src/views/kb/KBOperationsView.vue:84-116 | 必要 | 任务核心动作的载体 |
| 「重试 ingest」按钮 | apps/web/src/views/kb/KBOperationsView.vue:103-111 | 必要 | 唯一能解除失败态的写操作（`:333-347`） |
| 「文档详情」按钮（两处） | apps/web/src/views/kb/KBOperationsView.vue:112,137 | 必要 | 唯一携带 `document_id` 的深链（`:112`、`:137` 均带 id） |
| 「卡住文档」小节 | apps/web/src/views/kb/KBOperationsView.vue:118-141 | 必要 | 第二类需介入项 |
| 「阈值 N 小时」说明 | apps/web/src/views/kb/KBOperationsView.vue:121 | 必要 | 「卡住」的判定标准来自后端（api/kb.ts:381），页面上只有这一处解释 |
| Connector 卡（标题 + 列表） | apps/web/src/views/kb/KBOperationsView.vue:144-200 | 必要 | 第二类故障源 |
| Connector 指标盒 ×4 | apps/web/src/views/kb/KBOperationsView.vue:153-170 | 可合并 | 「启用调度」与每行 `:180` 同义；「近期失败」与 `:181` 的 `last_run_outcome` 同源；「总数」≈列表长度 |
| 「立即同步」按钮（每行） | apps/web/src/views/kb/KBOperationsView.vue:187-195 | 必要 | 唯一单条执行动作（`:349-363`） |
| 「连接器页」按钮（每行） | apps/web/src/views/kb/KBOperationsView.vue:196 | 可删 | 与卡头 `:150`、侧栏 MainLayout.vue:251-253 同一目的地；不带 `connector_id`，不构成上下文动作 |
| 事故事件流卡 | apps/web/src/views/kb/KBOperationsView.vue:203-225 | 必要 | 「发生了什么」的唯一时间线（`:212-223`） |
| 事件 outcome 标签 | apps/web/src/views/kb/KBOperationsView.vue:215 | 可合并 | 走 `statusClass`（`:299-303`）却直接渲染英文原文，而同页 `:41`、`:48` 走 `statusLabel`（`:305-314`）输出中文 |
| `trace:` 文本（每行） | apps/web/src/views/kb/KBOperationsView.vue:219 | 可下沉 | 每行渲染一次，只在排障交接时有用，属事件详情信息 |
| 事件 details `<pre>` | apps/web/src/views/kb/KBOperationsView.vue:222 | 可删 | `JSON.stringify(value\|\|{},null,2)`（`:322`）逐条渲染无界对象；对「当场处理」无贡献，高度不受控 |
| 页面级空态 | apps/web/src/views/kb/KBOperationsView.vue:32 | 必要 | 取数失败的唯一指示 |
| 局部空态 ×3 | apps/web/src/views/kb/KBOperationsView.vue:89,123,172 | 可合并 | 与 `:210` 一起最多可同时出现 4 个同权重虚线盒（共用 `:626-634` 样式） |
| 页面级 loading 文案 | apps/web/src/views/kb/KBOperationsView.vue:31 | 可下沉 | `loading` 为真时经 v-if（`:31`/`:33`）把整块内容卸载重建，滚动位置与上下文一起丢失 |
| 列表行 / 指标盒的边框 | apps/web/src/views/kb/KBOperationsView.vue:506-513,548-554 | 可下沉 | 卡片内再套带边框+底色的小盒（`:404-412` → `:506-513` → `:548-554` 三层），可用间距 / 分隔线区分 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 合并 | apps/web/src/views/kb/KBOperationsView.vue:215（同类：:96-98、:130-132、:180-182、:218-219） | 少一次判断 | 需要为 `job_status` / `document_status` / `outcome` / `last_run_outcome` / `connector_type` / `resource_type` 各补一份中文映射与未知值兜底（映射源：api/kb.ts:332-420）；映射表会随后端枚举漂移，维护成本落在本文件。若只改 `:215` 一处，收益最小（只影响事件流），反而不值得单独改。 |
| 删除 | apps/web/src/views/kb/KBOperationsView.vue:5,38,64,148,207 | 少一次判断 | `:38` 是页面上唯一写出后端依赖来源（readyz）的位置，删后排障的人需要另找；`:64`/`:148` 的「优先处理…」是流程指引，删前需确认这套优先级在治理页或文档里有承载。纯文案删除，无功能风险。 |
| 合并 | apps/web/src/views/kb/KBOperationsView.vue:69-82、153-170（样式 :542-568） | 少一次判断 | `dead_letter_documents`（api/kb.ts:379）与 `recent_failed_runs`（api/kb.ts:406）没有对应列表，直接删盒会让这两个数失去落点，必须指定归属或明文放弃该指标（需产品决定）；列表为空时，指标盒是卡片里唯一还有内容的元素，合并后冷启动页面会更空。 |
| 删除 | apps/web/src/views/kb/KBOperationsView.vue:196 | 少一次误操作 | 删除后连接器行右侧只剩「立即同步」，用户无法从某一条直接跳到连接器配置——但该按钮本来就不带 `connector_id`（固定跳 `/workspace/kb/connectors`），删掉不损失任何深链能力；若产品要「从这条去配置」，那是新增，本审计不建议。 |
| 删除 | apps/web/src/views/kb/KBOperationsView.vue:222（样式 :615-624） | 少一次判断 | 删除后本页看不到事件负载详情，需要先确认审计日志页（入口 MainLayout.vue:291-295，路径 `/workspace/audit`）或事件接口能提供等价信息；若不能，排障时 `trace_id` 之外的证据会消失。另见存疑中关于 details 内容卫生的未决问题。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 缺失的机会 | apps/web/src/views/kb/KBOperationsView.vue:31（触发点 :9、:13、:18；逻辑 :286-293） | 三个入口（范围、天数、刷新）都会置 `loading = true`，经 v-if（`:31`/`:33`）把 `.operations-content` 整块卸载再重建，过渡是浏览器瞬时替换：内容塌陷成一行虚线框文案再弹回，滚动位置与「刚才看到的那一条」同时丢失，用户无法区分「在加载」与「刷新后跳回顶部」。 | 内容不卸载，把加载态下沉到工具栏（`:18` 已有 `:disabled="loading"` 绑定可复用）；只有首次加载（`operations === null`）保留页面级占位。若确要过渡，只动 `opacity`、时长 ≤ `var(--transition-fast)`（style.css:46），并依赖全局 `prefers-reduced-motion` 兜底（style.css:806-815）。 |
| MEDIUM | 一致性与 token | apps/web/src/views/kb/KBOperationsView.vue:26、110、194（按钮态）；:434-496（样式定义） | 本视图全部交互控件都是手写 `<button class="toolbar-button">` 与原生 `<select class="toolbar-select">`（模板中无任何 el-* 组件，仅 `:231` 引入 ElMessage），因此拿不到全局 `.el-button` 的 hover 反馈（style.css:652-654 primary、:661-665 plain）；本文件内也完全没有 `:hover` / `:active` / `transition`（全文件检索无命中），请求期只能靠文案变化（`:26`「执行中...」、`:110`「重试中...」、`:194`「执行中...」）。 | 改用 `el-button` / `el-select`，或给 `.toolbar-button` 补齐与全局一致的**即时** hover（house style 是即时 `opacity: .9`，不是过渡——先对齐，不要为此新增动效）。若确要过渡只用 `var(--transition-fast)`，且必须包在 `@media (hover:hover) and (pointer:fine)` 内（本文件当前没有该包裹，属全局已知问题在本页的实例）。 |
| MEDIUM | 一致性与 token | apps/web/src/views/kb/KBOperationsView.vue:334、350、366 | 三个写操作全部用原生 `window.confirm` 二次确认，其中 `:366` 文案「确认执行当前所有到期连接器吗？」既不说作用范围（取决于 `:9` 的范围选择器），也不说作用数量（`:371` 硬编码 `limit 10`，而「当前到期」的数字只显示在另一个卡片的指标盒 `:163`）。原生模态不可样式化、不继承 token 与过渡，与随后的 ElMessage（`:340`、`:356`、`:372`）视觉语言割裂。 | 改用 `ElMessageBox` 并把「将执行 N 个（上限 10）」写进文案；或将确认下沉为卡片内行内确认。不要在没有后端幂等性结论前直接删除确认（见存疑）。 |
| LOW | 一致性与 token | apps/web/src/views/kb/KBOperationsView.vue:423、429、441、558、603（字号）；:484-496、537-538（颜色）；:615-624（字体） | 硬编码 16px / 13px / 22px / 14px / 12px 五档字号，以及 `#2f7d1f` / `#b26a07` / `#c03838` / `#8a5800` 与 `rgba()` 状态色，均无 token 来源（style.css:32-35 只有 4 档字号）；同一份 ingest 数据在 EntryView.vue:88-93 显示为「解析失败 / 长期卡住」，本页显示为「失败文档 / 长时间卡住」（`:72`、`:80`）；事件 details 的 `<pre>` 未指定字体，落到浏览器默认等宽，未用 `--font-mono`（style.css:7）。 | 字号改用 `--text-h2` / `--text-body` / `--text-caption`。状态色在本 token 集里没有语义色（无 green / amber / red），直接回退到 slate / blue 会让「失败 / 降级」失去颜色区分——需产品先决定是否补语义色 token，否则宁可维持现状。 |

## 存疑

- 页面自述受众是「知识库管理员」（`KBOperationsView.vue:5`），但范围选择器只在 `authStore.isAdmin()` 为真时渲染（`:9`），而 `isAdmin()` 仅对 `platform_admin` 为真（`apps/web/src/store/auth.ts:30-32`），角色清单里的 `kb_admin`（`store/auth.ts:41`）不计入；路由门槛却是 `kb.manage`（`router/index.ts:134`）。即 `kb_admin` 进入时默认 `view='personal'`（`:255`）且无法切到管理范围。是有意的最小权限，还是漏配？需要产品确认。
- 「执行到期连接器」的幂等性与影响面未知：`:371` 固定 `limit 10`、`dry_run=false`，toast 只说「已触发」（`:372`），不回传条数。到期连接器多于 10 个时用户需要再点一次；若后端非幂等，重复点击会重复执行。需后端确认（本次未读后端实现）。
- 三处 `window.confirm`（`:334`/`:350`/`:366`）能否直接去掉确认，取决于重试与同步是否幂等 / 可重入，即后端 `retryKBIngestJob`（api/kb.ts:503）与 `syncConnector`（api/kb.ts:791）的实现，本次未读。
- 事件流 `details`（`:222`、`:322`）是任意后端对象、逐字渲染。是否可能包含凭据、内网 URL 或个人信息，需要后端确认；测试夹具里的 `last_error` 用的是「token invalid」这类消息文本（`KBOperationsView.test.ts:130`），不构成证据。若可能含敏感值，删除 `:222` 的意义就不只是减噪。
- 响应式：`.operations-grid` 用 `minmax(360px, 1fr)`（`:400`），移动端内容区 padding 为 12px（`MainLayout.vue:728`），375px 视口可用宽约 351px < 360px，而 `.page-shell` 是 `overflow-x: hidden`（`style.css:182-191`），存在右侧被裁切的可能。需真机或 DevTools 在 360–390px 宽度下确认。
- 快速连续切换范围 / 天数会并发请求 `getKBOperations`（`:9`、`:13` 的 `@change` 都直接调 `reloadAll`，`:286-293` 无请求序号或取消），后到的响应无条件覆盖（`:264-278`）。数据与筛选标签是否可能不一致，需弱网实测。
- 「可重试任务」与「卡住文档」是否可能包含同一份文档（同一 doc 既有 failed job 又超过阈值）？取数逻辑在后端，本次未读；若会，同一份文档将在两个区块各出现一次。
- 仪表盘的「入库健康度」卡（`EntryView.vue:69-106`）用同一类 ingest 指标，但「去处理异常」指向 upload（`EntryView.vue:72-73`）。全仓库引用 `/workspace/kb/operations` 的位置只有 `router/index.ts:130`、`MainLayout.vue:256` 与两个测试文件（检索结果），没有页面内的入向链接。是否应把仪表盘入口改指本页，需要产品确认——本次未改任何文件。
- 时间显示用 `toLocaleString('zh-CN')`（`utils/time.ts:9-11`），无时区标注；与「卡住阈值 N 小时」（`:121`）比较时的可读性需要人确认。
- 本页当前零动效。若采纳动效发现第 1 条，本页会成为全站首个有页面内加载反馈的界面，需确认产品是否接受；我的建议是只做「不卸载内容」，不加过渡。
