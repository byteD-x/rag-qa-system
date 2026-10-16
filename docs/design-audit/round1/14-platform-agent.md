# 14 Agent 工作台 / Prompt 库

文件：`apps/web/src/views/platform/AgentProfileView.vue`（界面 A，路由 `/workspace/platform/agents`，`apps/web/src/router/index.ts:183-193`）· `apps/web/src/views/platform/PromptTemplateView.vue`（界面 B，路由 `/workspace/platform/prompts`，`apps/web/src/router/index.ts:194-204`）。两个界面同属 `platform-page` 容器模式（各写一份 `.platform-page`/`.platform-content`/`.loading-state`）。

---

## 界面 A：Agent 工作台

### 唯一用户任务
成员在 Agent 工作台，要先用最短路径看清"我有哪些智能体、每个智能体挂载了哪些知识库/能力插件/提示词"，然后就地新建或改动其中一个，让下次问答能直接用上它。

### 完成该任务的必要步骤
1. 看清有哪些智能体（网格卡片）— `apps/web/src/views/platform/AgentProfileView.vue:22-51`（keep）
2. 判断某个智能体挂了什么（知识库/Prompt/插件）— `AgentProfileView.vue:37-48`（keep，但当前只有原始 id 与布尔，见提案 3）
3. 新建一个智能体（名称/描述/人设/插件/知识库/Prompt 六项）— `AgentProfileView.vue:55-94`（keep）
4. 修改已有智能体 — `AgentProfileView.vue:33` + `:154-165`（keep）
5. 删除一个智能体 — `AgentProfileView.vue:34` + `:188-197`（keep）
6. 从卡片读"未启用任何插件"判断这个智能体没有能力 — `AgentProfileView.vue:46`（drop：空数组在运行时会被替换成 3 个默认工具 `search_scope`/`list_scope_documents`/`search_corpus`，`apps/services/api-gateway/src/app/gateway_agent.py:75`，这句文案会给出错误结论）
7. 靠卡片左上角首字母头像识别智能体 — `AgentProfileView.vue:25-27`（drop：字母取名字首字符，与紧邻的 `h3` 同名重复）
8. 从卡片正面确认挂了哪些知识库 — `AgentProfileView.vue:40`（demote：只回答"有没有"，库名要开编辑弹窗才看得到）
9. 用页内大标题「Agent 智能体市场」确认自己在哪个页面 — `AgentProfileView.vue:3`（drop：侧栏与顶栏都叫「Agent 工作台」，这个页内名字是第三个说法）

