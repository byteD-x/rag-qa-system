# 13 切片管理

审计范围：`apps/web/src/views/kb/KBChunkReviewView.vue`（300 行）
路由/入口：`/workspace/kb/documents/:id/chunks`（`apps/web/src/router/index.ts:172-182`，`requiresPermission: 'kb.write'`），从文档详情页的「切片管理」按钮进入（`apps/web/src/views/kb/KBDocumentView.vue:7`）
取证依赖（仅在与本界面相关处引用）：`components/PageHeaderCompact.vue`、`components/EnhancedEmpty.vue`、`api/kb.ts`、`layouts/MainLayout.vue`、`styles/theme-extras.css`，以及后端 `apps/services/knowledge-base/src/app/kb_chunk_governance.py`、`kb_chunk_routes.py`

## 唯一用户任务

知识库文档的属主/管理员（`kb.write`，`apps/web/src/router/index.ts:177`；后端还会按文档创建者再收窄一次，`apps/services/knowledge-base/src/app/kb_chunk_governance.py:66-78`）在「这份文档的检索/问答结果不对，怀疑切片切错了」的场景下，要**逐条核对切片边界并就地修正：过碎的合并、混成一团的拆开、跑题的停用**。

## 完成该任务的必要步骤

1. 从文档详情点「切片管理」进入，等 `getKBDocument` + `getKBChunks` 两个请求（`apps/web/src/views/kb/KBChunkReviewView.vue:217-220`）→ **keep**
2. 扫读每条切片正文与状态标记（`KBChunkReviewView.vue:46-52`）→ **keep**
3. 判断「这段属于哪一节、和前后是否重叠」：列表把全部切片按 `(section_index, chunk_index)` 拍平成一条流（`apps/services/knowledge-base/src/app/kb_chunk_governance.py:136`），界面不渲染 `section_title`（数据已返回，`kb_chunk_governance.py:94`）→ **demote**（把「小节」降为卡片的次要信息即可，不必新增大元素）
4. 修正切错的边界：「拆分」（`KBChunkReviewView.vue:34`）与「向上合并」（`:35`）→ **merge**（同一个目标被平铺成两个同级按钮，且合并的目标语义不可靠，见提案 1）
5. 改文字 / 记修改原因：「编辑」对话框（`KBChunkReviewView.vue:33` → `:58-71`）→ **keep**
6. 把跑题段落停用并填原因（`KBChunkReviewView.vue:36-43` → 模态框 `:153`）→ **keep**
7. 确认改动已生效：每个写操作后 `loadChunks()` 整表重载（`KBChunkReviewView.vue:143`、`:194`、`:211`）→ **keep**（重载方式代价高，见提案 3）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页头标题「知识切片管理」+ 副标题（文件名） | apps/web/src/views/kb/KBChunkReviewView.vue:3 | 必要 | 副标题（`document?.file_name`）是唯一上下文，没有它无法确认在审哪份文档 |
| 「返回」按钮 | apps/web/src/views/kb/KBChunkReviewView.vue:5 | 必要 | 唯一返回入口：MainLayout 的面包屑是纯 `span`，不可点（apps/web/src/layouts/MainLayout.vue:84-90）；但它用 `router.back()`，深链进入时语义不可靠（见存疑） |
| 「显示已禁用」开关 | apps/web/src/views/kb/KBChunkReviewView.vue:6 | 可合并 | 与卡片里的「禁用/启用」按钮同属一个状态轴；后端是"含"语义（apps/services/knowledge-base/src/app/kb_chunk_governance.py:121-122），打开后是启用+禁用混合，文案读起来却像"只看已禁用"，直接影响步骤 3/4 的相邻判断（见提案 1、3） |
| 开关的内联 `style="margin-left: 16px;"` | apps/web/src/views/kb/KBChunkReviewView.vue:6 | 可删 | 与 PageHeaderCompact 自带的 `gap: 12px` 重复叠加（apps/web/src/components/PageHeaderCompact.vue:59-64），且 16px 不在间距刻度里 |
| 加载态 | apps/web/src/views/kb/KBChunkReviewView.vue:11-14 | 可合并 | 与全站 12 个视图同名同体的 `.loading-state` 重复（KBChunkReviewView.vue:238-245、SceneManagerView.vue:195、CostDashboardView.vue:210 等），且它以 `v-if` 整体替换列表，每次保存都让列表消失重建（见提案 3） |
| 空态 EnhancedEmpty | apps/web/src/views/kb/KBChunkReviewView.vue:16-21 | 必要 | `variant="document"` +「暂无切片」是冷启动的唯一说明；但请求失败也会落到这里（`loadChunks` 无 catch，`:119-127`），见存疑 |
| 切片卡容器 | apps/web/src/views/kb/KBChunkReviewView.vue:24-29 | 必要 | 一条切片 = 一个记录单元，`is-disabled` 用透明度区分（`:263-266`） |
| 序号 `#{{ index + 1 }}` | apps/web/src/views/kb/KBChunkReviewView.vue:31 | 必要 | 唯一的行列定位锚点；注意它是**列表位置**（`:25` 的 v-for index），不是 `chunk_index`，切换「显示已禁用」后全部重排 |
| `(ID: {{ chunk.chunk_id.slice(0,8) }}...)` | apps/web/src/views/kb/KBChunkReviewView.vue:31 | 可删 | 页面上没有任何按 ID 检索/复制/跳转的动作，用户无法据此行动；它与 `#N` 挤在同一行还挤走操作区（见提案 5） |
| 「编辑」按钮 | apps/web/src/views/kb/KBChunkReviewView.vue:33 | 必要 | 改文字/备注的唯一入口（`updateKBChunk`，`:137-140`） |
| 「拆分」按钮 | apps/web/src/views/kb/KBChunkReviewView.vue:34 | 必要 | 修正"混成一团"的唯一入口；但它对已停用切片同样可见（`:34` 无状态判断），而后端拆分会把原切片强制置回启用（apps/services/knowledge-base/src/app/kb_chunk_governance.py:383）→ 提案 2 |
| 「向上合并」按钮 | apps/web/src/views/kb/KBChunkReviewView.vue:35 | 可下沉 | 目标是**列表上一项**（`chunks[index - 1]`），不是文档里的上一片：跨小节必失败（kb_chunk_governance.py:467-468，409），默认视图下若中间隔着被隐藏的停用切片还会撞 `chunk_merge_requires_contiguous_range`（kb_chunk_governance.py:470-472）→ 提案 1 |
| 「禁用 / 启用」按钮 | apps/web/src/views/kb/KBChunkReviewView.vue:36-43 | 必要 | 唯一启停入口；`type` 随状态在 danger/success 间切换（`:38`） |
| 切片正文 | apps/web/src/views/kb/KBChunkReviewView.vue:46-48 | 必要 | 本页最重元素，`white-space: pre-wrap` 保留原始换行（`:292`） |
| 「禁用原因」tag | apps/web/src/views/kb/KBChunkReviewView.vue:50 | 必要 | 停用状态的唯一回显（`chunk.disabled_reason`） |
| 「备注」tag | apps/web/src/views/kb/KBChunkReviewView.vue:51 | 必要 | 人工备注的唯一回显（`chunk.manual_note`） |
| 卡片四边边框 + 手写阴影 | apps/web/src/views/kb/KBChunkReviewView.vue:257、:260 | 可删 | 阴影 `0 1px 3px rgba(0,0,0,0.05)` 是就地手写值，与 `--shadow-sm`（apps/web/src/style.css:50）不同且全仓仅此一处（grep `box-shadow: 0 1px 3px` 仅命中本行）；单列列表靠边框足以分层 |
| 卡片头部下边框 | apps/web/src/views/kb/KBChunkReviewView.vue:273 | 可删 | 与卡片外边框、下一张卡片的上边框叠成一屏三条线；`margin-bottom: 12px`（`:272`）已足够分组 |
| 按钮的 4 个色变体（primary / warning / 默认 / danger-success） | apps/web/src/views/kb/KBChunkReviewView.vue:33-43 | 可下沉 | 同一行 4 个按钮里 3 个带色，违反"同一时刻只允许一个元素最重"；`warning` 在本文件是唯一使用处，与「编辑」的 `primary` 之间没有用户可感知的语义差 |
| 「禁用」的选填原因模态框 | apps/web/src/views/kb/KBChunkReviewView.vue:153-156 | 可合并 | 每次停用都要过一次模态框，而原因是选填；同一界面的合并确认框（`:200-204`）没写 `confirmButtonText`，两处默认按钮文案不一致 |
| 编辑对话框 | apps/web/src/views/kb/KBChunkReviewView.vue:58-71 | 必要 | 标题只有「编辑切片」，而相邻切片正文往往高度相似 → 用户无法确认自己改的是哪一片（见提案 4） |
| 「切片内容」textarea（rows=6） | apps/web/src/views/kb/KBChunkReviewView.vue:61 | 必要 | 主编辑面；固定 6 行、无自动增高、无字数提示，长切片靠内部滚动 |
| 「人工备注」输入 | apps/web/src/views/kb/KBChunkReviewView.vue:63-65 | 必要 | 落入 `manual_note`；但后端是 `manual_note if manual_note else 旧值`（apps/services/knowledge-base/src/app/kb_chunk_governance.py:297），清空是静默无效（见存疑） |
| 拆分对话框 | apps/web/src/views/kb/KBChunkReviewView.vue:74-85 | 必要 | 预填原切片按空行切分的片段（`split('\n\n')`，`:178`），用户在其上增删 |
| 拆分片段 textarea × N | apps/web/src/views/kb/KBChunkReviewView.vue:76-79 | 必要 | `:key="i"` + `splice` 的索引键循环（`:76`、`:78`），删除中间片段后的输入表现需实机确认（见存疑） |
| 片段删除按钮（纯图标） | apps/web/src/views/kb/KBChunkReviewView.vue:78 | 必要 | **当前是一个空按钮**：`icon="Delete"` 传字符串，而全仓没有任何全局图标注册（apps/web/src/main.ts:27-34 只注册 elementComponents / EnhancedEmpty / ThemeToggle；element-plus-components.ts:1-105 无图标），Element Plus 用 `resolveDynamicComponent(__props.icon)` 渲染（node_modules/element-plus/es/components/button/src/button.vue2.mjs），Vue 对未注册的字符串返回字符串本身（node_modules/@vue/runtime-core/dist/runtime-core.cjs.js 中 `resolveAsset(COMPONENTS, component, false)`）→ 渲染成无内容的未知元素，既看不到图标也没有可访问名（见提案 4） |
| 「增加拆分片段」按钮 | apps/web/src/views/kb/KBChunkReviewView.vue:80 | 必要 | 唯一增行入口；同样 `icon="Plus"` 失效，但按钮有文字，只损失一个图标 |
| 拆分对话框的内联间距（16px / 10px / 8px、`width: 100%`） | apps/web/src/views/kb/KBChunkReviewView.vue:75-80 | 可删 | 与 `--content-gap` / `--section-gap` 无关的就地数值，且宽度直接写在按钮上；等于删掉这些局部刻度 |
| `.chunk-card.is-disabled { background: var(--bg-body) }` | apps/web/src/views/kb/KBChunkReviewView.vue:265 | 可删 | `--bg-body` 全仓未定义（apps/web/src/style.css:1-84 无此变量；全仓 grep 只有 2 处引用：本行与 PromptTemplateView.vue:259）→ 该声明在计算值阶段失效，禁用态实际只靠 `opacity: .6`（`:264`） |
| `.chunk-id` 13px / `.chunk-body` 14px | apps/web/src/views/kb/KBChunkReviewView.vue:279、:289 | 可删 | 两个就地字号都不在刻度内（`--text-caption` 12px / `--text-body` 15px，apps/web/src/style.css:32-35）；13px 只服务 ID 行，随 ID 一起消失 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 加反馈 | apps/web/src/views/kb/KBChunkReviewView.vue:35、:200-214 | 少一次误操作 | 需要用已返回的 `section_id` / `chunk_index`（apps/services/knowledge-base/src/app/kb_chunk_governance.py:91-93）判"真实相邻"：跨小节时按钮消失，用户失去"跨小节合并"的假能力（后端本就 409 拒绝，kb_chunk_governance.py:467-468）；确认框还要写明"保留上一段，后一段的正文与人工备注会被并入后删除"（后端把文本并进 `chunk_index` 较小的一条并 DELETE 其余，kb_chunk_governance.py:473-509，且合并不带上后一段的 `manual_note`）——文案变长会让这个低频对话框更重 |
| 加反馈 | apps/web/src/views/kb/KBChunkReviewView.vue:34、:175-181 | 少一次误操作 | 后端拆分时会把原切片强制 `disabled = FALSE`（apps/services/knowledge-base/src/app/kb_chunk_governance.py:383），所以用户"拆一段已停用的切片"会静默把它放回检索。若产品认为"拆分=人工修边，本就该重新启用"，只需在拆分对话框加一句提示；若改成禁止拆分已停用切片，用户要先启用再拆分（多一步），且会挡住"拆完再停用"的合理路径。前端无法单方面决定，需要后端确认这是有意还是漏写 |
| 加反馈 | apps/web/src/views/kb/KBChunkReviewView.vue:11-14、:105、:119-127、:143/:194/:211 | 少一步 | 改成"列表保持可见（局部 loading）+ 变更落点反馈"会用到后端已返回的 `counts`（apps/services/knowledge-base/src/app/kb_chunk_routes.py:31-35），而它只在 `include_disabled=true` 时才是全量真值——只改文案不同时改请求参数会显示错误数字；就地替换列表需要消费写接口的返回体（split/merge 已返回 `items`，kb_chunk_governance.py:451、:538；PATCH 只返回单条，kb_chunk_governance.py:346-349），前端逻辑会比现在的"无脑重取"复杂，回滚时也不再有一份权威全量 |
| 加反馈 | apps/web/src/views/kb/KBChunkReviewView.vue:58、:74-80 | 少一次误操作 | 对话框标题拼上 `#序号 / 小节` 后变长，窄屏更容易折行（两个对话框写死 `width="600px"`，`:58`、`:74`，而 Element Plus 的 `.el-dialog` 基础样式没有 max-width，node_modules/element-plus/theme-chalk/src/dialog.scss:18）；给片段删除按钮补文字会压缩 textarea（行内 `flex: 1`，`:77`）；修好图标要在本文件新增一行 `@element-plus/icons-vue` 的 import（全仓无全局注册，apps/web/src/main.ts:27-34），用一行 import 换掉两处字符串图标 |
| 降层级 | apps/web/src/views/kb/KBChunkReviewView.vue:31、:33-43、:257-275 | 少一次判断 | 删掉 ID 前缀后，排障时少一个可核对的标识（只能挪进编辑对话框，那又是一处新增信息）；去掉 `warning` 色后「拆分」与「编辑」只靠文字区分（两者都是对同一段做结构/文本修改，本来也不需要色差）；删掉阴影后卡片与页面底色更接近，必须在实机上确认 `--border-color`（rgba 8%）在 `--bg-panel-muted` 上仍能划出边界——这是纯视觉验证项 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| MEDIUM | 缺失的机会 | apps/web/src/views/kb/KBChunkReviewView.vue:11-14、:143/:194/:211 | 每个写操作（保存 / 拆分 / 合并）后调 `loadChunks()` 整表重载，列表被 `.loading-state` 整体替换再重建：滚动位置丢失，也没有"改动落在哪"的指示，用户得重新找到刚改的那一段 | 消费写接口返回的 `items`（apps/services/knowledge-base/src/app/kb_chunk_governance.py:451、:538）就地替换；或重载后保留滚动位置，只对受影响切片做一次入场反馈（仅 opacity / transform，<300ms） |
| MEDIUM | 缓动与时长 / 性能 | apps/web/src/styles/theme-extras.css:131-144（在 apps/web/src/layouts/MainLayout.vue:103 生效） | 本界面唯一的页面级动效是 `page` 过渡：`opacity .25s ease, transform .25s ease` + `translateY(6px)`，用了 `ease` 预设曲线；进入本页时它还与 `loadChunks()` 的加载态叠加——先"页面滑入 + 加载中"，再列表出现，同一个"内容出现"被表达两次 | 入场曲线换 `cubic-bezier(0.23,1,0.32,1)`，或让首屏加载不参与这次过渡（数据未到时不做位移） |
| MEDIUM | 无障碍 / 目的与频次 | apps/web/src/components/EnhancedEmpty.vue:108-113（本页空态 apps/web/src/views/kb/KBChunkReviewView.vue:16-21 渲染它） | 空态插图挂 `:hover` 做 `scale(1.05) rotate(2deg)`、300ms、`cubic-bezier(0.34,1.56,0.64,1)` 过冲曲线；它是纯装饰、无任何交互监听，却给出可点的错觉，且未包在 `@media (hover: hover) and (pointer: fine)` 内（触屏会粘住 hover）。另：全局 reduced-motion 只把 duration 清零（apps/web/src/style.css:806-814），本处 `transform` 仍会瞬间生效 | 删掉该 hover 变换；若保留，reduce 下必须把 scale/rotate 一并去掉。同一组件在 docs/design-audit/round1/07-kb-upload.md 已按 HIGH 记过一次，此处只记录本界面的实例，不另立结论 |
| LOW | 状态指示 / 一致性与 token | apps/web/src/views/kb/KBChunkReviewView.vue:263-266 | 禁用态由 `opacity: .6` + `background: var(--bg-body)` 表达，而 `--bg-body` 未定义 → 背景那半条失效，只剩整体降透明度；用户要结合「禁用原因」tag（`:50`）才能确认这是被停用、而非加载或不可用 | 改用已存在的 `--bg-panel-muted`，或左侧 2px 边框；`opacity` 保留即可，不必加过渡（停用是低频操作） |
| LOW | 一致性与 token | apps/web/src/views/kb/KBChunkReviewView.vue:6、:234、:257-260、:279、:289、:75-80 | 就地数值散落：内联 `margin-left: 16px`（`:6`）与页头自身 12px gap 叠加、容器 padding 16px（`:234`，`--content-gap` 是 20px）、手写阴影（`:260`，全仓唯一）、字号 13px / 14px（`:279`、`:289`，刻度是 12 / 15）、拆分对话框内联 16/10/8px（`:75-80`） | 统一回到已有 token；`--bg-body` 与手写阴影属死值，可直接删 |

