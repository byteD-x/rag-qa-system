# 06 AI 模拟面试

审计范围：`apps/web/src/views/interview/InterviewView.vue`、`apps/web/src/api/interview.ts`
路由：`/workspace/interview`（`apps/web/src/router/index.ts:85-95`，`requiresPermission: 'chat.use'`；导航项与同一权限过滤见 `apps/web/src/layouts/MainLayout.vue:220-224`、`MainLayout.vue:267-277`）
依赖组件（仅在与本界面相关处取证）：`components/PageHeaderCompact.vue`、`api/request.ts`、`style.css`（本页实际吃到的全局 el-* 覆盖：`style.css:644-732`）
后端对照（仅用于判断「接口已返回但界面丢弃了什么」）：`apps/services/api-gateway/src/app/gateway_interview_routes.py`、`apps/services/knowledge-base/src/app/kb_generic_routes.py:426-497`

## 唯一用户任务

有 `chat.use` 的求职者/自测用户在「已有绑定了岗位、且题池已发布」的场景下，要在本页连续答完 N 道题，并在结束前拿到每题评分与改进点、结束时拿到总分与逐题结论。

（依据：进入权限 `router/index.ts:90`；题池只取「已发布 + 来源文档可查」的题 `kb_generic_routes.py:440-446`，不足即 409 `kb_generic_routes.py:479-480`；报告接口已返回逐题 `feedback` / `weak_points` `gateway_interview_routes.py:275-287`，前端类型也已声明 `api/interview.ts:62`，但模板未渲染 —— 任务的关键产出被丢在接口与界面之间。）

## 完成该任务的必要步骤