### 元素清单
| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页内 h1「Agent 智能体市场」 | apps/web/src/views/platform/AgentProfileView.vue:3 | 可删 | 顶栏 h1 取 `route.meta.title`「Agent 工作台」（`apps/web/src/layouts/MainLayout.vue:92,308` + `apps/web/src/router/index.ts:189`）、侧栏也是「Agent 工作台」（`MainLayout.vue:227`），同一屏出现两个不同名字（同屏双 h1 已在全局层报告，本行只记名字不一致） |
| 副标题「管理您的智能体角色、能力插件及知识库挂载」 | AgentProfileView.vue:3 | 必要 | 全页唯一解释"这里能配哪三样"的一句话，与弹窗表单的三块（插件/知识库/Prompt）对应 |
| 「创建智能体」主按钮 | AgentProfileView.vue:5 | 必要 | 唯一创建入口，且 title 里的"市场"没有任何浏览/共享能力支撑（见提案 4） |
| 加载态（`el-icon.is-loading` + 文案） | AgentProfileView.vue:10-13 | 可合并 | 与空态用两套语言；同型手写加载块全仓 17 处（已在全局层报告，不重复计分） |
| 空态 EnhancedEmpty | AgentProfileView.vue:15-20 | 可合并 | 引用共享组件却没用它的 `actions` 槽（`apps/web/src/components/EnhancedEmpty.vue:17-19`），改为"去点右上角"（`:19`），却与页头按钮是同一个动作 |
| `.agent-grid` 网格 | AgentProfileView.vue:22 | 必要 | 列表承载容器，`minmax(320px,1fr)` 自适应 |
| `.agent-card` 卡片壳 | AgentProfileView.vue:23 | 可合并 | 卡片壳 + 内边距样式在约 19 个界面各写一遍（已知全局问题，不重复计分） |
| 首字母头像 `.agent-avatar` | AgentProfileView.vue:25-27 | 可删 | 内容 = 名字首字符（`:26`），与右侧 `h3`（`:29`）同一信息；`background: var(--blue-100)`（`:261`）是全仓 0 处定义的变量 → 色块消失，只剩一个 48px 的蓝色字母（推断，见存疑） |
| 智能体名称 h3 | AgentProfileView.vue:29 | 必要 | 卡片的唯一主标识 |
| 描述行 + 「暂无描述」占位 | AgentProfileView.vue:30 | 可删 | 占位串是空值兜底；`description` 默认空串（`apps/services/api-gateway/database/migrations/006_agent_profiles_and_prompt_templates.sql:17`），空描述行只需消失，不需要一句话解释它为空 |
| 「编辑」按钮 | AgentProfileView.vue:33 | 必要 | 改动智能体的唯一入口（`:154-165`） |
| 「删除」按钮 | AgentProfileView.vue:34 | 必要 | 有二次确认（`:190`），且 `chat_agent_profiles.prompt_template_id` 是 `ON DELETE SET NULL`（迁移 006:21），删除不会连带删模板 |
| 「已绑定 Prompt」布尔标签 | AgentProfileView.vue:39 | 可删 | 只回答"有/没有"，不含模板名；接口已返回完整 `prompt_template` 对象（`apps/services/api-gateway/src/app/gateway_platform_store.py:42,157-159`） |
| 「已挂载知识库」布尔标签 | AgentProfileView.vue:40 | 可删 | 同上，接口已返回 `default_corpus_ids`（`gateway_platform_store.py:40`），且 `bases` 已在同一次加载里拿到（`AgentProfileView.vue:134`） |
| 「启用插件:」小标题 | AgentProfileView.vue:43 | 可删 | 标签本身自明，小标题只占一行（`:312-317` 的样式随之一并消失） |
| 插件标签（渲染原始英文 id） | AgentProfileView.vue:45 | 可合并 | 卡片上直接显示 `search_scope` / `list_scope_documents`（服务端白名单值，`apps/services/api-gateway/src/app/gateway_schemas.py:10`），对应中文名只写在创建弹窗里（`AgentProfileView.vue:71-74`），同一事实两套命名 |
| 「未启用任何插件」 | AgentProfileView.vue:46 | 可删 | 与运行时相反：空 `enabled_tools` 会被替换成 3 个默认工具（`apps/services/api-gateway/src/app/gateway_agent.py:75`） |
| 创建/编辑弹窗 | AgentProfileView.vue:55-94 | 必要 | 唯一承载 6 个字段的编辑面（`:55` 宽 600px） |
| 弹窗 6 个表单项 | AgentProfileView.vue:57-88 | 必要 | 名称/描述/人设/插件/知识库/Prompt，与后端 `AgentProfileRequest` 一一对应（`gateway_schemas.py:447-453`）；插件选项 4 个与白名单完全一致，不缺口 |
| 弹窗底部 取消/保存 | AgentProfileView.vue:91-92 | 必要 | 保存按钮已有 `saving` loading（`:92`），是全页唯一真实的操作反馈 |
| 卡片 hover（边框 + 阴影） | AgentProfileView.vue:243,246-249 | 可删 | 卡片本身不可点（点击无事件，只有 `:33-34` 两个按钮有），hover 给的是假的可点暗示；`border-color` 用全仓 0 处定义的 `--blue-400`，`box-shadow` 用硬编码 `rgba(0,0,0,0.05)` 而非 `--shadow-md` |

统计：必要 11 · 可合并 3 · 可下沉 0 · 可删 8（共 22 行）。

