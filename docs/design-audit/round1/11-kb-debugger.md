# 11 检索测试（检索调试器）

审计范围：`apps/web/src/views/kb/RetrievalDebuggerView.vue`（415 行，模板 1-128 / 逻辑 130-232 / 样式 234-415）
路由：`/workspace/kb/debugger`（`apps/web/src/router/index.ts:141-149`，`requiresPermission: 'kb.manage'`）
依赖组件（仅在与本界面相关处取证）：`apps/web/src/components/PageHeaderCompact.vue`、`apps/web/src/components/EnhancedEmpty.vue`、`apps/web/src/api/kb.ts`
后端取证（仅为确认字段语义，未修改）：`apps/services/knowledge-base/src/app/kb_query_routes.py`、`apps/services/knowledge-base/src/app/retrieve.py`、`apps/services/knowledge-base/src/app/vector_store.py`、`packages/python/shared/retrieval.py`

## 唯一用户任务

知识库管理员 / 检索质量负责人在「有用户反馈某个问题答不出来或答错、需要定位是召回、融合还是重排哪一环出问题」的场景下，要一次性地看到各通道候选数与每条证据的分数、排名，从而判断下一步该改什么。

（权限与入口依据：路由要求 `kb.manage`（`apps/web/src/router/index.ts:141-149`），导航项同样受 `kb.manage` 门控（`apps/web/src/layouts/MainLayout.vue:261-263`、`apps/web/src/layouts/MainLayout.vue:279-286`）；页面副标题自述边界「不触发 LLM 生成，专注诊断召回、融合与重排结果」（`apps/web/src/views/kb/RetrievalDebuggerView.vue:3`）；后端调试接口独立于 `/kb/query` 且不带 LLM（`apps/services/knowledge-base/src/app/kb_query_routes.py:141-178`）。）

## 完成该任务的必要步骤

