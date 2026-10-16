# 02 登录 / 注册 / 找回密码 / 无权限

审计范围：`apps/web/src/layouts/AuthLayout.vue`、`apps/web/src/views/LoginView.vue`、`RegisterView.vue`、`PasswordResetView.vue`、`AccessDeniedView.vue`、`loginPresets.ts`；路由 `/login`、`/register`、`/password-reset`、`/workspace/forbidden`（apps/web/src/router/index.ts:14-42,64-73）。
本轮只读，未修改任何源码。

## 唯一用户任务

一个已有账号的企业成员或管理员，在打开工作台（或会话过期被弹回、或被权限拦下）时，要用尽量少的输入进入工作台并回到他原本要访问的那一页。

## 完成该任务的必要步骤

1. 打开 `/login`，邮箱被浏览器自动填充或手动输入 → **keep**（`autocomplete="username"`，LoginView.vue:20）
2. 输入密码 → **keep**（`autocomplete="current-password"`，LoginView.vue:33）
3. 回车或点「进入工作台」提交 → **keep**（LoginView.vue:12,40）
4. 失败时读到原因并重试 → **keep**（401 文案由请求层给出，api/request.ts:86-89）
5. 成功后回到 `redirect` 指定的原页面 → **keep**（LoginView.vue:140-141）
6. 分支：没有账号 → 去注册 → 邮箱/密码/部门 → 自动进入工作台 → **merge**（`department` 是承重字段，但标签写「可选」，见提案 5）
7. 分支：忘记密码 → 申请令牌 → 从邮件复制令牌 → 粘贴令牌 + 新密码 → 回登录页 → **merge**（这条路径目前走不完，见提案 1）
8. 分支：被权限拦下 → 弄清缺什么 → 返回工作台 → **drop**（「403」大字与「请求页面」行对动作零贡献，见提案 3）

## 元素清单

