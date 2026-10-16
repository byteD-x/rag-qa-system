# 04 统一问答（页面层）

## 唯一用户任务

业务员工在需要依据公司内部文档确认流程或规则时，要在 `/workspace/chat` 用一句自然语言提问，并拿到一条带出处、可当场核对的答案。

## 完成该任务的必要步骤

1. 打开 `/workspace/chat`，等知识库与会话列表加载完，页面自动打开一条会话或停在草稿态 — keep（`apps/web/src/views/chat/UnifiedChatView.vue:197-213`、`apps/web/src/store/chat.ts:171-179`）
2. 判断是否要限定检索范围：默认全库可直接提问，要限定才打开「范围」chip — keep（`apps/web/src/views/chat/components/ChatHeader.vue:27-100`；非全库且未选库时提交会被拦下：`apps/web/src/store/chat.ts:334-337`）
3. 在输入框输入问题并发送（Enter 或点发送按钮） — keep（`apps/web/src/views/chat/components/ChatComposer.vue:4-24`、`UnifiedChatView.vue:148-158`）
4. 等待期间确认「正在检索 / 正在生成」 — merge（同一等待态有两套指示器：`UnifiedChatView.vue:47-59` 与 `apps/web/src/views/chat/components/ChatMessageItem.vue:29-32`）
5. 读回答正文 — keep（`ChatMessageItem.vue:28-35`）
6. 需要核对时读引用来源 — keep（`ChatMessageItem.vue:37-39`）
7. 被拒答或降级时读安全提示条，决定是否换问法 — keep（`ChatMessageItem.vue:15-21`、`apps/web/src/store/chat.ts:90-103`）
8. 需要补充信息时（interrupt）在卡片里选一项再继续 — keep（`ChatMessageItem.vue:33`、`apps/web/src/store/chat.ts:149-157`、`:409-444`）
9. 需要排障或看依据时打开「轨迹」抽屉 — demote（`ChatMessageItem.vue:46-48` → `UnifiedChatView.vue:68`、`:176-180`；低频，且已按需展开）
10. 对回答给反馈 — demote（`ChatMessageItem.vue:51-92`；打开弹层即写入，低频动作占每屏常驻位置）
11. 换问题继续或回到历史会话 — keep（`apps/web/src/views/chat/components/ChatSidebar.vue:21-38`、`:88-96`）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 全屏容器 `page-shell chat-page` | `apps/web/src/views/chat/UnifiedChatView.vue:2` | 必要 | 撑满视口并禁止页面级滚动（`:243-251`），使消息列表成为唯一滚动容器 |
| 历史会话侧栏 | `UnifiedChatView.vue:5` | 必要 | 回到既有问答的唯一入口，含搜索与「开启新对话」（`ChatSidebar.vue:13-37`、`:88-96`） |
| 移动端侧栏开关 | `ChatHeader.vue:4-12` | 必要 | ≤768px 侧栏默认收起（`UnifiedChatView.vue:129-131`），没有它无法打开历史 |
| 会话标题 | `ChatHeader.vue:13` | 必要 | 回答「我在哪条对话里」（`apps/web/src/store/chat.ts:52-58`） |
| 焦点 chip（条件渲染） | `ChatHeader.vue:16-25` | 可合并 | 整块 chip 就是「清除」（`:20`），内层「清除」文字是伪控件（`:24`、`:241-244`） |
| 范围 chip + 弹层（模式 / 知识库 / 文档 / 常识兜底） | `ChatHeader.vue:27-100` | 必要 | 决定回答落在哪个知识库；非全库且未选库时提交被拦（`apps/web/src/store/chat.ts:334-337`） |
| 弹层内「范围摘要」段 | `ChatHeader.vue:96-98`、`:138-157` | 可删 | 把上方四个控件已表达的状态改写成句子；唯一增量只是解释默认全库 |
| 执行模式 chip + 弹层（标准 RAG / Agent） | `ChatHeader.vue:102-119` | 可删 | 面向实现分支，弹层自述差异是「多步检索 vs 速度」（`:116`），业务用户无法据此判断；KB 跳转路径固定以 grounded 起草（`apps/web/src/store/chat.ts:233`） |
| 状态朗读区 | `UnifiedChatView.vue:11-13` | 必要 | 长回答期间唯一的进度播报（`:150`、`:226-235`），视觉上 1px 隐藏（`:272-282`） |
| 消息列表容器 | `UnifiedChatView.vue:15` | 必要 | 唯一滚动容器，`@scroll` 维护自动滚动开关（`:119-126`） |
| 欢迎区（图标 / 标题 / 副标题） | `UnifiedChatView.vue:17-23` | 可删 | 仅在无会话或点「开启新对话」后可见（`:210-212`、`ChatSidebar.vue:88-91`）；图标为纯装饰，且用硬编码 16px 圆角 / 32px 字号（`:290-301`） |
| 推荐问题卡 ×3 | `UnifiedChatView.vue:24-35`、`:102-106` | 可删 | 硬编码演示问题，与用户自己的知识库无关；点击只填词、不发送也不聚焦（`:170-174` → `ChatComposer.vue:52-54`） |
| 用户消息条目 | `ChatMessageItem.vue:2-6`、`:33-34` | 必要 | 任务输入的确认 |
| Assistant 身份行 + 回答模式徽章 / Agent 徽章 | `ChatMessageItem.vue:9-13` | 可合并 | 与「回答依据」（`:23-26`）是同一类信息的两处表达 |
| 安全提示条 safety-alert | `ChatMessageItem.vue:15-21` | 必要 | 拒答 / 降级时的唯一解释（`apps/web/src/store/chat.ts:90-103`） |
| 回答依据 answer-basis | `ChatMessageItem.vue:23-26` | 可合并 | 同「Assistant 身份行」，同一件事的第三种写法 |
| 引用列表 | `ChatMessageItem.vue:37-39` | 必要 | 「可当场核对」这一任务的载体 |
| 性能指标（检索 ms / 召回条数 / 可信度） | `ChatMessageItem.vue:43-45` | 可下沉 | 三个数字都不产生用户动作；同类数据在轨迹抽屉已有（`apps/web/src/views/chat/components/ChatTraceDrawer.vue:15-17`） |
| 轨迹入口 + 轨迹抽屉 | `ChatMessageItem.vue:46-48`、`UnifiedChatView.vue:68`、`:176-180` | 可下沉 | 低频排障动作，已是按需抽屉 |
| 反馈按钮 + 反馈弹层 | `ChatMessageItem.vue:51-92` | 可合并 | 打开弹层即写入 verdict（`:156-160`），弹层里的「取消」（`:87`）并不能撤销已提交的表态 |
| interrupt 补充信息卡 | `ChatMessageItem.vue:33` | 必要 | 复杂问题唯一继续路径（`apps/web/src/store/chat.ts:149-157`、`:409-444`） |
| 页面级 typing 兜底指示器 | `UnifiedChatView.vue:47-59`、样式 `:377-426` | 可合并 | 与 `ChatMessageItem.vue:29-32`、`:273-300` 同一状态两套实现；新建会话（`apps/web/src/store/chat.ts:341-352` 的 ensureSession 网络往返）与 resumeInterrupt（`:409-419`，不推占位消息）时只有它在显示 |
| Composer 输入框 + Enter 发送 | `ChatComposer.vue:4-13` | 必要 | 主任务唯一输入 |
| Ctrl+Enter 绑定 | `ChatComposer.vue:11` | 可删 | Enter 已发送（`:12`），组合键不减少任何步骤 |
| 发送 / 停止按钮 | `ChatComposer.vue:14-24` | 必要 | 唯一停止入口（`apps/web/src/store/chat.ts:206-213`） |
| 底部 AI 免责声明 | `ChatComposer.vue:26-28` | 必要 | 逐条回答之外唯一的 AI 风险声明 |
| ≥1920px 三栏 grid 规则 | `apps/web/src/styles/responsive-enhancements.css:225-227` | 可删 | 对 flex 容器无效（`UnifiedChatView.vue:253-261`），是 360/1fr/420 三栏时代的遗留 |
| ≤768px `.message-bubble` 强制覆盖 | `apps/web/src/styles/responsive-enhancements.css:127-130` | 可删 | 把 assistant 纯文本气泡的 `padding: 4px 0`（`ChatMessageItem.vue:251-254`）强制改成 14px/16px，正文在移动端被额外内缩（需渲染确认，见存疑） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 加反馈 | `apps/web/src/views/chat/components/ChatComposer.vue:11-12`（配套 `apps/web/src/views/chat/UnifiedChatView.vue:148-158`） | 少一次误操作 | 发送绑定只判 Enter 与修饰键（`.enter.exact`），前端 `apps/web/src` 全量 grep 没有任何 `isComposing` 守卫；而 element-plus 2.13.3 在合成期间不写回 v-model（依赖源码 `node_modules/element-plus/es/components/input/src/input.vue2.mjs:189-190` 的 `if (isComposing.value) return;`），所以只要输入法在合成中派发 key 为 Enter 的 keydown，提交的就是合成前的旧文本（半句话）。修复：`handleAsk` 前判 `event.isComposing`。代价与风险：不同输入法 / 浏览器在合成期是否派发 Enter 的行为不一致，必须先真机验证（见存疑）；加守卫后，少数输入法「回车确认候选、再回车发送」的第二下可能被吞掉，用户要再按一次。 |
| 合并 | `apps/web/src/store/chat.ts:341-352`、`:409-419`（删 `apps/web/src/views/chat/UnifiedChatView.vue:47-59` 与样式 `:377-426`） | 少一次判断 | 让用户消息与占位 assistant 消息先入列、再 `ensureSession()`，同一等待态就只剩 `ChatMessageItem` 一处指示器，页面级兜底块（约 30 行模板 + 样式）可整块删除；副作用是问句立刻出现在列表里，缩短「点了发送但列表没反应」的窗口。代价与风险：乐观入列后若建会话失败，列表会留下一条没有对应的用户消息（`store/chat.ts:397-401` 目前只清理流式占位，需要在 catch 里回滚或标失败）；`resumeInterrupt`（`:409-444`）必须同时补占位消息，否则恢复期间没有任何指示器。 |
| 加反馈 | `apps/web/src/store/chat.ts:397-401`、`:331-350`（配套 `ChatComposer.vue:44-49`） | 少一步 | 失败时占位 assistant 消息被整条移除，列表里没有失败标记，唯一信号是 3 秒 toast（`:401`），问句留在列表里却无法就地重发，用户要重新输入或复制粘贴一遍。修复：复用 `safety_notice` 通道（`store/chat.ts:90-103`）在同一条消息上承载失败态，或失败时把问题回填输入框。代价与风险：回填会覆盖用户失败后已经输入的新内容（只能约定「输入框非空则不覆盖」，否则又要新增「恢复上一问」入口）；把失败态做成一条消息会永久留在会话记录里，进入历史会话时会再次加载，后端是否承认这类消息类型需确认。 |
| 删除 | `apps/web/src/views/chat/UnifiedChatView.vue:24-35`、`:102-106`（配套样式 `:285-351`） | 少一次误操作 | 三条硬编码演示问题（报销审批 / 试用期请假 / 客服升级）与用户自己的知识库无关，却是空态首屏最大的一块；点击只填词不发送（`:170-174` → `ChatComposer.vue:52-54`），用户容易把它当成「已经问过了」。代价与风险：新建会话的空态只剩输入框和一行标题，新用户没有示例可点；要保留示例就必须改成按当前知识库动态生成（新增数据依赖与空库兜底），成本高于删除。 |
| 删除 | `apps/web/src/views/chat/components/ChatHeader.vue:102-119` | 少一次判断 | 头部常驻「标准 RAG / Agent 模式」开关，弹层文案自述差异是「多步思考、多次检索 vs 速度较快」（`:116`），业务用户无法据此判断该选哪个，却每次都要在头部多扫一个 chip。代价与风险：这是全仓唯一能设置 `executionMode='agent'` 的入口（grep 命中的只有本文件与 store），删除后 Agent 模式从 UI 不可达，必须产品确认是否已无人使用；若仍需保留，应移到检索测试 / 调试类界面而不是业务问答页头部。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 无障碍 | `apps/web/src/views/chat/UnifiedChatView.vue:113-116`（全局规则 `apps/web/src/style.css:806-815`） | 程序化 `scrollTo({behavior:'smooth'})` 不受 `prefers-reduced-motion` 约束：全局通配符只清 CSS 动画与过渡，而 `scroll-behavior` 这个 CSS 属性管不到 API 里显式传入的 `smooth`（CSS 只决定 `auto` 时怎么滚）。少数派用户每轮问答仍会看到整屏平滑滚动。 | 在 `scrollMessagesToBottom` 内读 `matchMedia('(prefers-reduced-motion: reduce)')`，命中时传 `'auto'`；不要指望样式表兜住。 |
| HIGH | 缓动与时长 | `apps/web/src/views/chat/UnifiedChatView.vue:429-437` | `.chat-fade` 是 `0.3s ease`：`ease` 属被禁止的 CSS 预设曲线，时长又顶在「UI 动效一律 <300ms」的边界；enter 与 leave 共用同一组值，切换会话或清空列表时旧列表与新列表在 300ms 内重叠（`transition-group` 未定义 move 类，leave 元素仍占位）。 | 入场改 `opacity`（可配 8px 位移或最低 `scale(0.95)`）200ms `cubic-bezier(0.23,1,0.32,1)`；整列表替换（`startDraftSession`、`selectSession`）不走 enter/leave。 |
| MEDIUM | 可打断性 / 一致性与 token | `apps/web/src/views/chat/UnifiedChatView.vue:108-117`、`:119-126`、`:133-139`、`:151-157`、`apps/web/src/store/chat.ts:377`、`:396` | 同一回合里同一个容器用了两种滚动行为：显式 `smooth`（起、止各一次）与 ResizeObserver 里的瞬时滚动（`:135` 传 `false`），用户看到「平滑滚一下 + 突然跳一下」；而 `shouldAutoScroll` 只在 `@scroll` 事件里更新（`:119-126`），RO 的兜底时机取决于渲染时序而非用户意图。 | 固定一种行为：建议只在结果到达时滚一次 `smooth`；RO 仅在 `shouldAutoScroll` 为真且无进行中滚动时兜底；reduced-motion 一律走 `auto`。 |
| MEDIUM | 物理性与原点 | `apps/web/src/views/chat/UnifiedChatView.vue:419-422` | 兜底指示器的 `@keyframes typing` 从 `scale(0)` 起（规则要求入场最低 `scale(0.95)`；循环指示器每 1.4s 完全消失再出现，观感等同「重启」），且与 `apps/web/src/views/chat/components/ChatMessageItem.vue:293-296` 完全重复（同名 keyframes、同名类）。 | 两处合成一处（见提案 2）；要保留循环脉冲就改成 opacity 或 `scale(0.6) → 1`。 |
| MEDIUM | 一致性与 token | `apps/web/src/views/chat/UnifiedChatView.vue:331-339` | `.suggest-card` 用 `transition: all 0.2s`（已在全局清单）加 hover `translateY(-2px)` + `box-shadow`，并且 `border-color: var(--blue-400)` 引用了一个不存在的 token（`apps/web/src/style.css:17-20` 只定义到 blue-500/600/700/50）。本页特例是：这是页面唯一的 hover 位移，且过渡里含着一条无效属性。 | 删掉位移与投影，hover 只留边框或背景；`--blue-400` 换成已定义 token 或补定义（见系统性候选）。 |
| MEDIUM | 缺失的机会 | `apps/web/src/store/chat.ts:397-401`、`:331-350` | 失败路径把占位 assistant 消息整条删除，列表里没有失败痕迹，唯一反馈是 3 秒 toast（`:401`），用户无法就地重试。 | 用同一条消息承载失败态（复用 `safety_notice` 通道），或失败时回填输入框（见提案 3）。 |
| MEDIUM | 缺失的机会 | `apps/web/src/api/chat.ts:138-150`、`apps/web/src/views/chat/UnifiedChatView.vue:47-59` | 问答走的是非流式 POST（`createChatRunV2` 是普通 `request.post`，无 SSE），等待期间没有任何增量输出，`streaming` 只是占位标记（`store/chat.ts:352-374`、`:389`）；同文件的流式接口 `streamChatMessage`（`api/chat.ts:108-120`）全仓已无调用方。 | 确认是否要接回流式；若不接，删掉页面级兜底指示器与 `isRetrieving` 分支，只留一处静态等待态。 |
| LOW | 一致性与 token | `apps/web/src/views/chat/UnifiedChatView.vue:290-311`、`:341-351` | 欢迎区硬编码 24px / 15px / 18px / 32px 字号与 16px 圆角，均不在 token 刻度内（`apps/web/src/style.css:31-44`：`--text-h1` 22px、`--text-h2` 18px、`--text-body` 15px、圆角 6/8/12/14）。 | 提案 4 若删掉欢迎区，随删除消失；若保留，字号改 token，18px/32px 无对应刻度则删或用 caption。 |
| LOW | 一致性与 token | `apps/web/src/views/chat/components/ChatSidebar.vue:107` | 侧栏上挂着 `transition: width 0.3s ease`，但桌面固定 280px、宽度从不变化，属死属性；且 width 是规则禁止动的属性（≤768px 的开合已由 `:252-253` 的 `transform 0.2s` 承担）。 | 删除该 transition；保留移动端 transform 方案。 |