1. 打开页面 → `onMounted` 拉知识库列表并静默默认选中第一个库（`apps/web/src/views/kb/RetrievalDebuggerView.vue:188-194`、`apps/web/src/views/kb/RetrievalDebuggerView.vue:229-231`）→ **keep**
2. 确认或切换知识库（`apps/web/src/views/kb/RetrievalDebuggerView.vue:8-12`）→ **keep**
3. 输入测试问题（`apps/web/src/views/kb/RetrievalDebuggerView.vue:13-21`）→ **keep**
4. 按需填写「文档 ID 范围」（`apps/web/src/views/kb/RetrievalDebuggerView.vue:22-29`）→ **demote**
5. 按需修改「召回数量 Limit」（`apps/web/src/views/kb/RetrievalDebuggerView.vue:30-32`）→ **demote**
6. 点击「开始检索测试」（`apps/web/src/views/kb/RetrievalDebuggerView.vue:33-44`）→ **keep**
7. 读 5 个阶段候选数，判断断在哪一环（`apps/web/src/views/kb/RetrievalDebuggerView.vue:74-81`）→ **keep**
8. 读「聚焦查询 / 重写查询 / 重排方式」（`apps/web/src/views/kb/RetrievalDebuggerView.vue:84-89`）→ **keep**
9. 逐条读分数、信号分与证据路径（`apps/web/src/views/kb/RetrievalDebuggerView.vue:91-121`）→ **keep**
10. 改问题后重跑做对照（`apps/web/src/views/kb/RetrievalDebuggerView.vue:206-227`）→ **keep**（失败会被渲染成「未命中」，见提案 1）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页面标题 + 副标题 | apps/web/src/views/kb/RetrievalDebuggerView.vue:3 | 必要 | 副标题声明「不触发 LLM 生成」的边界；本页与 `/workspace/chat` 在导航中并列（MainLayout.vue:261-263），无此行则易被当成问答入口 |
| 知识库选择 el-select | apps/web/src/views/kb/RetrievalDebuggerView.vue:8-12 | 必要 | `base_id` 是请求必填（api/kb.ts:756）与运行门控（RetrievalDebuggerView.vue:37） |
| 测试问题 textarea | apps/web/src/views/kb/RetrievalDebuggerView.vue:13-21 | 必要 | `question` 同上；本页唯一输入诊断变量的地方 |
| 文档 ID 范围 textarea | apps/web/src/views/kb/RetrievalDebuggerView.vue:22-29 | 可下沉 | `document_ids?` 为可选（api/kb.ts:758）且需手输 UUID；结果卡片里的 `Doc:` 是纯文本（RetrievalDebuggerView.vue:117），无法回填，形成不了闭环 |
| 召回数量 Limit | apps/web/src/views/kb/RetrievalDebuggerView.vue:30-32 | 可下沉 | 非诊断变量，有默认值 10（RetrievalDebuggerView.vue:178）；注意它覆盖了后端默认 8（retrieve.py:279） |
| 「开始检索测试」按钮 | apps/web/src/views/kb/RetrievalDebuggerView.vue:33-44 | 必要 | 唯一触发 `retrieveDebugKB` 的入口（RetrievalDebuggerView.vue:206-227） |
| 按钮 disabled 规则 | apps/web/src/views/kb/RetrievalDebuggerView.vue:37 | 必要 | 防住空查询（`runDebug` 会静默早退，RetrievalDebuggerView.vue:207）；代价是「为什么点不动」不可解释 |
| 检索中 loading 块 | apps/web/src/views/kb/RetrievalDebuggerView.vue:49-52 | 可合并 | 与按钮的 `:loading`（RetrievalDebuggerView.vue:36）表达同一状态；且它整块替换结果区，见动效发现 |
| 空态「等待测试」 | apps/web/src/views/kb/RetrievalDebuggerView.vue:54-59 | 必要 | 首屏可辨识，文案与左侧表单动作对齐 |
| 空态「未命中任何切片」 | apps/web/src/views/kb/RetrievalDebuggerView.vue:61-66 | 必要 | 零命中的唯一解释面；但它同时被复用为「请求失败」的表现，见提案 1 |
| 结果标题「召回结果 (N)」 | apps/web/src/views/kb/RetrievalDebuggerView.vue:71 | 必要 | 唯一的条数确认；N 与实际渲染条数同源（`results.length`） |
| Trace ID 行 | apps/web/src/views/kb/RetrievalDebuggerView.vue:72 | 必要 | `trace_id` 是跨服务排查的关联键（kb_query_routes.py:177） |
| 阶段计数行（结构/全文/向量/融合/重排/ms） | apps/web/src/views/kb/RetrievalDebuggerView.vue:74-81 | 必要 | 本页核心诊断面；来源为后端 stats（retrieve.py:557-574）。两点噪声：`selected_candidates` 未渲染；耗时用 `toFixed(4)`（RetrievalDebuggerView.vue:203）把毫秒显示到 4 位小数 |
| 「原始问题」行 | apps/web/src/views/kb/RetrievalDebuggerView.vue:85 | 可删 | 与左侧输入框同源：重写模块把输入问题（仅做换行合并与空白归一）原样带回（query_rewrite.py:33、query_rewrite.py:64），前端再显示一遍（retrieve.py:558） |
| 「聚焦查询 / 重写查询 / 重排方式」行 | apps/web/src/views/kb/RetrievalDebuggerView.vue:86-88 | 必要 | 重写与聚焦查询只在此处可见（retrieval.py:65-67、retrieval.py:80） |
| 结果卡片容器 | apps/web/src/views/kb/RetrievalDebuggerView.vue:91-122 | 必要 | 单条证据的唯一承载 |
| 排名 #N | apps/web/src/views/kb/RetrievalDebuggerView.vue:94 | 必要 | 三级回退 `debug.rank → evidence_path.final_rank → index+1`；后端从 1 起编号（kb_query_routes.py:161） |
| 文档标题 / 章节名 | apps/web/src/views/kb/RetrievalDebuggerView.vue:96-97 | 必要 | 定位证据来源；缺失时有「未知文档/未命名章节」兜底 |
| Score / Rerank 两枚 el-tag | apps/web/src/views/kb/RetrievalDebuggerView.vue:99-102 | 可合并 | 与 signal-chip 行重复：后端把 `debug.score` 直接取自 `evidence_path.final_score`（kb_query_routes.py:165）、`debug.rerank_score` 直接取自 `signal_scores.rerank`（kb_query_routes.py:167），所以 Rerank 值必然同时出现在标签与 chip 上 |
| 正文 quote / raw_text | apps/web/src/views/kb/RetrievalDebuggerView.vue:105-107 | 必要 | 判断「召回了但不对」的唯一依据 |
| signal-chip 行 | apps/web/src/views/kb/RetrievalDebuggerView.vue:109-113 | 必要 | 各通道原始分；键名由后端动态给出（retrieval.py:53），前端原样输出 |
| 结果 footer（Unit / Doc / FTS# / Vector# / Structure hit） | apps/web/src/views/kb/RetrievalDebuggerView.vue:115-121 | 必要 | 证据路径的唯一直读面（retrieval.py:54、retrieve.py:485-492） |
| `selected_candidates` 字段声明 | apps/web/src/views/kb/RetrievalDebuggerView.vue:146 | 可删 | 后端已计算并返回（retrieve.py:570），前端声明后在模板里从不使用（全文仅此一处出现） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/views/kb/RetrievalDebuggerView.vue:209、220-224 | 少一次误操作 | 请求失败时 catch 会清空 `results/retrievalStats/traceId`，而 `hasRun` 已在发请求前置真（RetrievalDebuggerView.vue:209），于是失败被渲染成「未命中任何切片 / 尝试调整查询词或检查知识库内容」（RetrievalDebuggerView.vue:61-66）——用户会据此得出「库里没这块内容」的结论并去改查询词。改法无需新增元素：删掉 catch 里的三行清空，并把 `hasRun` 置真移到成功分支。代价：重跑失败时面板保留上一次的结果，存在被误读成本次结果的风险（toast 是瞬时的，request.ts:128）；若判定该风险不可接受，就得新增一个「本次运行失败」标记，那违反默认删除 |
| 下沉 | apps/web/src/views/kb/RetrievalDebuggerView.vue:22-32 | 少一次判断 | 两个可选参数常驻在必填路径上，默认路径上用户要对 4 个字段做判断而不是 2 个。折叠后，需要按文档缩小范围的少数用户多一次展开，且折叠期间用户可能不知道有这个能力，把「召回噪声」误判为库内容问题。风险：`limit` 默认 10（RetrievalDebuggerView.vue:178）与后端默认 8（retrieve.py:279）不一致，折叠前应先对齐口径，否则「默认值」含义不明 |
| 合并 | apps/web/src/views/kb/RetrievalDebuggerView.vue:74-81、86-88、99-102、109-113 | 少一次判断 | 同一个概念有三套写法：阶段计数用中文（结构/全文/向量/融合/重排，RetrievalDebuggerView.vue:75-79），重排方式又是一个中文短语（RetrievalDebuggerView.vue:88），卡片里是英文 `Score:`/`Rerank:`（RetrievalDebuggerView.vue:100-101）加后端信号键名（structure/fts/vector/rerank，RetrievalDebuggerView.vue:110-111）。用户要自己推断「融合 3」和「structure 1.2000」是不是同一套通道。代价：改文案会打破现有断言（RetrievalDebuggerView.test.ts:136-141 断言 `structure 1.2000`、`fts 0.8000`、`FTS #1` 等），必须同步改测试；且信号键由后端动态给出（retrieval.py:53），做中文映射时对未知键必须保留原样，否则新信号会显示成空白 |
| 加反馈 | apps/web/src/views/kb/RetrievalDebuggerView.vue:74-81（配合接口声明 137-149） | 少一次误操作 | 向量通道失败时后端返回空列表并把 `["vector"]` 写进 `degraded_signals`（vector_store.py:213-217），一路带到 stats（retrieve.py:413-420、retrieve.py:563），本页把它渲染成「向量 0」，与「确实没有向量命中」完全同形；用户会据此去改分块，实际是通道故障。改法不新增元素：`degraded_signals` 非空时，把那一枚 chip 从「向量 0」改成「向量 降级」——同一位置、同一枚 chip，只换语义。代价：前端接口需补 `degraded_signals`（RetrievalDebuggerView.vue:137-149 目前没有该字段），要确认「降级」对非工程用户可读；该字段只在 Qdrant 抛异常时产生，正常数据无法回放，必须人为停 Qdrant 或断网才能验证 |
| 降层级 | apps/web/src/views/kb/RetrievalDebuggerView.vue:99-102 | 少一次判断 | 两枚标签用两种语义色表达同一类数据：`Score` 是 `type="info"`（灰）、`Rerank` 是 `type="success"`（绿），而绿色在 Element Plus 里表示「成功」，用户会把它读成质量判定（「这条好」），它其实只是重排分数。同时这两枚标签的信息已分别在 chip 行出现（RetrievalDebuggerView.vue:109-113）。降层级 = 去掉语义色与标签外观，改为与 chip 同级的等宽文本，并让 rerank 只保留一处。代价：卡片头部失去彩色锚点后，10 条结果的分数更难扫读，需要改由字重和列对齐来承担；另需确认删掉 `Score` 标签后该值仍可见——`signal_scores` 里没有 final 总分这个键（retrieval.py:53），只有在 `debug` 缺失时才回退到 `evidence_path.final_score` |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 | apps/web/src/components/EnhancedEmpty.vue:108-113 | 装饰插图挂 `:hover` 做 `scale(1.05) rotate(2deg)`，300ms，`cubic-bezier(0.34, 1.56, 0.64, 1)`（带过冲），而 `.default-illustration` 内无任何交互监听（EnhancedEmpty.vue:99-109）——纯装饰元素给出了可点的错觉；本页经 `:54`、`:61` 两处渲染该组件，「等待测试」恰是首屏状态 | 删除该 hover 变换与其 transition；若确要保留，须包进 `@media (hover: hover) and (pointer: fine)` 并去掉过冲曲线 |
| MEDIUM | 性能 / 目的与频次 | apps/web/src/views/kb/RetrievalDebuggerView.vue:49-52、68 | 提交即把整个结果区换成居中 spinner：无延迟阈值、无过渡，旧结果瞬间跳空。检索是几十次/天的高频循环，快请求会闪一下，重跑时用户失去上一轮对照 | 去掉整块 loading-state（结果区内不再放 spinner），只保留按钮 `:loading`（RetrievalDebuggerView.vue:36）与结果区的轻量置灰；若要保留整块替换，至少加 300ms 延迟显示阈值 |
| MEDIUM | 缓动与时长 | apps/web/src/views/kb/RetrievalDebuggerView.vue:50 | `el-icon.is-loading` 继承 Element Plus 的 `rotating 2s linear infinite`（node_modules/element-plus/theme-chalk/el-icon.css）——检索这种亚秒到数秒的过程，2 秒转一圈偏慢，看不出「还在动」 | 本页覆盖为 ~0.9s linear（保持线性、不引入缓动曲线），或改用 Element Plus 的 `v-loading` 指令统一 |
| LOW | 一致性与 token | apps/web/src/views/kb/RetrievalDebuggerView.vue:296、306、327、362、380、393、406、412 | 8 处硬编码 px 字号（12/12/13/16/12/14/12/12），全部绕过已定义的 `--text-caption/--text-body/--text-h2`（style.css:32-35） | 换成 token；同时 `.results-header h3`（RetrievalDebuggerView.vue:290-292）只设了 margin，字号落到浏览器 UA 默认 1.17em（≈18.7px），比页头 `--text-h2`（1.125rem，PageHeaderCompact.vue:42）还大——层级倒挂，应显式指定 `--text-h2` 或 `--text-body` |
| LOW | 无障碍 | apps/web/src/views/kb/RetrievalDebuggerView.vue:50 | 全局 reduced-motion 规则把动画压成 0.01ms/1 次（style.css:806-815），本页唯一的「进行中」视觉指示因此变成一张静止图标，只剩「检索中...」文案（RetrievalDebuggerView.vue:51） | 该全局问题已在已知清单；本页特例只需保证文案本身足够（现状可以），或在降低动效时改为 opacity 呼吸 |
| LOW | 缺失的机会 | apps/web/src/views/kb/RetrievalDebuggerView.vue:68 | 结果刷新没有任何「已更新」反馈（`v-else` 直接切换），用户要重新读一遍才能确认是新结果 | 不建议在此处补位移/缩放动效（几十次/天，按频次规则应砍）；若确实存在「结果是否属于本次查询」的困惑（看存疑），用文本回显本次 query / 时间更省，不动画 |

