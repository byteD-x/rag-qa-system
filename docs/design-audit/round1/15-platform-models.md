# 15 模型接入

审计对象：`apps/web/src/views/platform/ModelProviderView.vue`（563 行）
路由：`/workspace/platform/models`（`apps/web/src/router/index.ts:206-208`）
审计性质：只读。本文件是本次审计唯一写入的文件。

## 唯一用户任务

运维/研发人员在需要把一个 OpenAI-compatible 中转站接到本系统时，探测该中转站有哪些模型，选定一个，并把可落地的路由配置片段复制到部署环境。

## 完成该任务的必要步骤

1. 打开页面，看当前已生效的 Provider / 模型 / 密钥状态 —— **merge**（`template:16-35` 四张 summary 卡与 `template:190` 配置片段、`template:193-211` 已配置路由表展示同一批事实，唯一性存疑：同一事实在一屏内出现 2–3 次）
2. 填 `Provider 标识` / `Base URL` / `API Key` —— **keep**（`template:83-106`）
3. 点「获取模型列表」，等待返回 —— **keep**（`template:120-123`，状态由 `discovering` 驱动，`script:380-399`）
4. 在返回的模型里选定一个 —— **merge**（`template:151-166` 下拉框与 `template:168-176` 表格是同一份 `models` 的两种呈现，见 `script:254`）
5. 填 `Route Key` / `Fallback Route Key` —— **demote**（`template:108-118` 默认值 `grounded` / `grounded_backup` 已足够，`script:238-239`；仅在部署需要改名时才改）
6. 复制 `配置片段` —— **keep**（`template:181-191`，`script:411-414`）

