# 20 A/B 实验 / Agent 协作编排 / 审计日志

审计对象：`apps/web/src/views/platform/AbExperimentView.vue`（207 行）、`apps/web/src/views/platform/AgentOrchestrationView.vue`（170 行）、`apps/web/src/views/AuditView.vue`（213 行）
路由：`/workspace/platform/experiments`、`/workspace/platform/orchestration`、`/workspace/audit`（`apps/web/src/router/index.ts:326-358`，另有 `/audit` → `/workspace/audit` 的重定向 :366-368）
审计性质：只读。本文件是本次审计唯一写入的文件。

## 唯一用户任务

- **A/B 实验**：实验负责人在要判断某个 Prompt / 模型改动值不值得上线时，起一个实验并在样本收够后读结论，决定「采用 B / 保留 A / 继续收数据」。
- **Agent 协作编排**：平台工程师在排查某次多 Agent 编排为什么慢或失败时，从列表定位到那一次运行，再看清是哪个子任务、哪个 Worker 出的错、耗时多少。
- **审计日志**：合规 / 安全审查者在事后追责或排障时，按服务、结果、操作者等条件筛出相关审计事件，并读到那条事件的完整详情。

## 完成该任务的必要步骤

### A/B 实验（`apps/web/src/views/platform/AbExperimentView.vue`）

1. 点「新建实验」打开弹窗 —— **keep**（`apps/web/src/views/platform/AbExperimentView.vue:5-7`）
2. 填实验名 —— **keep**（`:82-84`）
3. 填对照组指令 A / 实验组指令 B —— **keep**（`:85-90`）
4. 设目标样本量 —— **demote**（`:91-93`，默认 100 与后端 30–1000 约束同值，`apps/services/api-gateway/src/app/gateway_platform_routes.py:786`）
5. 设流量分配 B 比例 —— **drop**（`:94-96`，后端默认 0.5，`gateway_platform_routes.py:783`）
6. 点「启动实验」 —— **keep**（`:100`）
7. 在列表看进度条与样本数 —— **keep**（`:40-45`）
8. 点「查看报告」 —— **keep**（`:51`）
9. 读结论标签 + 建议 + 指标表 —— **keep**（`:58-72`）

注：步骤 4/5 之所以是删除候选，是因为实验一旦创建就没有任何界面能改动它们 —— 后端只有 list / create / stop / report 四个路由，没有 update（`gateway_platform_routes.py:765-811`）。也就是说这两项不是「以后再调」，而是「要么现在填对，要么重开一个实验」。这既是删除的理由，也是删除前必须先确认的风险。

### Agent 协作编排（`apps/web/src/views/platform/AgentOrchestrationView.vue`）

1. 点「刷新」取最新运行 —— **keep**（`apps/web/src/views/platform/AgentOrchestrationView.vue:5-7`）
2. 扫统计卡判断整体健康 —— **demote**（`:13-30`）
3. 在表格里找到那一次运行 —— **keep**（`:33-60`）
4. 点行打开抽屉 —— **keep**（`:33`，无光标提示，见动效发现）
5. 读拓扑排序看并行结构 —— **keep**（`:72-80`）
6. 逐个看 Worker 结果与错误 —— **keep**（`:84-96`）

### 审计日志（`apps/web/src/views/AuditView.vue`）

1. 选服务 —— **keep**（`apps/web/src/views/AuditView.vue:13-17`）
2. 选结果 —— **keep**（`:18-23`）
3. 填用户 ID / 动作 / 资源类型 / 资源 ID —— **demote**（`:24-27`）
4. 点「查询」 —— **keep**（`:28`）
5. 扫表格定位事件 —— **keep**（`:41-64`）
6. 点「详情」读 JSON —— **keep**（`:61`、`:73`）

注：步骤 3 的四个框都是精确匹配的文本输入（直接进查询串，`AuditView.vue:105-109`；后端按精确值过滤，`apps/services/api-gateway/src/app/gateway_admin_routes.py:56-57`）。审查者通常不知道准确的 action 字面量（如 `platform.experiment.stop`）或完整的资源 ID，只能猜 —— 这是「少一次误操作」的直接来源。

