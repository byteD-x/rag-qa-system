# 03 业务总览

文件：`apps/web/src/views/EntryView.vue` · 入口 `/workspace/entry`（登录后默认落点：`apps/web/src/views/LoginView.vue:140`、`apps/web/src/views/RegisterView.vue:39`、侧栏首项 `apps/web/src/layouts/MainLayout.vue:209-214`）

## 唯一用户任务
刚登录或回到工作台的成员，在工作台首页，要先用最短路径确认"知识库/问答有没有需要我处理的异常"，再一键回到最近的知识库或最近会话继续干活。

## 完成该任务的必要步骤
1. 读「入库健康度」的 4 个数字（总文档/就绪/解析失败/长期卡住）— `apps/web/src/views/EntryView.vue:78-95`（keep）
2. 读一行中文结论，把数字翻译成"要不要处理" — `apps/web/src/views/EntryView.vue:96-104`（keep）
3. 有异常时离开首页去处理 — `apps/web/src/views/EntryView.vue:72`（keep）
4. 回到最近的知识库继续 — `apps/web/src/views/EntryView.vue:291-301`（keep）
5. 回到最近的会话继续 — `apps/web/src/views/EntryView.vue:317-327`（keep）
6. （仅管理员）调整统计口径（7/14/30 天、个人/全局）— `apps/web/src/views/EntryView.vue:6-14`（keep）
7. 用「核心转化漏斗」判断端到端链路是否健康 — `apps/web/src/views/EntryView.vue:28-63`（merge：六步与步骤 1、8 的数字重复且口径不同）
8. 用「问答质量洞察 / 补问闭环」判断答得好不好 — `apps/web/src/views/EntryView.vue:109-207`（demote：二次确认信息，不产生动作）
9. 点页头「统一问答」进入问答 — `apps/web/src/views/EntryView.vue:15`（drop：侧栏常驻同名入口）

