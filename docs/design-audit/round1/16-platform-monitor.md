# 16 Agent 监控 / 成本分析

审计对象：`apps/web/src/views/platform/AgentMonitorView.vue`（650 行）、`apps/web/src/views/platform/CostDashboardView.vue`（255 行）
路由：`/workspace/platform/monitor`（`apps/web/src/router/index.ts:217-219`）、`/workspace/platform/cost`（`apps/web/src/router/index.ts:250-252`）
审计性质：只读。本文件是本次审计唯一写入的文件。

## 唯一用户任务

负责 Agent 平台的运维/研发在出现「某次回答不可信」或「本期花费异常」时，要在这里定位到具体是哪一次运行、哪一步、哪个模型出的问题，并据此决定下一步动作。

## 完成该任务的必要步骤

1. 打开 `/workspace/platform/monitor`，用状态筛选把列表缩到失败/中断的运行（`apps/web/src/views/platform/AgentMonitorView.vue:40-45`）—— **keep**
2. 从列表里认出要查的那一次运行（状态/时间/问题/工具调用数/延迟）（`apps/web/src/views/platform/AgentMonitorView.vue:61-85`）—— **keep**
3. 点开该运行的详情抽屉，看任务拆解与并行分组（`apps/web/src/views/platform/AgentMonitorView.vue:101-129`）—— **keep**
4. 顺着决策链路看在哪一步、调了哪个工具、返回多少条（`apps/web/src/views/platform/AgentMonitorView.vue:132-159`）—— **keep**
5. 核对工具调用记录表（`apps/web/src/views/platform/AgentMonitorView.vue:162-169`）—— **merge**（与第 4 步同源同事实：两处分别读 `runDetail.tool_calls` 与 `runDetail.agent_events`，描述的是同一批工具调用）
6. 读反思自检的分数与问题列表，决定是否重跑（`apps/web/src/views/platform/AgentMonitorView.vue:172-206`）—— **keep**
7. 用顶部 5 张统计卡判断「整体是否变差」（`apps/web/src/views/platform/AgentMonitorView.vue:14-35`）—— **drop**（3/5 张数字结构性失真，且随筛选与分页变化，见提案 1）
8. 打开 `/workspace/platform/cost`，选时间范围 7/30/90 天（`apps/web/src/views/platform/CostDashboardView.vue:5-9`）—— **keep**
9. 看总成本 / 总 Token / 总调用次数（`apps/web/src/views/platform/CostDashboardView.vue:19-36`）—— **keep**
10. 在「按模型成本分布」里找出最贵的模型（`apps/web/src/views/platform/CostDashboardView.vue:48-62`；后端已按 `estimated_cost DESC` 排序，`apps/services/api-gateway/src/app/gateway_platform_routes.py:361`）—— **keep**
11. 到「模型健康状态」判断该模型是否降级/熔断（`apps/web/src/views/platform/CostDashboardView.vue:74-112`）—— **merge**（同一批模型在两处以不同顺序各出现一次，见提案 5）
12. 看场景分布与每日趋势，判断是否要止损（`apps/web/src/views/platform/CostDashboardView.vue:115-142`）—— **demote**（趋势只画最后 14 天且与选择器不一致，见提案 4，只宜粗看）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 页面标题「Agent 执行监控」 | apps/web/src/views/platform/AgentMonitorView.vue:3 | 必要 | 定位当前界面 |
| 副标题（实时观测…工具调用链路与反思决策） | apps/web/src/views/platform/AgentMonitorView.vue:3 | 可删 | 宣称「实时观测」，实现是挂载 + 手动刷新（同文件 `:342-344`、`:318-328`），无轮询；去掉「实时」承诺后语义与页面标题重复 |
| 刷新按钮 | apps/web/src/views/platform/AgentMonitorView.vue:5-8 | 必要 | 无自动刷新，这是唯一的手动重取入口，也是失败后重试的唯一途径 |
| 统计卡「总执行次数」 | apps/web/src/views/platform/AgentMonitorView.vue:15-18 | 可删 | 值 = 当前加载条数（`limit` 固定 50，`:321`）且随状态筛选变化（`:322`、`:250-255`）；列表接口的 `total` 本身也是本次返回条数（`apps/services/api-gateway/src/app/gateway_platform_routes.py:216`），没有真总数可用 |
| 统计卡「平均复杂度」 | apps/web/src/views/platform/AgentMonitorView.vue:19-22 | 可删 | 无拆解数据的运行按 1 记入（`:256` 的 `\|\| 1`），无法区分「复杂度确实是 1」与「这条没有拆解数据」 |
| 统计卡「任务拆解率」 | apps/web/src/views/platform/AgentMonitorView.vue:23-26 | 可删 | 判据是 `'complexity_score' in r`（`:252`），而后端对每条记录都返回该键（`gateway_platform_routes.py:190`，缺省 1）→ 列表非空时恒为 100%；真正表达拆解的是同接口返回的 `requires_decomposition`（`gateway_platform_routes.py:191`），未被使用 |
| 统计卡「平均延迟」 | apps/web/src/views/platform/AgentMonitorView.vue:27-30 | 可合并 | 与运行卡片上的 ⏱ 延迟（`:82`）、详情「性能指标」总延迟（`:213-215`）三处表达同一事实；且分子只取 `completed`（`:258`），标签未说明口径 |
| 统计卡「自检通过率」 | apps/web/src/views/platform/AgentMonitorView.vue:31-34 | 可删 | 分母筛选 `x.reflection_passed !== undefined`（`:253`），而该键在后端恒存在、未做反思时为 `null`（`gateway_platform_routes.py:192`），`null !== undefined` 为真 → 分母 = 全部已完成，含从未做过反思的运行（详情接口在同情况下返回 `reflection: null`，`gateway_platform_routes.py:254`） |
| 区块标题「Agent 运行记录」 | apps/web/src/views/platform/AgentMonitorView.vue:38-39 | 可删 | 页面上唯一的列表，页面标题已表达同一含义 |
| 状态筛选下拉 | apps/web/src/views/platform/AgentMonitorView.vue:40-45 | 必要 | 从一堆运行里缩小范围的唯一手段 |
| 筛选的「全部」选项 + `clearable` | apps/web/src/views/platform/AgentMonitorView.vue:40-41 | 可合并 | 同一「清空筛选」有两个入口（值为空串的选项 + 输入框清除按钮） |
| 列表加载态 | apps/web/src/views/platform/AgentMonitorView.vue:48-51 | 必要 | 首屏与刷新时的等待反馈 |
| 空态「暂无运行记录」 | apps/web/src/views/platform/AgentMonitorView.vue:53-58 | 必要 | 空态本身必要，但请求失败时也走这里（`:318-328` 无 catch），失败与真没数据同形，见提案 3 |
| 运行卡片（整卡可点击） | apps/web/src/views/platform/AgentMonitorView.vue:61-67 | 必要 | 列表项，点击进详情；但 `div` + `@click` 无 `tabindex`/键盘处理（全仓仅 `apps/web/src/views/kb/KBUploadView.vue:17` 用过 `tabindex`），键盘用户进不去 |
| 运行状态标签（中文） | apps/web/src/views/platform/AgentMonitorView.vue:70-72 | 必要 | 认出目标运行的第一判据（映射见 `:268-271`） |
| `execution_mode` 标签（原始枚举） | apps/web/src/views/platform/AgentMonitorView.vue:73-75 | 可下沉 | 直接渲染后端枚举（如 `plan_reflect_repair`）未翻译，在 50 条列表里是噪音；该字段详情接口同样返回（`gateway_platform_routes.py:183`、`:246`），可只在抽屉里出现 |
| 运行时间 | apps/web/src/views/platform/AgentMonitorView.vue:77 | 必要 | 「我要看哪一次」的主要判据之一 |
| 问题正文（2 行截断） | apps/web/src/views/platform/AgentMonitorView.vue:79 | 必要 | 认出目标运行的主要依据 |
| meta 行（🔧 工具调用 / ⏱ 延迟 / 📊 `answer_mode`） | apps/web/src/views/platform/AgentMonitorView.vue:80-84 | 可合并 | 延迟与详情「总延迟」重复（`:213-215`）；`answer_mode` 是原始枚举且与 `execution_mode` 标签语义重叠（`:73-75`），两者常同时在场 |
| meta 行的三个 emoji | apps/web/src/views/platform/AgentMonitorView.vue:81-83 | 可删 | 与全站 Element Plus 图标体系不一致，纯装饰，且会被读屏当内容朗读 |
| 详情抽屉 | apps/web/src/views/platform/AgentMonitorView.vue:90-95 | 必要 | 完成任务的核心容器（`size="720px"`；窄屏由 `apps/web/src/styles/responsive-enhancements.css:57`、`:194-196` 覆写为 85%） |
| 抽屉加载态 | apps/web/src/views/platform/AgentMonitorView.vue:96-99 | 必要 | 详情请求期间的状态 |
| 任务拆解区块（含复杂度分数） | apps/web/src/views/platform/AgentMonitorView.vue:103-129 | 必要 | 「哪一步出错」的核心视图 |
| 并行组标签「并行组 N」 | apps/web/src/views/platform/AgentMonitorView.vue:107 | 必要 | 解释分组语义，否则同组节点之间没有关系说明 |
| DAG 节点 id（`taskId`） | apps/web/src/views/platform/AgentMonitorView.vue:116 | 可删 | 内部任务 id，对「判断哪一步失败」无决策作用；节点描述（`:119`）已说明内容 |
| DAG 节点状态标签（英文枚举） | apps/web/src/views/platform/AgentMonitorView.vue:117 | 可合并 | 与运行状态标签（`:70-72`）用了两套语言：运行状态有中文映射（`:268-271`），子任务状态直接把 `getTaskStatus` 的英文值上屏（`:297-299`） |
| DAG 节点 依赖 / 类别 | apps/web/src/views/platform/AgentMonitorView.vue:120-123 | 可下沉 | 依赖关系是排障信息，类别是未翻译枚举；两者已是 11px 最弱层级，可收进节点展开态 |
| 组间箭头 ↓ | apps/web/src/views/platform/AgentMonitorView.vue:126 | 可删 | 顺序已由「并行组 N」+ 纵向排列表达，字符箭头是纯装饰 |
| 决策链路区块 | apps/web/src/views/platform/AgentMonitorView.vue:132-159 | 必要 | 「在哪一步失败」的主线证据 |
| 链路时间戳位（渲染 `event.type`） | apps/web/src/views/platform/AgentMonitorView.vue:138 | 可合并 | 把事件类型串放在 `timestamp` 位置；四类事件正文（`:143-156`）已表达事件是什么，是同一信息的第二次表述 |
| 工具调用记录表 | apps/web/src/views/platform/AgentMonitorView.vue:162-169 | 可合并 | 与决策链路 `tool_request`/`tool_result`（`:150-156`）同源同事实 |
| 反思自检区块 | apps/web/src/views/platform/AgentMonitorView.vue:172-206 | 必要 | 决定「是否重跑」的依据 |
| 四条进度条（完整性/准确性/引用/置信度） | apps/web/src/views/platform/AgentMonitorView.vue:175-192 | 可合并 | 4 个 0–1 分数用 4 条百分比进度条呈现，纵向占用远大于等价的文本行；且进度条宽度本身由 Element Plus 动（见动效发现 2） |
| 反思问题 / 改进建议列表 | apps/web/src/views/platform/AgentMonitorView.vue:193-204 | 必要 | 唯一给出「下一步改什么」的文本 |
| 性能指标「总延迟」 | apps/web/src/views/platform/AgentMonitorView.vue:209-215 | 可合并 | 与卡片 meta（`:82`）、统计卡（`:27-30`）三处重复 |
| 检索延迟 / 生成延迟 / 证据数 | apps/web/src/views/platform/AgentMonitorView.vue:216-227 | 必要 | 判断「慢在检索还是生成」「是否召回不足」的唯一数字 |
| 页面标题「成本可观测性」 | apps/web/src/views/platform/CostDashboardView.vue:3 | 必要 | 定位当前界面 |
| 副标题（实时追踪…Token 消耗趋势） | apps/web/src/views/platform/CostDashboardView.vue:3 | 可删 | 同样宣称「实时」，实现是挂载 + 手动刷新（`:196`、`:182-194`） |
| 时间范围下拉 7/30/90 天 | apps/web/src/views/platform/CostDashboardView.vue:5-9 | 必要 | 决定全部数值口径的开关 |
| 刷新按钮 | apps/web/src/views/platform/CostDashboardView.vue:10-13 | 必要 | 同上页：无自动刷新 |
| 统计卡「总成本」（primary） | apps/web/src/views/platform/CostDashboardView.vue:20-23 | 必要 | 本页主数字；但 `formatCost` 硬编码 `¥`（`:170-174`）而同卡标签用 `currency` 字段（`:22`，后端取自可配置的 `llm_price_currency`，`gateway_platform_routes.py:368`） |
| 统计卡「总 Token 消耗」 | apps/web/src/views/platform/CostDashboardView.vue:24-27 | 必要 | 单价之外的量级判据 |
| 统计卡「总调用次数」 | apps/web/src/views/platform/CostDashboardView.vue:28-31 | 必要 | 与总成本共同解释「贵是因为用得多还是因为单价高」 |
| 统计卡「千次调用平均成本」 | apps/web/src/views/platform/CostDashboardView.vue:32-35 | 可合并 | 完全由相邻两张卡派生（`:33` 用 `total_cost / total_calls * 1000`）；三张同族数字并排时，读者需要自行确认口径关系，若要保留应标明它是单位成本而非第四种统计 |
| 页面加载态 | apps/web/src/views/platform/CostDashboardView.vue:38-41 | 必要 | 首屏等待反馈 |
| 区块标题「按模型成本分布」 | apps/web/src/views/platform/CostDashboardView.vue:45-47 | 必要 | 区分四种数据切分 |
| 模型成本卡（名称 / 金额 / tokens） | apps/web/src/views/platform/CostDashboardView.vue:49-61 | 必要 | 找出「谁最贵」的主视图 |
| 模型成本条 `mc-bar` | apps/web/src/views/platform/CostDashboardView.vue:54-56 | 可删 | 唯一样式来源是 `linear-gradient(90deg, var(--blue-400), var(--blue-600))`（`:223`），`--blue-400` 未定义 → 填充可能整条不可见（见提案 2）；占比信息已由同卡金额与 token 数给出（`:57-60`） |
| 模型成本卡「N 次调用」标签 | apps/web/src/views/platform/CostDashboardView.vue:52 | 必要 | 判断「贵」是单价还是量级的唯一同卡线索 |
| 模型健康摘要行（健康 X / Y、N 个熔断中） | apps/web/src/views/platform/CostDashboardView.vue:67-72 | 可合并 | 与卡片状态标签的阈值不一致：摘要取自后端 `healthy_models`（`health_score >= 0.5 and not circuit_open`，`apps/services/api-gateway/src/app/model_health.py:262-263`），而卡内标签用 `>= 0.8` 判「健康」（`:83-85`）→ 同屏两套「健康」定义 |
| 健康卡 模型名 | apps/web/src/views/platform/CostDashboardView.vue:82 | 必要 | 唯一定位字段 |
| 健康卡 状态标签（熔断/健康/降级） | apps/web/src/views/platform/CostDashboardView.vue:83-85 | 必要 | 本节的结论字段 |
| 健康卡 健康度进度条 | apps/web/src/views/platform/CostDashboardView.vue:88-91 | 可删 | 与同一张卡的标签（`:83-85`）由同一个 `health_score` 派生，是同一判断的第二次表述 |
| 健康卡 成功率 / P50 / P95 / 调用数 | apps/web/src/views/platform/CostDashboardView.vue:92-109 | 必要 | 支撑「是否降级」的判断，是标签结论的证据 |
| 区块标题「按场景成本分布」 | apps/web/src/views/platform/CostDashboardView.vue:115-117 | 必要 | 区分数据切分 |
| 场景行（名称 / 占比 / 金额） | apps/web/src/views/platform/CostDashboardView.vue:119-128 | 必要 | 回答「钱花在哪类链路」 |
| 场景条 `scene-bar` | apps/web/src/views/platform/CostDashboardView.vue:124-126 | 可删 | 填充色 `var(--blue-400)`（`:246`）未定义 → 可能透明；占比已由 `:122` 文本给出，条是同一比例的第二次表达 |
| 每日成本趋势区块 | apps/web/src/views/platform/CostDashboardView.vue:133-141 | 可删 | 窗口硬编码 `by_day.slice(-14)`（`:137`）与时间范围选择器 7/30/90（`:5-9`）不一致；每根柱子的唯一数值在原生 `title`（`:138`），键盘不可达，无轴值，见提案 4 |
| 趋势柱 + 日期标签（9px、rotate -45deg） | apps/web/src/views/platform/CostDashboardView.vue:138-139 | 可删 | 随上一行；日期字号 9px（`:254`）低于 `--text-caption` 12px，旋转标签在窄屏会互相压叠 |
| 空态「暂无场景数据」 | apps/web/src/views/platform/CostDashboardView.vue:130 | 可合并 | 与下一处空态同形；且「按模型成本分布」「模型健康状态」两节没有空态（`:48-62`、`:74-112` 无 `v-if`），空数据时是「什么都不显示」，与失败不可区分 |
| 空态「暂无趋势数据」 | apps/web/src/views/platform/CostDashboardView.vue:142 | 可合并 | 同上，一处空态即可覆盖两节 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 删除 | apps/web/src/views/platform/AgentMonitorView.vue:14-35 | 少一次误操作 | 会失去「整体是否变差」的一眼概览。5 张卡里 3 张无法原地修好：「总执行次数」要把 `limit=50`（`:321`）与状态筛选（`:322`）拆开才谈得上「总」，而接口的 `total` 就等于本次条数（`apps/services/api-gateway/src/app/gateway_platform_routes.py:216`），要真数字必须新增后端聚合接口；「任务拆解率」「自检通过率」缺少可用判据（后端 summary 恒返回 `complexity_score`（缺省 1）与可为 null 的 `reflection_passed`，`gateway_platform_routes.py:190-192`）。若只留「平均延迟」，它同样只统计 `completed`（`:258`），单独一张卡更需要口径注释，不如删净。另：`.stats-row` 是 5 列硬网格无断点（`:362-367`，`apps/web/src/styles/responsive-enhancements.css` 内无 `.stats-row` 规则），窄屏下每卡约 57px（375px 视口减 40px padding 减 4×12px gap），删卡同时消掉这个溢出风险。 |
| 加反馈 | apps/web/src/views/platform/CostDashboardView.vue:205、:223、:229、:246、:252；apps/web/src/views/platform/AgentMonitorView.vue:517、:520-522、:579-580、:611、:620 | 少一次误操作 | 这 11 处引用的 `--blue-400`/`--green-400`/`--orange-400`/`--red-400`/`--red-500`/`--red-600` 在仓库里没有任何定义：`apps/web/src/style.css:9-20` 只定义 slate 系列与 `--blue-500/600/700/50`，运行时注入器 `apps/web/src/utils/theme.ts:11-57`（浅色/深色两套）也没有这些键。按 CSS 变量规范，声明会在 computed-value 阶段失效并回退为 unset：条形填充（`:223` 的 gradient、`:246`、`:252`）变透明，状态左边框（`AgentMonitorView:517`、`:520-522`、`:579-580`）整条不再绘制，反思区红蓝强调（`:611`、`:620`）退回普通文字色。修复不得新增色板（本轮约束），只能用已存在的变量：条形改 `--blue-500`，状态色改 Element Plus 语义色 `--el-color-success/-warning/-danger`（Element Plus 在 `:root` 已定义，`AgentMonitorView:283-285` 里的 `#67c23a/#e6a23c/#f56c6c` 正是它们）。风险：EP 语义色与主色 `--blue-600` 并置的对比度、以及深色模式下是否要另调，必须真机看过再定；若选择「删声明不换色」更省事，但会让「哪一步失败 / 是否熔断」失去第一眼信号，所以这里选择换色而不是删。 |
| 加反馈 | apps/web/src/views/platform/CostDashboardView.vue:21-35（另一个触发点：apps/web/src/views/platform/AgentMonitorView.vue:53-58、:330-340） | 少一次误操作 | 现在「失败」与「真的是 0」完全同形：成本页 `loadData` 是 try/finally 无 catch（`:182-194`），失败时 `costData` 保持 null，四张卡渲染成 `¥0.000000 / 0 / 0`（`:21-35`），而 ¥0 是一个看起来非常合理的值；Agent 页 `loadRuns` 同样无 catch（`:318-328`），首屏失败显示「暂无运行记录」（`:53-58`），详情请求失败则保留上一条运行的 `runDetail`（`:330-340` 未置空、无 catch），用户会把 A 运行的详情读成 B 的。代价：两个文件都要加失败分支；要净增 0 个元素，就得复用已有的空态/加载态容器（`EnhancedEmpty` / `.loading-state`），把「空」与「失败」映射到同一容器、用文案区分——实现时须确认不会同时渲染两份容器。风险：如果后端在失败时仍返回 200 + 空数组（未验证），前端的失败分支永不触发，那就得先统一后端契约，前端单独改无效。 |
| 删除 | apps/web/src/views/platform/CostDashboardView.vue:132-142 | 少一次误操作 | 趋势窗口硬编码 `by_day.slice(-14)`（`:137`），页头时间范围却是 7/30/90 天（`:5-9`），其余三节都按完整区间渲染（后端按 `period_days` 过滤，`apps/services/api-gateway/src/app/gateway_platform_routes.py:355`）——选「近 90 天」时这张图只画最后 14 天且无任何标注，等于给出一个会被误当成 90 天趋势的图形；柱子数值只存在于原生 `title`（`:138`），键盘与触屏都拿不到。代价：删掉后成本页只剩「按模型 / 按场景」两个切分，判断「本期是否比上期贵」需要外部手段。若不想删，最小修法是让窗口跟随选择器，但 90 根柱子在窄屏会挤成一团，需要先定聚合粒度（如按周），这已不是本页能单独决定的产品取舍。 |
| 合并 | apps/web/src/views/platform/CostDashboardView.vue:44-112 | 少一次判断 | 「按模型成本分布」与「模型健康状态」是同一批模型的两次呈现，且顺序不同：前者来自 SQL 的 `ORDER BY estimated_cost DESC`（`gateway_platform_routes.py:361`），后者是健康字典的插入顺序（`apps/services/api-gateway/src/app/model_health.py:246-258`）。判断「最贵的模型是否正在熔断」现在必须靠模型名在两处肉眼对齐。风险：两个数据源的模型集合不同——成本只含区间内有调用的模型，健康表含进程内见过的所有模型，取交集还是并集决定了是否会出现「成本 0 但状态健康」的行；合并后行内会有 6–7 列，窄屏需要横向滚动（当前 `model-health-grid` 用 `minmax(260px, 1fr)` 自适应，`:227`）。这两点必须在实现前定下来。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| MEDIUM | 性能 / 缓动与时长 | apps/web/src/views/platform/CostDashboardView.vue:223、:246、:252 | 三处 `transition` 动的是 `width`（0.5s）/ `height`（0.3s）——布局属性，属明令禁止项；0.5s 超过 UI 动效 300ms 上限；未使用 `--transition-*` token（走浏览器默认 `ease`）。同时这三处过渡大概率从不播放：刷新时 `v-if="loading"`（`:38`）先卸载整个 `<template v-else>` 内容，重建后的元素不会再触发首次样式过渡。 | 直接删除这三处 `transition`。若确实要提示「数值变了」，用 `opacity`/`color`（≤200ms，token 内），不要动尺寸。 |
| MEDIUM | 性能 / 一致性与 token | apps/web/src/views/platform/AgentMonitorView.vue:178、:182、:186、:190（同类：apps/web/src/views/platform/CostDashboardView.vue:90） | 继承 Element Plus 默认：`node_modules/element-plus/theme-chalk/el-progress.css` 的 `.el-progress-bar__inner{transition:width .6s ease}`。600ms 是上限的两倍，且动的是 `width`；本组两页共 5 处 `el-progress` 全部命中。 | 若保留进度条，加 scoped `:deep(.el-progress-bar__inner){transition:none}`（或改为只过渡 `transform`）；若采纳元素清单里「进度条可合并/可删」的意见，本条随之消失。 |
| MEDIUM | 无障碍 / 一致性与 token | apps/web/src/views/platform/AgentMonitorView.vue:427-429（同类：apps/web/src/views/platform/CostDashboardView.vue:253） | `:hover` 未包在 `@media (hover:hover) and (pointer:fine)` 内（全局已知问题，此处是本文件的特例）：hover 用的 `--blue-400` 未定义，悬停边框实际回退为 `currentColor`（深墨色），而选中态用的是已定义的 `--blue-500`（`:431-434`）→ 同一张卡片上「悬停」比「选中」更重，两套反馈语言；触屏上该悬停态会粘滞残留。 | 触屏部分用 `@media (hover:hover) and (pointer:fine)` 包住；色值改用已存在的 `--blue-500`，或干脆去掉 hover 变色（选中态已足够表达当前项）。 |
| LOW | 目的与频次 | apps/web/src/components/EnhancedEmpty.vue:108-113（本组经 apps/web/src/views/platform/AgentMonitorView.vue:53-58、apps/web/src/views/platform/CostDashboardView.vue:130、:142 触发） | 空态插画 hover 时 `scale(1.05) rotate(2deg)`，0.3s 弹性曲线 `cubic-bezier(0.34,1.56,0.64,1)`，且未包 hover 媒体查询。空态是静态占位，不属于「空间一致性/状态指示/操作反馈/防止突变」四类允许理由。 | 删掉位移与旋转；若要保留反馈只保留 `opacity`/`color`。同一发现已在 `docs/design-audit/round1/15-platform-models.md` 登记为组件级问题，此处仅登记本组的触发点。 |
| LOW | 缺失的机会 | apps/web/src/views/platform/AgentMonitorView.vue:48-58（同类：apps/web/src/views/platform/CostDashboardView.vue:38-43） | 加载态 → 空态/内容之间是硬切换，无过渡。 | 不建议新增：刷新是用户主动触发的「数十次/天」档动作，按规则应保持不动。仅当真机上确认加载态闪烁明显时，才用 `opacity` 150ms（token 内）过渡，且不动尺寸、不入场缩放。 |