注：`template:37-59`「已保存模型配置」面板与 `template:61-73` 新增配置弹窗不在上述任务路径上，它是一个独立的配置 CRUD 子流程（读 `/platform/model-configs`，与探测表单的 `discoverLlmModels` 不是同一条链路）。

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 页面标题「模型接入」 | apps/web/src/views/platform/ModelProviderView.vue:3 | 必要 | 定位当前界面 |
| 副标题（发现…并生成部署配置片段） | apps/web/src/views/platform/ModelProviderView.vue:5 | 必要 | 一句话说明本页产出，替代额外帮助文案 |
| 「刷新配置」按钮 | apps/web/src/views/platform/ModelProviderView.vue:8-11 | 必要 | 外部改配置后同步，免刷新页面 |
| summary 卡 1 当前 Provider | apps/web/src/views/platform/ModelProviderView.vue:17-20 | 可合并 | 同值在配置片段 `LLM_PROVIDER=`（:307）出现 |
| summary 卡 2 默认模型 | apps/web/src/views/platform/ModelProviderView.vue:21-24 | 可合并 | 同值在 `LLM_MODEL=`（:310）出现 |
| summary 卡 3 Base URL | apps/web/src/views/platform/ModelProviderView.vue:25-28 | 可合并 | 同值在 `LLM_BASE_URL=`（:308）出现，且探测表单本身就在编辑它（:93） |
| summary 卡 4 密钥状态 | apps/web/src/views/platform/ModelProviderView.vue:29-34 | 可合并 | 同事实在「已配置路由」表 API Key 列（:202-208）已表达 |
| 已保存模型配置 面板 | apps/web/src/views/platform/ModelProviderView.vue:37-59 | 可下沉 | 与探测链路无数据耦合；列表数据来自 `listModelProviderConfigs`（:328-329），探测结果不写入它 |
| 「新增配置」按钮 | apps/web/src/views/platform/ModelProviderView.vue:40 | 可下沉 | 打开 :61 弹窗 |
| 表格列 名称 | apps/web/src/views/platform/ModelProviderView.vue:43 | 必要 | 唯一定位字段 |
| 表格列 提供商 | apps/web/src/views/platform/ModelProviderView.vue:44 | 必要 | 与 :50 密钥列共同判断可用性 |
| 表格列 模型 | apps/web/src/views/platform/ModelProviderView.vue:45 | 必要 | 唯一定位字段 |
| 表格列 默认用途 | apps/web/src/views/platform/ModelProviderView.vue:46-48 | 必要 | 决定该配置在哪个链路被使用 |
| 表格列 密钥（tag + hint） | apps/web/src/views/platform/ModelProviderView.vue:49-51 | 必要 | 停用前判断是否会打断线上（不下发完整密钥，无泄露） |
| 表格列 操作 测试 | apps/web/src/views/platform/ModelProviderView.vue:54 | 必要 | 保存后需要验证可用性（但结果未被读取，见「存疑」） |
| 表格列 操作 停用 | apps/web/src/views/platform/ModelProviderView.vue:55 | 必要 | 唯一的配置下线入口（直接生效、无确认，见提案 1） |
| 新增配置弹窗 | apps/web/src/views/platform/ModelProviderView.vue:61-73 | 可合并 | 字段与探测表单重叠：provider_type（:65）、base_url（:68）、model_name（:66） |
| 弹窗 名称 | apps/web/src/views/platform/ModelProviderView.vue:63 | 必要 | 配置的唯一标识 |
| 弹窗 提供商 + 模型名 form-row | apps/web/src/views/platform/ModelProviderView.vue:64-67 | 必要 | 配置内容本身 |
| 弹窗 Base URL | apps/web/src/views/platform/ModelProviderView.vue:68 | 可合并 | 已在探测表单填写过（:91-97） |
| 弹窗 API Key | apps/web/src/views/platform/ModelProviderView.vue:69 | 必要 | 后端加密保存（:338-353） |
| 弹窗 默认用途 checkbox 组 | apps/web/src/views/platform/ModelProviderView.vue:70 | 必要 | 决定该配置的挂载链路 |
| 弹窗 取消/保存 | apps/web/src/views/platform/ModelProviderView.vue:72 | 必要 | 提交与退出路径 |
| 中转站探测 面板 | apps/web/src/views/platform/ModelProviderView.vue:76-130 | 必要 | 主任务入口 |
| 「不保存密钥」tag | apps/web/src/views/platform/ModelProviderView.vue:79 | 可删 | 与 :126-129「安全边界」段重复表达同一承诺的简化版 |
| Provider 标识（allow-create 下拉） | apps/web/src/views/platform/ModelProviderView.vue:83-89 | 必要 | 决定探测协议 |
| Base URL 输入 | apps/web/src/views/platform/ModelProviderView.vue:91-97 | 必要 | 探测目标 |
| API Key 输入 | apps/web/src/views/platform/ModelProviderView.vue:99-106 | 必要 | 私有中转站的鉴权凭据（提交后清空，见 :397） |
| 「最多返回」数字输入 | apps/web/src/views/platform/ModelProviderView.vue:108-111 | 可删 | 与主任务无关；默认 200（:251）即可，无人知道为何要改 |
| Route Key 输入 | apps/web/src/views/platform/ModelProviderView.vue:112-114 | 可下沉 | 仅改配置片段文本（:280），默认值已可用 |
| Fallback Route Key 输入 | apps/web/src/views/platform/ModelProviderView.vue:116-118 | 可下沉 | 同上（:281-303），低频 |
| 「获取模型列表」按钮 | apps/web/src/views/platform/ModelProviderView.vue:120-123 | 必要 | 主操作 |
| 安全边界说明段 | apps/web/src/views/platform/ModelProviderView.vue:126-129 | 必要 | 说明凭据不被持久化，是填 API Key 前的必要信任交代 |
| 模型列表 面板 | apps/web/src/views/platform/ModelProviderView.vue:132-178 | 必要 | 产出模型清单 |
| 计数「N 个模型」 | apps/web/src/views/platform/ModelProviderView.vue:135 | 必要 | 确认探测是否被截断（受 :110 max_models 影响） |
| 加载态 + 「正在请求中转站 /models...」 | apps/web/src/views/platform/ModelProviderView.vue:138-141 | 可删 | 按钮 loading(`:120`) 已给出同等反馈；`/models` 对用户是内部实现名 |
| 空态 EnhancedEmpty | apps/web/src/views/platform/ModelProviderView.vue:143-148 | 必要 | 捕获「填了 URL 但还没探测」的状态 |
| 模型选择下拉框 | apps/web/src/views/platform/ModelProviderView.vue:151-166 | 可删 | 与 :168 表格同为 `models`（:254）的呈现，是二次入口 |
| 模型表格 | apps/web/src/views/platform/ModelProviderView.vue:168-176 | 必要 | 可扫描列表，行点击即选定（:402-404） |
| 表格列 Owner | apps/web/src/views/platform/ModelProviderView.vue:170 | 可删 | 中转站返回的 owner 恒为转发方（:164 兜底 `unknown`），不区分模型来源 |
| 表格列 Created | apps/web/src/views/platform/ModelProviderView.vue:171-175 | 可删 | 仅日期（:406-409），对「选哪个模型」无决策作用 |
| 配置片段 面板 | apps/web/src/views/platform/ModelProviderView.vue:181-191 | 必要 | 任务最终产出 |
| 「复制」按钮 | apps/web/src/views/platform/ModelProviderView.vue:184-187 | 必要 | 交付动作 |
| `<pre>` 配置片段 | apps/web/src/views/platform/ModelProviderView.vue:190 | 必要 | 产出内容 |
| 已配置路由 面板 | apps/web/src/views/platform/ModelProviderView.vue:193-211 | 可下沉 | 与配置片段同为输出视图；是只读回显，非任务必经 |
| 路由表 Fallback 列 | apps/web/src/views/platform/ModelProviderView.vue:209 | 可删 | 值来自 `fallback_route_key`，配置片段 JSON 已完整包含 |
| 自研样式块（`.panel` / `.panel-header h2` / `.muted`） | apps/web/src/views/platform/ModelProviderView.vue:461-555 | 可合并 | `style.css` 无 `.panel` / `.panel-header` 类（只有 `--bg-panel` 变量），同名类在 apps/web/src/views/interview/InterviewView.vue:149 被独立重写；`.muted`（:534）与全局 `--text-muted` 语义重名；字号用 12/14/15px 字面量而非 `--text-caption` / `--text-body`（:445、:451、:491、:537、:551） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 加反馈 | apps/web/src/views/platform/ModelProviderView.vue:55 | 少一次误操作 | 「停用」是唯一的下线入口且即刻生效：请求成功后本地直接过滤掉该行（:362），列表里再也找不到它，无撤销。加确认会多一次点击；若改为「停用后仍留在列表并置灰」，需后端 `list` 接口继续返回 `enabled=false` 的项（当前前端假定它被移除，`script:362`），属于接口契约变更，须先与后端确认。 |
| 合并 | apps/web/src/views/platform/ModelProviderView.vue:37-59 | 少一步 | 把「已保存模型配置」压进探测流程需要把探测到的模型直接写成 `ModelProviderConfig`（当前 `createModelProviderConfig` 只接受弹窗里的手填字段，`script:338-353`），并要求后端打通两套存储；不打通就只能保留现状。另一个风险：核心用户若本来就是「只维护保存好的配置、从不做探测」，下沉会让他的高频路径变长。 |
| 降层级 | apps/web/src/views/platform/ModelProviderView.vue:16-35 | 少一次判断 | 四张卡在首屏最上方，会让人以为那是本页主内容，而实际主内容是它下方的探测表单。下沉/删除会牺牲「当前生效配置」的一眼可见性；`Base URL` 与 `密钥状态` 是运维排障时的常用事实，若删掉需确认没有别的入口能一眼看到它们（`已配置路由` 表只在 `routeEntries.length > 0` 时才渲染，`:193`，路由为空时这两项事实会彻底消失）。 |
| 删除 | apps/web/src/views/platform/ModelProviderView.vue:151-166 | 少一次判断 | 下拉框与表格同源（`:254`），读者要先判断「该用哪个」。风险：下拉框是键盘可达、可输入筛选的路径，表格 `@row-click`（`:168`）对键盘用户不可达 —— 直接删除会把只靠键盘的用户挡在选模型这一步之外，必须先把行选择补成可聚焦控件，否则不能删。 |
| 删除 | apps/web/src/views/platform/ModelProviderView.vue:184-190 | 少一次误操作 | 未选模型时 `<pre>` 仍渲染 `LLM_MODEL=<select-a-model>`（`:277-278`、`:310`），看起来是一份完整可用的配置；复制按钮虽被 `:disabled`（`:184`），但正文仍可被手选复制。改为未选模型时不渲染正文（或显式标记为占位），代价是失去「先看一眼最终产物长什么样」的可预期性，对首次使用者不利；折中是保留结构但把占位符显式标红。 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| MEDIUM | 目的与频次 / 无障碍 | apps/web/src/components/EnhancedEmpty.vue:108-113（本视图经 apps/web/src/views/platform/ModelProviderView.vue:143-148 触发） | 空态插画（72px 图标容器）带 `transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)`，hover 时 `scale(1.05) rotate(2deg)`。弹性缓动曲线不在允许集合内；且未包在 `@media (hover:hover) and (pointer:fine)` 内，触屏上会留下粘滞 hover 与倾斜姿态。它不是引导/首次成功类愉悦时刻，只是一个静态占位图标。 | 删除该 hover 位移与缩放；若要保留反馈，仅保留容器 border/背景的 color 过渡，并包进 `@media (hover:hover) and (pointer:fine)`。 |
| LOW | 缓动与时长 | apps/web/src/components/EnhancedEmpty.vue:108 | 时长 0.3s（300ms）未使用既有 token（`--transition-fast/base/smooth` = 150/200/250ms），是 token 外的第三套时长刻度。 | 若保留动效则改用 `--transition-base`；本项目当前 `prefers-reduced-motion` 是用通配符整体清零（apps/web/src/style.css:806-815），所以删动效不额外欠无障碍债。 |
| LOW | 缺失的机会 | apps/web/src/views/platform/ModelProviderView.vue:138-148 | `discovering`（`:380`）驱动的三态（加载 / 空 / 结果）之间是硬切换：`:138` 的 `v-if`、`:144` 的 `v-else-if`、`:150` 的 `v-else` 没有任何过渡。加载态出现/消失属于「防止突变突兀」，是允许动效的少数场景之一。 | 只对加载态容器加 opacity 过渡（150–200ms，token 内），不动尺寸；不要从 scale(0) 起。 |
| LOW | 一致性与 token | apps/web/src/views/platform/ModelProviderView.vue:421-562（scoped `<style>` 全文） | 本视图自身零 `transition` / `animation` 声明（全文仅 `:557` 一个 `@media`），所有交互动效都来自 Element Plus 默认值与 `EnhancedEmpty`。这意味着本视图的动效基调完全由外部决定，无法在本文件内统一。 | 无需新增；相反，本视图是本轮里「动效最少」的样板，保持现状即可，不要为了「一致性」引入新动效。 |