## 元素清单

### A/B 实验（`apps/web/src/views/platform/AbExperimentView.vue`）

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 统计卡「实验总数」 | apps/web/src/views/platform/AbExperimentView.vue:13-16 | 可删 | 数值等于列表行数，可直接数 |
| 统计卡「进行中」 | apps/web/src/views/platform/AbExperimentView.vue:17-20 | 可删 | 每张卡的 :35-37 tag 已逐条表达同一事实 |
| 统计卡「已完成」 | apps/web/src/views/platform/AbExperimentView.vue:21-24 | 可删 | 计算式是「非 active」（:128），与 :36 的文案「已停止」指同一状态却用两个词，制造一次术语判断 |
| 空态 EnhancedEmpty | apps/web/src/views/platform/AbExperimentView.vue:27-29 | 必要 | 唯一捕获「没有实验」状态的元素；外层 inline `style="text-align:center; padding: 40px"`（:27）与组件自带的居中与 padding（apps/web/src/components/EnhancedEmpty.vue:83-90）重复，inline 反而覆盖了组件的 56px 上边距 |
| 实验卡容器 v-for | apps/web/src/views/platform/AbExperimentView.vue:32 | 必要 | 列表基本单元 |
| 实验名 | apps/web/src/views/platform/AbExperimentView.vue:34 | 必要 | 唯一定位字段 |
| 状态 tag | apps/web/src/views/platform/AbExperimentView.vue:35-37 | 必要 | 判断能否点「停止」的唯一依据 |
| 进度条 | apps/web/src/views/platform/AbExperimentView.vue:40-44 | 必要 | 判断样本何时收够 |
| 样本文本「N / target」 | apps/web/src/views/platform/AbExperimentView.vue:45 | 必要 | 进度条的精确值 |
| 「创建于 …」 | apps/web/src/views/platform/AbExperimentView.vue:47-49 | 可删 | 对「要不要采用 B」无决策作用；且 `toLocaleDateString()`（:183）丢时间，同日创建的两个实验无法区分 |
| 「查看报告」 | apps/web/src/views/platform/AbExperimentView.vue:51 | 必要 | 任务终点的唯一入口 |
| 「停止」 | apps/web/src/views/platform/AbExperimentView.vue:52 | 必要 | 唯一的实验下线入口；直接调用后端（:154），无二次确认，失败也无提示（:153-157 无 try/catch） |
| 报告弹窗 | apps/web/src/views/platform/AbExperimentView.vue:56-75 | 必要 | 结论载体；但位于 `v-else` 分支内（:31 开、:76 关），只有列表非空时才存在于 DOM |
| 报告汇总行（样本 A / 样本 B / 显著 tag） | apps/web/src/views/platform/AbExperimentView.vue:58-64 | 可合并 | 样本数与 :66-72 表格同源；显著 tag 与逐指标显著性是同一判断的两种粒度 |
| 建议行 | apps/web/src/views/platform/AbExperimentView.vue:65 | 必要 | 直接回答「采用 / 保留 / 继续」 |
| 报告指标表（5 列） | apps/web/src/views/platform/AbExperimentView.vue:66-72 | 可合并 | 后端每条指标已返回 `significant`（apps/services/api-gateway/src/app/instruction_evaluator.py:262），但表里只有 p 值，读者要自己拿 p 与阈值比较 |
| 「正在加载报告...」 | apps/web/src/views/platform/AbExperimentView.vue:74 | 可删 | 弹窗此刻是空壳，纯文字不提供进度信息 |
| 新建弹窗 | apps/web/src/views/platform/AbExperimentView.vue:80-102 | 必要 | 主任务入口 |
| 实验名称输入 | apps/web/src/views/platform/AbExperimentView.vue:82-84 | 必要 | 唯一标识；但 `required`（:82）只是标签星号，表单无 `rules`，空名可提交 |
| 对照组指令 A | apps/web/src/views/platform/AbExperimentView.vue:85-87 | 必要 | 实验内容本身 |
| 实验组指令 B | apps/web/src/views/platform/AbExperimentView.vue:88-90 | 必要 | 实验内容本身 |
| 目标样本量 | apps/web/src/views/platform/AbExperimentView.vue:91-93 | 可下沉 | 后端默认值与上下限和这里完全一致（gateway_platform_routes.py:786），不改也能跑 |
| 流量分配 slider | apps/web/src/views/platform/AbExperimentView.vue:94-96 | 可删 | 后端默认 0.5（gateway_platform_routes.py:783）；创建后无任何界面可改 |
| 取消 / 启动实验 | apps/web/src/views/platform/AbExperimentView.vue:99-100 | 必要 | 提交与退出 |