## 存疑

- 失败时 toast 与「未命中」文案同时出现的实际观感需要真机验证：请求层会对非 `skipErrorHandler` 的失败弹 `ElMessage.error`（`apps/web/src/api/request.ts:128`、`apps/web/src/api/request.ts:151-160`），而本页没有传 `skipErrorHandler`（`apps/web/src/api/kb.ts:762-764`、`RetrievalDebuggerView.vue:211`）。构造一次 500/超时即可确认「弹出错误 + 显示未命中」是否同时发生。
- 「文档 ID 范围」的真实使用率未知（本仓库前端无埋点，我也不掌握线上调用分布），因此把它定为「可下沉」而非「可删」。验证方法：统计 `/kb/retrieve/debug` 请求中 `document_ids` 非空的比例（该参数在 `apps/services/knowledge-base/src/app/kb_query_routes.py:155` 直接透传，可在那里加统计）。
- 小屏适配未验证：本文件 234-415 行没有任何 `@media`，`apps/web/src/styles/responsive-enhancements.css` 全文也没有 `.debugger-*` 规则；布局是 320px 固定侧栏 + `gap: 20px`（`RetrievalDebuggerView.vue:242-256`）。而 `MainLayout` 存在移动端抽屉（`apps/web/src/layouts/MainLayout.vue:316-321`），说明窄屏是受支持场景。需要在 375 / 768 / 1024 三档宽度实际渲染确认是否不可用。
- 字号 token 事实上未落地：本页 8 处硬编码 px，全仓 `apps/web/src/views` 下同一模式的 grep 命中 210 处、涉及 30+ 文件。这不是本界面能单独修的问题，需要 owner 决定「补 token」还是「废 token」，本报告只记录事实。
- 两个分数的量纲是否可直接比较未确认：`final_score` 在样例里是 0.91 一类的 0-1 值，rerank 分数在样例里是 9.5（`RetrievalDebuggerView.test.ts:94-96`）甚至 0（`RetrievalDebuggerView.test.ts:107`）。需要后端确认 rerank 分数的取值范围与 0 的含义（是「未重排」还是「最低分」），否则合并标签（提案 5）可能丢掉一个重要区分。
- `#{{ item.debug?.rank || ... }}`（`RetrievalDebuggerView.vue:94`）用 `||` 而非 `??`，rank 为 0 时会回退；后端从 1 起编号（`kb_query_routes.py:161`），本次未构造出 rank=0 的实际数据来验证该分支。
- 本页无任何键盘处理（全文无 `@keydown/@keyup`），调试循环里每次重跑都要把鼠标移到按钮。是否值得加 Ctrl/Cmd+Enter 属产品决策（本次不作为提案，仅登记：它是纯新增交互，找不到被删除的等价物）。
