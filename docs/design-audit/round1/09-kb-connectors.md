# 09 多源同步（连接器）

文件：`apps/web/src/views/kb/KBConnectorsView.vue` · 入口 `/workspace/kb/connectors`（`apps/web/src/router/index.ts:119-127`，`requiresPermission: 'kb.manage'`；侧栏 `apps/web/src/layouts/MainLayout.vue:251-252`，仅对 `kb.manage` 可见，`MainLayout.vue:279-286`）· 接口 `apps/web/src/api/kb.ts:766-796`

## 唯一用户任务
知识库管理员在不看命令行、不查审计日志的前提下，确认每个已接入的内部数据源（本地目录 / Notion / 网页 / 飞书 / 钉钉 / 数据库）是否正在按计划把内容送进目标知识库、上一次跑成什么样，并在它没跑或跑坏时就地补跑一次、或改掉配置。

## 完成该任务的必要步骤
1. 判断"我到底配过数据源没有"（空态 / 列表二选一）— `apps/web/src/views/kb/KBConnectorsView.vue:21-26`、`:28`（keep）
2. 逐张卡判断"它现在是不是正常在跑"（本页存在的唯一理由）— `apps/web/src/views/kb/KBConnectorsView.vue:44-57`（keep：卡片只有 知识库/类型/定时任务 三行，没有任何"上次同步时间 / 上次结果 / 下次运行"，本步骤当前无法完成 → 见提案 1）
3. 确认每个数据源送进哪个知识库 — `apps/web/src/views/kb/KBConnectorsView.vue:45-48`（merge：与 `:49-56` 同属一组属性，三行各占一行，见元素清单）
4. 点「添加数据源」— `apps/web/src/views/kb/KBConnectorsView.vue:5`（keep）
5. 填名称 — `apps/web/src/views/kb/KBConnectorsView.vue:65-67`（keep）
6. 选目标知识库 — `apps/web/src/views/kb/KBConnectorsView.vue:69-73`（keep：一个知识库都没有时该步骤无解，见存疑）
7. 选数据源类型（6 选 1）— `apps/web/src/views/kb/KBConnectorsView.vue:75-84`（keep）
8. 手写「配置 JSON」— `apps/web/src/views/kb/KBConnectorsView.vue:87-89`（keep：前端唯一配置入口，但 6 种类型 key 各不相同而页面零提示 → 见提案 3）
9. 决定开不开定时同步、间隔多少分钟 — `apps/web/src/views/kb/KBConnectorsView.vue:91-97`（keep：可选项下限与后端不一致 → 见提案 5）
10. 保存 — `apps/web/src/views/kb/KBConnectorsView.vue:99-102`（keep）
11. 点「立即同步」并读结果 — `apps/web/src/views/kb/KBConnectorsView.vue:38` → `:105-140`（keep：执行期间零反馈 → 见提案 2）
12. 读 4 个计数（新增/更新/跳过/软删除）— `apps/web/src/views/kb/KBConnectorsView.vue:107-112`（keep：与后端 counts 的 4 个键一一对应，`apps/services/knowledge-base/src/app/kb_connector_sync.py:213-216`）
13. 读逐项明细 — `apps/web/src/views/kb/KBConnectorsView.vue:113-132`（merge：`action`/`reason` 是后端机器码原样渲染，明细无折叠，100+ 文件时全量铺进 720px 弹窗）
14. 读「版本建议」4 行原始字段 — `apps/web/src/views/kb/KBConnectorsView.vue:124-130`（drop → 见提案 4）
15. 点「配置」改已建数据源的配置 — `apps/web/src/views/kb/KBConnectorsView.vue:39` → `:241-252`（keep）
16. 删除不再需要的数据源 — `apps/web/src/views/kb/KBConnectorsView.vue:40` → `:297-306`（merge：与「立即同步」「配置」在 `:37-41` 同级同排，低频危险动作没有层级差）
17. 区分 加载中 / 加载失败 / 空 三态 — `apps/web/src/views/kb/KBConnectorsView.vue:10-26`（keep：失败态是本页唯一做全的三态分支，有测试锁定，`apps/web/src/views/kb/KBConnectorsView.test.ts:1-85`）

