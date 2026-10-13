# 修复验证记录（2026-10-13）

## 已验证

- `python -m compileall -q apps/services/api-gateway/src packages/python/shared`：通过。
- `python scripts/quality/check-encoding.py --root .`：通过，1431 个文件。
- `docker compose config --quiet`：通过。
- `cd apps/web && npm run test:unit`：通过，24 个测试文件、44 个测试。
- `cd apps/web && npm run build`：通过。
- `docker compose --profile init run --rm stack-init`：通过，已应用 `013_platform_resources.sql`。
- Docker Gateway `/readyz`：`status=ready`，数据库、KB Service、向量库和 LLM 检查均正常。
- Docker HTTP 链路：注册、登录、密码重置、API Key 创建/轮换/撤销、Webhook 注册/测试投递记录、PII 配置、A/B 实验创建/报告均已实测。
- Gateway 重启后再次查询 API Key、Webhook、A/B 实验：数据仍存在，确认 PostgreSQL 持久化生效。
- `docker compose exec gateway python -c ...`：PBKDF2 密码哈希正确验证通过。
- Playwright 移动视口 smoke：`/register`、`/password-reset` 和登录页入口均真实渲染，表单输入和链接可见。

## 已知限制

- 宿主机 Python 缺少 `jwt`、`psycopg_pool`、`langchain_core`，无法在宿主机收集后端 pytest；没有将此环境问题伪装成通过。后端核心验证在 Docker Gateway 容器中完成。
- 支付、订单、退款、订阅和取消订阅按用户最新要求暂不实现；README 已明确说明，不提供假入口。
- 生产找回密码必须配置 SMTP 环境变量；未配置时接口明确返回 503。开发环境返回一次性重置令牌用于无邮件服务联调。
