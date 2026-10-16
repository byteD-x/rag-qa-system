# 19 API Key 管理 / Webhook 管理 / PII 脱敏配置

审计对象：`apps/web/src/views/platform/ApiKeyManagerView.vue`（213 行）、`apps/web/src/views/platform/WebhookManagerView.vue`（157 行）、`apps/web/src/views/platform/PiiConfigView.vue`（158 行）

路由：`/workspace/platform/apikeys`、`/workspace/platform/webhooks`、`/workspace/platform/pii`（`apps/web/src/router/index.ts:283-292`、`:294-303`、`:305-314`，三者 `requiresPermission` 均为 `kb.manage`）

审计性质：只读。本文件是本次审计唯一写入的文件。

## 唯一用户任务

平台管理员/集成开发者 在把本系统的问答能力交给外部系统（或按合规要求收紧数据出口）时，需要在同三页内 发放/轮换/撤销 API 凭据、登记并验证回调地址、设定 PII 脱敏口径，且每个动作都必须当场确认「改动生效了、生效范围是我以为的那个」。

三页是同一层「工作台 → 平台配置」下的三件独立事（凭据、回调、脱敏），共性是形态：都是「一页表格/表单 + 一个主操作」，且都属**低频但不可逆**的操作域——这决定了下面所有提案都优先「防误操作」，而不是省点击。

## 完成该任务的必要步骤

### API Key 管理（/workspace/platform/apikeys）

1. 进页面，看清现有 Key 的名称、前缀、权限、配额、状态 —— keep（`apps/web/src/views/platform/ApiKeyManagerView.vue:30-61`）
2. 点「创建 Key」填名称 —— keep（`:5-7`、`:74-76`；名称是后端必填，`apps/services/api-gateway/src/app/gateway_platform_routes.py:564-565`）
3. 选权限 —— keep（`:77-84`；但默认只有 `chat.use` 一个勾，其余 3 项需用户判断，且文案有误，见元素清单）
4. 设 Token 配额与速率上限 —— keep（`:85-90`；后端校验 `rate_limit` 1-600、`quota_tokens` >=0，`gateway_platform_routes.py:573-574`）
5. 提交创建 —— keep（`:94`）
6. **复制明文 Key 并确认已保存，然后才关闭弹窗** —— keep（`:99-105`；`raw_key` 只在创建响应里返回一次，`apps/services/api-gateway/src/app/api_key_manager.py:140`，无二次获取接口，`apps/web/src/api/platform.ts:385-388` 只有 list/create/rotate/revoke）
7. 换代时点「轮换」，立即失效时点「撤销」并确认 —— keep（`:64-65`、`:158`、`:169`；轮换宽限期 24h 与提示文案一致，`api_key_manager.py:78`）
8. 怀疑配额或速率被限时，手动点刷新图标同步 —— **drop**（先删掉这个步骤：`onMounted` 已加载，`:201`；图标无文字无 aria-label，`:8-10`。若确实需要手动同步，应改成一个有标签的动作而不是裸图标）

### Webhook 管理（/workspace/platform/webhooks）

1. 进页面看清已登记的 URL、监听事件、状态 —— keep（`apps/web/src/views/platform/WebhookManagerView.vue:12-26`）
2. 点「注册 Webhook」，填回调 URL —— keep（`:5-7`、`:66-68`；后端强制 http/https，`gateway_platform_routes.py:620-625`）
3. 选监听事件（默认预选 `chat.completed`）—— keep（`:69-76`、`:104`）
4. 可选填 HMAC 签名密钥 —— keep（`:77-79`；有密钥时后端会带 `X-Webhook-Signature`，`apps/services/api-gateway/src/app/webhook_manager.py:264-266`）
5. 提交注册 —— keep（`:84-87`）
6. 点「测试」验证目标服务可达 —— keep（`:32`、`:129-134`）
7. **看投递记录确认刚才那次测试的结果** —— merge（`:42-61`；现在只能靠整页刷新，因为测试后不刷新投递表、返回结果被丢弃，见动效表与提案 1）
8. 临时停收用「停用」，彻底废弃才「删除」—— keep（`:33-36`；但删除当前无任何确认，`:142-146`，见提案 2）
9. 读「重试」列判断这个 webhook 被重试了几次 —— **drop**（该列恒显示 3 次：`retry_count` 是注册时的最大重试配置且注册路径从不传值，`webhook_manager.py:48`、`gateway_platform_routes.py:657`；它不表达任何观测结果）

