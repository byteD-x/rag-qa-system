# 08 知识治理工作台

审计范围：`apps/web/src/views/kb/KBGovernanceView.vue`（936 行）、`apps/web/src/views/kb/kbVersionSummary.ts`
路由：`/workspace/kb/governance`（`apps/web/src/router/index.ts:108-110`）
入口权限：侧栏项需 `kb.manage`（`apps/web/src/layouts/MainLayout.vue:279-286`）；写操作另需 `kb.write`（`KBGovernanceView.vue:549`）
依赖取证：`components/PageHeaderCompact.vue`、`api/kb.ts`、`apps/services/knowledge-base/src/app/kb_analytics_routes.py`、`styles/theme-extras.css`、`styles/responsive-enhancements.css`、`KBGovernanceView.test.ts`

> **阻塞级缺陷（不属设计提案，但优先于全部提案）**：`apps/web/src/views/kb/KBGovernanceView.vue:297,299,302,304,306,308` 存在 6 处 GBK 错码乱码，直接渲染给用户。字节级核对：文件为 UTF-8 无 BOM（首字节 60,116,101 = `<te`），乱码是「UTF-8 字节被按 GBK 解读」的产物，逆映射后应为 `区域`(:297) / `页码`(:299) / `置信度`(:302) / `坐标`(:304) / `无摘要`(:306) / `定位`(:308)；其中 :302、:306 末尾的 `?` 是落单字节（`置信度`/`无摘要` 各 9 字节，GBK 按 2 字节配对后余 1 字节被替换），即这两处原文已被有损截断。该缺陷仅存在于本文件（全前端范围内用 `鍖哄煙|缃俊|椤电爜|瀹氫綅|鏃犳憳瑕|鍧愭爣` 与 `鍒分|鐢ㄦ埛|鏌ヨ` 两组模式检索，仅本文件命中），因此**不构成跨界面系统性问题**，但它是本界面「查看全部低置信区域」展开后用户唯一能看到的证据文案，整块功能因此不可读。

## 唯一用户任务

知识库审核人/管理员 在「知识文档提交审核后在多队列里积压」的场景下，要**逐条或批量给出审核裁定（通过/驳回）并补齐版本元数据**。

（推论依据：本页同时做两类事——审核裁定与「粘贴 JSON → dry-run → 批量写入/rebuild」的知识灌入。后者见「元素清单」`可下沉` 组与提案 1，它服务的是另一个用户与另一个目标。范围切换由 `authStore.isAdmin()` 门控（`KBGovernanceView.vue:5`），个人/全局决定数据口径（`kb_analytics_routes.py:1215`），说明使用者是**跨库的管理角色**，而不是文档作者。）

## 完成该任务的必要步骤