## 存疑

- 提案 1 的 IME 行为需要真机验证（Windows 微软拼音 / 搜狗、macOS 拼音）：我只确认了代码里没有任何 `isComposing` 守卫（前端 `apps/web/src` 全量 grep 命中 0 处），以及 element-plus 2.13.3 合成期间不写回 v-model。若实测某些输入法在合成中根本不派发 Enter keydown，该提案降级为防御性改动；验证方法：在输入法候选未上屏时按 Enter 确认候选，观察是否发出请求。
- `var(--blue-400)` 的实际渲染结果需确认：按 CSS 自定义属性规范，未定义变量属「计算值无效」，该声明会退化成 `unset`，`border-color` 因此回退为 `currentColor`（hover 边框由浅灰突变深色）。是否补定义还是替换掉全部用法，需要设计决定。
- ≤768px 的 `.message-bubble { max-width: 90% !important; padding: 14px 16px !important }`（`apps/web/src/styles/responsive-enhancements.css:127-130`）会让 assistant 纯文本气泡额外内缩 16px，与同列 4px 缩进的标题行不对齐；严重程度需真机渲染确认。
- `applyRoutePreset` 无条件 `startDraftSession()`（`UnifiedChatView.vue:182-195`）：带 `preset` 参数进入会清空当前会话视图并把执行模式重置为 grounded（`store/chat.ts:227-234`）。从文档页跳转时这是预期行为，但在聊天页内改 query（浏览器前进 / 后退、外部链接）会静默丢弃当前视图，需产品确认是否要提示。
- 空态三条推荐问题（`UnifiedChatView.vue:102-106`）是否与部署时实际知识库内容匹配，无法从前端只读确认；需要拿真实 KB 清单核对，再决定「删除」还是「改为按知识库动态生成」。
- `store/chat.ts:210-212` 会自动打开 `sessions[0]`，但 `listChatSessions()`（`api/chat.ts:76-78`）未带任何排序参数，返回顺序依赖后端；若首条不是最近会话，首屏打开的就不是用户预期的那条。
- `api/chat.ts:96-120` 的 `sendChatMessage` / `streamChatMessage` 全仓无调用方（仅测试 mock 命中）：是待接回的流式方案，还是历史遗留可直接删除？这决定「缺失的机会」那一条的修复方向。
- `apps/web/src/styles/responsive-enhancements.css:110-112`、`:201-203`、`:225-227` 三处 `.chat-workspace` 用 grid 列定义（280/1fr/320、360/1fr/420），而页面容器是 flex（`UnifiedChatView.vue:253-261`）：规则不生效。是删除，还是产品计划恢复常驻的第三栏（轨迹面板）？需要产品确认。
- `executionMode='agent'` 目前是否仍有人使用无法从前端确认（唯一入口 `ChatHeader.vue:102-119`）；需查后端 run 记录或埋点，这决定提案 5 能否执行。
- 本轮为只读静态审计，未启动前端也未跑测试：`.dot` 动画在 reduced-motion 下的实际表现、toast 停留时长、移动端气泡内缩的观感均未实测，需实机或 `npm run test:unit` / 渲染验证。
