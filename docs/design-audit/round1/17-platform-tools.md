# 17 工具管理 / 记忆管理

审计对象：`apps/web/src/views/platform/ToolManagerView.vue`（333 行）、`apps/web/src/views/platform/MemoryManagerView.vue`（374 行）
路由：`/workspace/platform/tools`、`/workspace/platform/memory`（`apps/web/src/router/index.ts:227-248`）
审计性质：只读。本文件是本次审计唯一写入的文件。

## 唯一用户任务

运维人员（或任何能用聊天的用户，见存疑 5）在 Agent 行为出现异常后——某个工具被误调用、某条记忆导致答非所问——要在这两个页面里定位到那一个工具或那一条记忆，并切断它对后续回答的影响。

## 完成该任务的必要步骤

**工具管理**

1. 打开页面，扫过顶部 4 张统计卡 —— **drop**（`ToolManagerView.vue:14-31`：四个数字与"定位并停用某个工具"没有因果关系）
2. 缩小范围：用分类 Tab 过滤，或在卡片网格里直接找 —— **keep**（`ToolManagerView.vue:34-37`、`:51-93`）
3. 读出该工具的当前状态 —— **merge**（`ToolManagerView.vue:60-62` 的状态 tag 与 `:66-71` 的开关是同一状态的两处表达；`:78-89` 的三个数字里只有成功率是"该不该停用"的判据）
4. 用开关停用或启用 —— **keep**（`ToolManagerView.vue:66-71`，唯一操作入口；乐观更新 + 失败回滚见 `:144-154`）
5. 确认生效 —— **keep**（`ToolManagerView.vue:148` 成功提示；但生效范围仅限进程内，见存疑 1）

**记忆管理**