### 提案（<=5 条，按杠杆排序）
| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/views/platform/AgentProfileView.vue:46 | 少一次判断 | 删掉与运行时矛盾的"未启用任何插件"，用户不会再把一个其实带 3 个默认工具的智能体当成"没能力"而重复配置。代价：空插件状态在卡片正面不再有任何文字，用户要开弹窗才知道详情；若想改成"默认插件"文案，则是新增文案元素，偿还物是同时删掉 `:312-317` 的「启用插件:」小标题与 `:43` 这一行 |
| 加反馈 | AgentProfileView.vue:125-139（配合 :15-20） | 少一次误操作 | `loadData` 只有 try/finally 没有 catch，三个并发请求任一失败时 `profiles` 保持 `[]`（`:133`），页面走 v-else-if 显示"暂无智能体"，与"真的一个都没建"不可区分（请求层只给一条 3 秒 toast）；补一个失败态后用户不会误以为自己的智能体被删光。真实代价：要新增"加载失败 + 重试"这一态与文案（可用 `EnhancedEmpty` 现成 `actions` 槽，`apps/web/src/components/EnhancedEmpty.vue:17-19`），并且本页无单测，只能人工回归 |
| 合并 | AgentProfileView.vue:39-40,42-48 | 少一次判断 | 卡片正面三块原始数据（两个布尔标签 + 一串英文工具 id + 一行小标题）合成一行中文事实：能力用弹窗已有的中文名（`:71-74`）、知识库用已加载的 `bases` 名称（`:80,134`）、Prompt 用已返回的模板名（`gateway_platform_store.py:42`）。代价：要做 id→名称映射并处理"库/模板已被删"的回退显示；合并后行数减少但每行更长，扫视速度略降；另外，platform_admin 会看到所有人的智能体（`gateway_platform_store.py:150-153`）而卡片不显示归属人，若要在这条事实行里带上归属，前端需比对 `authStore.user.id`（`apps/web/src/store/auth.ts:5,14`）并复制 admin 例外判断 |
| 删除 | AgentProfileView.vue:3 | 少一次判断 | 删掉页内 h1 后，"这张页面叫什么"只剩侧栏/顶栏一个答案（「Agent 工作台」）。收益不只是去重：标题里的"市场"承诺了浏览/共享，而后端 `chat_agent_profiles` 没有任何 visibility/公开列（迁移 006:13-24），列表对非管理员只返回自己的记录（`gateway_platform_store.py:150-153`）。代价：页头只剩一行 12px 副标题（`:3` 的 subtitle 保留），页面上半部分视觉层级变弱；若要保留标题，就需要同时改文案与副标题（新增改动面），本提案选择删除 |
| 删除 | AgentProfileView.vue:243,246-249 | 少一次误操作 | 卡片不是可点元素，却给了 hover 边框变色 + 阴影浮起 + `transition`，用户会去点卡片；删掉后不再有假的可点暗示，同时消灭一处未定义 token（`--blue-400`）与一处硬编码阴影色。代价：网格里卡片之间的边界不再有动态强调，扫视时更平；此处只给"悬停反馈"这一层信息，删除后无需替代物 |

### 动效发现
| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 缓动与时长 | apps/web/src/views/platform/AgentProfileView.vue:243,246-249 | 卡片是不可点容器（只有 `:33-34` 两个按钮有事件），却有 hover 动效：`transition: box-shadow/border-color var(--transition-base)`（`:243`，200ms 本身在 token 内）动的是 `box-shadow` 这类非合成属性；hover 属"数十次/天"档，规则要求极简或砍掉；`border-color: var(--blue-400)` 的变量全仓 0 处定义，按 CSS 变量未解析时"计算值无效"的规则会落到 `currentColor`（深色）而不是蓝色，`box-shadow: 0 4px 12px rgba(0,0,0,0.05)` 也不等于 `--shadow-md`（`apps/web/src/style.css:51`） | 删掉 `:246-249` 整块 hover 与 `:243` 的 transition（Less is more 第一步）；若产品确实想让卡片可点，应改成"整卡可点 + 一条明确的进入动作"，而不是只补装饰 |
| MEDIUM | 防止突变突兀 | AgentProfileView.vue:10-13 与 :22 互斥，由 :126 的 `loading.value = true` 触发（保存后 :182、删除后 :196） | 任何一次保存/删除都会把整个网格（`v-else` 分支）卸载，换成居中 spinner 再重建；用户点完"保存"看到的是页面被清空又回来，滚动位置与视觉焦点丢失 | 不新增动效：保留旧卡片继续渲染，只在页头/局部给出进行中指示（保存按钮 `:92` 已有 `saving` loading，可复用到删除路径），避免整段卸载重建 |
| LOW | 一致性与 token | AgentProfileView.vue:246-249（对照 apps/web/src/views/platform/PromptTemplateView.vue:219-227） | 同类两个页面（同一 `platform-page` 容器模式）一个卡片有 hover 边框+阴影+transition、另一个完全没有；差异不是能力差，而是两种列表语言 | 以界面 B（无 hover 动效）为基准统一，即在 A 里删除；不要反过来给 B 增加动效 |