### PII 脱敏配置（/workspace/platform/pii）

1. 进页面，选默认脱敏策略（部分遮盖/哈希/完全删除/替换为类型标签）—— keep（`apps/web/src/views/platform/PiiConfigView.vue:15-22`；四个值后端都支持，`gateway_platform_routes.py:724-725`）
2. 设遮盖字符 —— demote（`:23-25`；只有「部分遮盖」策略会用到它，`apps/services/api-gateway/src/app/pii_detector.py:248-266` 里 hash/redact/replace 三个分支都不读 `mask_char`，只在 `:269-287` 的 mask 分支用到）
3. 逐个开关不该检测的 PII 类型 —— keep（`:30-41`）
4. 点「保存配置」 —— keep（`:5-7`、`:98-113`）
5. 用一段真实样本在「脱敏测试」里验证 —— merge（`:44-66`；测试只带上当前编辑的 strategy，检测类型与遮盖字符都取服务端已保存值，`gateway_platform_routes.py:757-762`，即"测的不是你眼前这份配置"，见提案 3）
6. 想看某几行的 key/说明区分类型 —— **drop**（`:36` 的类型 tag 与 `:35` 的中文标签重复，且是开发者术语 `id_card`/`license_plate`）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
|---|---|---|---|
| 页面标题「API Key 管理」 | apps/web/src/views/platform/ApiKeyManagerView.vue:3 | 可删 | 与固定顶栏 h1 完全同源同字符串：顶栏渲染 `route.meta.title`（apps/web/src/layouts/MainLayout.vue:92、:308），而该路由的 `title` 就是「API Key 管理」（apps/web/src/router/index.ts:288）；面包屑末项（`:290`）第三次重复同一串 |
| 副标题「创建、轮换、监控…」 | apps/web/src/views/platform/ApiKeyManagerView.vue:3 | 可删 | 描述页面能力，不含任何决策信息；用户到达此处靠左侧导航（MainLayout.vue:297-306）已知道自己在哪 |
| 「创建 Key」主按钮 | apps/web/src/views/platform/ApiKeyManagerView.vue:5-7 | 必要 | 发凭据的唯一入口 |
| 刷新图标按钮（无文字） | apps/web/src/views/platform/ApiKeyManagerView.vue:8-10 | 可合并 | 纯图标、无 aria-label、无 tooltip，且与主操作并排同权重；数据已在 `onMounted` 加载（`:201`），与「创建 Key」同区争夺注意力 |
| 统计行 3 张卡（活跃/已撤销/配额耗尽） | apps/web/src/views/platform/ApiKeyManagerView.vue:15-28 | 可删 | 「活跃 Key」的数值是 `keys.length`（`:17-18`），即**全部** Key，含已撤销与已过期（后端 `list_keys` 不过滤状态，api_key_manager.py:307-317）→ 标签与数值不符；另外两张卡的口径（`:129-130`）都可由表格「状态」列（`:57-61`）与「配额使用」列（`:44-56`）逐行读出的同一份数据聚合而来，属第二次呈现 |
| 表格「名称」列 | apps/web/src/views/platform/ApiKeyManagerView.vue:31 | 必要 | 唯一定位标识 |
| 表格「Key 前缀」列 | apps/web/src/views/platform/ApiKeyManagerView.vue:32-36 | 必要 | 明文不可再取，前缀是用户能对上外部系统配置的唯一线索（前缀生成见 api_key_manager.py:106） |
| 表格「权限」标签列 | apps/web/src/views/platform/ApiKeyManagerView.vue:37-43 | 可合并 | 最多 4 个 tag 挤在 180px 列内且用原始权限码（`chat.use`）显示；权限在创建后不可改，属"建时就该确认"的信息，可下沉到名称列的次要行或 tooltip |
| 表格「配额使用」列（进度条+数值） | apps/web/src/views/platform/ApiKeyManagerView.vue:44-56 | 必要 | 回答"这个 Key 快用完了吗"，是发放后唯一需要持续回看的列 |
| 「无限」标签（配额 0 时） | apps/web/src/views/platform/ApiKeyManagerView.vue:54 | 可删 | 通过本页创建的 Key 永远不会是"无限"：表单写「0=无限」（`:85`）但后端 `create_key` 用 `quota_tokens or DEFAULT_QUOTA_TOKENS` 把 0 换成 100000（api_key_manager.py:111）→ 该分支对本页创建的 Key 不可达，只在"别处造出来的 0 配额 Key"上出现（语义冲突见存疑） |
| 表格「状态」列 | apps/web/src/views/platform/ApiKeyManagerView.vue:57-61 | 必要 | 撤销/轮换后确认生效的唯一位置（映射缺一个状态，见存疑） |
| 表格「操作」列（轮换/撤销） | apps/web/src/views/platform/ApiKeyManagerView.vue:62-67 | 必要 | 生命周期动作的唯一入口；撤销已有确认（`:169`），轮换已有确认（`:158`） |
| 「创建 API Key」对话框 | apps/web/src/views/platform/ApiKeyManagerView.vue:72-96 | 必要 | 主流程容器 |
| 权限复选框组（4 项） | apps/web/src/views/platform/ApiKeyManagerView.vue:78-83 | 必要 | 权限是发放时的必要决策；但 `chat.use` 的显示文案是「问答问答」（`:79`），且后端允许的第 5 个权限 `audit.read`（gateway_platform_routes.py:563；用途见 gateway_runtime.py:13）没有任何入口 |
| 「Token 配额（0=无限）」输入 | apps/web/src/views/platform/ApiKeyManagerView.vue:85-87 | 必要 | 配额决策入口；但标签文案与后端行为不符（见上一行与存疑） |
| 「速率限制（次/分钟）」输入 | apps/web/src/views/platform/ApiKeyManagerView.vue:88-90 | 必要 | 与配额同级的必要上限；范围 1-600 与后端一致（gateway_platform_routes.py:573-574） |
| 「Key 创建成功」对话框 | apps/web/src/views/platform/ApiKeyManagerView.vue:99-105 | 必要 | 明文 Key 的唯一出口（api_key_manager.py:140） |
| 报警 el-alert「关闭后将无法再次查看」 | apps/web/src/views/platform/ApiKeyManagerView.vue:100 | 必要 | 这是本页最贵的一句话；但默认 `close-on-click-modal: true`（依赖内 element-plus/es/components/dialog/src/dialog.mjs:143）让"关闭"可以是一次误触遮罩 |
| 「复制到剪贴板」按钮 | apps/web/src/views/platform/ApiKeyManagerView.vue:103 | 必要 | 把明文带出页面的唯一手段；但 `navigator.clipboard.writeText` 未 await 也未 catch（`:176-179`），失败也会提示「已复制到剪贴板」 |
| 「注册 Webhook」按钮 | apps/web/src/views/platform/WebhookManagerView.vue:5-7 | 必要 | 登记回调的唯一入口（该页无刷新按钮，`:4-8` 的 actions 只有这一个） |
| 页面标题 + 副标题 | apps/web/src/views/platform/WebhookManagerView.vue:3 | 可删 | 同 API Key 页：与顶栏 h1（MainLayout.vue:92 + router/index.ts:299）重复 |
| 表格「回调 URL」列 | apps/web/src/views/platform/WebhookManagerView.vue:13 | 必要 | 唯一定位标识 |
| 表格「监听事件」标签列 | apps/web/src/views/platform/WebhookManagerView.vue:14-18 | 必要 | 回答"这个 hook 会在什么事上被叫醒" |
| 表格「说明」列 | apps/web/src/views/platform/WebhookManagerView.vue:19 | 可下沉 | 可空字段（注册时非必填，`:80-82`），整列常为空占宽；与 URL 同属"这是哪个 hook"，可并入 URL 列的次要行 |
| 表格「状态」列 | apps/web/src/views/platform/WebhookManagerView.vue:20-26 | 必要 | 停用/启用后确认生效 |
| 表格「重试」列 | apps/web/src/views/platform/WebhookManagerView.vue:27-29 | 可删 | 恒为「3次」：`retry_count` 是注册时的最大重试次数配置（webhook_manager.py:48），注册路径从不传该值（gateway_platform_routes.py:657）→ 全表同值、零信息；标签「重试」还会被误读为"已重试 3 次" |
| 表格「操作」列（测试/停用启用/删除） | apps/web/src/views/platform/WebhookManagerView.vue:30-38 | 必要 | 三个动作都挂在真实用户目标上；但「删除」直接执行、无确认（`:142-146`），与同项目 API Key 页的撤销确认（ApiKeyManagerView.vue:169）不一致 |
| 「最近投递记录」卡片 + 表格 | apps/web/src/views/platform/WebhookManagerView.vue:42-61 | 必要 | 验证"外部系统到底收到没有"的唯一位置 |
| 投递表「状态」列（二元映射） | apps/web/src/views/platform/WebhookManagerView.vue:46-52 | 可合并 | `status` 取值域是 pending/success/failed（webhook_manager.py:61），而 UI 把"非 success"一律写成「失败」（`:48-49`）→ 进行中的投递会被报成失败；同时失败原因 `error`（webhook_manager.py:284、:288）无处显示 |
| 投递表「HTTP」「耗时」两列 | apps/web/src/views/platform/WebhookManagerView.vue:53-56 | 可合并 | 两列合计 140px 只承载两个数字，且失败时（连接层错误）HTTP 为 `0`、耗时无意义（webhook_manager.py:285-288）；与状态列合并成"结果"一格更省一次横向扫视 |
| 「注册 Webhook」对话框 | apps/web/src/views/platform/WebhookManagerView.vue:64-88 | 必要 | 主流程容器 |
| 事件多选（4 个事件） | apps/web/src/views/platform/WebhookManagerView.vue:69-76 | 必要 | 回调范围决策 |
| 「密钥（可选）」输入 | apps/web/src/views/platform/WebhookManagerView.vue:77-79 | 必要 | 决定是否给回调签名（webhook_manager.py:264-266）；但保存后不可见也不可改（序列化时 `secret` 被剔除，gateway_platform_routes.py:609；PATCH 只接受 is_active/description/events，`:685`）→ 用户无法知道某个 hook 到底配没配密钥，也无法补配 |
| 「说明」输入 | apps/web/src/views/platform/WebhookManagerView.vue:80-82 | 必要 | 唯一能让 URL 之外的人读懂用途的字段（对应上面可下沉的那一列） |
| 「保存配置」按钮 | apps/web/src/views/platform/PiiConfigView.vue:5-7 | 必要 | 本页所有改动唯一的落地动作；但页面无 dirty 标记、无离开拦截（全文无 beforeRouteLeave，`:71-143`）→ 改完直接切页 = 静默丢弃 |
| 页面标题 + 副标题 | apps/web/src/views/platform/PiiConfigView.vue:3 | 可删 | 同前两页：与顶栏 h1（MainLayout.vue:92 + router/index.ts:310）重复 |
| 「全局脱敏策略」卡片外壳 | apps/web/src/views/platform/PiiConfigView.vue:13-27 | 可删 | 三张 el-card 靠边框+阴影分隔三段，按 Less is more 应先降层级：同页内容用间距/字重已足够区分（仓库已有 `--section-gap` 24px，apps/web/src/style.css:83） |
| 4 个策略单选 | apps/web/src/views/platform/PiiConfigView.vue:16-21 | 必要 | 本页最重的决策，四个值后端全支持（gateway_platform_routes.py:724-725）；示例文案「138****8000」让抽象策略可预期 |
| 「遮盖字符」输入 | apps/web/src/views/platform/PiiConfigView.vue:23-25 | 可下沉 | 只对 mask 策略有效（pii_detector.py:248-266 其余三个分支不读它）；四个策略同权重并列时它是"3/4 情况下无用"的常驻字段 |
| 「检测类型」卡片外壳 | apps/web/src/views/platform/PiiConfigView.vue:30-41 | 可删 | 同上，外壳而非内容 |
| 8 行类型开关（开关+标签+标签码+说明） | apps/web/src/views/platform/PiiConfigView.vue:31-40 | 必要 | 回答"哪些信息要被脱敏"，是脱敏口径的实体；缺 2 个后端存在的类型，见存疑 |
| 类型 tag（phone/id_card…） | apps/web/src/views/platform/PiiConfigView.vue:36 | 可删 | 与 `:35` 的中文名同义，且是开发者标识符；8 行 × 1 个 tag = 8 个纯噪声元素 |
| 「脱敏测试」卡片外壳 | apps/web/src/views/platform/PiiConfigView.vue:44-66 | 可删 | 同上，外壳而非内容 |
| 测试输入 + 「测试脱敏」按钮 | apps/web/src/views/platform/PiiConfigView.vue:45-51 | 必要 | 唯一能在保存前验证效果的手段（但口径不一致，见提案 3） |
| 测试结果区（计数+by_type 标签+脱敏文本） | apps/web/src/views/platform/PiiConfigView.vue:52-65 | 必要 | 对应响应里的 `pii_count` / `by_type` / `sanitized`（pii_detector.py:233-238、gateway_platform_routes.py:762），是验证的落点 |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
|---|---|---|---|
| 加反馈 | apps/web/src/views/platform/ApiKeyManagerView.vue:99-105（配套 :176-179） | 少一次误操作 | 明文 Key 只能看一次（api_key_manager.py:140），但关闭方式有三种且都不设防：点亮「关闭」X、按 ESC、**点遮罩**（依赖默认 `closeOnClickModal: true`，apps/web/node_modules/element-plus/es/components/dialog/src/dialog.mjs:143）。任何一次误触 = Key 永久不可见，只能重建。改法：`:close-on-click-modal="false"` + 复制改为 `await` 并在失败时给错误提示（现在无条件提示「已复制到剪贴板」，`:177-178`）+ 底部加一个「我已保存，关闭」。代价：新增 1 个按钮（等价删除 = 本报告元素清单里三页重复的页面级标题，共 3 个元素，净 -2）；若同时禁掉 ESC 关闭，会与用户对弹窗的肌肉记忆冲突，建议只禁遮罩、保留 ESC。风险：`navigator.clipboard` 在非 HTTPS 环境必然 reject（验证方法见存疑），改后需在 http:// 下复测提示文案是否如实 |
| 加反馈 | apps/web/src/views/platform/WebhookManagerView.vue:36、:142-146 | 少一次误操作 | 「删除」直接调接口且无确认、无撤销（对比 ApiKeyManagerView.vue:169 的撤销有确认）；删除后投递历史也随之消失（后端 `unregister`，gateway_platform_routes.py:691-697），不可恢复。改法与既有习惯对齐：包一层 `ElMessageBox.confirm`。代价：新增 1 次确认交互（等价删除 = 同表「重试」列，元素清单第 27 项，恒为同值零信息，净 -1 元素）。风险：删除是低频动作，确认不会拖慢主流程；但需确认产品是否希望"删除"直接放到停用之后（先停用观察一段时间再删）——若是，则确认文案应引导先停用 |
| 加反馈 | apps/web/src/views/platform/PiiConfigView.vue:122、:51-65 | 少一次判断 | 「测试脱敏」只把 strategy 传下去（`:122`），而检测类型与遮盖字符都取服务端**已保存**的配置（gateway_platform_routes.py:760、:762）→ 用户改了开关或遮盖字符后点击测试，看到的仍是旧口径，容易得出"我配的生效了/没生效"的错误结论。改法二选一：测试按钮旁常驻一句「测试使用已保存配置」，并在有未保存改动时禁用测试或提示先保存；或改后端让测试接受 `enabled_types`/`mask_char`。代价：前者新增一段说明文案与一个 dirty 判断（等价删除 = 同页 8 个类型 tag，元素清单第 41 项，净 -7 元素）；后者是接口行为变更，需同步 `docs/`。风险：若选择"禁用测试直到保存"，会让"先试再定"的探索路径变长一步——这与收益相反，故偏向前者 |
| 删除 | apps/web/src/views/platform/ApiKeyManagerView.vue:15-28 | 少一次判断 | 三张卡里「活跃 Key」展示的是全部 Key 数（`:17-18`），会把已撤销/已过期的 Key 算成活跃 → 用户据此判断"我还有 5 个在用的 Key"，实际可能只有 2 个；另两张卡是对表格同数据的聚合（依据见元素清单）。删除后：状态与配额仍逐行可见（`:44-61`）。代价：失去"一眼看到有几个 Key 配额耗尽"的聚合信号，用户需扫表；配额耗尽在行内仍有红色进度条兜底（`:49` 的 `exception` 态，阈值 90%）。风险：若将来列表变长（>50 行），聚合信号的价值会上升，届时更该做的是筛选器而不是三张卡 |
| 删除 | apps/web/src/views/platform/WebhookManagerView.vue:27-29、:53-56 | 少一次判断 | 一次改动换掉两个零信息元素：「重试」列全表恒为 3（依据见元素清单），「HTTP」「耗时」两列在失败时给出 `0` 和无效数值。把省下的宽度用来显示失败原因 `error`（"HTTP 500" / 连接异常，webhook_manager.py:284-288）——排障时不必再去翻服务端日志，这是"少一步"。代价：`error` 字段目前不在这张表的列里，需要新增一列（等价删除 = 上面的「重试」列 + HTTP/耗时并成一格，净 0 元素）；且后端已把 `error` 存库（webhook_manager.py:302），前端拿得到，无需改接口。风险：错误文本可能很长（异常字符串），需要限宽 + `show-overflow-tooltip`，否则会把表格撑变形 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
|---|---|---|---|---|
| MEDIUM | 性能 / 缓动与时长 | apps/web/src/views/platform/ApiKeyManagerView.vue:47-51（样式来源：依赖内 element-plus/theme-chalk/el-progress.css:1） | 三个页面的唯一自有动效来自组件库的配额进度条：`.el-progress-bar__inner { transition: width .6s ease }` —— 动的是 `width`（布局属性，规则要求只动 transform/opacity），600ms 超过"UI 动效一律 <300ms"，且 `ease` 属被禁的 CSS 预设曲线。表格每行同时有一条这样的过渡（`:44-56` 每行渲染一个 el-progress） | 在这张表作用域内覆盖为 `transition: none`（数据加载时不该做宽度动画）；若想保留"配额变化"的状态指示，改用透明度/颜色这类可合成属性、时长 ≤150ms，并复用 `--transition-fast`（apps/web/src/style.css:46） |
| LOW | 一致性与 token | apps/web/src/views/platform/PiiConfigView.vue:34（样式来源：依赖内 element-plus/theme-chalk/el-switch.css:1） | 8 个开关共用库默认 300ms（`--el-transition-duration`，theme-chalk/index.css:1）。开关切换属"数十次/天"频次，按规则应 ≤150ms；仓库自身有 `--transition-fast: 150ms`（apps/web/src/style.css:46），形成两套时长体系 | 在本页把 el-switch 的过渡覆盖为 `var(--transition-fast)`；不要新增动效，只是把已有的调快 |
| LOW | 一致性与 token | apps/web/src/views/platform/ApiKeyManagerView.vue:72、:99；apps/web/src/views/platform/WebhookManagerView.vue:64（样式来源：依赖内 element-plus/theme-chalk/el-dialog.css:1） | 三页共 3 个弹窗，入场走库默认：遮罩 200ms `ease`、弹窗 300ms。弹窗属"偶尔"频次、300ms 在允许区间（200-500ms），**不要求改**；但遮罩用的 `ease` 是被禁曲线，且与仓库 token 曲线（style.css:46-48）不同源 | 记录为已知库默认即可；若要统一，用仓库 token 覆盖 `--el-transition-duration` 与曲线，不要为这三页新写 keyframes |
| LOW | 缺失的机会 | apps/web/src/views/platform/WebhookManagerView.vue:129-134 | 点「测试」后只有一句 toast：接口返回的投递结果（含 http_status/耗时，gateway_platform_routes.py:669）被直接丢弃，`deliveries` 也不重新加载（`:106-117` 只在挂载时取一次）→ 页面无任何可视变化，用户无法判断"目标服务到底通不通" | 这不是动效问题，是操作反馈缺失：把返回结果写进提示文案（如「测试已发送：HTTP 200 / 128ms」）或把新投递插到记录表首行。不需要动画 |
| LOW | 缺失的机会 | apps/web/src/views/platform/PiiConfigView.vue:52-65 | 测试结果区由 `v-if` 从无到有整块出现（含计数、类型标签、脱敏文本），无任何过渡；属"防止突变突兀"的可选场景 | 结论是**不加**：这是低频、用户主动触发的整块内容揭示，突变不带来误解；若日后有人要加，下限是 opacity 150ms，且不得用位移/缩放 |