## 存疑

- **未定义变量的实际渲染效果需要浏览器确认。** 结论「条形填充透明、状态左边框消失、红蓝强调失效」是按 CSS 变量规范推导的（引用不存在的自定义属性 → 声明在 computed-value 阶段失效 → 非继承属性取初值）。验证方法：打开 `/workspace/platform/cost`，DevTools 选中 `.mc-bar`（`CostDashboardView.vue:54-56`）看 computed `background` 是否为空、选中 `.stat-card.primary`（`:205`）看 `border-color` 是否等于文字色；再打开 `/workspace/platform/monitor` 选中已完成的 `.dag-node`（`:517`）看 `border-left-style` 是否为 `none`。若渲染正常，说明另有注入来源需要追查。
- **统计卡失真程度依赖真实响应。** 「任务拆解率恒 100%」「自检通过率分母含未反思运行」基于后端对每条 summary 都返回 `complexity_score`（缺省 1）与 `reflection_passed`（可为 null）（`apps/services/api-gateway/src/app/gateway_platform_routes.py:190-192`）。验证方法：DevTools Network 抓 `/api/v1/platform/agent/runs` 的 JSON，确认这两键是否每条都存在，以及 `reflection_passed` 为 null 的比例。
- **`role='assistant'` 口径未与用户视角对齐。** 成本按 `chat_messages` 中 `role='assistant'` 的行聚合（`gateway_platform_routes.py:355`、`:359`），所以「总调用次数」是 assistant 消息数，不是用户提问次数，也不是 Agent 任务数。是否需要用任务数做分母（例如「每次问答的平均成本」）需产品确认。
- **币种是否可能非 CNY 未确认。** 标签读 `currency`（`CostDashboardView.vue:22`，来自可配置的 `llm_price_currency`，`gateway_platform_routes.py:368`），而金额符号硬编码 `¥`（`:170-174`）。验证方法：查部署环境的 `llm_price_currency` 配置项取值；若部署中可能是 USD，则必须二选一改齐。
- **移动端统计卡是否溢出需真机确认。** `.stats-row` 在 `AgentMonitorView.vue:362-367` 是 `repeat(5, 1fr)`、`CostDashboardView.vue:203` 是 `repeat(4, 1fr)`，两者都没有媒体查询，全局与 `apps/web/src/styles/responsive-enhancements.css` 也没有 `.stats-row` 规则；375px 视口下按 20px 内边距与 12px gap 估算，每卡内容宽度约 57px / 74px，而 `stat-value` 是 24px / 22px 字号。验证方法：真机或 DevTools 375px 视口截图确认是否截断或换行。
- **抽屉尺寸在 769–1280px 区间未验证。** `size="720px"`（`AgentMonitorView.vue:93`）只在 `@media (max-width: 768px)` 被覆写为 85%（`apps/web/src/styles/responsive-enhancements.css:57`、`:194-196`）；在 800–900px 窗口下留白是否可接受需实测，尤其确认关闭按钮不被裁掉。
- **失败态是否真会走到取决于后端契约。** 两个视图的请求都无 catch（`AgentMonitorView.vue:318-328`、`CostDashboardView.vue:182-194`），但若后端在异常时也返回 200 + 空数据，提案 3 的失败分支就永远不会触发，需要先确认 `/platform/cost/breakdown`、`/platform/agent/runs` 的错误返回约定（非 2xx 还是 200+空）。
- **`--text-secondary` 与 `--text-muted` 同值造成层级不可分。** `apps/web/src/style.css:28-29` 两个变量都指向 `--slate-600`，所以 `.run-time`（`:449`）与 `.run-meta`（`:465`）实际颜色相同，层级只靠字号（12px vs 12px）与位置区分。这是全局 token 决策，本组两视图不宜单方面改；需要设计侧确认是否要拆分这两个语义。
- **深色模式下的回退色需实测。** `apps/web/src/utils/theme.ts:11-35` 的深色变量集里同样没有这些 400/500 语义色，且把 `--text-secondary`/`--text-muted` 都改为 `#94a3b8`；若采纳提案 2 换成 EP 语义色，深色下 `#67c23a` 一类色是否需要另调，必须切换主题实测。
- **`el-progress` 是否真的不播放过渡未实测。** 「首次样式不触发过渡」是浏览器行为的推论，验证方法：在详情抽屉内切换两条运行观察进度条是否出现 600ms 生长动画（若出现，说明它并非每次重新挂载，动效发现 2 的严重度需要上调）。