### 存疑
- `--blue-400`（`:247`）与 `--blue-100`（`:261`）的实际呈现我未在浏览器实测：依据"自定义属性未解析 → 声明计算值无效 → 非继承属性回落到初始值"，推断 hover 边框会落到 `currentColor`（深色）而头像背景落到 `transparent`。验证：devtools 查看这两处的 computed 值，或全局搜索是否有运行时注入该变量的主题文件。
- "空 `enabled_tools` = 3 个默认工具"是按 `apps/services/api-gateway/src/app/gateway_agent.py:75` 的 `or {...}` 推断的。但该分支只在 Agent 执行链路里被消费（`apps/services/api-gateway/src/app/gateway_chat_service.py:1510-1514`），而 Web 端 `buildScope()` 不发送 `agent_profile_id`（`apps/web/src/store/chat.ts:62-69`），即本页面创建的智能体在当前 Web 端没有任何"选择使用"入口，只有 SDK/API 客户端能带（`sdk/python/rag_qa_client/client.py:77`）。验证：用 SDK 带 `agent_profile_id` 起一次会话，看 trace 里 persona 与工具是否生效；若确实只有 SDK 可达，这个页面的存在价值需要 owner 单独裁决（本报告不据此要求删页）。
- platform_admin 会在列表里看到所有人的智能体（`gateway_platform_store.py:150-153`），卡片不显示归属人，删除确认框（`:190`）也不含归属信息。是否已构成真实的跨人误删风险，取决于当前库里是否真有多人数据（我无法从代码判断）。
- 描述为空的比例、以及"多数用户会留空描述"这一判断，我没有数据支撑，只依据迁移里的 `DEFAULT ''`（迁移 006:17）。
- 本页无单测（`apps/web/src/views/platform/` 下只有 `ModelProviderView.test.ts`），上面所有改动都只能靠人工回归，这是各提案代价里最实际的一项。

---

## 界面 B：Prompt 库

### 唯一用户任务
成员在 Prompt 库，要先用最短路径看清"我有哪些提示词模板、哪条是团队公共的"，然后把其中一条拿去用，或者沉淀/修改一条新的，让提问时不必每次重写。

### 完成该任务的必要步骤
1. 扫读已有模板（名称/可见性/正文/标签）— `apps/web/src/views/platform/PromptTemplateView.vue:23-50`（keep）
2. 新建模板（名称/内容/可见性/标签）— `PromptTemplateView.vue:5` + `:55-84`（keep）
3. 修改自己创建的模板 — `PromptTemplateView.vue:32` + `:131-161`（keep）
4. 删除模板 — `PromptTemplateView.vue:33` + `:172-181`（keep）
5. 收藏/置顶常用模板 — `PromptTemplateView.vue:43-48` + `:163-170`（drop：别人的公共模板点收藏必然 403，`apps/services/api-gateway/src/app/gateway_platform_store.py:74-79`；且唯一效果只是排序（`gateway_platform_store.py:57`），本地还不重排）
6. 判断某条模板能不能改 — `PromptTemplateView.vue:27-29`（merge：卡片只有"公共/个人"，没有归属人，无法判断；接口其实返回了 `user_id`，`gateway_platform_store.py:26`）
7. 读一条模板的完整内容 — `PromptTemplateView.vue:263-266` 截断到 4 行（merge：唯一的全文入口是"编辑"弹窗 `:32` → `:131-140`，读全文被迫进入编辑态）
8. 把一条模板拿去用 — 本页没有这条路径（`getPromptTemplate` 已封装好的单条读取接口 `apps/web/src/api/platform.ts:12` 在本页未使用），落到存疑