## 元素清单
| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页面标题「业务总览」 | apps/web/src/views/EntryView.vue:4 | 可删 | 与顶栏 h1 同文案重复（`apps/web/src/layouts/MainLayout.vue:92` + `apps/web/src/router/index.ts:59`），同屏两个同名标题 |
| 个人数据 / 全局大盘 切换 | apps/web/src/views/EntryView.vue:6-9 | 必要 | 仅 platform_admin 可见（`apps/web/src/store/auth.ts:30-32`），管理员唯一的视角控制 |
| 近 7/14/30 天 选择器 | apps/web/src/views/EntryView.vue:10-14 | 必要 | 全页指标的唯一下钻口径（默认 14，`:356`）；但无 label，见存疑 |
| 「统一问答」主按钮 | apps/web/src/views/EntryView.vue:15 | 可删 | 侧栏常驻同入口（`apps/web/src/layouts/MainLayout.vue:216-219`）；移动端侧栏收进抽屉（`MainLayout.vue:78-80`）时它是唯一快入口，若保留即"有意的重复"，需 owner 裁决 |
| 「加载数据大盘…」spinner | apps/web/src/views/EntryView.vue:21-24 | 可合并 | 同屏另一处加载用骨架屏（`:280-282`、`:306-308`），两种加载语言 |
| 核心转化漏斗（6 步 + 5 箭头） | apps/web/src/views/EntryView.vue:28-63 | 可下沉 | 六步混用知识库/文档/问题/答案/反馈五种单位，无转化率；数字与 `:80-94`、`:120-130` 同义重复 |
| 「部分数据暂时降级…」提示条 | apps/web/src/views/EntryView.vue:31 | 可下沉 | 数据源是全局 `data_quality`（`:358`），却挂在漏斗标题行，容易被读成"只有漏斗降级" |
| 入库健康度 4 指标 | apps/web/src/views/EntryView.vue:78-95 | 必要 | 任务的核心判断依据；失败/卡住数是唯一"要不要处理"的信号 |
| 「去处理异常」按钮 | apps/web/src/views/EntryView.vue:72 | 必要 | 唯一把异常数字转成动作的入口；但当前无条件常驻（`:72` 无 v-if），无异常时也出现，建议加条件，见存疑 |
| 入库状态结论行（异常/处理中/就绪 3 态） | apps/web/src/views/EntryView.vue:96-104 | 必要 | 唯一用一句中文解释数字含义的元素 |
| 问答质量 3 指标 | apps/web/src/views/EntryView.vue:118-131 | 可下沉 | 与漏斗 `:54-62` 同义（grounded/feedback），对"我该做什么"无直接动作 |
| 「去检索调试」按钮 | apps/web/src/views/EntryView.vue:112 | 可删 | 文案指向检索调试，实际 push `/workspace/chat`（`:112`）；产品里的检索测试是 `/workspace/kb/debugger`（`MainLayout.vue:261-263`、`apps/web/src/router/index.ts:141-149`） |
| 质量条 3 行（有依据/依据不足/无依据拒答） | apps/web/src/views/EntryView.vue:132-148 | 可下沉 | 是 `:120-130` 分子的分母展开，二次确认信息 |
| 补问闭环面板 | apps/web/src/views/EntryView.vue:149-207 | 可下沉 | 单卡 9 个元素（标题/tooltip/说明/口径/3 指标/完成率/明细/类型标签），属专题页承载量 |
| 补问类型分布标签组 | apps/web/src/views/EntryView.vue:186-206 | 可下沉 | 每条说明藏在 tooltip（`:189-195`），首页不宜承载需 hover 才能读的内容 |
| 知识盲区（高频无命中）列表 | apps/web/src/views/EntryView.vue:215-224 | 必要 | 唯一给出"该补什么文档"的具体线索（query + 次数） |
| 热点词云 | apps/web/src/views/EntryView.vue:227-237 | 可删 | 数量仅由字号/透明度编码（`:232`），读不出准确值、不可点击；与 `:215-224` 同属"大家在问什么" |
| 满意度趋势条 + 图例 | apps/web/src/views/EntryView.vue:240-253 | 可删 | 柱高用 flex 在每天内部归一化（`:244-245`），跨天不可比；`|| 0.1` 让 0 也画出一根柱（假阳性）；日期只有原生 title（`:243`） |
| 消耗统计卡 | apps/web/src/views/EntryView.vue:256-272 | 可下沉 | 直接渲染原始字段名 `Prompt:` / `Completion:`（`:269-270`），与成本页 `apps/web/src/views/platform/CostDashboardView.vue` 同源 |
| 最近知识库列 | apps/web/src/views/EntryView.vue:277-303 | 必要 | 任务后半段的直接入口，点名 + 点击直达（`:296`，参数名与 `apps/web/src/views/kb/KBUploadView.vue:410` 一致） |
| 最近会话列 | apps/web/src/views/EntryView.vue:304-329 | 必要 | 同上（`:322`，参数名与 `apps/web/src/views/chat/UnifiedChatView.vue:202-207` 一致） |
| 骨架屏（两列各 4 条） | apps/web/src/views/EntryView.vue:280-282,306-308 | 可合并 | 与 `:21-24` 的 spinner 重复表达；且只渲染 4 条，接口却取 6 条（`:415`） |
| 空态 EnhancedEmpty（两处） | apps/web/src/views/EntryView.vue:283-289,309-315 | 可下沉 | 组件自带 72px 插画 + 56px 内边距（`apps/web/src/components/EnhancedEmpty.vue:88,103-108`），占位比列表本身还大 |
| 「N 篇」文档数 | apps/web/src/views/EntryView.vue:300 | 必要 | 判断这个库有没有内容的唯一数字——但当前恒为 `0`（见提案 1 与存疑） |
| 「N 问 / 继续」会话元信息 | apps/web/src/views/EntryView.vue:326 | 可删 | 接口不返回 message_count/question_count（`apps/services/api-gateway/database/migrations/001_init.sql:1-8`、`apps/services/api-gateway/src/app/gateway_chat_routes.py:182`），恒走 `'继续'` 分支，无信息量 |