说明：三页均无 `transition: all`、无 `:hover` 位移、无 `@keyframes`、无自有 `transition` 声明（对三个文件 grep `transition|animation|hover|@media` 均零命中），与任务书「已知全局问题」一致，此处不重复；上表只记这三页能触达的动效特例。

## 存疑

- **「0=无限」到底哪个才算数**：表单标签写「Token 配额（0=无限）」（`apps/web/src/views/platform/ApiKeyManagerView.vue:85`），但创建时 0 被后端换成默认 100000（`apps/services/api-gateway/src/app/api_key_manager.py:111` 的 `quota_tokens or DEFAULT_QUOTA_TOKENS`），而校验层又把 0 当作无限（同文件 `:201`）。两者对"0"的解释相反，我无法从代码判断哪个是预期语义。验证：建一个 quota_tokens=0 的 Key，看列表「配额使用」列显示进度条（=100K）还是「无限」标签（`:54`）。
- **轮换后的配额继承规则**：轮换把新 Key 的配额设为 `max(旧配额 - 已用, 0)`（`api_key_manager.py:283`），因此"配额已被耗尽的 Key"轮换后会走到上面那条 0 → 100000 的路径，等于换新后拿到一整份新配额；而"还剩一点配额"的 Key 会把这个余量带过去。UI 在轮换时只显示新明文 Key，不提配额（`ApiKeyManagerView.vue:156-165`），用户可能不知道自己刚发出去了多少额度。验证：对一个 tokens_used >= quota_tokens 的 Key 点轮换，对比新旧两行的「配额使用」。
- **轮换是否会丢过期时间**：`create_key` 的 `expires_in_days` 默认为 0（永不过期，`api_key_manager.py:93`、`:113`），`rotate_key` 没有传它（`:279-286`）→ 原本会过期的 Key 轮换后不再过期。需要确认这是有意的还是遗漏。验证：造一个带过期时间的 Key（当前 UI 无入口，需直接调接口或改库），轮换后看 `expires_at`。
- **状态映射缺 `rate_limited`**：本页写了 4 个状态的中文映射（`ApiKeyManagerView.vue:185-193`），但后端 `KeyStatus` 有 5 个值，其中 `RATE_LIMITED` 会在校验时被写回数据库（`api_key_manager.py:42`、`:211`、`:170-172`）→ 触发过限流的 Key 在表格里会显示英文原文 `rate_limited`。另外 `expired` 在 UI 创建路径下不可达（表单没有过期设置，`:73-91`），是"减状态"的候选。验证：把某 Key 的每分钟请求打满，刷新列表看「状态」列文本。
- **PII 类型清单只有 8 个，后端枚举有 10 个**：UI 列了 8 种（`PiiConfigView.vue:83-92`），后端 `PIType` 有 10 种，多出 `address`、`person_name`（`apps/services/api-gateway/src/app/pii_detector.py:34-45`），而默认配置是全部 10 种（`gateway_platform_routes.py:69`、`:711`）。目前 `_rules` 里没有 address/person_name 的检测规则（`pii_detector.py:130-139`），所以二者开关都不影响行为；但从 UI 保存会把已保存的 10 项收敛成 8 项（`:727`），一旦后端补上这两类规则，曾保存过的用户会静默地不检测它们。需要产品确认清单的唯一来源。验证：`GET /api/v1/platform/pii/config` 看 `enabled_types` 长度，再用 UI 保存一次后复查。
- **`.platform-page` 在这三页没有定义**：三个视图的根节点都写 `class="page-shell platform-page"`（`ApiKeyManagerView.vue:2`、`WebhookManagerView.vue:2`、`PiiConfigView.vue:2`），但该 class 只在另外 9 个 platform 视图各自的 scoped style 里定义（如 `CacheManagerView.vue:236-237`），全局样式里没有（`apps/web/src/style.css` 全文只有 `.page-shell`，`:182-191`）；scoped 样式不会跨组件生效，所以这三页拿到的是 `.page-shell`（整页滚动）而不是其他页的"外壳锁定 + 内容区独立滚动 + muted 背景"。预期后果：长表格下页头（含「创建 Key」「保存配置」）会随页面滚走。需要实际渲染确认（真机 / Playwright 截图比对两页的滚动条位置）。全仓 grep 复核：12 个 platform 视图在根节点使用该 class，其中 9 个在自己文件里给出定义且均为 `<style scoped>`（`CacheManagerView.vue:235-236`、`CostDashboardView.vue:199-200`、`SceneManagerView.vue:189-190`、`ModelProviderView.vue:421-422`、`AgentProfileView.vue:204-205`、`AgentMonitorView.vue:347-348`、`ToolManagerView.vue:176-177`、`PromptTemplateView.vue:188-189`、`MemoryManagerView.vue:259-260`），本任务的 3 个视图（`ApiKeyManagerView.vue:204`、`WebhookManagerView.vue:155`、`PiiConfigView.vue:145` 的 `<style scoped>` 里）没有它，且无任何全局定义（`apps/web/src/style.css` 无 `.platform-page`）。验证：`grep -rn "platform-page" apps/web/src` 应只在 `.vue` 内命中。
- **明文 Key 对话框关闭后无法补救**：前端只有 list/create/rotate/revoke 四个接口（`apps/web/src/api/platform.ts:385-388`），后端 `create_key` 明确只返回一次 `raw_key`（`api_key_manager.py:140`）→ 关掉弹窗只能重建。需确认这是有意的安全设计而非"还缺一个再取"的功能。
- **剪贴板失败是否可复现**：`navigator.clipboard.writeText` 未 await/未 catch（`ApiKeyManagerView.vue:176-179`），在非安全上下文（http:// 非 localhost）或权限被拒时会 reject，但页面仍提示「已复制到剪贴板」。验证：以 http:// 访问部署环境，点一次复制，观察提示与剪贴板内容是否一致。
- **el-checkbox 用 label 承载 value 的兼容性**：权限勾选用的是 `label="chat.use"` + 插槽文本（`ApiKeyManagerView.vue:79-82`），在当前依赖版本（element-plus 2.13.3）里这是已弃用写法（依赖内 `es/components/checkbox/src/composables/use-checkbox.mjs:47-56`，replacement 为 `value`，目标版本 3.0.0）；同页另一个 API 用的是新写法（`PiiConfigView.vue:16-21` 的 el-radio `value=`，依赖内 `es/components/radio/src/radio.mjs:36`）。功能是否仍正常、控制台是否报弃用告警，需要浏览器实测。
- **PII 测试的隐私面**：响应里带 `sample_values`（原始 PII 明文，`pii_detector.py:237`），前端没有渲染它（`PiiConfigView.vue:52-65` 只用了 pii_count/by_type/sanitized）；测试文本是否被后端持久化，我无法从前端判断（后端只有一条 debug 日志，且只记类型计数，`pii_detector.py:191`）。需要安全/产品确认这个字段是否该出现在响应里。