1. 打开 `/workspace/interview`，等 `listKnowledgeBases` + `listKBJobPositions` 两个请求返回（InterviewView.vue:90-94，挂载点 :140）→ **keep**
2. 选岗位（:11-15）→ **keep**（「开始面试」的 disabled 依赖它，:26）
3. 选知识库（:16-20）→ **keep**（可选项被岗位过滤 :83-88，岗位变更自动清空不匹配的库 :141-143，防误选已做对）
4. 设题数（:22，默认 5）→ **keep**（决定这场面试多长，后端按 `count` 取题 gateway_interview_routes.py:33）
5. （可选）填难度 / 题型（:23-24）→ **drop**（自由文本，后端按小写精确匹配 `kb_generic_routes.py:464-469`，猜错即 409，且 409 文案是英文原文）
6. 点「开始面试」（:26 → :96-109）→ **keep**
7. 读题干（:35）→ **keep**
8. 在输入框写回答（:36）→ **keep**
9. 点「提交回答」（:39 → :111-129）→ **keep**
10. 看本题评分与反馈（:41-44）→ **merge**（内容必要，但渲染位置落在「下一次提交后 / 下一题下方」，与题干不对应：`:116-121` 同一次更新里既写入评分又替换题干）
11. 重复 7-10 直到题尽（`completed`，:117-119）→ **keep**
12. 读报告：总分 + 维度分（:49-52）、逐题得分（:53-56）、来源（:57-59）→ **merge**（逐题 `feedback` / `weak_points` 已由接口返回 `gateway_interview_routes.py:283-284`、`api/interview.ts:62`，界面无一列渲染）
13. 「再来一场」复位（:48 → :131-138）→ **keep**（但它是报告加载失败时唯一的可见动作，见提案 5）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页头标题「AI 模拟面试」 | apps/web/src/views/interview/InterviewView.vue:3 | 必要 | 全页唯一的位置标识（MainLayout.vue:220-224 导航同名） |
| 页头副标题「题目只来自已发布且可追溯的知识库题池」 | apps/web/src/views/interview/InterviewView.vue:4 | 可删 | 静态声明，每次进入重复出现；「可追溯」实际由报告「来源」列承担（:57-59），副标题不提供任何操作或状态 |
| 面板标题「开始一场面试」 | apps/web/src/views/interview/InterviewView.vue:9 | 可删 | 与页头标题语义重复，且表单唯一的按钮已写「开始面试」（:26）；配置态由表单自身表达 |
| 岗位选择器 | apps/web/src/views/interview/InterviewView.vue:11-15 | 必要 | 决定题池范围（:83-88 用它过滤知识库；后端按 job_position_id 过滤 kb_generic_routes.py:449-463） |
| 知识库选择器 | apps/web/src/views/interview/InterviewView.vue:16-20 | 必要 | 题池的容器，「开始面试」的硬门控（:26） |
| 题数 | apps/web/src/views/interview/InterviewView.vue:22 | 必要 | 唯一的会话长度控制（:82 默认 5，后端按 count 取题 gateway_interview_routes.py:33） |
| 难度（自由文本） | apps/web/src/views/interview/InterviewView.vue:23 | 可删 | 无取值清单，后端小写精确匹配（kb_generic_routes.py:464-466）；输入任何库内不存在的词都会让整场开始失败（409，kb_generic_routes.py:479-480） |
| 题型（自由文本） | apps/web/src/views/interview/InterviewView.vue:24 | 可删 | 同上（kb_generic_routes.py:467-469）；取值约定只在知识库上传侧以 placeholder 出现（KBUploadView.vue:56、:59「例如：coding / medium」），面试端无从得知 |
| 「开始面试」按钮 | apps/web/src/views/interview/InterviewView.vue:26 | 必要 | 本页主任务动作；`disabled` 前置校验两个必填项，已防主要误操作 |
| 三列参数行 `.form-row` | apps/web/src/views/interview/InterviewView.vue:21、:152 | 可下沉 | 题数/难度/题型均为次要参数（有默认或可留空 :82），却与两个必填选择器同视觉权重（三列 grid） |
| 标题「第 N 题」 | apps/web/src/views/interview/InterviewView.vue:32 | 可合并 | 只显示 `sequence_no`，而总题数 `question_count` 已在同一响应里（api/interview.ts:14-19、gateway_interview_routes.py:204），用户无法判断还剩几题 |
| 难度标签（含「未标注难度」兜底） | apps/web/src/views/interview/InterviewView.vue:33 | 可删 | 值与题库同源，是后端小写原文（kb_generic_routes.py:364-365），中文界面里会显示 `medium` 之类；无值时渲染一个只写「未标注难度」的标签，占位不提供信息 |
| 题干 | apps/web/src/views/interview/InterviewView.vue:35 | 必要 | 任务的核心内容（保留式换行 :153） |
| 回答输入框 | apps/web/src/views/interview/InterviewView.vue:36 | 必要 | 唯一输入面；`rows=8` 与全站 textarea 最小高度一致（style.css:696-702） |
| 字数计数（`show-word-limit`） | apps/web/src/views/interview/InterviewView.vue:36 | 可删 | 上限 30000 字符对面试口述式回答不构成约束，计数常驻在输入框右下角，属于没有对应判断的信息 |
| 提示「来源已绑定到知识库文档与切片」 | apps/web/src/views/interview/InterviewView.vue:38 | 可删 | 声明性文案，占在操作行内与主按钮抢位置（:37-40）；当前题的真实来源（`source`，api/interview.ts:10）在答题态一律不展示，文案与可见事实不符 |
| 「提交回答」按钮 | apps/web/src/views/interview/InterviewView.vue:39 | 必要 | 唯一的推进动作；`disabled="!answer.trim()"` 已防空提交 |
| 评分反馈块 `.evaluation-note` | apps/web/src/views/interview/InterviewView.vue:41-44 | 必要 | 模拟面试的核心产出（分数 + 文字反馈）；但位置错误，见提案 1 |
| 标题「面试报告」 | apps/web/src/views/interview/InterviewView.vue:48 | 必要 | 唯一标识会话已结束的状态 |
| 「再来一场」按钮 | apps/web/src/views/interview/InterviewView.vue:48 | 必要 | 唯一复位入口（:131-138）；风险在于它同时是报告加载失败时唯一的出路，见提案 5 |
| 总分方块 | apps/web/src/views/interview/InterviewView.vue:50 | 必要 | 报告的首要结论（`?? 0` 兜底问题见提案 5） |
| 维度分方块（英文 key） | apps/web/src/views/interview/InterviewView.vue:51 | 可下沉 | key 直接来自 `config_json.scoring_dimensions`（默认 accuracy/depth/logic/expression，gateway_interview_routes.py:226），界面上原样渲染英文；在 `apps/web/src` 内未检索到中文映射 |
| 方块边框 `.score-item` | apps/web/src/views/interview/InterviewView.vue:157 | 可删 | 每个维度包一层 1px 边框方块，与总分方块共 5 个同权重方块；这些是同一层级的数据，用间距/字重即可区分 |
| 报告表格 | apps/web/src/views/interview/InterviewView.vue:53-60 | 必要 | 逐题结论的唯一载体 |
| 序号列「#」 | apps/web/src/views/interview/InterviewView.vue:54 | 可删 | 表格按 `sequence_no` 排序（gateway_interview_routes.py:271），行序即题号；56px 宽度可让给缺失的反馈列 |
| 「题目」列 | apps/web/src/views/interview/InterviewView.vue:55 | 必要 | 与得分对位的题面 |
| 「得分」列 | apps/web/src/views/interview/InterviewView.vue:56 | 必要 | 逐题结论 |
| 「来源」列（原始 UUID） | apps/web/src/views/interview/InterviewView.vue:57-59 | 可下沉 | 渲染 `document_id / chunk_id` 原文，用户无法据此判断任何事；KB 侧只返回 ID 与 quote（kb_generic_routes.py:483-496），前端拿不到文档标题 —— 可追溯承诺应保留，但不必占据一等问题列位 |
| 表单 `@submit.prevent` | apps/web/src/views/interview/InterviewView.vue:10 | 可删 | 表单内没有声明 `native-type="submit"` 的控件（:26 未声明），该防护没有作用对象；`start()` 由按钮 click 驱动（:26 → :96） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 合并 | apps/web/src/views/interview/InterviewView.vue:41-44（配合 :116-121） | 少一次误操作 | 现在评分与「下一题题干 + 空输入框」同帧出现（:121 替换题干、:116 写入评分），用户会把分数当成当前题的。修法：把该块放到下一题题干之上并标注题号（如「第 2 题评分」）。代价：面板变高，题干起始位置下移，滚动位置与视觉锚点变化（需真机确认，见存疑）；需要多存一个「上一题序号」状态，且最后一题的评分在切到报告时仍无处显示（`lastEvaluation` 在报告态不渲染，:47-61）。偿还：删除「未标注难度」标签（:33）与字数计数（:36） |
| 合并 | apps/web/src/views/interview/InterviewView.vue:54、:57-59（数据源 api/interview.ts:62、gateway_interview_routes.py:283-284） | 少一次判断 | 报告已含逐题 `feedback` / `weak_points` 但一列都不显示，用户读完只知道自己「几分」，不知道错在哪。修法：删掉「#」列（行序即题号），把「来源」原样 UUID 降为 hover 提示（题目列已用 show-overflow-tooltip，:55），腾出的列位给反馈/弱项。代价：来源从显性列降为 hover 才可见，「可追溯」在报告页的可见度下降（与页头副标题的承诺相关，需产品确认）；`feedback` 后端可长至 4000 字符（gateway_interview_routes.py:141），需要限行/展开策略，否则表格行高失控 |
| 加反馈 | apps/web/src/views/interview/InterviewView.vue:113-122（输入框 :36） | 少一次误操作 | 提交后等评分往返（LLM 调用，gateway_interview_routes.py:160-165）期间输入框仍可编辑，响应到达时 `:122` 直接清空，用户在这段时间补写的内容静默消失；界面上只有按钮 loading 一个状态位。修法：提交中把输入框置为只读并明示「评分中」，清空只在下一题渲染后发生。代价：新增一句状态文案与一个只读态（违反默认删除，由删除字数计数 :36、提示文案 :38 偿还）；若评分耗时接近 axios 60s 超时（api/request.ts:30），只读等待会放大焦虑，需要真实耗时数据支撑（见存疑） |
| 删除 | apps/web/src/views/interview/InterviewView.vue:23-24 | 少一次误操作 | 两个自由文本字段的取值只能靠猜，而猜错不会得到「筛选条件无效」的反馈 —— 只会拿到 409，提示文案是英文原文（gateway_interview_routes.py:58 + api/request.ts:104-105），用户会去怀疑知识库而不是自己填的词。删掉后默认「不限」，与 placeholder 的承诺一致。代价：失去按难度/题型收窄题池的能力；若要保留，必须先把它们换成取自题库的枚举（本次未发现任何 facet/取值接口，grep `question-pool` 仅命中 kb_generic_routes.py:426，需要后端先提供） |
| 删除 | apps/web/src/views/interview/InterviewView.vue:50、:125 | 少一次判断 | 两处「说假话」的兜底：(1) 报告请求失败时 `completed` 已置 true（:118），`:50` 的 `?? 0` 会把失败渲染成「总分 0」的空报告；(2) `:125` 的 catch 与请求层拦截器（api/request.ts:158）对同一次失败各弹一条 toast，文案还不一样（「回答提交失败」vs 服务端原文）。修法：删掉 `?? 0` 与重复 toast，改用未加载/失败态并保留会话（否则用户只剩「再来一场」一条路，:48，等于销毁这场面试）。代价：只剩服务端文案，而当前 409/502 是英文（gateway_interview_routes.py:58、:45），需要后端本地化或在前端按 code 映射，否则用户从「两条中文错」变成「一条英文错」；新增失败态分支需要一个容器（由删除 `@submit.prevent` :10、维度方块边框 :157 偿还） |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 状态指示 / 缺失的机会 | apps/web/src/views/interview/InterviewView.vue:41-44、:116-121 | 提交后题干与评分在同一帧整体替换：旧题的分数出现在新题下方，界面没有任何位置或文案说明它属于上一题；评分块本身是纯 `v-if` 出现（:41），无入场也无状态位 | 先修归属（见提案 1），再考虑动效：只对该块做 opacity + 位移 ≤4px、200ms、`cubic-bezier(0.23,1,0.32,1)` 入场；不要做高度/边距过渡，也不要从 scale(0) 起 |
| HIGH | 操作反馈 | apps/web/src/views/interview/InterviewView.vue:113-122、:36 | 评分往返期间输入框仍可编辑（:36 无 `:disabled`/`:readonly`），响应到达后 `:122` 直接 `answer.value = ''`；用户在这段时间的输入没有任何提示地消失。整段等待只靠按钮 loading 表达 | 提交中将输入框置为只读并给出文本状态；不要加动效 —— 该场景属「数十次/天」级别，按规则只做状态指示 |
| MEDIUM | 防止突变突兀 | apps/web/src/views/interview/InterviewView.vue:30、:47（对照 :149 单容器） | 三个状态共用同一个 `.panel`（:149）用 `v-if/v-else-if/v-else` 整块替换，三态高度差异大（表单 → 题干+文本框 → 表格），而 `.interview-content` 是独立滚动容器（:148、:147 覆盖了 style.css:182-191 的滚动） | 不做位移过渡；先靠固定顶部锚点（题干与表单同一水平起始位）稳定视觉，仅在报告首次出现时允许 opacity ≤250ms；是否有可见跳变需真机确认 |
| MEDIUM | 一致性与 token | apps/web/src/views/interview/InterviewView.vue:151、:153、:158、:159 | 字号全部硬编码 px：18px / 20px / 22px / 13px，未使用 `--text-h1/h2/body/caption`（style.css:32-35）；22px 与 `--text-h1`（1.375rem）等值，18px 与 `--text-h2` 等值，20px 与 13px 在现有刻度上没有对应值 | 归位到已有 token：面板标题与题干用 `--text-h2`、大分数用 `--text-h1`、`.muted` 用 `--text-caption`；不得新增刻度，13px/20px 的取舍需设计确认 |
| MEDIUM | 无障碍 | apps/web/src/views/interview/InterviewView.vue:41-44、:39 | 评分/反馈块是条件渲染出现，没有 `aria-live`；提交完成后按钮从 loading/disabled 回到可用，焦点不回到题干或输入框，键盘与读屏用户不会被告知「评分已到、可以继续」 | 该块加 `aria-live="polite"`（不新增视觉元素）；下一题渲染后把焦点移回输入框 |
| LOW | 目的与频次 | apps/web/src/views/interview/InterviewView.vue:26、:39（样式来自 style.css:652-654） | 主按钮 hover 只有瞬时 `opacity: 0.9`，无过渡也无位移；按钮 hover 属高频交互，按规则应「极简或砍掉」。全局 `:hover` 位移问题已在已知清单，本条是该全局样式落在本页的特例（属性是 opacity，不是位移） | 推荐删除该 hover（本页按钮已用 loading/disabled 表达可用性）；若保留，时长 ≤150ms 且包进 `@media (hover:hover) and (pointer:fine)` |