1. 判断哪个队列最该先处理 —— 读各区段计数（`KBGovernanceView.vue:251`）→ **keep**（当前由页顶汇总卡与区段 tag 双重承担，见提案 3）
2. 把范围切到「待我处理」（`KBGovernanceView.vue:25-29`）→ **keep**
3. 在队列里定位到目标文档 —— 受每区段 8 条上限约束（`KBGovernanceView.vue:543,685`）→ **keep**（但当前无法越过第 8 条，见提案 2）
4. 打开文档 / 低置信区域确认证据（`KBGovernanceView.vue:287-311,313-316`）→ **keep**（文案乱码，见上方阻塞级缺陷）
5. 打开「治理修正」抽屉，填审核结论与备注（`KBGovernanceView.vue:341-357`）→ **keep**
6. 保存——「通过 / 驳回 / 保存修正」三选一（`KBGovernanceView.vue:359-365`）→ **keep**
7. 对多条执行同一裁定：选中 → 批量通过 / 批量驳回（`KBGovernanceView.vue:162-163`）→ **merge**（与第 5、6 步同一目标的两条路径；当前与 rebuild 挤在同一按钮行，见提案 4）
8. 裁定后看失败项并重试（`KBGovernanceView.vue:200-219,221-237`）→ **keep**
9. 粘贴 JSON → dry-run → 批量写入 → rebuild（`KBGovernanceView.vue:37-151`）→ **drop**（与本任务无关，属知识灌入/运维路径）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页面标题「知识治理工作台」 | apps/web/src/views/kb/KBGovernanceView.vue:3 | 必要 | `PageHeaderCompact` 的 title 槽；本页唯一标题 |
| 范围切换（个人范围/全局范围） | apps/web/src/views/kb/KBGovernanceView.vue:5-8 | 必要 | 决定 `view` 查询参数与后端统计口径（kb_analytics_routes.py:1215）；仅 admin 可见 |
| 头部「刷新」 | apps/web/src/views/kb/KBGovernanceView.vue:9 | 可删 | 与面板级刷新（:224）职责重叠；其 `:loading` 与整页骨架（:239-241）重复表示同一状态 |
| 头部「知识库管理」 | apps/web/src/views/kb/KBGovernanceView.vue:10 | 可删 | 与侧栏同目标重复：MainLayout.vue:241-244 侧栏项同指 `/workspace/kb/upload`，但标签为「知识库治理」，两处名称不一致 |
| 汇总卡 ×5（label+value+hint） | apps/web/src/views/kb/KBGovernanceView.vue:14-20 | 可删 | 5 个数字在页面他处各出现一次：4 个在区段 tag（:251），`version_conflicts` 在自己的面板 tag（:327）；`tone` 字段（:597-601）模板从未使用；hint 句（:597-601）与区段 description（:607-612）同义 |
| 汇总数字字号 28px | apps/web/src/views/kb/KBGovernanceView.vue:919 | 可删 | 不在 token 刻度（22/18/15/12）内，且大于页面标题的 `--text-h2`（PageHeaderCompact.vue:42，18px），视觉重心倒挂 |
| 「工作集」标签文字 | apps/web/src/views/kb/KBGovernanceView.vue:24 | 可删 | 选项文案（全部/待我处理/我已处理）已自解释；且该筛选只作用于队列区（:615），标签却承诺了全页范围 |
| 工作集筛选（3 选项） | apps/web/src/views/kb/KBGovernanceView.vue:25-29 | 必要 | 唯一的「只看我的」分诊开关（:624 `filterItems`） |
| 「生成时间」 | apps/web/src/views/kb/KBGovernanceView.vue:32 | 可下沉 | 数据新鲜度信息，可并入副标题或工具提示（PageHeaderCompact.vue:5-7 有空闲的 subtitle 槽） |
| 降级提示文案 | apps/web/src/views/kb/KBGovernanceView.vue:33 | 可删 | 依赖 `hasDegradedSections`（:583）读 `data_quality.degraded_sections`，而该字段在后端恒为 `[]`（kb_analytics_routes.py:429-432）→ 永不可达 |
| 「批量知识库 JSON」面板（标题+清空+预览+批量写入+重建写入结果） | apps/web/src/views/kb/KBGovernanceView.vue:37-79 | 可下沉 | 知识灌入能力，与审核裁定无关；落点已存在（MainLayout.vue:255-259 → KBOperationsView.vue） |
| JSON textarea（6 行） | apps/web/src/views/kb/KBGovernanceView.vue:80-86 | 可下沉 | 同上；要求用户手写 `documents[]` 结构（占位符即示例，:85） |
| JSON 三态提示 | apps/web/src/views/kb/KBGovernanceView.vue:87-91 | 可删 | 只判 payload 是否为 null（:551-560），因此 JSON 语法错误与「未提供」落到同一句「请提供 documents JSON。」 |
| 「批量预览结果」面板 | apps/web/src/views/kb/KBGovernanceView.vue:94-112 | 可下沉 | dry-run 结果，服务灌入路径 |
| 「批量写入结果」面板 | apps/web/src/views/kb/KBGovernanceView.vue:114-132 | 可下沉 | 同上 |
| 「批量重建结果」面板 | apps/web/src/views/kb/KBGovernanceView.vue:134-151 | 可下沉 | 同上 |
| `字符 / section / chunk / ready` 等管线术语 | apps/web/src/views/kb/KBGovernanceView.vue:101,102,109,127,147 | 可下沉 | 把管线内部计数当作面向用户的标签；审核决策不依赖这些字段 |
| 「已选 N 项」+ 清空选择 | apps/web/src/views/kb/KBGovernanceView.vue:155-156 | 必要 | 批量动作的唯一可见选区状态 |
| 统一备注 textarea | apps/web/src/views/kb/KBGovernanceView.vue:158 | 必要 | 批量驳回的硬门控（:808 无备注则拦下） |
| 「批量指派给我」 | apps/web/src/views/kb/KBGovernanceView.vue:160 | 必要 | 认领动作，行内无等价物 |
| 「批量提交审核」 | apps/web/src/views/kb/KBGovernanceView.vue:161 | 可删 | 待审核队列的谓词本身即 `review_status = 'review_pending'` 或草稿（kb_analytics_routes.py:214-227），对已入队项再提交多为空操作；语义需人确认（见存疑） |
| 「批量通过」 | apps/web/src/views/kb/KBGovernanceView.vue:162 | 必要 | 主裁定动作 |
| 「批量驳回」 | apps/web/src/views/kb/KBGovernanceView.vue:163 | 必要 | 主裁定动作（含备注门控） |
| 「预览 rebuild」 | apps/web/src/views/kb/KBGovernanceView.vue:164-172 | 可下沉 | 单文档重建前的 dry-run，属运维路径 |
| 「执行 rebuild」 | apps/web/src/views/kb/KBGovernanceView.vue:173-182 | 可下沉 | 同上；与批量审核按钮混排（见提案 4） |
| rebuild 三态提示 | apps/web/src/views/kb/KBGovernanceView.vue:184-188 | 可删 | :185「rebuild 仅支持单文档选择。」是「rebuild 与审核共用 `selectedDocumentIds`」这一耦合的产物，耦合解除后该句消失 |
| 「最近一次 rebuild 结果」面板（裸字段名当标签） | apps/web/src/views/kb/KBGovernanceView.vue:191-198,577-580 | 可下沉 | 标签为 `doc_id/version/chunk_count/indexed_chunks/deleted_previous` 原文 |
| 「最近一次批量治理结果」面板 | apps/web/src/views/kb/KBGovernanceView.vue:200-219 | 可合并 | 与审计记录列表（:221-237）及其抽屉（:369-450）覆盖同一 `task_id`；批量动作后 `loadBatchEvents` 会刷新（:807），新事件即列表首条 |
| 「仅重试失败项」 | apps/web/src/views/kb/KBGovernanceView.vue:203 | 必要 | 失败恢复的唯一入口（门控 :585） |
| 「最近一次批量治理没有失败项。」空态 | apps/web/src/views/kb/KBGovernanceView.vue:218 | 可删 | 同面板的「总数/成功/失败」已表达同一事实（:206-208） |
| 审计面板标题 + 面板级「刷新」 | apps/web/src/views/kb/KBGovernanceView.vue:223-224 | 可合并 | 与头部刷新（:9）重复；`loadBatchEvents` 亦被 :687 一并调用 |
| 审计骨架 / 空态 | apps/web/src/views/kb/KBGovernanceView.vue:226-227 | 必要 | `batchEventsLoading` 期间的可辨识状态 |
| 审计记录行（动作/操作人/时间/成功失败/详情） | apps/web/src/views/kb/KBGovernanceView.vue:229-235 | 必要 | 治理审计的唯一列表（`kb.manage` 才可读，kb_analytics_routes.py:1246） |
| 整页骨架 loading | apps/web/src/views/kb/KBGovernanceView.vue:239-241 | 可删 | `v-if="loading"` 与队列 grid 的 `v-else`（:243）互斥，刷新即整体替换内容（见动效发现 A） |
| 区段标题 | apps/web/src/views/kb/KBGovernanceView.vue:247 | 必要 | 6 个队列的锚点（:607-612） |
| 区段 description 句 | apps/web/src/views/kb/KBGovernanceView.vue:248 | 可合并 | 与汇总卡 hint 同义重复（:597-601 对 :607-612） |
| 区段计数 tag `total / items` | apps/web/src/views/kb/KBGovernanceView.vue:251 | 必要 | 总数（含 8 条上限外的条目）与已加载数的唯一区分处；但无文字说明，且无「加载更多」（:543、:685） |
| 「本列全选 / 取消全选」 | apps/web/src/views/kb/KBGovernanceView.vue:252-254 | 必要 | 批量裁定的效率入口（`toggleSectionSelection` :634） |
| 区段空态（6 处同句） | apps/web/src/views/kb/KBGovernanceView.vue:257 | 可删 | `v-for` 6 个区段各渲染一次「当前筛选下没有待处理项。」；该句还把「队列本身为空」与「被工作集筛到零」混为一谈 |
| 行 checkbox | apps/web/src/views/kb/KBGovernanceView.vue:260-264 | 必要 | 选区唯一入口（`select-document-*` 亦为测试锚点） |
| 行 file_name | apps/web/src/views/kb/KBGovernanceView.vue:266 | 必要 | 主识别字段 |
| 行元数据 8 个同权 span | apps/web/src/views/kb/KBGovernanceView.vue:267-278 | 可合并 | `reasonLabel`（:621）与 `reviewLabel`（:620）映射高度重叠（同一状态两套中文），8 个 span 同字号同色平铺，需逐个读 |
| 低置信区域计数块 | apps/web/src/views/kb/KBGovernanceView.vue:279-285 | 可合并 | 计数与紧随其后的按钮文案（:288-290）重复，且 label/置信度与展开列表（:295-305）再次重复 |
| 审核备注展示 | apps/web/src/views/kb/KBGovernanceView.vue:286 | 必要 | 驳回原因的唯一落点（`reviewer_note`） |
| 「查看全部低置信区域（N）」 | apps/web/src/views/kb/KBGovernanceView.vue:287-291 | 必要 | 低置信证据的唯一展开入口（按需拉取，:641-672） |
| 低置信区域列表 + 区域卡 | apps/web/src/views/kb/KBGovernanceView.vue:292-311 | 必要 | 证据主体；但 6 处文案乱码（见页首缺陷） |
| 区域卡文案（`summary \|\| ocr_text`） | apps/web/src/views/kb/KBGovernanceView.vue:306 | 可合并 | 无长度约束（`kbVersionSummary.ts:21-26` 的 `truncateText` 具备该能力却未被本界面复用），长 OCR 文本会撑高卡片 |
| 区域卡「定位」 | apps/web/src/views/kb/KBGovernanceView.vue:308 | 可合并 | 与行级「定位低置信区域」（:314）落同一个 `openDocument` + query（:815-830） |
| 行「查看文档」 | apps/web/src/views/kb/KBGovernanceView.vue:313 | 必要 | 进入 `/workspace/kb/documents/:id`（:814） |
| 行「定位低置信区域」 | apps/web/src/views/kb/KBGovernanceView.vue:314 | 可合并 | 与 :313 同路由，仅多 `assetId/regionId` 两个 query（:821-830） |
| 行「打开知识库」 | apps/web/src/views/kb/KBGovernanceView.vue:315 | 必要 | 跨页跳转（`:831` → 上传页带 `baseId`） |
| 行「编辑」 | apps/web/src/views/kb/KBGovernanceView.vue:316 | 必要 | 单条治理修正入口（:810-812） |
| 「多当前版本冲突」面板 + 计数 tag | apps/web/src/views/kb/KBGovernanceView.vue:324-328 | 必要 | 冲突队列唯一列表（后端 kb_analytics_routes.py:342-395） |
| 冲突空态 | apps/web/src/views/kb/KBGovernanceView.vue:329 | 必要 | 「没有冲突」是有意义的结论 |
| 「查看冲突文档」 | apps/web/src/views/kb/KBGovernanceView.vue:336 | 必要 | 跳转到 `current_document_ids[0]`（:832） |
| 「治理修正」抽屉 + 12 个表单项 | apps/web/src/views/kb/KBGovernanceView.vue:341-357 | 必要 | 版本元数据修正的唯一表单；但生效区间/替代 ID/版本号等低频项与审核结论同层（见存疑） |
| 抽屉 5 个动作按钮 | apps/web/src/views/kb/KBGovernanceView.vue:359-365 | 可合并 | 指派给我/提交审核/通过/驳回/保存修正 同级并列，其中「保存修正」与三个状态下发是同一提交的不同 `review_status`（:812） |
| 审计详情抽屉元数据 6 行 | apps/web/src/views/kb/KBGovernanceView.vue:374-399 | 必要 | 任务状态/操作人/成功失败/重试链路 |
| 时间线筛选 select | apps/web/src/views/kb/KBGovernanceView.vue:400-407 | 必要 | 全部链路/仅重试/仅上游（下推服务端 :838） |
| 「重试该任务失败项」 | apps/web/src/views/kb/KBGovernanceView.vue:408-419 | 必要 | 历史任务的补偿入口（门控 :590-593） |
| 抽屉内失败项列表 | apps/web/src/views/kb/KBGovernanceView.vue:420-430 | 必要 | 重试决策依据 |
| 重试时间线 + 加载更多 | apps/web/src/views/kb/KBGovernanceView.vue:431-446 | 必要 | 唯一分页正确的列表（`has_more`，:444） |
| 裸 JSON `<pre>` | apps/web/src/views/kb/KBGovernanceView.vue:447 | 可删 | `JSON.stringify(details, null, 2)` 直接呈现后端原始结构（跨界面系统性问题，见返回 JSON 的 systemic_candidates） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 下沉 | apps/web/src/views/kb/KBGovernanceView.vue:37-151（含关联状态与动作 :529-533、:561-567、:689-766） | 少一次判断 | 这是本页最大的一块内容：4 个面板 + 1 个 JSON textarea + 4 个按钮（:41-77），全部排在真正的队列（:243）之前，首屏几乎谈不到治理。下沉目标已存在：`/workspace/kb/operations`（MainLayout.vue:255-259）。**真实代价**：知识灌入/rebuild 目前**只有**这一处 UI，必须先落到 KBOperationsView.vue 再删，否则能力不可达；且 `KBGovernanceView.test.ts:291-366` 覆盖 dry-run→写入→rebuild 的签名门控，迁移要重写该用例并迁移 4 个 `data-testid`（kb-batch-*） |
| 加反馈 | apps/web/src/views/kb/KBGovernanceView.vue:543,615,624,685,251,257 | 少一次误操作 | 每区段只取 8 条（`:543` 的 `limit` 从未被修改，后端上限 8、最大 50，kb_analytics_routes.py:1216），而工作集筛选是在这 8 条上做客户端二次过滤（:615→:624）。后果：后端有 23 条待审核时，选「待我处理」可能显示 0 条并给出「当前筛选下没有待处理项。」（:257），用户会判断为「已处理完」而漏处理。修复方向二选一：把 `workset` 下推服务端（需后端支持按 owner 过滤），或把 tag 文案写清并把 `limit` 提到 50。**真实代价**：全量拉取 50 条会放大首屏渲染成本（每行约 20 个 DOM 节点、6 个区段），且 `limit` 提到上限仍不等于分页；后者才是完整解，但需要后端加 offset |
| 删除 | apps/web/src/views/kb/KBGovernanceView.vue:14-20（及 :597-603 的 summaryCards） | 少一次判断 | 5 张卡片的 5 个数字在别处均已存在：4 个在区段 tag（:251）、1 个在冲突面板 tag（:327）。而且汇总卡与队列之间隔了 7 个 panel（:37-237），用户必须靠「记住数字→往下滚→找对应区段」来配对，这正是提案 1 落地后仍会残留的成本。删除后区段标题与它自己的计数相邻。**真实代价**：失去「一屏看到全部积压」的分诊视图；若将来队列很长，需要以「队列区顶部的一行计数」形式恢复，而不是复位到页顶；`tone` 字段（:597-601）一并清理 |
| 下沉 | apps/web/src/views/kb/KBGovernanceView.vue:164-182（及耦合提示 :184-188） | 少一次误操作 | rebuild 是**单文档**操作（`rebuildTarget` 要求恰好选中 1 条，:568），却和批量审核共用 `selectedDocumentIds`（:153-189）。选中多条时「预览 rebuild / 执行 rebuild」静默置灰并额外出现一句解释（:185），这与「批量通过/批量驳回为何变灰」难以区分，是误读来源。**真实代价**：单文档 rebuild 需要新落点，行内已有 4 个按钮（:313-316），再加会加剧拥挤，建议移入文档详情页；同时 `KBGovernanceView.test.ts:167-289` 依赖 `select-document-*` + `kb-rebuild-*` 锚点，删除会破坏该用例对「切换选中项后签名失效」的断言 |
| 删除 | apps/web/src/views/kb/KBGovernanceView.vue:10 | 少一次判断 | 该按钮与侧栏项指向同一路由 `/workspace/kb/upload`（MainLayout.vue:241-244），但标签不同（「知识库管理」vs「知识库治理」），会让人怀疑是两个不同的地方。桌面端侧栏常驻，删除零功能损失。**真实代价**：窄屏侧栏收起时少一个直达入口——侧栏在移动端的展开方式本次未验证（见存疑）；若确认收起后不可达，则该项降级为「改名与侧栏一致」而非删除 |