### Agent 协作编排（`apps/web/src/views/platform/AgentOrchestrationView.vue`）

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 「刷新」 | apps/web/src/views/platform/AgentOrchestrationView.vue:5-7 | 必要 | 唯一的手动取数入口 |
| 统计卡「编排计划」 | apps/web/src/views/platform/AgentOrchestrationView.vue:14-17 | 可删 | 等于表格行数（:131） |
| 统计卡「执行成功率」 | apps/web/src/views/platform/AgentOrchestrationView.vue:18-21 | 可删 | 口径可疑：`failure_count === 0` 即计入成功（:132），零 Worker 的运行也会被算成成功 |
| 统计卡「平均 Worker 数」 | apps/web/src/views/platform/AgentOrchestrationView.vue:22-25 | 可删 | 分母是当前返回条数（:134-136），后端 limit 默认 50 时这个口径在界面上不可见 |
| 统计卡「平均执行时间」 | apps/web/src/views/platform/AgentOrchestrationView.vue:26-29 | 可删 | 同上（:137-139） |
| 运行表 | apps/web/src/views/platform/AgentOrchestrationView.vue:33-60 | 必要 | 定位某次运行 |
| 列「计划 ID」 | apps/web/src/views/platform/AgentOrchestrationView.vue:34 | 可删 | 内部 ID，抽屉 :66 已有；横向扫描时是噪声 |
| 列「问题」 | apps/web/src/views/platform/AgentOrchestrationView.vue:35 | 必要 | 唯一定位字段 |
| 列「子任务」 | apps/web/src/views/platform/AgentOrchestrationView.vue:36-38 | 必要 | 判断本次编排规模 |
| 列「成功/失败」 | apps/web/src/views/platform/AgentOrchestrationView.vue:39-45 | 必要 | 判断要不要点进去 |
| 列「耗时」 | apps/web/src/views/platform/AgentOrchestrationView.vue:46-48 | 必要 | 排查「慢」的第一维度 |
| 列「Worker 类型」 | apps/web/src/views/platform/AgentOrchestrationView.vue:49-59 | 可合并 | 与「子任务」列同源（:128 由 `worker_results` 派生），逐 Worker 明细在抽屉 :84-96 |
| 行点击开抽屉 | apps/web/src/views/platform/AgentOrchestrationView.vue:33 | 必要 | 唯一的详情入口；无指针光标与悬停提示（见动效发现） |
| 执行详情抽屉 | apps/web/src/views/platform/AgentOrchestrationView.vue:63-98 | 必要 | 详情载体 |
| 抽屉 el-descriptions 3 项 | apps/web/src/views/platform/AgentOrchestrationView.vue:65-69 | 可合并 | 计划 ID / 问题 / 总耗时三项在表格 :34 / :35 / :46 已有 |
| 执行顺序（拓扑排序） | apps/web/src/views/platform/AgentOrchestrationView.vue:72-80 | 必要 | 看懂并行结构 |
| 「并行组 N」 tag | apps/web/src/views/platform/AgentOrchestrationView.vue:74 | 可合并 | 外层 `v-for` 已按组分组，容器本身即可表达「这是一组」 |
| Worker 结果块 | apps/web/src/views/platform/AgentOrchestrationView.vue:84-96 | 必要 | 定位失败点 |
| 「证据数: N」 | apps/web/src/views/platform/AgentOrchestrationView.vue:93-95 | 可删 | 只是 `array.length`，对「谁出错了、慢在哪」没有决策作用；需要证据内容时抽屉里无法展开 |

