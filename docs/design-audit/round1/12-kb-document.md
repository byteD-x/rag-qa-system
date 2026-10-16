# 12 文档详情

## 唯一用户任务

知识库维护者在从上传结果 / 治理列表 / 问答引用点进某份文档后，要确认「当前查看的那个版本」的解析结果（切片、截图、处理事件）是否符合预期，并带着正确的版本（或截图区域）上下文发起提问。

## 完成该任务的必要步骤

1. 打开 `/workspace/kb/documents/:id`，等文档、截图、版本列表加载完成 — keep（`apps/web/src/views/kb/KBDocumentView.vue:24-27`、`:965-987`）
2. 读顶部信息行确认「现在看的是哪一版、状态、是否生效」 — keep（`KBDocumentView.vue:30-54`）
3. 在「版本治理」里确认当前版本与家族关系，必要时选一个对比版本 — keep（`KBDocumentView.vue:105-163`、`:545`）
4. 核对解析结果：切片粒度与截图资产 — keep（`KBDocumentView.vue:249-267`、`:270-313`）
5. 需要排障时展开「处理事件」确认解析链路是否走完 — keep（默认折叠，`KBDocumentView.vue:388-390`、`:508`）
6. 需要对比时点版本卡里的「查看内容 / 对比当前」，读检查器里的差异 — merge（`:143` 与 `:150` 是同一个 `inspectVersion()`，只差一个 tab，应合成一个动作）
7. 带着正确的版本 / 截图焦点去提问 — merge（页面有 7 个提问入口：`:18`、`:19`、`:94`、`:95`、`:98`、`:144`、`:158`）
8. 返回上一页 — drop（`:5` 的目标硬编码为上传页，与多数入口不符）
9. 需要修正元数据时打开编辑抽屉 — demote（`:6` + `:395-453`，低频动作不应占首屏按钮行）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页面标题（文件名） | `KBDocumentView.vue:3` | 必要 | 唯一标识当前对象 |
| 返回按钮 | `KBDocumentView.vue:5` | 可删 | 目标硬编码 `/workspace/kb/upload`；入口还包括治理列表（`KBGovernanceView.vue:814`）、运维（`KBOperationsView.vue:112`）、问答引用（`CitationList.vue:124`）；同项目 `KBChunkReviewView.vue:5` 用的是 `router.back()` |
| 编辑按钮 | `KBDocumentView.vue:6` | 可下沉 | 低频管理动作，与主任务同排 |
| 切片管理按钮 | `KBDocumentView.vue:7` | 可下沉 | 已有独立路由 `kb/documents/:id/chunks`（`apps/web/src/router/index.ts:173`），且页内「知识切片概览」（`:249-267`）已承担查看 |
| 删除按钮 | `KBDocumentView.vue:8` | 可下沉 | 破坏性动作与主任务按钮同排，中间只隔 5 个按钮就是主按钮 `:18` |
| 重试按钮 | `KBDocumentView.vue:9-17` | 可下沉 | 仅 `latest_job.retryable && canManage` 时出现；出现时头部同时有 primary / danger / warning 三种强色（`:8`、`:12`、`:18`） |
| 头部「按当前版本提问」 | `KBDocumentView.vue:18` | 可合并 | 与 `:94` 同为 `goChat()`；且文案在 `is_current_version=false` 时与实际目标不一致（`goChat` 不传参时取当前页面文档，`:1012-1014`） |
| 头部「比较提问」 | `KBDocumentView.vue:19` | 可合并 | 与 `:95` 等价——两者最终都落到 `selectedVersionRecord`（`:541-544`） |
| 信息项：大小 / 分类 / 版本标签 | `KBDocumentView.vue:31-33` | 可合并 | 版本标签与 `:65-67` 重复；分类缺失时直接渲染 `-`（`:32`） |
| 状态 tag | `KBDocumentView.vue:34-36` | 必要 | `statusMeta` 是解析是否成功的首个信号 |
| 当前 / 历史版本 tag | `KBDocumentView.vue:37-43` | 可合并 | 同义标签在 `:127-129`、`:173-175` 共出现三处 |
| 当前生效 tag | `KBDocumentView.vue:44-50` | 必要 | `effective_now` 与 `is_current_version` 是两个独立判断（`:545`） |
| 截图数量 tag | `KBDocumentView.vue:51-53` | 可合并 | 与 `:273`「截图资产 N 张」重复 |
| 面板标题「智能提问」 | `KBDocumentView.vue:59` | 可删 | 自述标题；面板用途已由输入框与焦点 tag 表达 |
| 面板描述段 | `KBDocumentView.vue:60` | 可删 | 一句话解释功能，非操作必需；可问什么已由 placeholder（`:617-628`）承载 |
| 面板上下文 tag `activeQuestionContextV2` | `KBDocumentView.vue:62` | 可合并 | 与紧跟其后的 tags 行 `:64-74` 表达同一上下文；旧版同名计算属性 `:598-643` 未渲染 |
| 面板「当前版本 X」tag | `KBDocumentView.vue:65-67` | 可合并 | 与 `:33` 重复 |
| 面板「比较 X」tag | `KBDocumentView.vue:68-70` | 必要 | 指示当前对比目标，防止误比较 |
| 面板「截图焦点 X」tag | `KBDocumentView.vue:71-73` | 必要 | 指示上下文里带了哪个截图区域 |
| 问题输入框 | `KBDocumentView.vue:75-81` | 必要 | 任务出口的输入 |
| 预设问题 ×3 | `KBDocumentView.vue:82-92` | 可删 | 点击整体覆盖已输入内容（`:1038-1040`），无确认无撤销 |
| 面板「按当前版本提问」 | `KBDocumentView.vue:93-94` | 可合并 | 与 `:18` 重复 |
| 面板「比较当前与所选版本」 | `KBDocumentView.vue:95-97` | 可合并 | 与 `:19` 重复 |
| 面板「聚焦当前截图区域」 | `KBDocumentView.vue:98-100` | 必要 | 唯一带截图焦点的提问入口 |
| 折叠容器 | `KBDocumentView.vue:104` | 必要 | 承载 4 个内容区 |
| 版本治理 header + 版本数 tag | `KBDocumentView.vue:105-109` | 必要 | 版本数是选版本前的主要判断信息 |
| 版本卡 | `KBDocumentView.vue:117-163` | 必要 | 选版本与读版本元信息的唯一载体 |
| 版本卡 当前 / 生效 tag | `KBDocumentView.vue:127-132` | 可合并 | 与 `:37-50`、`:173-175` 同义 |
| 版本卡 meta 五行 | `KBDocumentView.vue:135-141` | 可下沉 | 版本号与 header tag 重复；生效起止时间对「确认解析」非必要 |
| 版本卡「查看内容」 | `KBDocumentView.vue:143` | 可合并 | 与 `:150` 同一 `inspectVersion()`，只差一个 tab |
| 版本卡「按此版本提问」 | `KBDocumentView.vue:144` | 必要 | 版本级提问是核心出口 |
| 版本卡「对比当前」 | `KBDocumentView.vue:145-153` | 可合并 | `inspectVersion(item, true)`，与 `:143` 同函数 |
| 版本卡「比较提问」 | `KBDocumentView.vue:154-161` | 可合并 | 与 `:19`、`:95` 同功能；卡内已有两个按钮 |
| 版本检查器 | `KBDocumentView.vue:165-246` | 必要 | 「确认解析结果」的主要内容承载 |
| 检查器 当前 / 历史 tag | `KBDocumentView.vue:173-175` | 可合并 | 同义标签第三处 |
| Tab 快速摘要 | `KBDocumentView.vue:178-218` | 必要 | 长文档的快速核对 |
| Tab 版本内容 | `KBDocumentView.vue:219-226` | 必要 | 原文核对 |
| Tab 与当前版本差异 | `KBDocumentView.vue:227-244` | 可下沉 | 默认选中版本即当前文档（`:981-984`），该 tab 只会显示空态（`:228-234`） |
| 切片概览 header + 计数 tag | `KBDocumentView.vue:249-253` | 必要 | 计数即解析结果的规模指标 |
| 切片节点（序号 / 120 字截断 / 字符数） | `KBDocumentView.vue:261-267` | 必要 | 判断切片粒度是否合理 |
| 截图资产 header + 计数 tag | `KBDocumentView.vue:270-274` | 可合并 | 与 `:51-53` 重复 |
| 截图缩略图 + 红框 | `KBDocumentView.vue:283-292`、`:1515-1522` | 必要 | 截图焦点的定位基准 |
| 截图 meta 四行 | `KBDocumentView.vue:295-300` | 可下沉 | status 与区域数对「确认解析」弱相关 |
| 区域条四字段 | `KBDocumentView.vue:301-313` | 可下沉 | 置信度与归一化坐标（`:308-310`）是工程信息，用户无可执行含义 |
| 跨版本截图对比面板 | `KBDocumentView.vue:316-385` | 必要 | 「某版本截图变了什么」的唯一直接证据 |
| 对比策略 tag | `KBDocumentView.vue:324-326` | 可下沉 | 内部匹配策略（`:589-597`），用户只需知道对比的是哪一版 |
| 对比摘要 4 span | `KBDocumentView.vue:354-359` | 可合并 | 变化像素占比与热区图例（`:378-379`）重复 |
| 三块 canvas | `KBDocumentView.vue:360-383` | 必要 | 对比结论本体 |
| 处理事件折叠项 | `KBDocumentView.vue:388-390` | 必要 | 排障入口，默认折叠（`:508`） |
| DocumentEvents 重复标题 | `KBDocumentView.vue:389` | 可删 | collapse 标题「处理事件」（`:388`）与组件内 h3（`apps/web/src/components/DocumentEvents.vue:3-6`）相邻渲染同一串 |
| 编辑抽屉 | `KBDocumentView.vue:395-453` | 必要 | 修正元数据 |
| 抽屉「版本家族 Key」 | `KBDocumentView.vue:410-412` | 可下沉 | 工程概念，placeholder 已在教用户 |
| 抽屉「被当前版本替代的旧文档 ID」 | `KBDocumentView.vue:445-447` | 可删 | 要求用户手输 UUID，无选择器、无校验 |
| 加载中态 | `KBDocumentView.vue:24-27` | 必要 | 首屏反馈 |
| 未渲染的 v1 上下文计算属性 | `KBDocumentView.vue:598-643` | 可删 | 只被 `:642-643` 的 `void` 引用，模板用的是 v2（`:62`、`:80`）；同一串文案两套来源 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | `KBDocumentView.vue:18`（配套文案 `:1018`） | 少一次误操作 | 「按当前版本提问」在 `is_current_version=false` 时，实际请求的是当前页面这一版（`goChat` 无参取 `document.id`，`:1012-1014`），兜底问句（`:1018`）却写着「当前版本」，会有答错版本的观感。改文案会削弱「一键按最新版提问」的直达感；若改为历史版本页禁用该主按钮，则历史版本页失去主按钮位置，需要版本卡内 `:144` 承接。 |
| 合并 | `KBDocumentView.vue:93-101`（与 `:18-19`、`:144`、`:158` 共 7 个入口） | 少一次判断 | 收敛为「头部 1 个主入口 + 版本卡内 1 个绑定该版本的入口」后：提交按钮留在头部，用户在 textarea 打完字要回到顶部提交；留在面板内则和头部主按钮重复，必须二选一并固定位置。版本卡内「按此版本提问」与「比较提问」合并后，单版本提问与对比提问要靠下拉表态，多一次点击。截图焦点入口（`:98`）必须保留，否则「聚焦截图提问」失效。 |
| 下沉 | `KBDocumentView.vue:5-17`（编辑 / 切片管理 / 删除 / 重试） | 少一次误操作 | 四类管理动作收进一个入口后，删除与重试各多一次点击；下拉项需按 `canWrite` / `canManage`（`:535-536`）逐项禁用，否则变成「点开才发现没权限」；重试当前依赖 `latest_job.retryable`（`:10`）即时可见，收进菜单后排障时多一次展开。 |
| 删除 | `KBDocumentView.vue:5` 的硬编码返回目标 | 少一步 | 改成 `router.back()` 后，从问答引用（`CitationList.vue:124`）或新标签直接打开时没有浏览历史，会退出站点；必须保留 fallback 到治理列表 `/workspace/kb/governance`（`router/index.ts:108-115`）。另外顶栏面包屑是纯文本 span（`MainLayout.vue:84-90`），不可点，删掉返回按钮后「回到列表」只剩侧边栏一条路。 |
| 删除 | `KBDocumentView.vue:227-244`（默认态恒空的差异 tab） | 少一次误操作 | 按 `compareVersionReady`（`:545`）同条件隐藏后，「当前版本与自身比较」的入口消失（本就没有内容）。风险：隐藏逻辑若复用 `compareVersionReady`，将来后端对 (id,id) 真返回差异时会被一并藏掉；el-tabs 会在两 tab 与三 tab 之间切换，需确认默认选中 `content`（`:504`）仍有效。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 无障碍 | `KBDocumentView.vue:283-291`、`:302`（样式 `:1507-1513`、`:1546-1557`） | 截图缩略图与区域条只有 `@click`，没有 `tabindex` / `role` / 键盘处理，样式只有 `cursor: pointer`。而「截图焦点」会进入提问上下文（`:565-578`、`:1028-1036`），键盘与读屏用户完全无法设置它。 | 改为 button 语义或加 `tabindex="0"` + `role="button"` + Enter/Space，焦点态用现有 ring 变量；偿还：把每个区域条里的置信度/坐标（`:305-310`）删掉，降低 tab 序列噪音。 |
| HIGH | 缺失的机会 | `KBDocumentView.vue:143`、`:165-246` | 点「查看内容」后内容渲染在整套版本列表之后，无滚动定位、无 loading 反馈，唯一可见变化是卡片描边（`:1339-1342`）；同页的截图焦点却已有 `scrollToVisualAnchor`（`:715-729`）。多版本时用户会以为没反应而重复点击。 | 复用 `:715-729` 的模式把检查器滚入视野，或让检查器在卡片内联展开；偿还：`version-card--active` 的 `box-shadow` ring 可删，由内容变化本身承担反馈。 |
| MEDIUM | 性能 | `KBDocumentView.vue:1159-1170` 与 `:764`、`:777`、`:1000` | 同一次点击同时走显式调用和 watch 两条链路，全量像素 diff 跑两遍：每遍 2 次 `getImageData` + 逐像素循环（`apps/web/src/views/kb/kbVisualCompare.ts:165-193`，320×220 约 7 万像素），并对 `visualDiffState` 连续写两轮。 | 只保留一条触发链路（显式调用或 watch 二选一）。 |
| MEDIUM | 可打断性 / 物理性 | `KBDocumentView.vue:728` 与 `:1172-1177` | 一次区域点击会连续启动两次 `scrollIntoView({behavior:'smooth'})`：`focusVisualRegion`（`:767-778`）先调一次，随后 `router.replace`（`:775`）触发 route watch → `syncVisualFocusFromRoute`（`:731-744`）再调一次，后一次会打断前一次。 | 固定单一 owner（建议 route → sync 一条），去掉点击路径上的直接滚动。 |
| MEDIUM | 缓动与时长 / 一致性与 token | `KBDocumentView.vue:1264`、`:1490`、`:1556` | 三处 `transition: ... 0.2s ease`：硬编码时长 + CSS 预设曲线 `ease`，未用 `--transition-fast/base`（`apps/web/src/style.css:46-48`）。 | 统一换 token；进入类动效如需自定义用 `cubic-bezier(0.23,1,0.32,1)`。 |
| MEDIUM | 一致性与 token | `KBDocumentView.vue:897-899`、`kbVisualCompare.ts:182-185`、`KBDocumentView.vue:1515-1520` | 同一个「变化」概念用了三套颜色：差异框 `#f97316`、掩膜 `rgb(217,45,32)`、缩略图区域框 `#d92d20` + `rgba(217,45,32,0.14)`；图例文案只说「橙框」（`:378-379`），与实际红框不符。 | 收敛到一个 token 色 + 一个描边色；文案改为与颜色一致。 |
| MEDIUM | 无障碍 | `KBDocumentView.vue:728` | JS 的 smooth scroll 不受 `prefers-reduced-motion` 约束——全局只在 `style.css:806-815` 与 `styles/responsive-enhancements.css:252` 清 CSS 动画与过渡，管不到 `scrollIntoView`。本仓仅此一处 JS 平滑滚动（grep `scrollIntoView` 只有本文件）。 | 读 `matchMedia('(prefers-reduced-motion: reduce)')`，命中时用 `behavior: 'auto'`。 |
| MEDIUM | 目的与频次 | `KBDocumentView.vue:1256-1271` | 预设问题 chip 的 hover 位移 `translateY(-1px)` + `box-shadow` 属「好看」类，不对应空间一致性/状态指示/操作反馈/防突变任何一类；hover 属数十次/天频次，规则要求极简或砍掉。 | 删掉 `transform` 与投影，只留 border-color / 字重变化；本页唯一的 `:hover` 规则就是这一条。 |
| MEDIUM | 无障碍 | `KBDocumentView.vue:1267` | 该 `:hover` 位移未包在 `@media (hover:hover) and (pointer:fine)` 内；全仓 `*.vue` 中该 media 出现 0 次。触屏上会出现粘滞 hover。 | 与上一条一并处理（位移删掉即无此问题）；如需保留 hover 效果再包裹 media。 |
| MEDIUM | 目的与频次 / 缓动与时长 | `apps/web/src/components/EnhancedEmpty.vue:108-113`（在本页被实例化 8 次：`:110`、`:179`、`:228`、`:254`、`:275`、`:328`、`:339`、`:346`） | 空状态插画（非交互装饰元素）在 hover 时 `scale(1.05) rotate(2deg)`，缓动是回弹曲线 `cubic-bezier(0.34,1.56,0.64,1)` 0.3s。既不对应任何允许的动效理由，又用在不可点击的元素上。 | 删除 hover 缩放与旋转；如确需提示可交互，改由容器自身状态表达。 |
| LOW | 物理性与原点 | `KBDocumentView.vue:1493-1497` | 选中态用 `translateY(-1px)` 表达（在网格里与相邻卡片基线不齐），而选中态已由 border + ring + 背景三重视觉表达。 | 删位移，保留 border/ring；同一时刻只留一个最重的选中信号。 |

