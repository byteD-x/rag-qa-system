# 18 场景模板 / 缓存管理 / 指令模板市场

审计对象：`apps/web/src/views/platform/SceneManagerView.vue`（222 行）、`apps/web/src/views/platform/CacheManagerView.vue`（273 行）、`apps/web/src/views/platform/InstructionMarketView.vue`（135 行）

路由：`/workspace/platform/scenes`、`/workspace/platform/cache`、`/workspace/platform/market`（`apps/web/src/router/index.ts:261-270`、`:271-281`、`:315-325`，三者 `requiresPermission` 均为 `chat.use`）

审计性质：只读。本文件是本次审计唯一写入的文件。

## 唯一用户任务

三个页面共用同一层「工作台 → 平台配置」外壳，但不是一个任务，是三件独立的事，不能合并成一句话：

1. **场景模板**：平台使用者要给当前问答换一套「回答行为预设」，在 6 个候选里选一个并让它生效。
2. **缓存管理**：运维想让回答更快更省，调缓存策略参数，或让某批已过期的缓存立刻失效。
3. **指令模板市场**：使用者想复用别人沉淀的 Prompt 指令模板并用到自己的问答里（或建/导入自己的模板）。

三者唯一的共性是形态：都是「配置输入 + 卡片列表 + 一个动作」，都要求用户做一次「选一个然后生效」的决策。因此下面按页分别审计。

## 完成该任务的必要步骤

### 场景模板（/workspace/platform/scenes）

1. 打开页面，一屏看到 6 张场景卡 —— **keep**（`apps/web/src/views/platform/SceneManagerView.vue:27-72`）
2. 判断哪张卡是我要的：读卡片名称 + 描述 —— **keep**（`apps/web/src/views/platform/SceneManagerView.vue:32-33`）
3. 看清「这个场景到底会改变什么行为」 —— **drop**（作为 UI 步骤无法完成：卡片 prompt 预览 `:38-40` 与预览弹窗 `:76-92` 展示的 `system_prompt` 在数据源里就是占位串，见 `:126-131` 的 `'你是一个企业级知识助手...'`；这一步需要后端补真实 prompt，不是界面能修的）
4. 点「应用此场景」 —— **keep**（`apps/web/src/views/platform/SceneManagerView.vue:67-69`，但它的真实效果是创建/改名 Agent Profile，见 `:168-178`，不是"应用场景"）
5. 看到成功反馈、卡片进入 active 态 —— **merge**（`:179-180` 与 `:201`；active 只是内存变量，刷新即失）

### 缓存管理（/workspace/platform/cache）

1. 打开页面看当前缓存规模与命中率 —— **keep**（`apps/web/src/views/platform/CacheManagerView.vue:14-35`；但加载中渲染的是 5 个真实的 `0`，不是占位，因为 stats-row 在 `v-if="loading"`（`:37`）之外）
2. 判断要不要调阈值 / TTL / 条目上限 —— **keep**（`apps/web/src/views/platform/CacheManagerView.vue:48-75`）
3. 改值并保存 —— **keep**（`apps/web/src/views/platform/CacheManagerView.vue:46`）
4. 定位要失效的范围：填 corpus_id，或填完整问题文本 —— **drop**（"按问题失效"整块应删：`:91-99` 要求用户逐字输入完整问题，后端是等值匹配 `apps/services/api-gateway/src/app/semantic_cache.py:223`，而页面上没有任何缓存条目列表可供挑选，成功率极低）
5. 执行失效 —— **keep**（`apps/web/src/views/platform/CacheManagerView.vue:86-97`），但必须补前置确认（见提案 1）
6. 清空全部 —— **keep**（`apps/web/src/views/platform/CacheManagerView.vue:100-106`，已有二次确认）
7. 读「三层缓存架构」说明 —— **demote**（`:109-138` 是静态科普，页面上的 stats 并无分层数据与之对应）

### 指令模板市场（/workspace/platform/market）

