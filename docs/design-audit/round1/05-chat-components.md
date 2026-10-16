# 05 统一问答（组件层：侧栏/头部/输入框/消息/轨迹抽屉/中断卡）

审计范围：apps/web/src/views/chat/components/{ChatSidebar,ChatHeader,ChatComposer,ChatMessageItem,ChatTraceDrawer,ChatInterruptCard}.vue，路由 /workspace/chat。只读审计，未修改任何源码。

## 唯一用户任务

知识库使用者 在 需要基于内部资料拿到可核查答案 的场景下，要 一次输入问题、读完带依据的回答，并能当场核对它的来源或执行轨迹。

## 完成该任务的必要步骤

1. 打开或切换会话（侧栏列表 /「开启新对话」）— keep
2. 在输入框写下问题并发送 — keep（清零时机有问题，见提案 2）
3. 阅读回答正文 — keep
4. 核对回答的依据与可信度 — merge（当前同一消息里有 5 处可信度/遥测信号：ChatMessageItem.vue:11、:23-26、:43-45）
5. 需要时展开「轨迹」抽屉看执行过程、失败原因或重试 — keep
6. 可选：对回答给 👍/👎 — keep（👎 的写入时机有问题，见提案 1）
7. 命中中断卡时选项/补话后「继续」 — keep

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 侧栏容器（aria-hidden + inert） | apps/web/src/views/chat/components/ChatSidebar.vue:2 | 必要 | 移动端为覆盖层，inert 保证离屏时不可聚焦 |
| 「开启新对话」按钮 | apps/web/src/views/chat/components/ChatSidebar.vue:4-7 | 必要 | 侧栏内唯一非会话列表动作 |
| 移动端侧栏关闭按钮 | apps/web/src/views/chat/components/ChatSidebar.vue:8-10 | 必要 | 44px 触控目标；无遮罩可点，只能靠它关闭 |
| 会话搜索框 | apps/web/src/views/chat/components/ChatSidebar.vue:14 | 必要 | 会话多时定位历史对话的唯一入口（过滤逻辑 :70-77） |
| 空态两分支（无历史 / 无匹配） | apps/web/src/views/chat/components/ChatSidebar.vue:15-20 | 可合并 | 两个 v-if 分支输出同一 `.session-empty` 结构，仅文案不同 |
| 「最近对话」分组标题 | apps/web/src/views/chat/components/ChatSidebar.vue:22 | 可删 | 列表只有一个分组，标题不承担任何分组区分（样式 :164-170） |
| 会话行图标 ChatLineRound | apps/web/src/views/chat/components/ChatSidebar.vue:31 | 可删 | 每行重复同一图标、不区分信息，占掉 28px 标题宽度（:181 gap 12px + :204 16px） |
| 会话标题 + title 兜底 | apps/web/src/views/chat/components/ChatSidebar.vue:32-34 | 必要 | 截断时的兜底提示 |
| 会话日期 | apps/web/src/views/chat/components/ChatSidebar.vue:35 | 必要 | 同名会话的唯一区分（:78-82 格式化） |
| 会话选项下拉（重命名/删除） | apps/web/src/views/chat/components/ChatSidebar.vue:41-55 | 必要 | 删除带二次确认（apps/web/src/store/chat.ts:266） |
| footer 顶部分隔线 rgba(0,0,0,0.05) | apps/web/src/views/chat/components/ChatSidebar.vue:224 | 可删 | 非令牌色；上下已有 16px padding，用间距即可区分（Less is more 降层级） |
| `transition: width 0.3s ease` | apps/web/src/views/chat/components/ChatSidebar.vue:107 | 可删 | 死过渡，见动效表第 1 行 |
| 三处 hover 浅底 | apps/web/src/views/chat/components/ChatSidebar.vue:145-149, :193-195, :242-245 | 可合并 | 同一种「浅底 + 变色」重复三次，未用令牌 |
| 移动端侧栏开关 | apps/web/src/views/chat/components/ChatHeader.vue:4-12 | 必要 | 移动端侧栏默认关闭（UnifiedChatView.vue:129-131） |
| 会话标题 | apps/web/src/views/chat/components/ChatHeader.vue:13 | 必要 | 当前上下文唯一标识 |
| 焦点 chip（含内嵌「清除」） | apps/web/src/views/chat/components/ChatHeader.vue:16-25 | 可合并 | 标签与「清除」是同一动作的两个入口，@click 只有一个（:20）——合并成一个可点击目标 |
| 范围 chip | apps/web/src/views/chat/components/ChatHeader.vue:27-32 | 必要 | 但标签只取 scopeMode，可能与实际检索范围不一致，见存疑 |
| 范围 popover 容器 | apps/web/src/views/chat/components/ChatHeader.vue:34-99 | 必要 | 4 项设置挂在一个触发点后，符合降层级 |
| 范围模式三选一 | apps/web/src/views/chat/components/ChatHeader.vue:38-42 | 必要 | 与 chip 文案同源（:31） |
| 知识库多选 | apps/web/src/views/chat/components/ChatHeader.vue:45-62 | 必要 | 选项带可检索文档数（:59），是选库的关键依据 |
| 限定文档多选 | apps/web/src/views/chat/components/ChatHeader.vue:65-82 | 可下沉 | 多数会话不缩圈到文档；已在一层 popover 内，可再收进「高级」折叠 |
| 回答策略开关 | apps/web/src/views/chat/components/ChatHeader.vue:85-93 | 必要 | 常识兜底 vs 严格依据，影响答案可信边界 |
| 范围摘要框 | apps/web/src/views/chat/components/ChatHeader.vue:96-98 | 可删 | 复述上方控件已表达的状态（生成逻辑 :138-157），不新增信息 |
| 执行模式 chip | apps/web/src/views/chat/components/ChatHeader.vue:102-108 | 必要 | 切换点，文案即当前模式 |
| 执行模式 popover + 说明段 | apps/web/src/views/chat/components/ChatHeader.vue:109-118 | 必要 | 两选项后果不同，说明段是决策支持（区别于上一条的纯复述） |
| 硬编码品牌色（is-agent / focus） | apps/web/src/views/chat/components/ChatHeader.vue:229-239 | 可删 | #059669/#a7f3d0/#ecfdf5/#275dad/#bfd7ff/#f5f9ff 绕过 token，见 systemic_candidates |
| 输入框 | apps/web/src/views/chat/components/ChatComposer.vue:4-13 | 必要 | 主任务入口 |
| 发送/停止 单按钮双态 | apps/web/src/views/chat/components/ChatComposer.vue:14-24 | 必要 | 两个互斥动作共用一个 44px 目标，已满足「同一时刻只允许一个最重」 |
| 两个 keydown 绑定（Enter / Ctrl+Enter） | apps/web/src/views/chat/components/ChatComposer.vue:11-12 | 可合并 | 同一处理函数、无 IME 守卫，见提案 2 |
| AI 免责声明 | apps/web/src/views/chat/components/ChatComposer.vue:26-28 | 必要 | 12px caption，信任成本最低的一行 |
| 移动端 padding 重复声明 | apps/web/src/views/chat/components/ChatComposer.vue:126-130 | 可删 | 与 apps/web/src/views/chat/UnifiedChatView.vue:361-365 完全重复（后者作用于同一根元素） |
| 用户头像 | apps/web/src/views/chat/components/ChatMessageItem.vue:5 | 可删 | 右对齐灰底气泡已表达角色（:178-180、:245-249） |
| 助手头像 | apps/web/src/views/chat/components/ChatMessageItem.vue:4 | 必要 | 流式回答的唯一角色锚点（:194-197） |
| 「RAG 助手」名称 | apps/web/src/views/chat/components/ChatMessageItem.vue:9-10 | 可删 | 每条回答重复同一名字，页面本身即该助手（样式 :219-223） |
| answer_mode 徽标 | apps/web/src/views/chat/components/ChatMessageItem.vue:11 | 可合并 | 可信度信号之一，与 :23-26、:45 重复 |
| Agent 徽标 | apps/web/src/views/chat/components/ChatMessageItem.vue:12 | 可删 | header 已有执行模式 chip（ChatHeader.vue:102-108），逐条重复 |
| safety_notice 安全提示 | apps/web/src/views/chat/components/ChatMessageItem.vue:15-21 | 必要 | 低频高价值，可纠正误信 |
| 回答依据框 | apps/web/src/views/chat/components/ChatMessageItem.vue:23-26 | 可合并 | 可信度信号之一，见提案 3 |
| typing 指示器 | apps/web/src/views/chat/components/ChatMessageItem.vue:29-32 | 可合并 | 与 apps/web/src/views/chat/UnifiedChatView.vue:47-59 重复实现，文案还不一致 |
| markdown 回答正文 | apps/web/src/views/chat/components/ChatMessageItem.vue:34 | 必要 | 任务产物本体 |
| 代码块复制按钮 | apps/web/src/views/chat/components/ChatMessageItem.vue:127, :141-145 | 必要 | 但复制后零反馈，见动效表「缺失的机会」 |
| 引用区 | apps/web/src/views/chat/components/ChatMessageItem.vue:37-39 | 必要 | 核对依据的主路径 |
| 遥测指标（检索 ms / 召回条 / 可信度 %） | apps/web/src/views/chat/components/ChatMessageItem.vue:43-45 | 可合并 | 前两条是面向实现的遥测；第三条应并入唯一的可信度信号，见提案 3 |
| 轨迹入口按钮 | apps/web/src/views/chat/components/ChatMessageItem.vue:46-48 | 必要 | 步骤 5 的唯一入口，且受 workflow_run 存在性约束 |
| 👍 反馈 | apps/web/src/views/chat/components/ChatMessageItem.vue:52-61 | 必要 | 单次点击即提交，反馈成本最低 |
| 👎 + 反馈面板 | apps/web/src/views/chat/components/ChatMessageItem.vue:62-91 | 必要 | 但打开面板即写入，见提案 1 |
| 反馈面板说明句 | apps/web/src/views/chat/components/ChatMessageItem.vue:77 | 可删 | h4「反馈问题」已表达同一意思 |
| 抽屉标题「执行轨迹 (Trace)」 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:2 | 必要 | 「(Trace)」为冗余英文重复，可并入删除 |
| 状态条（tag + run id） | apps/web/src/views/chat/components/ChatTraceDrawer.vue:4-9 | 必要 | 重试前判断任务成败的唯一依据 |
| 基本信息 KV（模式/阶段/耗时/路由/可恢复） | apps/web/src/views/chat/components/ChatTraceDrawer.vue:11-18 | 可合并 | 面向实现的字段（route_key、耗时）与面向用户的状态混在一组，需分层 |
| 事件时间线 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:20-41 | 必要 | 状态用颜色 + 文字各表达一次（:26 与 :32），文字版是色盲可达性所需，保留 |
| 失败与恢复区 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:43-64 | 必要 | 失败原因聚合（:129-146），仅失败时出现 |
| 工具调用摘要表 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:66-77 | 必要 | 可读版本，替代原始 JSON |
| 三块原始 JSON 折叠（LLM Trace / Tool Calls / State） | apps/web/src/views/chat/components/ChatTraceDrawer.vue:79-89 | 可删 | 面向实现者的原始 payload；Tool Calls 与上方表格同数据，见提案 4 |
| 重新执行按钮 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:91-95 | 必要 | 仅 status=failed 时出现 |
| 加载占位 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:97-99 | 必要 | 抽屉打开到数据返回之间的间隔 |
| 中断卡容器（渐变底 + 硬编码边框） | apps/web/src/views/chat/components/ChatInterruptCard.vue:91-96 | 可删 | linear-gradient + #dbe3f4 不含信息，与内部推荐选项的高亮（:145-148）争夺「最重元素」 |
| 中断 kind 标签 | apps/web/src/views/chat/components/ChatInterruptCard.vue:3-6 | 必要 | 说明「为什么被中断」（映射 :68-76） |
| 中断标题 | apps/web/src/views/chat/components/ChatInterruptCard.vue:5 | 必要 | 需要用户决策的那句话 |
| subject.summary | apps/web/src/views/chat/components/ChatInterruptCard.vue:7 | 可删 | 与 detail 同层同色（:115-126），密度重复 |
| 中断 detail | apps/web/src/views/chat/components/ChatInterruptCard.vue:8 | 必要 | 决策所需的上下文 |
| 选项列表（含推荐选项环） | apps/web/src/views/chat/components/ChatInterruptCard.vue:10-25, :145-148 | 必要 | 推荐项有独立视觉权重（:145-148），是卡片唯一的「最重元素」候选 |
| 选项 badges | apps/web/src/views/chat/components/ChatInterruptCard.vue:20-22 | 可删 | 与 label/description 同层堆叠，内容由后端给定，见存疑 |
| 自由文本输入 | apps/web/src/views/chat/components/ChatInterruptCard.vue:27-34 | 必要 | 选项覆盖不到时的唯一出口（allow_free_text 控制） |
| 「继续」按钮 | apps/web/src/views/chat/components/ChatInterruptCard.vue:36-46 | 必要 | 提交中断响应；空 payload 仍可点，见存疑 |
| 移动端 `.message-bubble` 全局 !important 覆盖 | apps/web/src/styles/responsive-enhancements.css:127-130 | 可删 | 强制 max-width:90% + padding:14px 16px，覆盖本组件助手气泡的 padding:4px 0（ChatMessageItem.vue:251-254），见提案 5 |