### 元素清单
| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 页内 h1「Prompt 模板库」 | apps/web/src/views/platform/PromptTemplateView.vue:3 | 可删 | 顶栏/侧栏都叫「Prompt 库」（`apps/web/src/layouts/MainLayout.vue:232` + `apps/web/src/router/index.ts:200`），页内又多一个名字（同屏双 h1 已在全局层报告） |
| 副标题「管理公共提示词及个人收藏夹」 | PromptTemplateView.vue:3 | 可删 | 承诺了两件不存在的事：没有"收藏夹"视图/筛选（`:43-48` 是唯一入口，效果只有排序 `gateway_platform_store.py:57`），也没有任何共享协作动作，删除它不需要替代物 |
| 「新建模板」主按钮 | PromptTemplateView.vue:5 | 必要 | 唯一创建入口 |
| 加载态（`el-icon.is-loading` + 文案） | PromptTemplateView.vue:10-13 | 可合并 | 同界面 A，与空态两套语言；手写加载块全仓 17 处（已全局报告） |
| 空态 EnhancedEmpty | PromptTemplateView.vue:15-20 | 可合并 | 没用组件已有的 `actions` 槽（`apps/web/src/components/EnhancedEmpty.vue:17-19`），文案是"沉淀您的第一个优质 Prompt 吧"，用户得自己去找右上角 |
| `.template-grid` 网格 | PromptTemplateView.vue:22 | 必要 | 列表承载容器，`minmax(340px,1fr)` |
| `.template-card` 卡片壳 | PromptTemplateView.vue:23 | 必要 | 承载容器；卡片壳样式在约 19 个界面各写一遍（已知全局问题，不重复计分） |
| 模板名 `max-width: 180px` 截断 | PromptTemplateView.vue:26,248 | 可删 | 硬编码 180px 上限，卡片最小宽 340px（`:215`），长名字被截断且没有 `title`/tooltip 兜底，读不到全名 |
| 可见性标签（公共/个人） | PromptTemplateView.vue:27-29 | 必要 | 判断"这条能不能被别人用/我能不能改"的第一个信号，但只有这一个维度（缺归属人） |
| 「编辑」「删除」按钮 | PromptTemplateView.vue:32-33 | 必要 | 自有模板的核心动作；对非本人的公共模板必然失败（`gateway_platform_store.py:74-79`），见提案 1 |
| 正文预览 `tpl-body` | PromptTemplateView.vue:36-38 | 必要 | 扫读模板内容的唯一入口，但被截到 4 行（`:263-266`），见提案 3 |
| 标签组 | PromptTemplateView.vue:40-42 | 必要 | 唯一的分类信息；标签本身不可点、列表也没有按标签筛选（`:73` 允许自建标签，`gateway_platform_store.py:57` 只有 favorite/updated 两种排序） |
| 收藏星（含 toggle 逻辑） | PromptTemplateView.vue:43-48,163-170 | 可删 | 别人的公共模板点它必 403（`gateway_platform_store.py:74-79`）；自己的模板点它只改本地对象（`:166`），排序要到下次进页面才生效（`gateway_platform_store.py:57`）；色值 `#e6a23c`/`#c0c4cc`（`:44`）不在 token（`apps/web/src/style.css:17-24`）。该行同时是已在全局层报告的无障碍问题（不重复计分） |
| 创建/编辑弹窗 | PromptTemplateView.vue:55-84 | 必要 | 唯一承载 4 个字段的编辑面（`:55` 宽 550px） |
| 弹窗 4 个表单项 | PromptTemplateView.vue:57-78 | 必要 | 名称/内容/可见性/标签，与后端 `PromptTemplateRequest` 对应；可见性只有两个值 `private`/`public`（`:67-68`），与列表过滤条件一致（`gateway_platform_store.py:56`） |
| 弹窗底部 取消/保存 | PromptTemplateView.vue:81-82 | 必要 | 保存按钮已有 `saving` loading（`:82`），是全页唯一真实的操作反馈 |