## 存疑

- 评分往返的真实耗时未知（LLM 评分，`max_tokens ≤ 1200`，gateway_interview_routes.py:160-165）。「评分中」是否需要进度或计时文案，取决于 P50/P95 实测。
- 刷新页面后 `session` 只存在于内存 ref（InterviewView.vue:75），后端我只检索到 `start / answer / report` 三个端点（gateway_interview_routes.py:173、:207、:258），没有「继续面试」入口。进行中的面试无法恢复是刻意设计还是缺失，需要产品确认。
- 13px 与 20px 应归到哪个 token 需设计确认：13px 在现有刻度（12/15/18/22）之间，20px 也介于 `--text-h2` 与 `--text-h1` 之间。
- 本仓库未见给 Element Plus 传 locale（main.ts:1-36；element-plus-components.ts:11、:64 只做组件注册）。本页「知识库」下拉在未选岗位时必然为空（:83-88），其空态文案的实际语言需要在浏览器里确认（Element Plus 默认 locale 为英文）。
- 报告逐题 `feedback` 的长度分布未知（后端截断 4000 字符，gateway_interview_routes.py:141）。放进表格前需要限行/展开策略，取多长合适要与产品确认。
- 窄屏（<680px，:160 只调整了 `form-row` 与题干字号）下 `el-table`（:53）会横向溢出，`.interview-content` 的 `overflow: auto`（:148）表现需真机确认。
- 维度 key 的中文映射：我只在 `apps/web/src` 范围内 grep 过（`accuracy` 仅命中无关字段 platform.ts:222），「没有映射」这个结论只在我的检索范围内成立，需要人确认是否有别处的字典或后端已本地化。
- 「提交后立刻清空输入框导致丢失补写内容」这条，我判断的依据是代码路径（:113-122），用户是否真的会在等待期继续输入需要真机观察或埋点确认。
- 本页 `el-table` 的 `show-overflow-tooltip`（:55）在移动端无 hover，溢出内容如何查看未验证；若按提案 2 增加反馈列，这一点会放大。