## 存疑

- 「与当前版本差异」tab 在默认态的实际返回：代码在选中版本 = 当前文档时仍会请求 `/versions/{id}/diff`（`KBDocumentView.vue:989-996`，`apps/web/src/api/kb.ts:69-73`，`compare_to_document_id` 省略），我按空态 `:228-234` 推断；后端对同 id 是返回空、还是返回整篇差异，需查后端或实测一次。
- 「按当前版本提问」在历史版本下是否真答错版本，取决于 `/workspace/chat` 对 `focusHint` 的解析（`chatRoutePresets.ts` 侧未审）。代码层只能确认 `goChat`（`:1012-1026`）发的是当前页面文档 id，且兜底问句写的是「当前版本」。需实际发起一次对比观察。
- 折叠区默认展开 3 项（`:508`）在真实长文档（数百切片 + 多张截图）下的首屏长度与滚动距离，需要真实数据渲染确认；本次为只读审计，未启动前端。
- canvas 未按 `devicePixelRatio` 放大：尺寸固定约 320×220（`:852-868`），CSS 宽度却占满卡片（`:1640-1646`）。DPR>1 屏幕上截图会不会糊到影响「看差异」，需实机比对 `canvas.width` 与 `clientWidth`。
- 截图焦点的粘滞 hover（`:1267`）在真机触屏上的实际表现需要真机确认，桌面模拟器不会重现。
- 权限为 false 时头部按钮仅 `disabled`、无原因说明（`:6`、`:8`、`:10`），是否需要在 UI 上解释取决于产品取舍；需以无权限账号实测。
- 数据依赖未核对后端 schema：`stats_json.category`（`:32`）、`stats_json.visual_asset_count`（`:51`）、`stats_json.section_preview`（`:534`）、`latest_job.retryable`（`:10`）缺失时这些元素会静默消失或显示 `-`，需要在接口层确认字段稳定性。
- 本页存在两个 `h1`：顶栏 `MainLayout.vue:92`（`route.meta.title` =「文档详情」，`router/index.ts:167`）与页头 `PageHeaderCompact.vue:4`（文件名，`KBDocumentView.vue:3`）。是否为既有约定需与全站口径确认，本次只作为系统性候选上报，未计入本页提案。