## 提案（<=5 条，按杠杆排序）
| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/views/EntryView.vue:300（并含 :326 同类） | 少一次误操作 | 删掉恒为 `0` 的「N 篇」后，用户不会再把有文档的库当成空库去重复上传；代价是最近列表只剩名称、信息密度下降，`apps/web/src/views/EntryView.vue:326` 的「继续」也一并消失。若要真的显示文档数，成本更高的路径是补后端（`apps/services/knowledge-base/src/app/kb_base_routes.py:101-136` 的 `_decorate_base_rows` 增加计数）或前端按库逐个查文档（N+1 请求），本提案不采用 |
| 删除 | apps/web/src/views/EntryView.vue:240-253 | 少一次误操作 | 柱高按天归一化 + `\|\| 0.1` 会让"零反馈的一天"看起来有两条柱，删除可消除误判；代价是失去"满意度随时间变化"的唯一视图，趋势能力丢失，需 owner 确认接受。折中方案（一行"近 N 天 赞 X / 踩 Y"）会新增文案元素，偿还物是删掉 `:249-252` 的图例与 `:536-574` 的柱状样式 |
| 删除 | apps/web/src/views/EntryView.vue:112 | 少一次误操作 | 文案「去检索调试」与落点 `/workspace/chat` 不符，删除可避免"以为去调试检索、结果进了问答"；代价是「问答质量」卡退化为纯展示、失去唯一下钻入口。若保留则必须同时改文案、改目标为 `/workspace/kb/debugger`（该路由需 `kb.manage`，`apps/web/src/router/index.ts:145`）并补权限判断，成本高于删除 |
| 合并 | apps/web/src/views/EntryView.vue:28-63（并入 :78-95、:118-131） | 少一次判断 | 同一事实以两组字段名出现两次（`documents_ready` `:46` vs `ready_documents` `:84`；`grounded` `:56` vs `grounded_answers` `:136`；`feedback.up/down` `:61` vs 满意度趋势 `:244-245`），用户不需要判断"它们是不是同一个数"；代价是丢掉"上传→就绪→提问→有据回答→反馈"的端到端叙事，需 owner 确认可接受，若要在卡标题保留路径提示则会新增文案元素，偿还物是删掉漏斗的 5 个箭头图标（`:38,43,48,53,58`） |
| 加反馈 | apps/web/src/views/EntryView.vue:392-393（联动 :74-76、:114-116） | 少一次判断 | 加载失败后 `dashboardData` 置空，页面永久显示"暂不支持入库指标或服务降级"（`:75`）/"暂无问答质量数据"（`:115`），与"真的没有数据"不可区分（接口层只给一条 3 秒 toast，`apps/web/src/api/request.ts:151-161`）；代价是要新增"加载失败 + 重试"状态并区分加载中/失败/空三态，偿还物是把两处自写 `empty-state` 合并进已有的 `EnhancedEmpty` 调用（`:283-289`，净增 0 元素）；本页无单测，改动需人工回归 |

## 动效发现
| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 缓动与时长 | apps/web/src/components/EnhancedEmpty.vue:108-113（本页实例：apps/web/src/views/EntryView.vue:283-289,309-315） | 装饰插画（非可点元素）带 hover 位移+旋转 `scale(1.05) rotate(2deg)`，`0.3s` 已在 300ms 上限、曲线 `cubic-bezier(0.34,1.56,0.64,1)` 为回弹过冲，且未使用 `--transition-*` token；组件被 15+ 界面复用（本页两处） | 按 Less is more 第一步直接删掉 `:108-113` 的 `transition` 与 `:111-113` 的 hover transform；空态只需静态插画，无需替代物 |
| MEDIUM | 性能 / 一致性与 token | apps/web/src/views/EntryView.vue:665-676（使用点 :280-282、:306-308） | 骨架屏 `animation: skeleton-shimmer 1.2s ease-in-out infinite` 动的是 `background-position`（逐帧重绘、非合成属性），首页最多 8 个元素同时无限循环；1.2s 与 ease-in-out 均为硬编码，未用 `--transition-fast/base/smooth`；该 keyframes 全仓仅此一处 | 保留骨架屏则改为 `transform: translateX` 合成动画并把时长收敛到 token；若采纳「加载表达统一到 spinner」，整段 `@keyframes skeleton-shimmer` 可删 |
| MEDIUM | 缺失的机会 / 防止突变突兀 | apps/web/src/views/EntryView.vue:387-396 触发 :21-24 的整段替换 | 切换 7/14/30 天或 个人/全局 时 `loadingDashboard` 直接把整个大盘换成 spinner 再重建，内容闪断；滚动容器 `.entry-content`（`:439-446`，`overflow-y:auto`）在同一次交互中高度归零，滚动位置与视觉焦点丢失 | 不新增动效：保留旧数据渲染 + 局部 loading 指示（如标题行状态点），避免整段卸载重建；符合"缓动效"优先级最后一档之前先做减状态 |
| LOW | 一致性与 token / 状态指示 | apps/web/src/views/EntryView.vue:632-638（`.recent-item` 及其 hover） | hover 同时改背景（`--bg-panel-muted`→`--bg-panel`）与边框，背景变白后与所在卡片 `.recent-col`（`:612` 同为 `--bg-panel`）边界消失，两个信号方向相反；且该 hover 未包在 `@media (hover:hover) and (pointer:fine)` 内（全站已知问题的"只改色不改位移"特例） | 二者留一：只保留边框变实或只保留背景加深；并给该规则补 hover/pointer 媒体查询 |