| 元素 | 位置 | 标签 | 依据 |
| --- | --- | --- | --- |
| 左侧展示栏（左半屏） | apps/web/src/layouts/AuthLayout.vue:3 | 必要 | 桌面端唯一的产品标识；`<900px` 整块隐藏（AuthLayout.vue:150-152），删掉则小屏彻底没有品牌信息 |
| 品牌图标块 56×56 | apps/web/src/layouts/AuthLayout.vue:6 | 可删 | 纯装饰；色值硬编码 `rgba(59,130,246,.15/.3)`、`#93c5fd`（AuthLayout.vue:78-80），不在 token 内也不随主题切换；同款图标已存在于 MainLayout.vue:8-10 |
| 产品名 + 定位句 | apps/web/src/layouts/AuthLayout.vue:9-13 | 必要 | 回答「我打开的是不是正确的系统」 |
| 三条能力列表（含 3 个 feature-dot） | apps/web/src/layouts/AuthLayout.vue:14-27 | 可删 | 与「进入工作台」无因果关系；来访者已经有账号；三个圆点（AuthLayout.vue:113-119）是纯装饰 |
| 右侧表单栏 | apps/web/src/layouts/AuthLayout.vue:31 | 必要 | 承载全部任务动作 |
| 表单卡片面（padding+边框+阴影+圆角） | apps/web/src/layouts/AuthLayout.vue:129-138 | 可下沉 | 一层内容套一层容器；栏与栏之间已由整屏分区区分（Less is more 第 2 步：能用对齐/间距表达的，不用边框/背景/阴影） |
| 卡片 hover 阴影与描边 | apps/web/src/layouts/AuthLayout.vue:140-143 | 可删 | 宿主元素不可点击；动的是 `box-shadow`/`border-color`（非 transform/opacity）；未包在 `@media (hover:hover) and (pointer:fine)` 内 |
| 标题「登录」 | apps/web/src/views/LoginView.vue:3 | 必要 | 全页唯一可见标题（页面里唯一的 `<h1>` 在被 `aria-hidden` 的展示栏内，AuthLayout.vue:3,10） |
| 副标题「使用企业账号或演示账号登录工作台」 | apps/web/src/views/LoginView.vue:4 | 可删 | 删掉演示区后，它只在说「登录页可以用来登录」 |
| 邮箱字段（label + 输入 + 前缀图标） | apps/web/src/views/LoginView.vue:14-24 | 必要 | 任务的第一个输入 |
| 前缀图标 `Message` | apps/web/src/views/LoginView.vue:19 | 可删 | label 已写明字段含义，图标不承载信息 |
| 密码字段（label + 输入 + `show-password`） | apps/web/src/views/LoginView.vue:26-37 | 必要 | `show-password` 让用户能核对自己输入，少一次误操作 |
| 前缀图标 `Lock` | apps/web/src/views/LoginView.vue:31 | 可删 | 同「前缀图标 Message」 |
| 「进入工作台」按钮 | apps/web/src/views/LoginView.vue:39-43 | 必要 | `loading` 期间按钮真被 disabled，不存在重复提交（`apps/web/node_modules/element-plus/es/components/button/src/use-button.mjs:63-64`） |
| 注册 / 忘记密码 两个链接 | apps/web/src/views/LoginView.vue:46-49 | 必要 | 两条真实分支；登录后回跳由 LoginView.vue:140-141 保证 |
| 「演示账号」标签 | apps/web/src/views/LoginView.vue:52 | 可删 | 服务演示场景，不挂在「员工登录」这个目标上 |
| 管理员一键填充按钮 | apps/web/src/views/LoginView.vue:54-63 | 可删 | 把口令直接写进输入框；与「成员」用同一个 `User` 图标（LoginView.vue:60,70），两按钮无法靠图标区分 |
| 成员一键填充按钮 | apps/web/src/views/LoginView.vue:64-73 | 可删 | 同上 |
| 明文口令提示行 | apps/web/src/views/LoginView.vue:75 | 可删 | 口令原文渲染在页面上（LoginView.vue:102-110）；值来自 `VITE_DEMO_*` 或内置默认（loginPresets.ts:13-16,22-33） |
| 标题「注册账号」 | apps/web/src/views/RegisterView.vue:3 | 必要 | 唯一标题；字号走浏览器默认（RegisterView.vue:48 未设 `font-size`） |
| 副标题（注册能带来什么） | apps/web/src/views/RegisterView.vue:4 | 必要 | 回答「为什么要注册」；也是密码规则最省成本的挂载点 |
| 邮箱字段 | apps/web/src/views/RegisterView.vue:6 | 必要 | — |
| 密码字段 | apps/web/src/views/RegisterView.vue:7 | 必要 | 客户端只校验 `min: 8`（RegisterView.vue:29），后端另要求字母+数字（apps/services/api-gateway/src/app/gateway_schemas.py:42-43） |
| 部门（可选）字段 | apps/web/src/views/RegisterView.vue:8 | 必要 | 该字段决定检索可见范围（apps/services/knowledge-base/src/app/retrieve.py:632-643、kb_resource_store.py:44-53），「可选」与后果不符 |
| 「注册并进入工作台」按钮 | apps/web/src/views/RegisterView.vue:9 | 必要 | 注册后直接进工作台，少一步 |
| 返回登录链接 | apps/web/src/views/RegisterView.vue:11 | 必要 | — |
| 标题「找回密码」 | apps/web/src/views/PasswordResetView.vue:3 | 必要 | 唯一标题 |
| 副标题「输入注册邮箱获取一次性重置链接。」 | apps/web/src/views/PasswordResetView.vue:4 | 必要 | 但文案与事实不符：邮件给的是令牌，链接本身不带令牌（apps/services/api-gateway/src/app/auth_store.py:122） |
| 邮箱字段 | apps/web/src/views/PasswordResetView.vue:6 | 必要 | — |
| 「发送重置链接」按钮 | apps/web/src/views/PasswordResetView.vue:7 | 必要 | — |
| 重置令牌字段 | apps/web/src/views/PasswordResetView.vue:10 | 必要 | 生产环境下只有它能让用户完成重置；当前该分支不可达（PasswordResetView.vue:5,40-42） |
| 新密码字段 | apps/web/src/views/PasswordResetView.vue:11 | 必要 | — |
| 「更新密码」按钮 | apps/web/src/views/PasswordResetView.vue:12 | 必要 | — |
| 返回登录链接 | apps/web/src/views/PasswordResetView.vue:14 | 必要 | — |
| 「403」大字 | apps/web/src/views/AccessDeniedView.vue:4 | 可删 | 状态码是给工程师看的；它是页面上最重的元素（48px，AccessDeniedView.vue:49）却不指向任何动作 |
| 标题「没有访问权限」 | apps/web/src/views/AccessDeniedView.vue:5 | 必要 | 结论本身 |
| 说明句「当前账号无法访问此页面。」 | apps/web/src/views/AccessDeniedView.vue:6 | 必要 | 唯一的解释 |
| 「所需权限：xxx」 | apps/web/src/views/AccessDeniedView.vue:7 | 可合并 | 对报障/申请权限有用，可并入上一句而不是独占一行 |
| 「请求页面：xxx」 | apps/web/src/views/AccessDeniedView.vue:8 | 可删 | 用户刚从那页被弹回来，该信息不产生任何动作 |
| 「返回工作台」按钮 | apps/web/src/views/AccessDeniedView.vue:9-11 | 必要 | 唯一出口，且 `/workspace/entry` 无权限门槛（router/index.ts:54-63） |