## 元素清单
| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页内标题「多源数据同步」+ 副标题 | apps/web/src/views/kb/KBConnectorsView.vue:3 | 可删 | 与顶栏 h1 同屏（全局问题，`apps/web/src/layouts/MainLayout.vue:92`）；本页特例是同一目的地三个名字：页面写「多源数据同步」、路由 `apps/web/src/router/index.ts:124` 写「多源同步」、侧栏 `apps/web/src/layouts/MainLayout.vue:252` 写「多源同步」，而路由本来就有 `meta.title`/`meta.subtitle`（`router/index.ts:124-125`，subtitle 是空串）——页面又硬编码了一份标题与副标题 |
| 「添加数据源」按钮 | apps/web/src/views/kb/KBConnectorsView.vue:5 | 必要 | 全页唯一创建入口，也是空态文案 `:25` 指向的目标 |
| 加载态（旋转图标 +「加载数据源...」） | apps/web/src/views/kb/KBConnectorsView.vue:10-13 | 可合并 | 与 `:15-19` 失败态、`:21-26` 空态构成三套并列的三态表达；且 `:291`、`:305` 保存/删除后同样调 `loadData()`，整张列表会被这段 spinner 替换（见动效发现） |
| 失败态 +「重新加载」 | apps/web/src/views/kb/KBConnectorsView.vue:15-19 | 必要 | 唯一把"请求失败"与"确实没有数据源"分开的元素，有测试锁定（`apps/web/src/views/kb/KBConnectorsView.test.ts:1-85`） |
| 空态 EnhancedEmpty | apps/web/src/views/kb/KBConnectorsView.vue:21-26 | 必要 | 唯一给出"点右上角"下一步的元素；组件本体 72px 插画（`apps/web/src/components/EnhancedEmpty.vue:103-104`）与 56px 内边距（`EnhancedEmpty.vue:88`）已在 03-entry 报告，本页是它的第 N 个使用者 |
| 数据源卡容器 | apps/web/src/views/kb/KBConnectorsView.vue:29、`:372-380` | 可合并 | 背景 + 1px 边框 + `--radius-md` + 20px padding 的基础卡片在约 19 个界面各写一遍（全局已知）；本页卡片自身无任何状态表达、无 hover |
| 类型图标 | apps/web/src/views/kb/KBConnectorsView.vue:32-34 | 可删 | 6 种类型只映射到 3 个图标（`:213-217`：sql_query→Coin、web_crawler→Position、其余全部→Document），飞书/钉钉/Notion/本地目录都显示同一个 Document；类型名已在 `:50-51` 出现，图标不承载新信息；`:219-221` 生成的 `icon-<type>` class 在 `apps/web/src` 下零定义（悬空 class） |
| 数据源名称 | apps/web/src/views/kb/KBConnectorsView.vue:35 | 必要 | 用户识别对象的唯一标签（列表既不显示 connector id，也不显示状态与时间） |
| 「立即同步」按钮 | apps/web/src/views/kb/KBConnectorsView.vue:38 | 必要 | 唯一手动补跑入口；请求全程无 loading/disabled → 见提案 2 |
| 「配置」按钮 | apps/web/src/views/kb/KBConnectorsView.vue:39 | 必要 | 唯一编辑入口 |
| 「删除」按钮 | apps/web/src/views/kb/KBConnectorsView.vue:40 | 可合并 | 低频 + 危险，却与两个高频按钮同级同排（`:37-41`）；确认框文案只说"该数据源"（`:299`）不含名称，多建几个数据源后无法确认删的是哪一个 |
| 「知识库:」行 | apps/web/src/views/kb/KBConnectorsView.vue:45-48 | 可合并 | 与 `:49-56` 同属一组属性；`.detail-item` 用 `justify-content: space-between`（`:408-411`）把标签与值拉到两端，每行一个标签 |
| 「类型:」行 | apps/web/src/views/kb/KBConnectorsView.vue:49-52 | 可合并 | 与 `:32-34` 的图标重复表达同一字段 |
| 「定时任务:」行 | apps/web/src/views/kb/KBConnectorsView.vue:53-56 | 可合并 | 唯一表达调度状态的元素；"已禁用"（`:55`）指"调度关"，与连接器自身的 `status`（后端可 active/paused，`apps/services/knowledge-base/src/app/kb_schemas.py:597-611`）不是一回事，而 `status` 本页完全不显示 |
| 创建/编辑弹窗 | apps/web/src/views/kb/KBConnectorsView.vue:63-103 | 必要 | 唯一配置入口，标题按 `editingConnector` 切换（`:63`） |
| 「数据源名称」输入 | apps/web/src/views/kb/KBConnectorsView.vue:65-67 | 必要 | 有必填校验（规则 `:171-174`） |
| 「目标知识库」下拉 | apps/web/src/views/kb/KBConnectorsView.vue:69-73 | 必要 | 有必填校验（`:171-174`）但无空态提示；一个知识库都没有时用户只能停在这一步（见存疑） |
| 「数据源类型」下拉 | apps/web/src/views/kb/KBConnectorsView.vue:75-84 | 必要 | 编辑态 disabled（`:76`），避免误改类型导致后续文档错位（合理） |
| 「配置 JSON」文本域 | apps/web/src/views/kb/KBConnectorsView.vue:87-89 | 必要 | 前端唯一配置入口；6 种类型要的 key 完全不同（`apps/services/knowledge-base/src/app/kb_connector_routes.py:149-181`：local_directory→`source_path`、notion→`page_ids`、web_crawler/feishu_document/dingtalk_document→`urls`、sql_query→`dsn_env`+`query`），页面零提示；预填只对 web 类型正确（`:237`），且切换类型不重填（`:145` 只引入 `ref`/`onMounted`，无 `watch`）→ 见提案 3 |
| 「定时同步」开关 + 分钟数 | apps/web/src/views/kb/KBConnectorsView.vue:91-97 | 必要 | `:min="10"`（`:94`）低于后端 `ge=15`（`apps/services/knowledge-base/src/app/kb_schemas.py:563`），10–14 分钟必然保存失败 → 见提案 5 |
| 弹窗 footer（取消/保存） | apps/web/src/views/kb/KBConnectorsView.vue:99-102 | 必要 | 保存按钮有 `:loading="saving"`（`:101`）——本页唯一做对的执行中态 |
| 同步结果弹窗 | apps/web/src/views/kb/KBConnectorsView.vue:105-140 | 必要 | 手动同步后唯一的反馈载体（`width="720px"`，窄屏由 `apps/web/src/styles/responsive-enhancements.css` 统一收敛，不计问题） |
| 结果 4 个计数 | apps/web/src/views/kb/KBConnectorsView.vue:107-112 | 必要 | 唯一把本次同步翻译成人能读的数字；4 项与后端 counts 的键完全对应（`apps/services/knowledge-base/src/app/kb_connector_sync.py:213-216`） |
| 结果逐项明细 | apps/web/src/views/kb/KBConnectorsView.vue:113-122 | 可下沉 | 同步 100+ 文件时全量渲染（无折叠、无分页），720px 弹窗里要滚很久；`action` 标签直接渲染后端机器码（`apps/services/knowledge-base/src/app/kb_connector_sync.py:88,108,119,135`：create/skip/update/soft_delete） |
| 结果的 reason 行 | apps/web/src/views/kb/KBConnectorsView.vue:123 | 可合并 | 同样是机器码（`apps/services/knowledge-base/src/app/kb_connector_sync.py:92,100,102,104,113,140`：new_source / restore_deleted_source / content_changed / file_name_changed / unchanged / missing_from_source） |
| 「版本建议」面板 | apps/web/src/views/kb/KBConnectorsView.vue:124-130、`:457-471` | 可删 | 4 行原始字段名（family/label/supersedes/confidence）；`:461` 的 `var(--color-primary)` 在 `apps/web/src` 下 100 个 vue/css/ts 文件中零定义（`:461` 是全仓唯一引用点），`color-mix` 遇无效自定义属性整条声明失效 → 背景实际透明 → 见提案 4 |
| 结果弹窗空态 EnhancedEmpty | apps/web/src/views/kb/KBConnectorsView.vue:133-138 | 可合并 | 同一组件在本页第二处实例（第一处 `:21-26`）；用 72px 插画回答"这次没什么可看的" |