## 动效发现

前提事实：本文件 scoped 样式（`KBGovernanceView.vue:913-936`）**不含任何** `transition` / `animation` / `@keyframes` / `transform`（全文检索零命中）。本页所有动效均来自 Element Plus 默认（抽屉滑入+遮罩淡入、`el-skeleton animated` 微光、按钮 loading）与布局页过渡（MainLayout.vue:103，属已知全局项）。两个抽屉（:341、:369）属「偶尔」频次，EP 默认动效合规，无需改造；下表只记录本页特有的问题。

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 物理性与原点 | apps/web/src/views/kb/KBGovernanceView.vue:239-241,243 | `v-if="loading"` 的整页骨架与 `v-else` 的队列 grid 互斥：刷新时整个队列区（最长 6 个区段 × 8 条）从有到无再重建，页面高度与滚动位置整体跳变，属于典型的空间不连续；同时触发它的按钮（:9）自身已有 `:loading`，两个指示器表达同一状态 | 骨架只用于首屏（`governance === null`）；已有数据时的刷新保留列表，仅用头部按钮 loading 或面板顶部一条细进度条；不要用整块内容替换来表达「正在刷新」 |
| MEDIUM | 一致性与 token | apps/web/src/views/kb/KBGovernanceView.vue:919 | `.summary-value { font-size: 28px }` 脱离 token 刻度（22/18/15/12），并大于页面标题的 `--text-h2`（PageHeaderCompact.vue:42，18px）：页面最重的元素是 5 个统计数字，而不是用户要处理的那条文档。该硬编码字号模式跨 10+ 界面重复（见返回 JSON 的 systemic_candidates） | 降到 `--text-h2`（或 `--text-h1`），与页面标题同级或更低；不要新增字号刻度 |
| MEDIUM | 目的与频次 | apps/web/src/views/kb/KBGovernanceView.vue:226,240,371 | 同一个「加载中」状态有三种表示（3 行骨架 / 6 行整页骨架 / 6 行抽屉骨架）；其中 :226 的面板级骨架与 :224 的按钮 loading 会同时出现，是「同一状态两处指示」的重复 | 统一为一种局部骨架行数；面板级刷新只保留按钮 loading，避免骨架与 loading 并存 |
| LOW | 一致性与 token | apps/web/src/views/kb/KBGovernanceView.vue:914,918,922,930 | 三处 token 漂移：`gap: 20px` 写死（:914 未用 `--content-gap`，数值相同故无视觉差，但会随 token 变动而失效）、`font-size: 12px` 写死两次（:918、:930 未用 `--text-caption`）、`color: var(--warning-color, #e6a23c)`（:922）引用了 `style.css:1-84` 中**不存在**的变量，实际落到硬编码的 `#e6a23c`，等于在 token 体系外引入了一个色值（同写法另见 EntryView.vue:690,799,840） | 改用 `var(--content-gap)` / `var(--text-caption)`；`--warning-color` 要么补进 token 层，要么改用现有色阶，避免 fallback 静默生效 |
| LOW | 缺失的机会 | apps/web/src/views/kb/KBGovernanceView.vue:15-19,251,327 | 批量裁定成功后计数是静默跳变的（本文件无任何过渡声明），用户只能回看 toast 判断是否生效；这是状态指示的缺口，而非装饰缺口 | 只对计数本身做 `opacity`/`color` 的短反馈（<200ms，`--transition-fast`），不动 `width/height/margin`；若与 `prefers-reduced-motion` 的全局清零冲突则直接不做 |