1. 打开市场看模板卡 —— **keep**（`apps/web/src/views/platform/InstructionMarketView.vue:23-52`）
2. 在搜索 / 标签 / 可见性三个控件里缩小范围 —— **merge**（`:11-21`）
3. 预览模板正文 —— **keep**（`apps/web/src/views/platform/InstructionMarketView.vue:44`、`:58-63`；`content` 是真实内容，与卡片互补）
4. 用它 —— **drop**（作为当前 UI 步骤不可完成：`:45` 的「使用」调用的 `/platform/prompt-templates/{id}/apply` 在后端不存在，见 `apps/web/src/api/platform.ts:376`；`apps/services/api-gateway/src/app/gateway_platform_routes.py` 全文只有 list/post/get/patch/delete 五条 prompt-templates 路由，必然 404）
5. 收藏 —— **drop**（`InstructionMarketView.vue:46-48` 只改内存计数 `:115`，刷新即失）
6. 创建 / 导入自己的模板 —— **drop**（作为当前 UI 步骤不可完成：`:5-6` 两个按钮只翻转 `showCreate` / `showImport`（`:78-79`），没有任何对话框绑定它们）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 页面标题 + 副标题 | apps/web/src/views/platform/SceneManagerView.vue:3-4 | 必要 | 定位当前界面 |
| 标签筛选条（12 个 el-tag） | apps/web/src/views/platform/SceneManagerView.vue:8-20 | 可删 | 6 张卡片共 12 个标签，每个标签只命中 1 张卡（`:126-131` 逐条核对：qa/enterprise、tech/support、compliance/legal、training/education、data/analytics、code/review）；且卡片上不渲染 `tags`（`:28-71` 无 tags 输出），用户无法预判标签归属，筛选后只剩 1 张本来就在屏上的卡 |
| 「清除筛选」按钮 | apps/web/src/views/platform/SceneManagerView.vue:19 | 可合并 | 与「再点一次同一标签即取消」（`:14`）重复，是同一目标的两个入口 |
| 加载态 | apps/web/src/views/platform/SceneManagerView.vue:22-25 | 必要 | 首次加载 |
| 场景卡片容器（grid） | apps/web/src/views/platform/SceneManagerView.vue:27 | 必要 | 承载 6 个候选 |
| 卡片 emoji 图标 | apps/web/src/views/platform/SceneManagerView.vue:30 | 可删 | 与 `h3` 名称同义（`:32`），不携带卡片间判别信息；emoji 在不同平台字宽不一致，会把 `h3` 起始位推歪 |
| 卡片名称 | apps/web/src/views/platform/SceneManagerView.vue:32 | 必要 | 选择的唯一标识 |
| 卡片描述 | apps/web/src/views/platform/SceneManagerView.vue:33 | 必要 | 选择依据 |
| 卡片内 prompt 预览（截断 180） | apps/web/src/views/platform/SceneManagerView.vue:38-40 | 可删 | 数据源是占位串（`:126-131`），`truncate(...,180)`（`:147`）对 11 字占位串是空操作；与预览弹窗内容重复 |
| meta-row 推荐工具 | apps/web/src/views/platform/SceneManagerView.vue:44-49 | 可下沉 | 选择时非首要判据（用户先看"这个场景是干什么的"）；同值在预览弹窗 `:88` 重复出现 |
| meta-row 模型策略 + 层级 | apps/web/src/views/platform/SceneManagerView.vue:50-58 | 可下沉 | 同上，且同值在弹窗 `:85-86` 重复 |
| meta-row 检索偏好 | apps/web/src/views/platform/SceneManagerView.vue:59-62 | 可下沉 | 同上，且同值在弹窗 `:87` 重复 |
| 「预览 Prompt」按钮 | apps/web/src/views/platform/SceneManagerView.vue:66 | 可删 | 打开后只显示占位串 + 与卡片完全重复的 4 行元数据 |
| 「应用此场景」按钮 | apps/web/src/views/platform/SceneManagerView.vue:67-69 | 必要 | 页面上唯一的生效动作（语义与实现不符，见提案 4） |
| 预览对话框 | apps/web/src/views/platform/SceneManagerView.vue:76-92 | 可删 | 内容全量重复卡片（`:82` vs `:38-40`；`:85-88` vs `:44-62`），且主内容 `system_prompt` 是占位串 |
| 弹窗内 el-descriptions（4 行） | apps/web/src/views/platform/SceneManagerView.vue:84-89 | 可删 | 与 meta-row 三行是同一批字段的第二次呈现 |
| 卡片 active 态 | apps/web/src/views/platform/SceneManagerView.vue:28、:201 | 可合并 | 仅内存态（`:179`），刷新即失；与 hover 态（`:200`）同为阴影语言，两个状态同时可亮，违反"同一时刻只允许一个元素最重" |
| 页面标题 + 刷新按钮 | apps/web/src/views/platform/CacheManagerView.vue:3-10 | 必要 | 数据需手动同步 |
| stats 概览 5 张卡 | apps/web/src/views/platform/CacheManagerView.vue:14-35 | 可合并 | 5 张同权重卡（同一 22px/700/蓝 数值并列，`:241`），5 个数字同时最重；应并成一行内联指标并区分主次。另：加载中显示的是真实 `0` 而非占位 |
| 加载态 | apps/web/src/views/platform/CacheManagerView.vue:37-40 | 必要 | 首次加载 |
| 「缓存配置」段头 + 保存配置 | apps/web/src/views/platform/CacheManagerView.vue:44-47 | 必要 | 参数入口 |
| 相似度阈值 slider（marks + show-input） | apps/web/src/views/platform/CacheManagerView.vue:52-59 | 可合并 | `marks`（`:57` 0.7/0.85/0.92/0.99）与 `show-input`（`:58`）同时显示同一个数值，二选一 |
| 默认 TTL 输入 | apps/web/src/views/platform/CacheManagerView.vue:65-67 | 必要 | 参数本身 |
| 最大条目数输入 | apps/web/src/views/platform/CacheManagerView.vue:70-72 | 必要 | 参数本身 |
| 「缓存失效」段头 | apps/web/src/views/platform/CacheManagerView.vue:78-80 | 可合并 | 与「缓存配置」同层级第二段（`:44`），靠 `style="margin-top:28px"`（`:78`、`:110`）拉开，可并入同一面板 |
| 按知识库失效（输入 + 按钮） | apps/web/src/views/platform/CacheManagerView.vue:83-89 | 必要 | 批量失效的唯一可用入口（但空输入会清空全部，见提案 1） |
| 按问题失效（输入 + 按钮） | apps/web/src/views/platform/CacheManagerView.vue:91-99 | 可删 | 要求逐字输入完整问题文本；后端 `entry.question == question` 等值匹配（apps/services/api-gateway/src/app/semantic_cache.py:223）；无候选列表、无校验、无反馈差异（0 条也报"成功"） |
| 清空全部缓存 + 确认弹窗 | apps/web/src/views/platform/CacheManagerView.vue:100-106、:201-209 | 必要 | 危险操作的唯一受保护入口 |
| danger-hint 文案 | apps/web/src/views/platform/CacheManagerView.vue:105 | 可下沉 | 与确认弹窗文案（`:203`）重复；且用未定义变量 `--red-500` 着色（`:264`） |
| 「三层缓存架构」3 张说明卡 | apps/web/src/views/platform/CacheManagerView.vue:110-138 | 可下沉 | 纯静态科普，与本页数据无对应关系（stats 只给聚合值，无分层数值），占一屏三分之一高 |
| layer 卡 emoji 图标 | apps/web/src/views/platform/CacheManagerView.vue:115、:123、:131 | 可删 | 装饰，无判别信息 |
| 标题 + 「导入」/「创建模板」按钮 | apps/web/src/views/platform/InstructionMarketView.vue:3-7 | 必要 | 承载两个主任务入口（当前均未接线，见提案 2 与存疑） |
| 搜索输入 | apps/web/src/views/platform/InstructionMarketView.vue:12 | 必要 | 模板增多后唯一的定位手段（`:87` 匹配 name/description） |
| 标签下拉筛选 | apps/web/src/views/platform/InstructionMarketView.vue:13-15 | 可合并 | 卡片上已渲染 tags（`:32-36`），下拉是同一份数据的第二个出口 |
| 可见性单选（全部/公共/私有） | apps/web/src/views/platform/InstructionMarketView.vue:16-20 | 可合并 | `private` 永不匹配：后端 `visibility` 只允许 `personal` / `public`（apps/services/api-gateway/src/app/gateway_schemas.py:405），序列化默认值也是 `personal`（apps/services/api-gateway/src/app/gateway_platform_store.py:23），而这里是 `t.visibility !== 'private'`（`:89`）→ 选「私有」恒为空结果 |
| 模板卡名称 | apps/web/src/views/platform/InstructionMarketView.vue:26 | 必要 | 唯一标识 |
| 可见性徽章 | apps/web/src/views/platform/InstructionMarketView.vue:27-29 | 可合并 | 与上面的单选组同义；且把后端 `personal` 显示为「私有」（`:28`），与筛选值 `private` 用词不一致，同一个模板在两处被叫两个名字 |
| 模板描述 | apps/web/src/views/platform/InstructionMarketView.vue:31 | 必要 | 选择依据（有 '暂无描述' 兜底） |
| 模板 tags chips | apps/web/src/views/platform/InstructionMarketView.vue:32-36 | 可下沉 | 辅助信息，不参与"用哪个"的决策（真正决定的是正文，见 `:61`） |
| 卡片统计（⭐/📥/v 版本） | apps/web/src/views/platform/InstructionMarketView.vue:38-42 | 可删 | `downloads`、`version` 不是接口字段：序列化只返回 id/name/content/visibility/tags/favorite/user_id/created_at/updated_at（apps/services/api-gateway/src/app/gateway_platform_store.py:17-29）→ 恒显示 `📥 0` 与 `vundefined`；`stars` 也不是后端字段（后端是 `favorite`） |
| 「预览」按钮 + 预览弹窗 | apps/web/src/views/platform/InstructionMarketView.vue:44、:58-63 | 必要 | 正文是真实内容，卡片不展示正文 |
| 「使用」按钮 | apps/web/src/views/platform/InstructionMarketView.vue:45 | 必要 | 页面上唯一把模板落到用户身上的动作（当前后端无此路由，见提案 2） |
| 「⭐ 收藏」按钮 | apps/web/src/views/platform/InstructionMarketView.vue:46-48 | 可删 | 只做本地自增（`:115`）+ 假成功提示（`:116`），无接口、无持久化；后端真有 `favorite` 字段却没有收藏接口 |
| 空状态 EnhancedEmpty | apps/web/src/views/platform/InstructionMarketView.vue:54 | 必要 | 空库提示；但请求失败时也会走这条分支（`:99` 静默吞异常），见提案 5 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 加反馈 | apps/web/src/views/platform/CacheManagerView.vue:86、:95、:220-222 | 少一次误操作 | 空输入时按钮当前仍可点：`params` 被条件拼成空对象（`:220-221`），后端把三个空串归一为空（apps/services/api-gateway/src/app/gateway_schemas.py:177-185），`clear_all = not any((corpus_id, question, model_name))` 判真（apps/services/api-gateway/src/app/semantic_cache.py:217）→ **点「失效该知识库缓存」（橙色，非危险色）会静默清空全部缓存，而"清空全部"本身有二次确认**。代价：需要前端 disabled 校验（含纯空格，后端会 strip）+ 复用 `:203` 已有的危险确认文案；禁用态还需一句说明为什么不能点，否则用户会以为是 bug。 |
| 删除 | apps/web/src/views/platform/InstructionMarketView.vue:45（配套 apps/web/src/api/platform.ts:376） | 少一次误操作 | 「使用」是页面唯一实质出口，点下去必得两条错误提示（拦截器 `apps/web/src/api/request.ts:128` 的"请求的资源不存在" + 视图层的"应用失败" `:111`）。代价：删掉后「市场」退化为只读目录，用户看完正文无处可去；恢复必须先补后端 `POST /platform/prompt-templates/{id}/apply`（需要产品决定"应用模板"到底改什么状态）。 |
| 删除 | apps/web/src/views/platform/SceneManagerView.vue:8-20、:66、:76-92 | 少一步 | 一次删掉三个同源元素：标签筛选条（12 标签 × 每标签只命中 1 张卡）、卡片内 prompt 预览、预览弹窗与其中重复的 el-descriptions。代价：若后端将来返回真实长 prompt，被截断的卡片会需要弹窗回来；12 个标签将无处显示（它们对用户目前零判别价值）；删后每张卡只剩 1 个动作，页面变薄——需要接受"6 张卡一屏看完"的极简形态。 |
| 加反馈 | apps/web/src/views/platform/SceneManagerView.vue:67-69、:165-184 | 少一次误操作 | 按钮写着「应用此场景」，实际是 `updateAgentProfile('default', {scene_template_key, name})`：`scene_template_key` 不是任何请求模型的字段（apps/services/api-gateway/src/app/gateway_schemas.py:447-453、:475-481），全仓无 `scene_template` 引用，`scene_templates.py` 已在提交 f7f878d 被物理删除；PATCH 失败则回退 `createAgentProfile`（`:171-178`）——重复点击会重复创建同名 Agent Profile，而提示始终是「已应用场景」（`:180`）。代价：要在 UI 上说真话必须先定义"场景"与"Agent Profile"的关系（是绑定预设还是新建实体）；语义改成"创建/更新 Agent Profile"后按钮的理想形态是需要一个目标选择器（新增一个选择器 → 偿还：删掉本轮提案 3 里的标签条与预览弹窗两个元素）。 |
| 合并 | apps/web/src/views/platform/InstructionMarketView.vue:12-20 | 少一次判断 | 三个控件筛同一份列表：搜索（`:12`）、标签下拉（`:13-15`）、可见性单选（`:16-20`）；其中「私有」因取值不匹配恒为空结果（`:89` vs apps/services/api-gateway/src/app/gateway_schemas.py:405）。代价：只剩搜索后，"只看公共模板"的批量浏览路径消失（需要确认它是否真是浏览习惯）；标签下拉收起后卡片 tags（`:32-36`）成为唯一出口；删 `private` 态需要产品确认是否真的不做"仅自己可见"。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| HIGH | 一致性与 token / 性能 | apps/web/src/views/platform/SceneManagerView.vue:199-201 | 卡片 hover 过渡的是 `border-color` + `box-shadow`：`box-shadow` 不是可合成属性（规则要求只动 transform/opacity）。更实际的问题是 `border-color: var(--blue-400)`（`:200`）引用了**未定义**的变量——全仓无 `--blue-400` 定义（`--blue-600` 才在 apps/web/src/style.css:18）→ 悬停时边框色声明被浏览器丢弃，只剩阴影在变，反馈实际是半失效的 | 悬停只改 `border-color`，色值改用已定义的 `--blue-500`（apps/web/src/style.css:17）或 `--border-strong`（:38）；阴影复用 `--shadow-md` 而非字面量，并把 transition 限定在 `border-color` 上 |
| HIGH | 一致性与 token | apps/web/src/views/platform/InstructionMarketView.vue:126-127 | `.template-card:hover { border-color: ... }` 整段 scoped 样式没有任何 `transition` → 悬停瞬间跳变（突变突兀），且这是全页唯一的悬停反馈；同区另一个卡片列表（SceneManagerView:199）却带 200ms 过渡 | 加 `transition: border-color var(--transition-fast)`（apps/web/src/style.css:46）；色值从 `--el-color-primary` 换成 design token `--blue-500` |
| MEDIUM | 一致性与 token | apps/web/src/views/platform/SceneManagerView.vue:199、:200-201 vs apps/web/src/views/platform/InstructionMarketView.vue:126-127、:134 | 同属 platform 区的两个卡片列表用了两套悬停语言：一个靠阴影（SceneManagerView），一个靠主题色边框且无过渡（InstructionMarketView）；圆角也两套：`--radius-md`（12px，apps/web/src/views/platform/SceneManagerView.vue:199）vs 硬编码 `10px`（apps/web/src/views/platform/InstructionMarketView.vue:126），弹窗内 `pre` 又写 `6px`（`:134`，恰为 `--radius-xs` 的值） | 统一为一个卡片 recipe：`border-color` + `--radius-md` + `--transition-fast`；字面量圆角改回 `--radius-xs` / `--radius-md` |
| MEDIUM | 缺失的机会 | apps/web/src/views/platform/CacheManagerView.vue:14-35 | 5 张 stats 卡在 `v-if="loading"`（`:37`）之外，加载中渲染 5 个真实的 `0`（`:16-33` 全部 `\|\| 0` 兜底），与"缓存确实为空"不可区分；页面唯一的"在加载"信号是下方一个旋转图标 | 加载中让数值位保持占位（不显示 0），或把 stats 纳入同一个加载态分支；不要把 `null` 兜底成看起来有效的数值 |
| LOW | 缓动与时长 | apps/web/src/views/platform/SceneManagerView.vue:199 | 卡片悬停用 `--transition-base`（200ms，apps/web/src/style.css:47）；悬停属高频反馈，token 里已有更合适的 `--transition-fast`（150ms，:46） | 悬停改 `--transition-fast` |