### 审计日志（`apps/web/src/views/AuditView.vue`）

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 副标题「N 条」 | apps/web/src/views/AuditView.vue:5 | 可合并 | 与表格行数重复，且只是当前页条数 |
| 副标题「N 拒绝」 | apps/web/src/views/AuditView.vue:6 | 可合并 | 由当前页 events 计算（:99），非全量 |
| 副标题「N 失败」 | apps/web/src/views/AuditView.vue:7 | 可合并 | 同上（:100） |
| FilterBarSticky 容器 | apps/web/src/views/AuditView.vue:11-31 | 必要 | 表格很长时保持筛选可达 |
| 「服务」下拉 | apps/web/src/views/AuditView.vue:13-17 | 必要 | 三选一，决定查哪个服务 |
| 「结果」下拉 | apps/web/src/views/AuditView.vue:18-23 | 必要 | 审查「被拒绝」的核心入口 |
| 「用户 ID」输入 | apps/web/src/views/AuditView.vue:24 | 可下沉 | 精确匹配（:105-109），需知道完整 ID |
| 「动作」输入 | apps/web/src/views/AuditView.vue:25 | 可下沉 | 精确匹配，需知道 `platform.experiment.stop` 这类字面量 |
| 「资源类型」输入 | apps/web/src/views/AuditView.vue:26 | 可下沉 | 同上 |
| 「资源 ID」输入 | apps/web/src/views/AuditView.vue:27 | 可下沉 | 同上 |
| 「查询」 | apps/web/src/views/AuditView.vue:28 | 必要 | 触发筛选 |
| 「重置」 | apps/web/src/views/AuditView.vue:29 | 必要 | 一次清空 6 个条件（:116-124） |
| 空态 | apps/web/src/views/AuditView.vue:34-40 | 必要 | 捕获「查无结果」；但它在请求失败时也会渲染，语义见提案 3 |
| 审计表 | apps/web/src/views/AuditView.vue:41-64 | 必要 | 事件列表 |
| 列「时间」 | apps/web/src/views/AuditView.vue:42 | 必要 | 追责的第一维度；直接渲染原始 `created_at`，无格式化 |
| 列「服务」 | apps/web/src/views/AuditView.vue:43-47 | 可删 | 单选筛选后该列恒定；不筛选时也只有两个值 |
| 列「动作」 | apps/web/src/views/AuditView.vue:48 | 必要 | 判断发生了什么 |
| 列「资源类型」 | apps/web/src/views/AuditView.vue:49 | 可下沉 | 筛选后恒定 |
| 列「资源 ID」 | apps/web/src/views/AuditView.vue:50 | 必要 | 定位被操作对象 |
| 列「操作者」 | apps/web/src/views/AuditView.vue:51 | 必要 | 追责主体 |
| 列「角色」 | apps/web/src/views/AuditView.vue:52 | 可下沉 | 与操作者绑定，非独立决策维度 |
| 列「结果」tag | apps/web/src/views/AuditView.vue:53-57 | 必要 | 审查核心 |
| 列「追踪 ID」 | apps/web/src/views/AuditView.vue:58 | 可下沉 | 仅跨系统串联时用 |
| 列 空 label「详情」 | apps/web/src/views/AuditView.vue:59-63 | 可删 | `label=""` 产生一个无名列头；按钮本身必要（:61） |
| 详情抽屉 | apps/web/src/views/AuditView.vue:67-74 | 必要 | 完整信息 |
| JSON pre | apps/web/src/views/AuditView.vue:73 | 可合并 | 只渲染 `details`，抽屉里看不到 service / action / actor / outcome 的完整值 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 下沉 | apps/web/src/views/AuditView.vue:24-27 | 少一次判断 | 一级筛选从 6 个控件降到「服务 + 结果」2 个，其余四个移入可展开的高级筛选。代价：想按动作筛的人多一次展开。风险：如果真实查询分布里「动作」其实是高频维度，下沉反而让高频路径变长 —— 这一点我无法从代码判断，需要真实查询日志或使用者访谈验证后再动。 |
| 删除 | apps/web/src/views/platform/AbExperimentView.vue:12-25 | 少一次判断 | 三张卡与列表里的状态 tag 重复表达同一批事实，且「已完成」(:23) 与 tag 文案「已停止」(:36) 用两个词说同一状态，读者要判断它们是不是一回事。代价：列表为空时失去「一共几个实验」这个一眼可见的数。风险：`apps/web/src/views/**` 下另有 7 个视图有同款统计行（AbExperimentView.vue:191-194 与 AgentOrchestrationView.vue:158-161、ApiKeyManagerView.vue:206-209 逐字相同），单删本页会让 platform 区的视觉节奏不一致；要做就整批做，或先确认这是否是刻意的「平台页统一抬头」。 |
| 加反馈 | apps/web/src/views/AuditView.vue:102-114 | 少一次误操作 | 两件事合并在同一个函数里：① `loadAuditEvents` 只有 `try/finally`，没有 `catch`，请求失败时 `events` 保持 `[]`，于是 :34-40 渲染出「暂无审计事件 / 符合条件的审计记录将在此展示」—— 把「查询出错」说成「没有符合条件的记录」，审查者据此可能得出错误结论；② 请求硬编码 `limit: 50, offset: 0`（:107-108），后端返回的 `pagination` 元数据（`apps/services/api-gateway/src/app/gateway_admin_routes.py:78`）被丢弃，用户不知道是否还有更多。代价：需要一个失败态分支与一行范围提示（或分页控件）。风险：后端 `pagination` 只回 `limit/offset/returned`，**没有 total**，所以做不出「共 N 条」，最多说「已加载 50 条，可能还有更多」；要真 total 需改后端。 |
| 加反馈 | apps/web/src/views/platform/AbExperimentView.vue:52 | 少一次误操作 | 「停止」是唯一的实验下线入口，点击即刻生效（:154 → `gateway_platform_routes.py:794-800` → `instruction_evaluator.py:148-153` 置 `is_active=FALSE`），界面无二次确认；同时 `stopExperiment`（:153-157）没有 `try/catch`，请求失败时既不回滚也无任何提示，用户会以为已停而实际还在跑。代价：低频操作多一次点击。偿还：同页删除 3 张统计卡（:12-25）与「创建于」行（:47-49）之后，本页净元素仍为减少。风险：加确认对话框会引入一个 `ElMessageBox`，需确认它在深色主题下的样式已被 `theme-extras.css:64-74` 覆盖（已覆盖，此项风险低）。 |
| 加反馈 | apps/web/src/views/platform/AgentOrchestrationView.vue:18-21 | 少一次误操作 | 「执行成功率」按 `failure_count === 0` 计成功（:132），零 Worker 的运行（`sub_tasks` 为空或全部未执行）也会被算成成功，卡片可能显示一个偏乐观的数；同时分母是当前返回条数（:131），后端 limit 默认 50（`gateway_platform_routes.py:815`）而界面从不说明。代价：卡片下方多一行口径说明（或改成「最近 N 次运行中的成功率」）。风险：我这个判断基于对 `:132` 的静态阅读，**没有确认后端在运行进行中 / 被取消时如何填 `success_count` / `failure_count`** —— 见存疑第 2 条，验证前不要改逻辑本身的语义。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| HIGH | 目的与频次 / 无障碍 | apps/web/src/components/EnhancedEmpty.vue:108-113（本报告经 `apps/web/src/views/platform/AbExperimentView.vue:28` 与 `apps/web/src/views/AuditView.vue:34-40` 两处触发） | 空态插画（72px 容器）带 `transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)`，`:hover` 时 `scale(1.05) rotate(2deg)`。该图标不可点击，hover 不改变任何状态，旋转 2° 是纯装饰；曲线含超调，不在允许集合内；且 hover 未包在 `@media (hover:hover) and (pointer:fine)` 内，触屏上会留下粘滞姿态。 | 删除该 hover 与整条 transition。空态不表达任何状态，属于「可以完全不动」的场景。 |
| MEDIUM | 缓动与时长 | apps/web/src/components/EnhancedEmpty.vue:108 | 时长 300ms 已达「UI 动效一律 <300ms」的上限，且未使用既有 token（`--transition-fast/base/smooth` = 150/200/250ms，`apps/web/src/style.css:46-48`），是 token 外的第三套时长刻度。 | 若保留则改用 `--transition-base` 并降到 ≤200ms。 |
| MEDIUM | 一致性与 token | apps/web/src/style.css:46-48 vs apps/web/src/views/platform/AbExperimentView.vue:56、:80 / apps/web/src/views/platform/AgentOrchestrationView.vue:63 / apps/web/src/views/AuditView.vue:67 | 项目声明了 `--transition-fast/base/smooth`（`apps/web/src/style.css:46-48`），但全仓没有任何 `--el-transition-*` 覆写（对 `apps/web/src/style.css` 与 `apps/web/src/styles/*.css` 的检索命中数为 0）。因此本报告三个界面里的全部弹窗与抽屉入场动效走 Element Plus 默认曲线与时长，完全不受 design token 管辖 —— 这三页自身零 `transition` / `animation` 声明，动效基调由外部决定。 | 在 `theme-extras.css` 集中把 Element Plus 的过渡变量映射到 `--transition-*`，不要在各视图内单独覆写。 |
| MEDIUM | 性能 / 一致性 | apps/web/src/styles/theme-extras.css:131-143（经 `apps/web/src/layouts/MainLayout.vue:103` 的 `mode="out-in"` 作用于本报告三个页面） | 路由过渡 `page` 用 `transition: opacity 0.25s ease, transform 0.25s ease` + `translateY(±6px)`。`ease` 属于被禁止的 CSS 预设曲线；`mode="out-in"` 意味着离场与入场串行，而这三个页面是本次审计里最重的（审计日志是 10 列 × 最多 50 行的整表），整页位移会让大表被合成两次。 | 这三个重内容页收掉位移分量、只留 opacity，或把 `translateY` 换成不含位移的进入方式；曲线改用 `cubic-bezier(0.23, 1, 0.32, 1)`。 |
| LOW | 缺失的机会 | apps/web/src/views/platform/AgentOrchestrationView.vue:33 | 整行可点击打开抽屉，但没有指针光标也没有悬停提示：已核实 `apps/web/node_modules/element-plus/dist/index.css` 只为可排序表头（`.el-table th.el-table__cell.is-sortable`）设 `cursor:pointer`，没有给表体行设置，全仓也没有为 `.el-table__row` 补过。用户不知道行可点。 | 加 `cursor: pointer`（静态样式，零动效成本），不要为此加动效。 |