## 存疑

- 6 处乱码的确切原文无法从文件本身 100% 反推：:302、:306 各丢失 1 字节（文件里已固化为 `?`）。上面的逆映射（区域/页码/置信度/坐标/无摘要/定位）是按 GBK 规则推导的语义推测，**改之前需人按上下文确认**，且必须保持 UTF-8 无 BOM（当前文件确为无 BOM）。另需确认是否有同类乱码存在于后端返回的 `region_label` 等字段中——若数据本身是乱码，只改前端文案不够。
- 「批量提交审核」（:161）对已处于 `review_pending` 的文档是否为幂等空操作？本次只读了队列谓词（kb_analytics_routes.py:214-227）与前端调用（:808），未读批量更新接口的写入路径，无法确认它是否还有别的副作用（如写 `reviewed_at`、触发通知）。
- 工作集筛选是否**应该**作用于汇总/冲突/审计记录？当前只作用于队列区（:615，`filteredDocumentSections`）。这属于产品语义选择，需要人确认，而不是实现缺陷。
- 提案 5 的前置：窄屏（<768px）侧栏收起后，`/workspace/kb/upload` 是否仍有足够的可达入口？需要真机确认侧栏的移动端展开方式。
- `responsive-enhancements.css:194-196` 的 `.el-drawer { width: 85% !important }` 位于 `@media (max-width: 768px)`（该块起始于 :57），会覆盖本页两个抽屉的 `size="460px"`（:341、:369）。768px 以下抽屉的实际宽度是否符合设计意图，需真机确认；本次未渲染。
- 队列区段上限 8 的**真实影响**未知：需要知道生产环境待审核队列的典型长度，才能判断「无加载更多」是瓶颈还是常态够用。提案 2 的收益量级取决于这个数字。
- 未实际渲染，因此下列判断未经视觉验证：28px 与 18px 在当前字重/字距下的真实重心关系；移动端 `@media (max-width: 768px)`（:935）把 `toolbar-row/panel-head/list-item` 改为纵向后，6 个区段堆叠的滚动成本；低置信区域列表（:295）在长 `ocr_text` 下的卡片高度。
- `data_quality.unsupported_fields`（api/kb.ts:317）本页从未渲染（同样恒为空数组，kb_analytics_routes.py:430）。需确认是「故意不展示」还是遗漏。
- `kbVersionSummary.ts` 在本界面**零引用**（`buildVersionSummary` 仅被 KBDocumentView.vue:481,537 使用，另有 kbVersionSummary.test.ts 覆盖）。它是纯函数模块、不渲染任何 UI，因此对本报告的元素清单贡献 0 项；它唯一与本界面相关的点是：本页区域卡（:306）未复用其 `truncateText` 能力，是否需要复用取决于上面提到的长文本实测结果。