## 提案（<=5 条，按杠杆排序）
| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 加反馈 | apps/web/src/views/kb/KBConnectorsView.vue:44-57 | 少一次判断 | 后端早已返回这些字段（`apps/services/knowledge-base/src/app/kb_connector_routes.py:36-42` 的 `last_run_at`/`last_result`/`next_run_at`），并且有一个现成却全仓无人调用的接口 `getConnectorRuns`（`apps/web/src/api/kb.ts:787-788`），所以这不是"要不要做"而是"页面没接"。真代价：`last_result` 有两种形态——成功存 `{counts, items}`、失败只存 `{error_message}`（`kb_connector_routes.py:229-240`），失败时要显示的是后端英文异常文本，想中文化得再做一层映射；`last_run_at` 为空（新建未跑）需要定"尚未同步"的占位文案；`:308-317` 的 `runSync` 成功后不刷新列表，必须同时补 `loadData()`，否则新加的那行永远停在旧值；偿还物是把 `:45-56` 三行属性并成一行 meta（净增 0 行）。本页列表渲染路径无单测（`apps/web/src/views/kb/KBConnectorsView.test.ts:1-85` 只覆盖失败态与重试），改动只能人工回归 |
| 加反馈 | apps/web/src/views/kb/KBConnectorsView.vue:38（联动 `:308-317`） | 少一次误操作 | 手动同步是同步阻塞请求（`apps/services/knowledge-base/src/app/kb_connector_routes.py:426-461`），执行期间按钮既无 `loading` 也无 `disabled`，每点一次就是一次真实写入；仓库里已有现成模式可抄（`apps/web/src/views/kb/KBOperationsView.vue:187-195` 的 `runningConnectorId` + 执行中文案）。真代价：大目录同步会让按钮长时间停在"执行中..."而没有任何进度，用户可能以为卡死；要进度就得引入轮询 `getConnectorRuns`（`apps/web/src/api/kb.ts:787-788`），那是另一个更大的改动。偿还物是删掉 `:313` 的「同步任务已提交」——该接口返回即已完成，"已提交"是假反馈，删掉后"已发出"的即时信号消失、反馈延迟到请求返回；同时 `:314-316` 把任何失败都吞成一句「同步提交失败」，与 request 层已经弹过的错误提示（`apps/web/src/api/request.ts:151-159`）重复，需一并收敛成一条 |
| 加反馈 | apps/web/src/views/kb/KBConnectorsView.vue:87-89（联动 `:237`、`:250`） | 少一次误操作 | 两个真实风险被这一行空白框藏住：（a）6 种类型要的 key 不同（`apps/services/knowledge-base/src/app/kb_connector_routes.py:149-181`），页面不提示，用户只能猜写；（b）`delete_missing` 默认是 `true`（`kb_connector_routes.py:142`），意味着源里消失的文件会在知识库中被软删除，而该键在新增（`:237` 只预填 `urls`）与编辑（`:250` 回显已存 config，没有该键）两条路径上都不可见，用户只在同步完成后从 `:111` 的"软删除 N"才第一次知道。真代价：要为 6 种类型各写一份必填 key 提示，这份契约会随后端漂移（当前只在一处写死预填）；把 `delete_missing` 提成可见开关会新增一个表单项，偿还物是删掉 `:237` 那段只对 web_crawler 正确的预填示例。若产品坚持"配置靠手写 JSON"，那至少要在 `:87` 的标签里写明当前类型必填哪些 key |
| 删除 | apps/web/src/views/kb/KBConnectorsView.vue:124-130（含样式 `:457-471`） | 少一次判断 | 这 4 行是 family/label/supersedes/confidence 原始字段名，删掉可省一次"这是给我看的还是给系统看的"判断，并顺手清掉 `:461` 这处全仓唯一的无效 token（`--color-primary` 零定义，背景已实际透明）。真代价：失去"这条新增文档是否与既有版本重复"的唯一提示——且它只在成功同步后出现一次；若产品要保留该能力，成本更高的路径是改成一句中文 + 用已有 token 重写 `:461`（如 `--blue-50`）、并定义 confidence 的取舍阈值，成本高于删除。本页无单测，删除后在结果弹窗里不会有任何回归信号 |
| 删除 | apps/web/src/views/kb/KBConnectorsView.vue:94 | 少一次误操作 | 把可选区间收到后端真能接受的范围，删掉 10–14 这段永远提交不了的取值：`:min="10"` 与 `apps/services/knowledge-base/src/app/kb_schemas.py:563` 的 `ge=15`（配合 `:567-568`：enabled 时 interval_minutes 必填）直接冲突，用户选 10–14 会在保存时被拒，屏幕上只有 request 层的通用提示「请求参数错误，请检查输入后重试。」（`apps/web/src/api/request.ts:93`），既不指向"定时同步"这一项，也不说下限是 15。真代价：若产品确实要 10 分钟档，就必须同时改后端 `ge=15` 并确认调度轮询节奏能支撑（`apps/services/knowledge-base/src/app/kb_connector_scheduler.py:20-104`），本提案不采用；另外把 min 改成 15 后，默认值 60（`:235`）与下限之间仍有距离，用户仍可能手输非法值再被夹回，提示缺失只解决了一半 |

