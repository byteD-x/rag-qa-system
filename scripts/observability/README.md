# Observability Scripts

观测与排障辅助脚本。

## 文件说明

- `aggregate-logs.ps1`：导出多服务日志快照
- `rag-daily-report.py`：聚合 benchmark、ablation、eval 报告并输出日报摘要

## 与成本估算的关系

- 统一聊天接口中的 `cost` 元数据由 `gateway` 计算，并随接口响应返回。
- `rag-daily-report.py` 当前不会汇总在线聊天成本，也不会重新计算币种或阶梯价格。
- 如需核对价格档位，请直接检查 [`.env`](/E:/Project/rag-qa-system/.env) 中的 `AI_PRICE_CURRENCY` 与 `AI_PRICE_TIERS_JSON`。