统计：必要 10 · 可合并 2 · 可下沉 0 · 可删 4（共 16 行）。

### 提案（<=5 条，按杠杆排序）
| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 删除 | apps/web/src/views/platform/PromptTemplateView.vue:32-33（判定依据 apps/web/src/store/auth.ts:5,14 + apps/services/api-gateway/src/app/gateway_platform_store.py:74-79） | 少一次误操作 | 列表把"我的私有 + 别人的公共"混在一起返回（`gateway_platform_store.py:52-60`），但卡片只在 `:27-29` 显示公共/个人、不显示归属人，于是"编辑/删除"对别人的公共模板点了必然 403，用户只看到一句"操作失败"式的失败回执，还会怀疑是自己网络问题；按归属人隐藏这两个按钮后，用户不再能点到注定失败的按钮。真实代价：前端要引入 owner 比对并复制后端的 admin 例外（`gateway_platform_store.py:75,78`），逻辑分支增多；别人的公共模板卡片会显得"只读"，这是接受的取舍；platform_admin 仍应保留全部按钮，需要单独判断 |
| 删除 | PromptTemplateView.vue:43-48（连带 :163-170 与 :153 的 `favorite: false`） | 少一次误操作 | 收藏是唯一会给出错误反馈的交互：非本人模板必失败（`gateway_platform_store.py:74-79`），本人模板点完图标立刻变色但列表不重排（`:166` 只改本地对象），"置顶"要到下次进页面才生效（`gateway_platform_store.py:57`），而副标题承诺的"个人收藏夹"根本没有页面；删掉后用户不会再期待一个不存在的收藏夹。真实代价：失去"常用模板置顶"这一排序能力，后端 `favorite` 列与 `ORDER BY favorite DESC` 仍在但无入口写入，需要 owner 决定是否接受"只按更新时间排"；若将来要保留收藏，必须同时补一个可进入的收藏筛选视图，成本显著高于删除。顺带删除的两处硬编码色值与 18px 字号（`:44`）不需要替代物 |
| 合并 | PromptTemplateView.vue:36-38（含 :263-266 的 4 行截断） | 少一次误操作 | 卡片正面只给 4 行预览，读全文的唯一入口是"编辑"弹窗（`:32` → `:131-140`），读一条模板被迫进入带"保存"的编辑语境，手滑即改动线上模板；把预览与"查看全文"合并（放开截断并在卡片内提供只读展开，或让点击卡片进只读详情）后，读与改分离。真实代价：放开截断会让长模板把网格整行拉高（网格同行取最高卡片，`:213-217`），必须同时决定上限或收起策略，这是新的判断与实现成本；只读详情是新增元素，偿还物是删掉的那颗收藏星（同页提案 2），净增 0 |
| 加反馈 | PromptTemplateView.vue:110-118（配合 :15-20、:19） | 少一步 | `loadData` 只有 try/finally 没有 catch，接口失败时 `templates` 保持 `[]`（`:114`），页面显示"暂无模板"并把用户引导去右上角新建（`:19`），与"一条都没建"不可区分；补失败态 + 在空态里直接放"新建模板"动作（复用 `EnhancedEmpty` 的 `actions` 槽，`apps/web/src/components/EnhancedEmpty.vue:17-19`），用户不必先失败再找不到按钮。真实代价：新增"加载失败/重试"状态与文案，空态多一个按钮（偿还物是删掉 `:19` 的指向性描述句，净增 0）；本页无单测，只能人工回归 |
| 删除 | PromptTemplateView.vue:248（配合 :242-249） | 少一次判断 | 名称被硬编码截断在 180px 以内，而卡片最小宽 340px（`:215`），名字相近的两个模板在列表里读出同一个前缀，用户误点误判；删掉上限后名称用满可用宽度（已有 `ellipsis` 与 `min-width:0` 兜底，`:239,245-247`）。真实代价：超长名称仍会被截断，若不补 `title` 兜底依然读不到全名；这项改动只解决"没空间也不给用"的问题，不解决极端长度 |