## 提案（<=5 条，按杠杆排序）

| 动作 | 位置 | 用户收益 | 代价与风险 |
| --- | --- | --- | --- |
| 加反馈 | apps/web/src/views/PasswordResetView.vue:5,9,40-42（配套改 :4 文案） | 少一步 | **这是功能性死路，不只是体验问题**：`token` 只有请求响应用 `reset_token` 时才被赋值（PasswordResetView.vue:40-42），而该字段只在 `APP_ENV` 属于 dev/development/local/test 时才返回（gateway_auth_routes.py:54-57）；生产环境改为发邮件，邮件正文是令牌、链接是 `/password-reset` 且不带令牌（auth_store.py:117-122）。用户点邮件链接回来后 `token` 仍为空，`v-if="!token"` 又显示申请表单（PasswordResetView.vue:5），重置流程走不完。建议：请求成功后无条件推进到「令牌+新密码」这一步，令牌只在返回时预填。代价：多一个步骤状态的确切定义；「邮箱不存在」与「已发送」后端目前统一返回 `accepted`（gateway_auth_routes.py:53），无法区分，会把没收到邮件的人也推进到令牌页——但那正是他们实际所处的状态。需在 `APP_ENV` 为生产值的环境真机跑一遍确认 |
| 删除 | apps/web/src/views/LoginView.vue:51-76（配套删 CSS :203-279） | 少一次判断 | 消除「我该点管理员还是成员、口令是什么」的判断，以及把口令明文渲染在登录页的暴露面（LoginView.vue:75；口令来源 loginPresets.ts:13-16,22-33）。真实代价：演示/验收流程需要一个可复述的账号；`loginPresets.ts` 与 `loginPresets.test.ts` 目前只被 LoginView.vue:87 引用，删除后需一并决定其去留；副标题（LoginView.vue:4）提到的「演示账号」必须同步改写。若 Owner 判定演示入口必须保留，退路是仅在非生产构建渲染并停止明文展示口令——但这需要新增构建期判断，届时必须偿还等价元素 |
| 删除 | apps/web/src/views/AccessDeniedView.vue:4,8（配套删 CSS :47-51,:63-66），:7 并入 :6 | 少一次判断 | 页面收敛为「一句结论 + 一个按钮」，用户不必去理解 403 编号与内部路径的含义。真实代价：截图报障时少一条路径线索；「所需权限」保留但降为从句后，管理员口述权限名仍可行。测试不受影响：AccessDeniedView.test.ts:23-27 只断言标题、「kb.manage」与按钮 |
| 降层级 | apps/web/src/layouts/AuthLayout.vue:129-138（连带 :137,:140-143） | 少一次误操作 | 删掉卡片边框/阴影/圆角与 hover，只留间距与对齐；同时消除「可点」的假反馈。真实代价：表单失去可见边界，在宽屏上要与左侧深色栏竞争视线；我无法只靠读代码判断视觉是否发散，必须先渲染确认（浅色与深色各一次）；若确认发散，则退一步只删 hover 与 `transition`（AuthLayout.vue:137,140-143），保留卡片面 |
| 加反馈 | apps/web/src/views/RegisterView.vue:8（部门标签）、:4 或 :7（密码规则） | 少一次误操作 | 部门填错/留空的后果是「检索结果里看不到本部门文档」（retrieve.py:632-643），而不是一条报错——用户只会认为系统不好用；建议把标签「部门（可选）」改成能说明后果的说法。密码规则同理：客户端只判 `min: 8`（RegisterView.vue:29），后端还会以 400 拒绝纯数字密码（gateway_schemas.py:42-43）。**这两处都用改写现有文案完成，不新增元素，所以无需偿还。** 真实代价：文案变长会把「可选」的轻松感变成必填压力，要看实际观感；「部门」是否需要（而不是由管理员/目录系统分配）是产品决策，见存疑 |