## 动效发现
| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| MEDIUM | 状态指示 / 操作反馈 | apps/web/src/views/kb/KBConnectorsView.vue:38（触发与反馈 `:308-317`） | 手动同步是全程无状态指示的阻塞请求：按钮没有 `loading`、也没有 `disabled`，请求进行中可反复点击，每次都是一次真实的全量同步写入（`apps/services/knowledge-base/src/app/kb_connector_routes.py:426-461`）；唯一反馈是请求返回后的一句「同步任务已提交」（`:313`），而它描述的动作在请求返回时其实已经完成了——属于操作反馈与真实状态不一致 | 不新增动效，只补状态：复用仓库已有模式 `syncingId` + 按钮 `:loading`/`:disabled`（`apps/web/src/views/kb/KBOperationsView.vue:187-195`），并把 `:313` 的假反馈替换为对结果弹窗的指向 |
| MEDIUM | 缺失的机会 / 防止突变突兀 | apps/web/src/views/kb/KBConnectorsView.vue:291、`:305` → `:10-13` | 保存成功后（`:291`）与删除数据源后（`:305`）都调 `loadData()`，于是 `:10-13` 的 loading 分支把整个 `.connector-list` 卸载、换成 padding 48px 的 spinner，再整体重建；卡片网格 `.connector-list`（`:366-370`）高度在这一次交互中归零又回来，滚动容器 `.connectors-content`（`:332-337`，`overflow-y: auto`）的滚动位置与"我刚改的是哪一张卡"的视觉锚点一起丢失 | 不新增动效：把 `loading` 限定为首次加载，保存/删除后的刷新保留旧数据渲染 + 局部 busy 指示（例如卡片自身的状态），避免整段卸载重建；符合 Less is more 里"减状态"优先于"缓动效"的顺序 |
| LOW | 一致性与 token | apps/web/src/views/kb/KBConnectorsView.vue:324-472（整段 scoped 样式） | 本页自研动效为零：`transition`、`animation`、`@keyframes`、`:hover`、`@media` 在本文件 grep 全部零命中；页面上唯一"动"的是 Element Plus 自带件（`:11` 的 `is-loading` 旋转图标、`:63` 与 `:105` 两个弹窗的出场），它们走 EP 自己的过渡变量，与 `--transition-fast/base/smooth` 无关联；好处是本页不动任何高频元素，风险是弹窗时长与曲线完全不受本项目 token 约束（`EnhancedEmpty` 的插画 hover 位移问题已在 03-entry 报告，本页仅复用它两次：`:21-26`、`:133-138`，此处不重复） | 维持现状不要在 `:324-472` 新增自研动效；若要统一弹窗手感，只改 EP 的主题变量（如 `--el-transition-duration`），不要给本页新增逐元素的 transition |