1. 打开页面，看顶部统计 —— **merge**（`MemoryManagerView.vue:14-27`：「总记忆条目」`:15-18` 是唯一展示总量的位置，分页器 `layout="prev, pager, next"`（`:127`）不显示总数，故保留；分类型卡 `:23-26` 的数量由后端 `by_type` 键数决定，层级应低于前两张）
2. 缩小范围：语义搜索或按类型筛选 —— **keep**（`MemoryManagerView.vue:31-42`、`:43-48`）
3. 在表格里读到目标行（类型/主体/关系/内容）—— **keep**（`MemoryManagerView.vue:69-82`）；其中置信度列 **demote**（`:83-93` 三重编码）、创建时间列 **drop**（`:101-105` 不可排序，见元素清单）
4. 点「停用」，并在确认框里核对内容 —— **keep**（`MemoryManagerView.vue:106-119`、`:239-244`；确认框回显 `subject + predicate + object` 是这一步唯一的关键保护）
5. 确认生效 —— **keep**（`MemoryManagerView.vue:96-98` 状态列翻转；无恢复路径，见存疑 2）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 工具页标题「工具注册中心」 | apps/web/src/views/platform/ToolManagerView.vue:3 | 必要 | 定位当前界面 |
| 工具页副标题 | apps/web/src/views/platform/ToolManagerView.vue:3 | 可删 | 是"注册、启停、MCP服务接入与执行统计"的功能枚举，与本页唯一任务（定位并停用某工具）无关，且枚举项中两项本页没有任何入口（见 `:23-30`） |
| 「刷新」按钮 | apps/web/src/views/platform/ToolManagerView.vue:5-8 | 必要 | 唯一的手动同步入口（注册状态可能被外部改动），且自带 loading |
| 统计卡「已注册工具」 | apps/web/src/views/platform/ToolManagerView.vue:15-18 | 可合并 | 数值取自 `summary.registered_tools`（`:16`），而卡片下方的列表受 `activeCategory` 过滤（`:128`）：切到某个类别后"卡片说 N 个、列表只显示 M 个"，两个数字互相矛盾 |
| 统计卡「工具类别」 | apps/web/src/views/platform/ToolManagerView.vue:19-22 | 可删 | 与 `:34-37` 的 Tab 完全同源（`:132-134` 从 `summary.tools` 派生出 `categories`），Tab 已把类别逐一列举 |
| 统计卡「MCP服务」 | apps/web/src/views/platform/ToolManagerView.vue:23-26 | 可删 | 全文件没有任何 MCP 接入/查看/操作入口，"mcp_servers"这个数字在本页不挂任何用户目标 |
| 统计卡「缓存条目」 | apps/web/src/views/platform/ToolManagerView.vue:27-30 | 可删 | 对应后端 `tool_registry._cache`（`tool_registry.py:471`），是工具发现子系统的内部量，本页无清理或查看入口 |
| 分类 Tab 行 | apps/web/src/views/platform/ToolManagerView.vue:34-37 | 必要 | 工具数量增长后唯一的范围缩小手段 |
| 加载态 | apps/web/src/views/platform/ToolManagerView.vue:39-42 | 可删 | 与 `:44` 空态、`:51` 列表构成三态硬切换，加载时整块内容塌陷（见动效发现 3）；刷新路径上按钮自带 loading（`:5`），这里的独立加载块是第二重反馈 |
| 空态 EnhancedEmpty | apps/web/src/views/platform/ToolManagerView.vue:44-49 | 必要 | 捕获"注册表为空"这一真实状态，并给出成因文案 |
| 工具卡 图标 | apps/web/src/views/platform/ToolManagerView.vue:54-56 | 可删 | 图标内容是 `category` 的 emoji 映射（`:164-169`），与下方 `:64` 的类别文本表达同一事实；底色来自 `categoryColor`（`:156-162`）5 个硬编码色值，不在 token 内 |
| 工具卡 状态 tag | apps/web/src/views/platform/ToolManagerView.vue:60-62 | 可删 | 与 `:66-71` 的开关表达同一状态；`effect="dark"` 使它成为卡内视觉最重的元素，压过工具名（`:59`） |
| 工具卡 工具名 | apps/web/src/views/platform/ToolManagerView.vue:59 | 必要 | 唯一定位字段（`:282-284` 单行省略，超长名会被截断） |
| 工具卡 类别文本 | apps/web/src/views/platform/ToolManagerView.vue:64 | 必要 | 若图标删除，这是类别信息的唯一载体 |
| 工具卡 启停开关 | apps/web/src/views/platform/ToolManagerView.vue:66-71 | 必要 | 唯一操作入口 |
| 工具卡 描述 | apps/web/src/views/platform/ToolManagerView.vue:73-75 | 必要 | "这个工具是干什么的"是停用前的判据；`:296-304` 用 `-webkit-line-clamp: 2` 截断且无展开/tooltip，超长描述读不全（见存疑 4） |
| 工具卡 成功率 | apps/web/src/views/platform/ToolManagerView.vue:82-85 | 必要 | 三个数字里唯一能支撑"是否停用"决策的信号 |
| 工具卡 调用次数 | apps/web/src/views/platform/ToolManagerView.vue:78-81 | 可下沉 | 只有成功率异常时才需要它来区分"从未被调用"与"调用后失败"，常态下是与另两个数字等权的噪声 |
| 工具卡 平均耗时 | apps/web/src/views/platform/ToolManagerView.vue:86-89 | 可下沉 | 用户无法据此做任何处置动作（本页没有超时/重试配置） |
| scoped 样式中的字面量刻度 | apps/web/src/views/platform/ToolManagerView.vue:206-216 | 可合并 | 字号 24px/12px（`:207`、`:214`）不在 `--text-h1/h2/body/caption` 刻度内（style.css:32-35）；同类问题见 `.tool-icon` 圆角 10px（`:259`）、`.tool-cat` 11px（`:288`）、`.tool-desc` 13px（`:297`）、`.stat-num` 14px（`:324`）、`.stat-lbl` 11px（`:331`） |
| 记忆页标题「记忆管理」 | apps/web/src/views/platform/MemoryManagerView.vue:3 | 必要 | 定位当前界面 |
| 记忆页副标题 | apps/web/src/views/platform/MemoryManagerView.vue:3 | 可删 | "浏览和管理…长期记忆与用户偏好"是功能描述；本页唯一动作是"停用某条记忆"，描述里并未提及，且未提"停用后不可恢复" |
| 「刷新」按钮 | apps/web/src/views/platform/MemoryManagerView.vue:5-8 | 必要 | 唯一的手动同步入口 |
| 统计卡「总记忆条目」 | apps/web/src/views/platform/MemoryManagerView.vue:15-18 | 必要 | 分页器不含 total 展示（`:127`），这是唯一能看到总量的位置 |
| 统计卡「活跃记忆」 | apps/web/src/views/platform/MemoryManagerView.vue:19-22 | 必要 | 唯一汇总"还有多少条仍在影响回答"的数字，正是本页任务的量化表达 |
| 统计卡 分类型计数 | apps/web/src/views/platform/MemoryManagerView.vue:23-26 | 可合并 | 卡片数量由后端 `by_type` 的键数决定（`v-for="(count, type) in memoryStats?.by_type"`，`:23`），排版不稳定；且与 `:43-48` 的类型筛选枚举同一组类型 |
| 搜索框 | apps/web/src/views/platform/MemoryManagerView.vue:31-42 | 必要 | 主定位手段（`:35` 回车提交，`:36` 清空回落列表） |
| 记忆类型下拉 | apps/web/src/views/platform/MemoryManagerView.vue:43-48 | 必要 | 与搜索组合缩小范围（`:206`、`:230` 同时下单） |
| 下拉中的「全部」option | apps/web/src/views/platform/MemoryManagerView.vue:44 | 可删 | `clearable`（`:43`）已表达同一状态，同一时刻有两种"取消筛选"的入口 |
| 「搜索」按钮 | apps/web/src/views/platform/MemoryManagerView.vue:49-52 | 必要 | 唯一的可见提交控件，回车（`:35`）只是快捷方式 |
| 表格列 类型 | apps/web/src/views/platform/MemoryManagerView.vue:69-75 | 必要 | 判断该条记忆的性质（`:71-73` 已映射为中文标签） |
| 表格列 主体 | apps/web/src/views/platform/MemoryManagerView.vue:76 | 必要 | 定位字段 |
| 表格列 关系 | apps/web/src/views/platform/MemoryManagerView.vue:77 | 必要 | 与主体、内容共同构成可读的三元组 |
| 表格列 内容 | apps/web/src/views/platform/MemoryManagerView.vue:78-82 | 必要 | 主判据（`:80` 用 `.inactive-text` 把停用行整体弱化，是有效的层级手段） |
| 表格列 置信度 | apps/web/src/views/platform/MemoryManagerView.vue:83-93 | 可下沉 | 同一数字被编码三次：进度条长度（`:85-90`）、三档色（`:87` 硬编码 `#67c23a`/`#e6a23c`/`#f56c6c`，EP 默认色板、不在 token 内）、百分比文本（`:91`） |
| 表格列 状态 | apps/web/src/views/platform/MemoryManagerView.vue:94-100 | 可合并 | 与 `:117` 的「已停用」文本表达同一状态（同一行里出现两次） |
| 表格列 创建时间 | apps/web/src/views/platform/MemoryManagerView.vue:101-105 | 可删 | 占 155px 宽；全表没有任何 `sortable` 列，无法按时间排序，对"找出那条错误记忆"不是可用定位方式（后端默认按 `updated_at DESC`，`gateway_platform_routes.py:300`） |
| 表格列 操作 | apps/web/src/views/platform/MemoryManagerView.vue:106-119 | 必要 | 唯一的处置入口（`:239-244` 带内容回显确认） |
| 操作列「已停用」文本 | apps/web/src/views/platform/MemoryManagerView.vue:117 | 可删 | 与状态列 tag（`:96-98`）重复；且它在"操作"列里没有任何可操作性，白白占位 |
| 分页器 | apps/web/src/views/platform/MemoryManagerView.vue:122-131 | 必要 | 唯一翻页入口，但搜索态下数据源错误（见提案 1） |
| 「高频记忆主体」标题 | apps/web/src/views/platform/MemoryManagerView.vue:135-137 | 可删 | 与其下方 chips 同生共死，`:135` 还带内联 `margin-top: 28px` |
| 高频主体 chips | apps/web/src/views/platform/MemoryManagerView.vue:138-143 | 可删 | 有 pill 外观（`:357` `border-radius: 20px`）却没有任何 click handler，看上去可点；位置在表格与分页之后；不服务于本页唯一任务 |
| 模板内联 style 属性 | apps/web/src/views/platform/MemoryManagerView.vue:37 | 可合并 | 同文件共 6 处内联样式（`:37`、`:43`、`:68`、`:91`、`:117`、`:135`），其中 `:91` 的 `font-size: 11px` 与 `:117` 的 `font-size:12px` 是同一语义的两种写法，且都不在 `--text-caption`（12px）刻度内 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 删除 | apps/web/src/views/platform/MemoryManagerView.vue:122-131 | 少一次误操作 | 搜索态下分页器会把用户带到未经过滤的数据：`@current-change="loadMemories"`（`:128`）恒调列表接口，而搜索走的是另一条链路（`:222-237`），且搜索返回的 `total` 就是它返回的行数、上限 50（`gateway_platform_routes.py:322`、`:310`，前端写死 `limit: 50` 见 `:229`）。命中超过 pageSize=20（`:177`）时，点第 2 页看到的是与关键词无关的记忆，用户可能在那里停用错误的条目。代价：禁用分页器后（仅搜索态）用户无法翻看第 21-50 条匹配结果；根治办法是给搜索加 offset 分页，但后端 `search` 路由没有 offset 参数（`gateway_platform_routes.py:310`），在补齐前"隐藏分页器"比"显示一个会跳错数据的分页器"更保守。 |
| 删除 | apps/web/src/views/platform/ToolManagerView.vue:60-62 | 少一次判断 | 同一状态在卡内有 tag 与开关两处表达，且 `effect="dark"` 的 tag 是卡内最重的视觉元素，与工具名（`:59`）争夺第一眼。只能删 tag：删开关会失去唯一操作入口。代价：扫视多张卡时"哪些被停用"的识别信号变弱，只能靠开关小圆点的位置/颜色（Element Plus 默认尺寸较小，色彩编码对色觉障碍用户不友好），需确认停用状态在实际网格里是否仍能一眼分辨。 |
| 删除 | apps/web/src/views/platform/ToolManagerView.vue:14-31 | 少一次判断 | 四张卡占据首屏最上方、最重的层级，但它们不参与"定位并停用某工具"：`:19-22` 与 `:34-37` 的 Tab 同源，`:23-26`、`:27-30` 在本页没有任何操作入口，`:15-18` 还会与分类过滤后的列表长度冲突。代价：MCP 服务数与缓存条目数将失去全站唯一展示位（`getToolRegistrySummary` 在整个前端只被 `:104` 这一处引用），需确认这两个数字是否还有人消费；另外首屏不再显示工具总数，分类过滤时列表长度不等于总数。 |
| 降层级 | apps/web/src/views/platform/MemoryManagerView.vue:85-91 | 少一次判断 | 置信度用了"条长 + 三档色 + 数字"三重编码，而决策只需要数字本身；`:87` 的三个色值是 EP 默认色板、不在 token 内，等于在本页引入了第三套颜色语义。代价：失去按低/中/高扫视分组的能力，而表格没有 `sortable`、也没有按置信度筛选的入口——如果"靠颜色一眼找出低置信度记忆"是用户的真实工作流，降为纯数字会让它变慢。需先确认该工作流是否存在，再在"保留色彩编码并补排序"与"降为纯数字"之间二选一。 |
| 删除 | apps/web/src/views/platform/MemoryManagerView.vue:135-143 | 少一次判断 | chips 有圆角胶囊外观却没有任何交互（`:139` 无 `@click`），给用户"可以点进去看这个主体的记忆"的错误预期；且位于表格与分页之后，与本页唯一任务无关。代价：失去记忆库主题分布的唯一致视图；若产品确有"点主体即筛选"的意图，后端 `search` 已支持 `subject ILIKE`（`gateway_platform_routes.py:313`）具备实现条件，但那是新增交互，需要先偿还——不能以"将来可能有用"作为保留理由。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| HIGH | 一致性与 token | apps/web/src/views/platform/ToolManagerView.vue:246-248 | `.tool-card:hover` 的 `border-color: var(--blue-400)` 引用了一个不存在的变量：`--blue-400` 在 style.css:17-20 与 utils/theme.ts:11-35（明暗两套）中都没有定义，本仓库 `src/` 内共有 8 个文件、9 处引用它，0 处定义。自定义属性未定义时该声明在计算值阶段失效，`border-color` 回退到初始值 `currentColor`——即卡内继承的文字色：浅色主题下 hover 让边框变近黑，深色主题下变近白，与"蓝色高亮"的意图完全相反。 | 二选一：删除整条 hover（该卡不可点击，见下条）；或改用已定义的 `--blue-500`/`--blue-600`。变量本身应补进 style.css:1-84 与 utils/theme.ts 的明暗两套变量——这是跨界面的全局决策，本文件不宜单独引入新色值。 |
| MEDIUM | 目的与频次 | apps/web/src/views/platform/ToolManagerView.vue:243,246-248 | hover 只改边框色，却加在一个没有任何 click / keydown handler 的静态卡上（`:52`），对不可交互的元素发出"可交互"信号；同时它也改变了整张卡片的边框（`:235-238` 的 `1px` 边框），属于"用边框区分状态"。按频次规则，hover 属"数十次/天"，应极简或砍掉。 | 删除 `:246-248`，以及随之失去意义的 `transition: border-color`（`:243`）。若将来给卡片加上真正的点击目标（例如打开工具详情），再把 hover 恢复到 `@media (hover:hover) and (pointer:fine)` 内并使用 token 时长。 |
| MEDIUM | 缺失的机会 / 性能 | apps/web/src/views/platform/ToolManagerView.vue:39-49 与 apps/web/src/views/platform/MemoryManagerView.vue:55-65 | 两个页面都是三态硬切换（`v-if loading` / `v-else-if !length` / `v-else`）。滚动容器是 `.platform-content`（`:184-189`、`:267-272`），加载态把内容整体替换成一个 padding 48px 的提示块（`:218-226`、`:307-315`），容器高度塌陷：切 Tab（`:140-142`）、点刷新（`:5`）、翻页（`:128`）都会让整块内容闪一次、滚动位置回到顶部。加载指示属于允许动效的"状态指示 / 防止突变突兀"，但当前做法是"替换内容"，方向与目的相反。 | 不要新增动效：保留既有列表，把 loading 表达为覆盖层或行内小指示（刷新按钮已有 loading，`:5`），让内容不再塌陷。若确需过渡，只对指示器本身做 opacity，150–200ms，用 token（`--transition-fast`/`--transition-base`），不动任何布局尺寸。 |
| LOW | 一致性与 token | apps/web/src/views/platform/MemoryManagerView.vue:367 | `.subject-count` 的 `background: var(--blue-100)` 同样引用未定义变量（与动效发现 1 同一类问题）：`background` 简写在计算值阶段失效、回退初始值 `transparent`，计数胶囊实际没有底色，只剩 `:368` 的蓝色文字和 `:369-370` 的圆角内边距。 | 随动效发现 1 一并处理：先补全局定义，或就地改用已定义的 `--blue-50`（style.css:20）。本行是 1 的特例，不单独修复。 |
| LOW | 缺失的机会 | apps/web/src/views/platform/MemoryManagerView.vue:245-248 | 停用成功后本地直接把 `memory.is_active` 置为 false（`:247`），该行状态 tag 由「活跃」瞬间翻成「停用」（`:96-98`）、操作按钮被替换为纯文本（`:117`），没有任何过渡或短暂强调。在多行列表里，用户不容易确认"改变的正是我刚点的那一行"——属于允许动效的"状态指示 / 操作反馈"。 | 若判定列表足够短、误认概率低，这条不加也成立。若加：只在本行做一次短暂的颜色/透明度强调（opacity/color，≤200ms，token 内，可被下一次操作打断），并从 `:117` 删除重复的「已停用」文本作为等价偿还。 |