## 存疑

- **后端分页没有 total。** `gateway_admin_routes.py:78` 只返回 `{"limit": ..., "offset": ..., "returned": ...}`，没有总数。因此「还有多少条审计记录」在现有接口下无法显示，提案 3 只能做到「可能还有更多」的提示。要给出真实总数需后端改动 —— 需产品和后端确认。
- **`执行成功率` 的口径未经真实数据验证。** `AgentOrchestrationView.vue:132` 用 `failure_count === 0` 判定成功，但后端在「运行进行中」「被取消」「部分子任务未执行」时如何填 `success_count` / `failure_count`，我没有在 `gateway_platform_routes.py:814-830` 之外的代码里确认。验证方法：查 `chat_workflow_runs` 表里 `failure_count = 0 AND success_count = 0` 的行数，若不为 0 则卡片确实说谎。验证前不要改判定逻辑。
- **运行列表的截断不可见。** `listOrchestrationRuns`（`apps/web/src/api/platform.ts:383`）不传 limit，后端默认 50（`gateway_platform_routes.py:815`）。若单用户历史运行超过 50 条，他看到的是最近 50 条且界面无任何提示。需确认真实数据量级后再决定是否加范围提示。
- **行点击抽屉对键盘用户不可达。** `AgentOrchestrationView.vue:33` 的详情入口只有鼠标点击行；表格内没有「详情」按钮（对比 `AuditView.vue:61` 有）。需要真机键盘测试确认 `el-table` 的行是否可聚焦 —— 若不可聚焦，此入口对键盘用户完全不存在。
- **报告弹窗位于 `v-else` 分支内。** `AbExperimentView.vue:56-75` 在 `.experiment-list`（:31 开、:76 关）内部，只有实验列表非空时才存在于 DOM。当前功能自洽（「查看报告」按钮也在同一分支内），但空态下任何把 `reportVisible` 置 true 的路径都会静默无反应（:159-161）。是否要把弹窗移出该分支，取决于未来是否为空态加报告入口 —— 需产品确认。
- **「实验名称」的 `required` 不生效。** `AbExperimentView.vue:82` 只是标签星号，`el-form` 没有 `rules`。空名可提交，后端用 `payload.get("name") or experiment_id` 兜底（`gateway_platform_routes.py:789`），于是列表里会出现 `exp_1755...` 这样的名字而没有任何报错。是否要前端拦截需产品确认。
- **`.audit-stats.muted` 没有任何视觉效果。** `--text-secondary` 与 `--text-muted` 同值（`apps/web/src/style.css:28-29` 都指向 `--slate-600` `#64748b`），所以 `AuditView.vue:5-7` 三个统计在视觉上权重完全相同，`.muted`（:161-163）是一条空规则。要建立层级只能用字重或间距（新增色阶被本次约束禁止）—— 需确认接受哪种做法。
- **审计「时间」列的实际显示内容未知。** `AuditView.vue:42` 直接 `prop="created_at"`，`apps/web/src/api/audit.ts:16-18` 不做转换。实际显示的是 ISO 串还是本地化串，取决于后端返回格式，需真机确认。
- **窄屏下三个页面的表格都没做列裁剪。** `AuditView.vue:200-212` 的 `@media (max-width: 640px)` 只处理标题与统计间距；`AbExperimentView.vue:189-207` 与 `AgentOrchestrationView.vue:156-170` 的 scoped style 里没有任何 `@media`。10 列表格在窄屏的实际表现（是横向滚动还是挤压）需真机确认。
- **`EnhancedEmpty` 的跨界面复用面。** 它在 16 个视图文件里被引用（另有 `apps/web/src/components/DocumentEvents.vue`），所以动效发现第 1、2 条不是本报告的局部问题，已登记进返回摘要的 `systemic_candidates`。
- **统计卡四件套是跨界面模式，不是本报告的特例。** `.stats-row` / `.stat-card` / `.stat-value` / `.stat-label` 在 `apps/web/src/views/platform/` 下 8 个视图各写一份，并分叉成两套互不相容的约定：一套 flex + `--el-fill-color-light` + 24px（`AbExperimentView.vue:191-194`、`AgentOrchestrationView.vue:158-161`、`ApiKeyManagerView.vue:206-209` 逐字相同），另一套 grid + `--bg-panel`/`--border-color` + `--radius-md` + 22px（`CacheManagerView.vue:239-242`、`AgentMonitorView.vue:362-387`、`CostDashboardView.vue:203-208`）。字号 22/24/26px 都不在 `--text-*` 刻度上。**是否统一属于跨界面全局决策，单页不宜改**，故只登记，不进入提案。
- **时间戳格式化在跨界面不一致。** `AbExperimentView.vue:182-184`（秒 ×1000 且丢时间）与 `WebhookManagerView.vue:149`（秒 ×1000）、`AgentMonitorView.vue:275`（不乘）、`KBDocumentView.vue:1147-1154`、`ChatSidebar.vue:80-81` 各不相同。已登记进 `systemic_candidates`。