## 存疑

- **「测试」按钮的结果从未被读取。** `testSavedConfig`（`apps/web/src/views/platform/ModelProviderView.vue:355-358`）只 `await` 请求，请求一 resolve 就 `ElMessage.success('连接测试成功')`，响应体没有参与判断。若后端 `/platform/model-configs/{id}/test` 在 HTTP 200 下返回 `{success:false}` 这类失败结果，UI 会说谎。验证方法：查 `apps/api-gateway` 中该路由的实现，确认失败时是否用非 2xx 状态码；只有确认后才有资格谈要不要读 payload。
- **`discoverModels` 静默重探测的反馈缺口。** `loadConfig` 在 `form.base_url` 有值时以 `silent=true` 调 `discoverModels`（`apps/web/src/views/platform/ModelProviderView.vue:330-332`），此时 `:371`、`:376`、`:395` 三处用户提示全部被静默，而 `discovering` 只驱动 `:138` 的加载块（在结果面板内）。刷新期间页面是否有可见忙碌指示，需实际渲染确认。
- **API Key 在每次请求后被清空，第二次探测改用后端已存密钥。** `finally` 中 `form.credential = ''`（`apps/web/src/views/platform/ModelProviderView.vue:397`）；此后 `:387` 的 `...(credentialValue ? {...} : {})` 不再带密钥，探测会回落到 `config.value?.api_key_configured` 判定的后端环境变量密钥（`:375`）。这是有意的还是副作用无法从代码判定；若中转站被换过密钥，用户会看到「用 A 成功、用 A 重试却报鉴权失败」的费解现象。需确认真机行为。
- **计数与表格可能不同源。** 成功提示（`已获取 ${payload.count || 0} 个模型`，`apps/web/src/views/platform/ModelProviderView.vue:395`）与面板标题计数（`:135`）都读 `payload.count`，而表格渲染的是 `payload.models`（`:254`、`:168`）。两者若不一致（例如被 `max_models` 截断），到底哪个是真实返回数需确认。
- **「已保存模型配置」面板的初始空态。** `modelConfigs` 初始为 `[]`（`:242`），`listModelProviderConfigs` 又被 `.catch(() => ({items:[]}))` 兜住（`:328`），所以接口失败与真的没配置在 UI 上完全一致 —— 都会渲染成一张空表且无任何提示。是否要区分，需产品确认。
- **`LlmModelDiscoveryPayload` 的密钥字段名。** 前端用 `['api_' + 'key']` 拼出字段名发送（`apps/web/src/views/platform/ModelProviderView.vue:387`），但类型声明里写的是 `api_key`（`apps/web/src/api/platform.ts:88`）。两者一致，但拼接写法让静态检查失效；这里只登记事实，不猜测原因。
- **下拉框显示值与内部 `form.provider` 会脱节。** `inferProviderFromUrl`（`:266-274`）能推断出 `ollama`/`lmstudio`/`deepseek`/`dashscope`（`:269-271`），但 `:85-87` 只列了 `openai-compatible`/`newapi`/`sub2api` 三个 option。推断出的 provider 只写进 `form.provider`（`:368`、`:394`），而 `el-select` 绑定同一个 `form.provider`（`:84`）—— 由于下拉是 `allow-create`，这种情况下没匹配 option 时显示什么，需实际渲染确认；不能仅凭代码断言它会显示为空。
- **未验证的渲染依赖。** `el-table height="280"`（`:168`）在结果面板内固定高度，与 `provider-layout` 的 `align-items: start`（`:465`）叠加后，窄屏（`:557` 的 `@media (max-width: 1100px)` 断点以下）两栏是否会产生双滚动条，需要真机确认。
- **`EnhancedEmpty` 的跨界面复用面。** 它在 20+ 个视图被引用（含 `views/kb/KBDocumentView.vue` 单文件 8 处），因此上面那条 hover 动效发现不是本视图的局部问题，已在返回摘要的 `systemic_candidates` 中登记。
- **字号字面量是跨界面模式，不是本视图特例。** 本视图 5 处字号用 px 字面量（`:445`、`:451`、`:491`、`:537`、`:551`），与 `--text-caption` / `--text-body` 数值部分重合、部分不符（`--text-body` = 0.9375rem = 15px，而 `:451` 用 14px，两者都不等于任何 token）。全仓 `apps/web/src/views/**/*.vue` 中有 25 个文件命中 `font-size: 12-15px`，已登记进 `systemic_candidates`。**是否应统一到 token 属于跨界面的全局决策，本视图不宜单方面改**，故此处只登记，不进入提案。