## 动效发现

| 严重度 | 类别 | 位置 | 发现 | 修复方向 |
| --- | --- | --- | --- | --- |
| HIGH | 目的与频次 / 性能 / 无障碍 | apps/web/src/layouts/AuthLayout.vue:137,140-143 | 全界面唯一的动效是给一张不可点击的卡片加了 hover 阴影+描边，200ms。三个问题叠在一起：① 指针在整个填表过程中都停在卡片上方，「悬停态」实际就是常态，这个反馈不报告任何信息；② 动的是 `box-shadow`/`border-color`，不是 transform/opacity，会触发重绘；③ 未包在 `@media (hover:hover) and (pointer:fine)` 内，触屏上点击后阴影会粘住。注：这是「非位移版」的悬停问题，与全局已知的「`:hover` 位移未包媒体查询」不是同一处代码，故在此单列 | 直接删除 `:hover` 块与 `transition` 声明（AuthLayout.vue:137,140-143）。删除后本界面为零动效——这与「登录页属于低频、且不需要任何动效」的判定一致；不要在 auth 三页新增过渡来「统一」 |
| MEDIUM | 状态指示 / 缺失的机会 | apps/web/src/views/PasswordResetView.vue:5,9,43 | 两步之间的切换只靠一条 toast（:43）和整块表单的瞬间替换：申请成功后字段从 1 个变成 2 个，标题和副标题（:3-4）却完全没变，用户无法从页面上确认「我进入下一步了」；令牌确认成功后又把 `token` 清空（:56），表单跳回申请状态，与新密码已生效的事实相反 | 让 `:3`/`:4` 两行文本随步骤变化（复用现有元素，不新增），而不是加动效；成功后在 `:56` 之后跳转 `/login`，与 toast 文案「请重新登录」一致，少一步 |
| LOW | 一致性与 token | apps/web/src/views/AccessDeniedView.vue:49,55,65；apps/web/src/layouts/AuthLayout.vue:85；apps/web/src/views/LoginView.vue:159,197,285 | 同一批文件里用了 48px/24px/13px/1.5rem/1rem 等现有 4 级字号刻度（style.css:31-35：22/18/15/12px）之外的尺寸；`h2` 在 RegisterView.vue:48 与 PasswordResetView.vue:64 未设字号，实际是浏览器默认 24px，而 LoginView.vue:159 用了 `--text-h1`=22px —— 同一个布局里三个标题三个字号。另有 `var(--text-caption, 0.8125rem)` 这种与 token 值（0.75rem）不一致的兜底（LoginView.vue:285） | 标题统一走 `--text-h1`；`403` 大字随提案 3 一并删除；兜底值改为与 token 一致的 `0.75rem` 或直接去掉兜底 |
| LOW | 一致性与 token | apps/web/src/layouts/AuthLayout.vue:56-57,78-80,93,109,117 | 展示栏整块用硬编码色（`#111827`、`#fff`、`rgba(255,255,255,.7/.88)`、`rgba(59,130,246,…)`、`#93c5fd`），这些色不参与主题切换（切换只改变量，utils/theme.ts:11-35）。深色模式下 `--bg-page` 为 `#0c1222`（theme.ts:13）、`--bg-panel` 为 `#131b2e`（theme.ts:14），与硬编码的 `#111827` 已经非常接近，左右分栏的层次只剩卡片边框在区分 | 若要保留展示栏，改用现有变量表达层次；若不保留，随提案 4 一并处理。渲染一次浅色/深色即可确认层次是否真的消失 |