## 存疑

- **工具的启停只在进程内生效，UI 却把它呈现为配置状态。** `set_enabled` 只改内存中的 `ToolDefinition.enabled`（`tool_registry.py:189-196`），`stats()` 全部从内存 `self._tools` 计算（`tool_registry.py:454-473`），这条链路上没有任何持久化写入。也就是说：页面显示「已启用/已停用」，重启 api-gateway 后开关会回到注册时的默认值（默认值需另查 `ToolDefinition` 定义）。验证方法：在页面上停用一个工具 → 重启网关 → 刷新页面看状态是否回退。若产品期望这是一项持久配置，那么 `:148` 的「已 XX」成功提示会制造错误信念——运维以为工具已关闭，实际没有。
- **搜索态下的分页确实会跳错数据，但触发条件需要真实数据确认。** 见提案 1。要点：`total` 由后端定义为"返回行数"（`gateway_platform_routes.py:322`）而前端当作"匹配总数"用（`:233`），且 `limit` 前端写死 50（`:229`）、`pageSize` 是 20（`:177`）。验证方法：造一个命中 21 条以上的关键词，搜索后点第 2 页，看列表内容是否仍与关键词相关。
- **两个页面的统计条都没有响应式回退。** `ToolManagerView.vue:191-196` 是固定 4 列 `repeat(4, 1fr)`；`MemoryManagerView.vue:274-279` 是 `auto-fill minmax(100px, 1fr)`，卡数随 `by_type` 键数变化。全局断点（style.css:760-804）只覆盖了已确认零使用的装饰类（`.page-hero`/`.page-grid-*` 等），对这两个 `.stats-row` 无效。窄屏下的实际表现（是否挤压、是否溢出）需真机确认。
- **工具描述被截断且没有展开路径。** `-webkit-line-clamp: 2`（`ToolManagerView.vue:296-304`）配合模板 `:74` 直接输出，没有 `show-overflow-tooltip` 或展开入口。如果真实描述普遍长于两行，用户在"是否该停用该工具"这一步会读不到完整信息。验证方法：取后端注册表里 `description` 最长的几条实际渲染，看两行是否够用。
- **两个页面的前端权限门槛是 `chat.use`。** `router/index.ts:232`、`:243` 都为这两个路由声明 `requiresPermission: 'chat.use'`，而它们能触发全局性写操作：工具启停（`gateway_platform_routes.py:278-284`，`set_enabled` 无用户维度）、记忆停用（`:325-335`，按 `user_id` 限定，只影响本人）。后端对应的权限检查分别是 `_platform_manage`（`:280`）与 `_platform_read`（`:327`）。前端是否应提高工具管理页的门槛、以及后端对工具启停实际要求什么权限，需产品与后端确认后统一。
- **开关在 loading 期间是否真的阻止重复点击，取决于 Element Plus 版本行为。** `ToolManagerView.vue:66-71` 传了 `:loading="tool._toggling"`，`toggleTool`（`:144-154`）是乐观更新 + 失败回滚；如果 loading 不阻止二次交互，快速连点会发出两个方向相反的请求。验证方法：在 Network 面板下快速连点同一开关，看是否出现两次 `POST /platform/agent/tools/{name}/toggle`。同理，`name=""` 的「全部」Tab（`:35`）与 `v-model` 空串的配合行为也需实际渲染确认。
- **`.page-shell` / `.el-table` 的既有全局样式是否与这两个页面的 scoped 样式冲突，未验证。** 本视图给 `.platform-content` 设了 `overflow-y: auto`（`:184-189`、`:267-272`），而 `style.css` 对 `html, body, #app` 设置了 `overflow: hidden` 与固定高度（style.css:90-117）；嵌套滚动容器在这种组合下通常需要真机确认是否出现双滚动条或滚动穿透。