## 存疑
- 列表渲染 / 同步 / 结果弹窗三条路径均无单测：`apps/web/src/views/kb/KBConnectorsView.test.ts` 全文 85 行，主要覆盖加载失败态与重试、以及 `listConnectors` 失败时不弹全局 toast；`:22-26` 空态、`:28-58` 卡片、`:105-140` 结果弹窗、`:308-317` 同步流程都未覆盖。因此我为提案 1/2 都写了"只能人工回归"。验证：`cd apps/web && npx vitest run src/views/kb/KBConnectorsView.test.ts --coverage`，看该文件的行覆盖分布。
- `last_result` 的真实形态是我按 `_finish_run_record`（`apps/services/knowledge-base/src/app/kb_connector_routes.py:229-240`）推断的"成功存 counts/items、失败只存 error_message"，我没有实际制造过一次失败的同步去核对返回体。验证：把某个 local_directory 数据源的 `source_path` 改成一个不存在的目录后点「立即同步」，看 `GET /api/v1/kb/connectors` 返回的 `last_result` 字段。
- 一个知识库都没有时，`bases` 为空（`:183-187`）、`:69-73` 下拉无选项、`:230-236` 把 `base_id` 预置为空串；`:171-174` 的 rules 又把 `base_id` 设为必填，于是用户会拿到"请选择目标知识库"却无从选择（下拉里没有任何选项，页面也不提供"去创建知识库"的出口）。验证：用一个没有任何知识库的账号打开本页并点「添加数据源」。
- 「已禁用」（`:55`）指的是调度关闭，而连接器自身还有一个 `status`（后端接受 active/paused，`apps/services/knowledge-base/src/app/kb_schemas.py:597-611`）本页既不显示也不可切换。这是"暂不提供停用能力"还是"漏做"属产品决策，需 owner 确认。
- `:461` 的 `var(--color-primary)` 在 `apps/web/src` 下零定义（100 个 vue/css/ts 文件全量搜索无定义，`:461` 为唯一引用点）。我按 CSS 规范推断 `color-mix` 遇到无效自定义属性时整条声明在 computed-value 阶段失效、面板背景实际透明，但没有真机截图确认浏览器对 `color-mix` 加无效 var 的具体处理。验证：DevTools 选中 `.sync-result__assist`（`:457-471`）看 background 是否被划掉。
- 窄屏：`.connectors-content` 固定 padding 20px（`:335`）叠加 `.connector-list` 的 `minmax(360px, 1fr)`（`:368`），在可用宽度小于约 400px 时卡片会被 `.connectors-page` 的 `overflow: hidden`（`:329`）裁掉且没有横向滚动；`apps/web/src/styles/responsive-enhancements.css` 是否覆盖本页我未逐条核对。验证：375px 视口渲染本页看是否有裁切。
- 「版本建议」面板的出现条件（`:124`）依赖 `item.version_assist?.suggested_version_family_key`，我未找到该字段的生成处与它的 confidence 分布，因此无法判断"该提示是否常常为空"。验证：在 `apps/services/knowledge-base/src/app/` 下定位 `version_assist` 的构造点，或跑一次真实同步看结果弹窗里是否出现该块。