## 提案（按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/views/chat/components/ChatMessageItem.vue:157 | 少一次误操作 | 删除 `openFeedback()` 里的 `handleFeedback(message,'down')`：现在仅「打开👎面板」就会写入一次差评（store/chat.ts:446-460 无 feedbackData 即 newVerdict='down' 并调用 submitMessageFeedback），点「取消」（:87）不回滚；连续点两次还会因 store/chat.ts:449 的 toggle 语义把 state 清成 undefined 而服务端仍是 down，造成前后端不一致。风险：删除后「👎」不再有"先记后改"的路径，必须确认产品接受"打开面板又取消 = 不留痕"；store 的 toggle-off 分支要重新对齐到提交路径，否则会失去"撤销差评"能力 |
| 合并 | apps/web/src/views/chat/components/ChatComposer.vue:11-12, :44-49 | 少一次误操作 | 两个问题同一路径：(a) `handleAsk` 在 emit 后无条件清空输入（:47），而 store 可拒绝本次提问（apps/web/src/store/chat.ts:331-337：scopeMode≠all 且未选库时仅 warning 并 return）→ 用户输入被吞；(b) `.exact` 只校验修饰键、不校验 `isComposing`，全仓无任何 composition 守卫（grep `isComposing|compositionstart` 零命中），中文输入法回车确认候选词即发送半成品。风险：需要 store/父组件回传"是否受理"（ask 现返回 void），改动跨 2 个文件且属行为变更；IME 行为需真机中文输入法回归；Ctrl+Enter 合并后要同步改 placeholder（:8） |
| 合并 | apps/web/src/views/chat/components/ChatMessageItem.vue:11, :23-26, :43-45 | 少一次判断 | 一条回答里同时给出 answer_mode 徽标、回答依据框、可信度百分比、检索耗时、召回条数五个"可信度"信号，用户要在它们之间比对哪个才算准。风险：三者语义不同（后端枚举 / 自然语言标签 / 数值），合并必须由产品指定唯一权威信号，否则会变成"更少但更不准"的信息；需要后端确认三者是否同源 |
| 删除 | apps/web/src/views/chat/components/ChatTraceDrawer.vue:79-89 | 少一次判断 | 三块 `JSON.stringify(...,null,2)` 原始 payload 面向实现者，且 Tool Calls JSON 与上方工具调用表（:66-77）同数据；删除后抽屉的阅读顺序变成 状态→时间线→失败→重试。风险：开发者失去 UI 内看原始 payload 的入口，需改用 network 面板或 `getWorkflowRun`（apps/web/src/api/chat.ts:126）；若支持排障依赖它，应改为 debug 开关下的折叠，而不是直接删 |
| 删除 | apps/web/src/styles/responsive-enhancements.css:127-130 | 少一次判断 | 该全局 `!important` 覆盖只在 ≤768px 生效，却强改助手气泡的 padding，使"纯文本回答"与"用户灰底气泡"在移动端看起来像同类卡片，角色区分需要靠重读判断。影响面已核实：`.message-bubble` 全仓只被 ChatMessageItem.vue:28 与 UnifiedChatView.vue:52 使用，均在本界面内。风险：这条规则可能被其它页面的同名类复用（当前 grep 无），删除前需做一次 375px 宽度的视觉回归 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 性能 | apps/web/src/views/chat/components/ChatSidebar.vue:107 | `.session-sidebar` 声明 `transition: width 0.3s ease`，但桌面宽度固定 280px（:100-108）、移动端切换走 transform（:248-261），全仓无任何规则改变该元素宽度 → 完全死掉的过渡；且 width 属于禁止动画属性，将来做折叠会直接引发布局抖动 | 删除该声明；移动端开合已由 :253 的 transform 承担 |
| MEDIUM | 一致性与 token | apps/web/src/views/chat/components/ChatSidebar.vue:130, :190, :253；apps/web/src/views/chat/components/ChatHeader.vue:214；apps/web/src/views/chat/components/ChatComposer.vue:102 | 本界面 5 处过渡全部硬编码 `0.2s ease`，完全未使用 --transition-fast/base/smooth（apps/web/src/style.css:46-48）；`ease` 不在允许曲线内 | 颜色类 hover 统一 `var(--transition-fast)`（150ms），面板/抽屉用 `var(--transition-base)`；进入曲线 `cubic-bezier(0.23,1,0.32,1)` |
| MEDIUM | 一致性与 token | apps/web/src/views/chat/components/ChatMessageItem.vue:273-300 | typing 指示器与 apps/web/src/views/chat/UnifiedChatView.vue:401-422 是两套同源实现（markup + @keyframes 各一份），且文案不一致：消息内会在「正在检索...」「正在思考中...」之间切换（:31 依 isRetrieving，apps/web/src/store/chat.ts:373 初值为 true），兜底版则固定「正在检索...」 | 只保留消息内一处，或抽成一个极小组件；文案统一为一个动词 |
| MEDIUM | 物理性与原点 | apps/web/src/views/chat/components/ChatSidebar.vue:253 | 移动抽屉用 `transform: translateX(-100%) → 0` + `0.2s ease`：方向正确，但曲线是 CSS 预设、时长未走令牌，进/出同一曲线 | 进入用 `cubic-bezier(0.23,1,0.32,1)` + `var(--transition-base)`；退出可更短；保持只动 transform |
| MEDIUM | 缺失的机会 | apps/web/src/views/chat/components/ChatMessageItem.vue:127, :141-145 | 代码块「复制」点击后零状态变化（不换文案、无 toast、无勾选），用户无法确认是否复制成功，只能重试或手动粘贴验证 | 加 1.2-1.5s 的「已复制」状态（只改 color/opacity，不改尺寸）；等价删除见提案 3 的遥测指标 |
| LOW | 无障碍 | apps/web/src/views/chat/components/ChatMessageItem.vue:438-441 | `:hover` 提亮未包在 `@media (hover:hover) and (pointer:fine)` 内；触屏点击后 sticky hover 会停在每条回答最高频的反馈按钮上（全局通配归零之外的组件特例，同类还有 ChatSidebar.vue:193-195） | 把 hover 规则包进 hover 媒体查询 |
| LOW | 目的与频次 | apps/web/src/views/chat/components/ChatMessageItem.vue:287-296 | 三点循环 1.4s、关键帧含 `scale(0)`；作为循环加载可接受，但它每次回答都出现且与 :31 的文案重复表达同一状态 | 保留文案 + 三点其一；若去掉三点，用 opacity 呼吸即可（仍只动 transform/opacity） |
| LOW | 缺失的机会 | apps/web/src/views/chat/components/ChatComposer.vue:88-108 | 发送按钮只有灰→蓝的背景色过渡，无按压反馈（无 :active）——属于允许的「操作反馈」，且 100+ 次/天的元素只做颜色过渡是浪费 | 加 100-160ms 的 :active transform；等价删除 :110-112 的 hover 变深 |