说明：三页均无 `@media (hover: hover) and (pointer: fine)`、无 `prefers-reduced-motion` 局部兜底、无 `transition: all`，与任务书「已知全局问题」一致，此处不重复；上表只记这三页特有的特例。

## 存疑

- **场景模板功能是否还打算存在**：`scene_templates.py` 在提交 `f7f878d`（"Phase 2 L2 物理删除死代码"）中被整文件删除（244 行），`scene_template_key` 在全仓无任何引用，前端 6 个场景的 `system_prompt` 仍是 `'...'` 占位串（`apps/web/src/views/platform/SceneManagerView.vue:126-131`）。我无法从代码判断意图是"接回后端"还是"整页下线"，需要产品确认。验证：`git show --stat f7f878d`；`rg -n "scene_template" apps/`。
- **空输入清空全部的实际后果**：我依据的是前端条件拼参（`apps/web/src/views/platform/CacheManagerView.vue:220-221`）+ 后端默认空串（`apps/services/api-gateway/src/app/gateway_schemas.py:177-185`）+ `clear_all` 判定（`apps/services/api-gateway/src/app/semantic_cache.py:217`）三条静态推断，未实际发请求。验证：起本地服务后 `POST /api/v1/platform/cache/invalidate` 传空 body，比对返回的 `invalidated_count` 与 `/cache/stats` 的 `total_entries`。
- **权限口径不一致**：`/workspace/platform/cache` 前端只要 `chat.use`（`apps/web/src/router/index.ts:276`），但该页的写操作要求 `kb.manage`（`apps/services/api-gateway/src/app/gateway_platform_routes.py:163`，被 `:391`、`:397` 调用），而读操作只要 `chat.use`（`:379`、`:385`）。推论是"只读用户能看到完整可交互的页面，每次写都 403"；需要真实账号确认，且要确认是否还有页面级菜单门控（本次未查导航配置）。
- **「应用此场景」的具体失败表现**：PATCH 到不存在的 profile id `'default'` 时走 `createAgentProfile` 回退（`apps/web/src/views/platform/SceneManagerView.vue:171-178`），但 `createAgentProfile` 未接收 `scene.key`，创建出的 profile 与场景无关联。需要真实请求确认点击一次后 Network 里 PATCH 的状态码、以及 `chat_agent_profiles` 是否新增了行。
- **⭐/📥/v 三个统计位的实际渲染文本**：我推断为 `0 / 0 / vundefined`（依据 apps/services/api-gateway/src/app/gateway_platform_store.py:17-29 的字段列表），未实际渲染确认。
- **el-tag 作为筛选控件的可访问性**：`apps/web/src/views/platform/SceneManagerView.vue:9-18` 用 `@click` + `style="cursor:pointer"` 让 el-tag 承担筛选，我无法从源码判断 Element Plus 是否为其输出 `tabindex`/`role`；需要键盘走查（Tab 能否到达、回车是否触发、焦点环是否可见）。
- **窄屏表现**：三个页面均无任何 `@media` 断点（`apps/web/src/views/platform/` 下只有 ModelProviderView.vue:557 有一处）。`.stats-row` 固定 5 列（`apps/web/src/views/platform/CacheManagerView.vue:239`）、`.cache-layers` 固定 3 列（`:267`）、卡片 grid 最小 340px（`SceneManagerView.vue:197`、`InstructionMarketView.vue:125`），在 <1100px 下的实际换行/溢出情况需要真机确认。
- **未核对的全局样式**：我只对 `apps/web/src/styles/` 下的文件做了定向 grep（悬停守卫、reduced-motion），没有逐行通读；`el-dialog` 的入场时长/缓动是否被某处全局覆盖，我未确认。
