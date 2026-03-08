# Tests

`tests/` 存放评测数据、纯 Python 回归测试和脚本 smoke 入口。

## 目录说明

- `evals/`：评测样本与问题集
- `test_*.py`：shared 能力、评测指标、gateway 成本估算和脚本 smoke

## 当前覆盖范围

- query rewrite、rerank、embedding、trace header
- eval 指标与离线 ablation 脚本
- `gateway` 的 `CNY + 阶梯计费` 成本估算

## 默认回归命令

```powershell
python -m pytest tests -q
```