### 动效发现
| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| MEDIUM | 防止突变突兀 | apps/web/src/views/platform/PromptTemplateView.vue:10-13 与 :22 互斥，由 :111 的 `loading.value = true` 触发（保存后 :157、删除后 :180） | 每次保存/删除都把整个模板网格卸载换成居中 spinner 再重建，内容闪断、滚动位置丢失；与本页"操作后立刻回来"的预期不符 | 不新增动效：保留旧列表继续渲染 + 局部进行中指示（弹窗按钮 `:82` 已有 `saving`，可复用到删除路径），避免整段卸载重建 |
| LOW | 状态指示 / 一致性与 token | PromptTemplateView.vue:44（`el-icon` 收藏星） | 收藏状态靠颜色瞬时替换表达（`#e6a23c` 与 `#c0c4cc`），两个色值都不在 token 表（`apps/web/src/style.css:17-24` 无此色）；瞬时切换本身符合"数十次/天不加动效"的规则，问题在状态表达强度与色值来源，而不是缺少动画 | 随提案 2 删除该交互；若保留，先把色值换成 `--blue-*` 并补可见文案（无 transition 是对的，不要为它加动效） |
| LOW | 一致性与 token | PromptTemplateView.vue:219-227（`.template-card`，对照 apps/web/src/views/platform/AgentProfileView.vue:243,246-249） | 与界面 A 同类卡片不一致：A 有 hover 边框+阴影+transition，本页完全没有；本页没有任何自建动效，属于正确一侧 | 以本页为基准统一（在 A 里删除），不要给本页增加动效 |

### 存疑
- "收藏只影响排序、且本地不重排"是我按 `gateway_platform_store.py:57`（`ORDER BY favorite DESC, updated_at DESC`）与 `:166`（只改本地 `tpl.favorite`）推断的，未在浏览器实测两边行为差异。验证：收藏一条模板后不刷新观察顺序，再刷新页面观察是否跳位。
- 非本人公共模板点"编辑/删除/收藏"的实际表现，我按 `gateway_platform_store.py:74-79` 的 403 与 `:167-169` 的 catch 推断为一条"操作失败"提示；未实测 toast 文案与状态码映射（请求拦截器在 `apps/web/src/api/request.ts`）。
- "拿去用"这条路径在本仓库里我没有找到可用的 Web 入口：本页没有任何读取/复制单条模板的动作，`getPromptTemplate`（`apps/web/src/api/platform.ts:12`）在本页未被调用；后端把模板注入问答的路径存在（`gateway_platform_store.py:277-292` 读 `scope_snapshot.prompt_template_id`），但 Web 端 `buildScope()` 不发送该字段（`apps/web/src/store/chat.ts:62-69`），只有 SDK/API 客户端能带（`sdk/python/rag_qa_client/client.py:77`）；另有一处 `applyPromptTemplate`（`apps/web/src/api/platform.ts:376`）打到 `/platform/prompt-templates/{id}/apply`，我在网关路由里没有找到这个端点（属 `InstructionMarketView` 的问题，不在本报告范围内）。验证：全仓 grep `prompt_template_id` 的写入点 + SDK 实测一次带模板的问答。
- 可见性取值有三套写法：弹窗写 `private`/`public`（`:67-68`），数据库列默认与序列化默认是 `personal`（迁移 006:6、`gateway_platform_store.py:23`），列表过滤只认 `public`（`:56`）。三者当前对得上，但若将来有客户端写入 `personal`，卡片会显示「个人」而弹窗单选组没有对应项（`:136` 回填原值）。我没有找到当前能写入 `personal` 的路径。
- 收藏接口 `PATCH` 会连带把 `visibility`、`tags` 一起重写（`gateway_platform_store.py:113-133` 整行 UPDATE），前端 `toggleFav` 只传 `favorite`（`:165`）所以当前安全；这个"部分更新靠服务端兜底"的耦合是否会被后续调用方破坏，我没有把握。
- 标签是用户自由输入（`:73` allow-create），没有按标签筛选或分组；模板数量到多少条会开始找不到，我没有数据。
- 本页无单测（`apps/web/src/views/platform/` 下只有 `ModelProviderView.test.ts`），所有改动只能人工回归。