## 存疑
- 「N 篇」恒为 0、「N 问」恒不出现，是我按静态链路推断的：`kb_bases` 无 `document_count` 列（`apps/services/knowledge-base/database/migrations/001_init.sql:3-10`），`_decorate_base_rows` 只补 `type_keys`/`job_positions`（`apps/services/knowledge-base/src/app/kb_base_routes.py:101-136`），网关对 `/api/v1/kb/{path}` 原样透传（`apps/services/api-gateway/src/app/gateway_admin_routes.py:172-174`），`chat_sessions` 无 `message_count`/`question_count` 列（`apps/services/api-gateway/database/migrations/001_init.sql:1-8`）且列表为 `SELECT *`（`gateway_chat_routes.py:182`）。验证：带 token 请求 `GET /api/v1/kb/bases`、`GET /api/v1/chat/sessions` 看返回体字段，或起真实数据渲染首页看是否恒显"0 篇"。
- 个人视图下 `funnel`/`ingest_health` 是否本来就会被后端降级，我未验证（页面文案 `:75` 暗示存在该状态）。验证：`GET /api/v1/analytics/dashboard?view=personal&days=14` 与 `view=admin` 对比字段。
- 角色到权限的权威映射我未找到（`chat.use`/`kb.read` 的具体授予见 `apps/services/api-gateway/src/app/gateway_runtime.py:12` 等定义处，未定位到角色表）。因此"权限不足的角色会在首页看到必然 403 的按钮"（`:15`、`:112` → `apps/web/src/router/index.ts:394-400` 跳 forbidden，而侧栏对同类入口做了过滤 `MainLayout.vue:270-286`）只在权限确实缺失时成立。验证：以 kb_viewer / audit_viewer 登录点这两个按钮。
- 窄屏下 `.health-quality-grid { grid-template-columns: repeat(auto-fit, minmax(360px,1fr)) }`（`:733-738`）在容器宽度 < 360px 时会横向溢出，而外层 `.page-shell` 是 `overflow-x:hidden`（`apps/web/src/style.css:190`）→ 内容可能被裁；我未逐条核对 `apps/web/src/styles/responsive-enhancements.css` 是否有覆盖。验证：375px 视口真机/窗口渲染本页看是否出现裁切。
- 深色模式：`darkThemeVars`（`apps/web/src/utils/theme.ts:11-35`）不含 `--success-color`/`--danger-color`/`--warning-color`/`--warning-bg`（本页 13 处依赖，`:559,563,573-574,690-691,729,795,799,807,839-841`）也不含 `--scrollbar-thumb`（`style.css:54-55`，本页滚动容器实际使用）；`theme.ts:12` 设的是名为 `--color-scheme` 的自定义属性，真正的 `color-scheme` 声明在 `style.css:2` 且深色下未被覆盖。结论是深色下这些状态色/原生控件仍取浅色值，但我未实际渲染核对视觉与对比度。验证：切深色模式截图本页，重点看 4 个状态 metric-box、降级提示条、滚动条。
- 「去处理异常」按钮（`:72`）无异常时也常驻，点击后目标页没有可处理的对象；是"条件显示"还是"常驻但显示为无异常文案"属产品决策，需 owner 确认（条件显示会引起布局位移，需固定位置）。
- 时间窗口选择器（`:10-14`）无 `aria-label`/label 关联，读屏只念当前值；需真机读屏确认严重程度。
- 本页无单测（未找到 EntryView 相关 `*.test.ts`），上述任何改动都只能靠人工回归，这是各提案"代价"里最实际的一项。