## 存疑

- `PasswordResetView` 的生产死路基于代码路径判断（PasswordResetView.vue:5,40-42 + gateway_auth_routes.py:54-57 + auth_store.py:117-122），未实际部署验证。验证方法：以 `APP_ENV=production` 启动 api-gateway，走一遍 `/password-reset`，确认响应体不含 `reset_token` 后，页面是否仍停在申请表单。
- 邮件链接不带令牌（auth_store.py:122 只给了 `{app_url}/password-reset`）。用户要手工从邮件正文复制令牌。是否改成把令牌放进链接（涉及后端改动与安全权衡）是产品决策，不在本次前端审计范围。
- `RegisterView.vue:33` 与 `PasswordResetView.vue:51` 使用 `await formRef.value?.validate()` 无回调形式，校验失败时 Element Plus 会 reject，这两处没有 catch，理论上会产生未处理的 Promise rejection（用户仍能看到字段级报错）。验证方法：`cd apps/web && npm run test:unit` 或对这两页写一个「空表单提交」的用例，看控制台是否出现 unhandled rejection。
- `LoginView.vue:12` 用 `@keyup.enter`，而 RegisterView.vue:5 / PasswordResetView.vue:5 用 `@submit.prevent` + `native-type="submit"`（RegisterView.vue:9）。两套机制都可用，但手机软键盘的「前往」键是否同样触发登录，需要真机确认。
- 部门字段由注册者自己填写，而它决定检索时的文档可见范围（retrieve.py:632-643）。自助声明权限范围是否可接受，需要产品/安全确认；另外我在前端只找到会话中推断部门的逻辑（apps/services/api-gateway/src/app/user_profile.py:201-202），没找到用户事后修改部门的界面，需要确认改部门走什么流程。
- `loginPresets.ts:13-16` 内置了一组默认演示口令（值不在本报告转述）。它随前端打包进入产物；是否需要确认构建产物中确实包含、以及是否属于可接受风险，需要 Owner 判断。验证方法：检查 `apps/web/dist` 的产物内容。
- 深色模式下左右两栏是否真的分不开（AuthLayout.vue:56 的 `#111827` vs theme.ts:13 的 `#0c1222`），我只做了数值比较，需要实际渲染并取色确认。
- `AccessDeniedView.vue:32-36` 用 `.page-shell`（style.css:182-191，`height:100%` + `overflow-y:auto`）再叠 `justify-content: center`。当内容（例如长路径被 `overflow-wrap` 折行，AccessDeniedView.vue:63-66）超过可视高度时，flex 居中会把内容顶部推到滚动区之外。需要在一个很矮的视口里实际渲染确认。
- 本界面内未发现满足「5 个以上界面重复出现」且不在已知清单里的模式，因此系统性候选只提交了 1 条跨面证据（见返回 JSON）。建议与其他审计面交叉确认后再归并。