## 存疑

- **范围 chip 与实际检索范围可能不一致**：chat chip 文案只由 `scopeMode` 推出（apps/web/src/views/chat/components/ChatHeader.vue:31），而请求体 `buildScope()` 同时携带 `corpus_ids`（apps/web/src/store/chat.ts:62-66），且 `handleScopeModeChange` 切到 all 时并不清空 `selectedCorpusIds`（:299-310）。若后端在 mode=all 时仍尊重 corpus_ids，就会出现「chip 写全库、实际只搜已选库」。验证方法：选 2 个知识库 → 切「全库」→ 观察 chip 文案与 POST 请求体/检索结果是否一致。
- **中断卡可提交空 payload**：`selectedOptionId` 仅默认取 recommended（ChatInterruptCard.vue:60），无推荐项且无选项时 `handleSubmit` 会发 `{}`（:78-87），「继续」按钮此时仍可点（:37-45）。需确认后端是否会返回这种中断（`fallback_prompt` 的存在暗示可能）。验证方法：构造 scope_ambiguity 中断，清空选择后点「继续」看响应。
- **`el-radio :label` 作为 value 已废弃**：apps/web/src/views/chat/components/ChatInterruptCard.vue:17 是全仓唯一一处；Element Plus 已挂 `useDeprecated`（node_modules/element-plus/es/components/radio/src/use-radio.mjs:37-46，`from: "label act as value"` → `replacement: "value"`，version 3.0.0）。当前安装版本 2.13.3 仍可用（仅告警），升级 EP 3 前必须改 `value`。
- **重试可能产生重复执行**：apps/web/src/views/chat/components/ChatTraceDrawer.vue:164-179 调用 `retryWorkflowRun(id)` 未传 `idempotencyKey`，而 API 显式支持该参数（apps/web/src/api/chat.ts:130）。`:loading="retrying"` 只挡住同 tick 的连点，挡不住"超时后用户再点"。需确认后端重试接口是否幂等。验证方法：mock 一个超时（如断网后重连）再点第二次「重新执行」，看是否生成两条 run。
- **`.meta-badge` 小字对比度临界**：11px 用 `var(--text-muted)`（= #64748b，apps/web/src/style.css:29）铺在 `#f1f5f9`（:24）上，按 WCAG 相对亮度公式手算约 4.35:1，低于小字 4.5:1 的门槛。我未用工具核验，且若采纳提案 3（合并徽标）该问题自然消失，因此不作为独立结论。验证方法：浏览器对比度检查器或 axe。
- **移动端无遮罩**：≤768px 时侧栏是 `position:absolute` + `translateX(-100%)`（ChatSidebar.vue:248-261），打开后点击侧栏以外区域不会关闭，只能点右上 44px 关闭按钮（:8-10）。是否可接受需真机判断（我的手边没有渲染环境）。
- **全局抽屉宽度覆盖**（已排除误报，供决策）：apps/web/src/styles/responsive-enhancements.css:194-196 在 ≤768px 用 `!important` 把 `.el-drawer` 宽度压到 85%，因此 ChatTraceDrawer.vue:2 的 `size="450px"` 在移动端并不造成溢出。需确认 85% 宽度是否够读；若采纳提案 4 删除 JSON 块，该顾虑也随之消失。
- **`.chat-workspace` 的网格规则是无效声明**：apps/web/src/styles/responsive-enhancements.css:110-112、:201-203、:225-227 为 `.chat-workspace` 设置 `grid-template-columns`，但该元素是 flex 容器（apps/web/src/views/chat/UnifiedChatView.vue:253-261），三处均不生效。需人工确认是删除还是本意要改成网格布局。
- **父级文件的失效令牌**（不在本次 6 个文件内，供参考）：apps/web/src/views/chat/UnifiedChatView.vue:336 使用 `var(--blue-400)`，而 style.css:17-20 只定义了 blue-50/500/600/700，该 hover 边框色失效，只剩阴影与位移。