## 存疑

- 「返回」用 `router.back()`（apps/web/src/views/kb/KBChunkReviewView.vue:5）：从文档详情点进来是正常的，但这条 URL 可直接打开/刷新（路由本身可深链，apps/web/src/router/index.ts:172-182），此时后退落点取决于浏览器历史，可能跳出应用。需要人确认期望语义（稳定回文档详情 vs 保持历史后退）；本次未在浏览器里实际点过。
- `loadChunks` 没有 catch（apps/web/src/views/kb/KBChunkReviewView.vue:119-127），请求失败时 `chunks` 保持 `[]`，界面落到「暂无切片 / 该文档暂时没有切片或切片正在生成中」（`:16-21`）。请求层会先弹一次全局 error toast（apps/web/src/api/request.ts:128、:158），但 toast 消失后留下的是一句错误诊断，用户可能据此重新灌库。需要真实触发一次 403/500（或断网）确认表现，并决定是否要独立错误态。
- 「人工备注」清空无效：输入框允许清空（apps/web/src/views/kb/KBChunkReviewView.vue:63-65），后端是 `manual_note if manual_note else 旧值`（apps/services/knowledge-base/src/app/kb_chunk_governance.py:297）→ 清空不会写回空串。需要人确认这是有意的"只追加"语义还是漏写；若是漏写，本页的交互承诺就是假的。
- 拆分对话框的 `:key="i"` + `splice`（apps/web/src/views/kb/KBChunkReviewView.vue:76、:78）在删除中间片段后是否出现光标跳动/输入法错位，需要实机试一次（文本值由 `splitParts[i]` 回填，理论上不会串值，但输入态无法靠读码判断）。
- 两个对话框写死 `width="600px"`（apps/web/src/views/kb/KBChunkReviewView.vue:58、:74），Element Plus 的 `.el-dialog` 基础样式无 max-width（node_modules/element-plus/theme-chalk/src/dialog.scss:18，全文件无 `@media` 兜底）→ 窄屏会横向溢出。需在 375px 宽度实机确认溢出程度，尤其确认拆分对话框的多行 textarea 是否还能用。
- 移动端卡片头部：`display: flex; justify-content: space-between` 不换行（apps/web/src/views/kb/KBChunkReviewView.vue:268-275），而触屏下全局给 `.el-button` 加了 `min-height: 44px`（apps/web/src/styles/responsive-enhancements.css:33-40）；4 个按钮 + `#N (ID: …)` 挤同一行，右侧按钮有被裁掉的嫌疑（外层 `.page-shell` 是 `overflow: hidden`，`:228`）。需要 375px 实机确认，重点确认最后一个「禁用」按钮是否还点得到。
- 合并的相邻前提：默认视图（`include_disabled=false`，apps/web/src/views/kb/KBChunkReviewView.vue:105、:122 → kb_chunk_governance.py:121-122）会把停用切片从列表里拿掉，但它们仍占着 `chunk_index`；此时"上一项"在库里并非相邻项，会命中 `chunk_merge_requires_contiguous_range`（apps/services/knowledge-base/src/app/kb_chunk_governance.py:470-472），前端只显示「合并失败」（`:213`）。需要人确认产品是否接受"停用切片会打断合并"；若要修，先决定列表是否始终拉全量。
- `chunk_id.slice(0,8)`（apps/web/src/views/kb/KBChunkReviewView.vue:31）在界面上没有任何使用场景；我按"用户无法据此行动"判为可删，但若排障流程要求用户回报这 8 位，就应保留——需要人确认是否存在该流程。
- 仓库级、非本界面：apps/web/vite.config.ts:13-16 把演示口令类环境变量带默认值注入前端构建（此处不引用具体值）。是否进入产物需要检查构建产物，建议单独跟踪。
