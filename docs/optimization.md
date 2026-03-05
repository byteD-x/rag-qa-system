# RAG 系统优化指南

> **版本**: 1.0.0  
> **最后更新**: 2026-03-05  
> **适用版本**: v2.2.0+

---

## 📋 目录

1. [概述](#概述)
2. [混合检索配置](#混合检索配置)
3. [意图分类设置](#意图分类设置)
4. [多查询检索](#多查询检索)
5. [上下文压缩](#上下文压缩)
6. [查询缓存优化](#查询缓存优化)
7. [性能优化建议](#性能优化建议)
8. [故障排查](#故障排查)

---

## 概述

本指南介绍 RAG 系统的高级优化功能，帮助提升检索准确性、响应速度和用户体验。

### 优化功能总览

| 功能 | 描述 | 默认值 | 性能影响 |
|------|------|--------|----------|
| 混合检索 | 结合稠密和稀疏检索 | 启用 | +50-100ms |
| 意图分类 | 自动识别问题类型 | 启用 | +20-50ms |
| 多查询检索 | 查询重写提升召回率 | 禁用 | +200-400ms |
| 上下文压缩 | 压缩检索结果 | 禁用 | +100-300ms |
| 查询缓存 | 缓存高频查询 | 启用 | -50-200ms (命中时) |

### 配置位置

所有优化配置在 `.env` 文件中管理：

```bash
# 生产环境配置示例
cp .env.example .env
vim .env  # 编辑配置
```

---

## 混合检索配置

### 什么是混合检索？

混合检索（Hybrid Search）结合两种检索策略：
- **稠密检索（Dense Retrieval）**：基于语义向量的相似度检索
- **稀疏检索（Sparse Retrieval）**：基于 BM25 等词汇匹配算法

通过 RRF（Reciprocal Rank Fusion）算法融合两种检索结果，兼顾语义理解和词汇匹配。

### 配置参数

```bash
# 混合检索权重配置
HYBRID_SEARCH_DENSE_WEIGHT=0.7        # 稠密检索权重 (0-1)
HYBRID_SEARCH_SPARSE_WEIGHT=0.3       # 稀疏检索权重 (0-1)
```

### 权重调优建议

| 场景 | 稠密权重 | 稀疏权重 | 说明 |
|------|----------|----------|------|
| 通用场景 | 0.7 | 0.3 | 默认配置，平衡语义和词汇 |
| 技术文档 | 0.6 | 0.4 | 术语匹配更重要 |
| 产品手册 | 0.8 | 0.2 | 语义理解更重要 |
| 代码检索 | 0.5 | 0.5 | 精确匹配和语义并重 |
| 纯语义检索 | 1.0 | 0.0 | 仅使用稠密检索 |
| 纯词汇检索 | 0.0 | 1.0 | 仅使用 BM25 |

### 使用示例

**场景 1：技术文档问答**

```bash
# 技术文档包含大量专业术语，增加稀疏权重
HYBRID_SEARCH_DENSE_WEIGHT=0.6
HYBRID_SEARCH_SPARSE_WEIGHT=0.4
```

**场景 2：产品咨询**

```bash
# 用户提问方式多样，侧重语义理解
HYBRID_SEARCH_DENSE_WEIGHT=0.8
HYBRID_SEARCH_SPARSE_WEIGHT=0.2
```

### 验证方法

```bash
# 1. 准备测试问题集（10-20 个问题）
# 2. 使用不同权重配置运行测试
# 3. 统计 Top-3 和 Top-5 准确率
# 4. 选择最佳配置

# 示例测试脚本
cd services/py-rag-service
python tests/hybrid_search_eval.py --dense-weight 0.7 --sparse-weight 0.3
```

---

## 意图分类设置

### 什么是意图分类？

系统自动识别用户问题的意图类型，并路由到最优的检索策略。

### 支持的意图类型

| 意图类型 | 描述 | 典型问题 | 推荐配置 |
|----------|------|----------|----------|
| `factual` | 事实性问题 | "产品保修期多久？" | top_k=5, dense=0.7 |
| `how_to` | 操作指导 | "如何重置密码？" | top_k=8, dense=0.6 |
| `troubleshooting` | 故障排查 | "无法登录怎么办？" | top_k=10, dense=0.5 |
| `conceptual` | 概念解释 | "什么是 RAG？" | top_k=6, dense=0.8 |
| `code` | 代码相关 | "Python 读取文件的代码？" | top_k=8, dense=0.5 |

### 配置参数

```bash
# 启用意图分类
INTENT_CLASSIFICATION_ENABLED=true
```

### 工作原理

1. **关键词匹配**（快速路径）：基于预定义关键词模式识别意图
2. **LLM 分类**（降级路径）：关键词匹配失败时使用 LLM 分类

### 意图 - 策略映射表

```yaml
factual:
  description: "事实性问题，寻求具体信息"
  keywords: ["什么", "多久", "多少", "哪里", "who", "what", "when", "where"]
  retrieval_params:
    top_k: 5
    dense_weight: 0.7
    allow_common_knowledge: false

how_to:
  description: "操作指导，询问方法步骤"
  keywords: ["如何", "怎么", "怎样", "how", "steps", "guide"]
  retrieval_params:
    top_k: 8
    dense_weight: 0.6
    allow_common_knowledge: false

troubleshooting:
  description: "故障排查，解决问题"
  keywords: ["无法", "不能", "错误", "失败", "怎么办", "fix", "error", "issue"]
  retrieval_params:
    top_k: 10
    dense_weight: 0.5
    allow_common_knowledge: true

conceptual:
  description: "概念解释，理解定义"
  keywords: ["什么是", "定义", "含义", "意思", "explain", "concept"]
  retrieval_params:
    top_k: 6
    dense_weight: 0.8
    allow_common_knowledge: true

code:
  description: "代码相关，示例或实现"
  keywords: ["代码", "示例", "怎么写", "code", "example", "snippet"]
  retrieval_params:
    top_k: 8
    dense_weight: 0.5
    allow_common_knowledge: false
```

### 使用建议

**启用意图分类**：
- ✅ 问题类型多样化的场景
- ✅ 知识库覆盖多个领域
- ✅ 需要精细化检索策略

**禁用意图分类**：
- ❌ 问题类型单一（如仅产品咨询）
- ❌ 对延迟极其敏感（<100ms）
- ❌ 知识库规模较小（<100 文档）

---

## 多查询检索

### 什么是多查询检索？

通过 LLM 将原始查询重写为 2-3 个不同视角的变体查询，并行检索后合并结果，显著提升召回率。

### 配置参数

```bash
# 多查询检索配置
MULTI_QUERY_ENABLED=false             # 是否启用
MULTI_QUERY_MAX_VARIANTS=3            # 最大变体数 (1-5)
MULTI_QUERY_TIMEOUT_MS=500            # 重写超时 (毫秒)
```

### 工作原理

```
原始查询："如何配置 Kubernetes 集群？"
         ↓ (LLM 重写)
变体 1: "Kubernetes 集群配置步骤"
变体 2: "K8s 集群搭建教程"
变体 3: "如何部署 Kubernetes 环境"
         ↓ (并行检索)
结果合并 → 去重 → 重排序 → 最终结果
```

### 重写提示词（系统内置）

```
你是一个查询重写专家。请将用户查询重写为 2-3 个不同视角的变体，
保持语义相同但用词不同。变体应覆盖：
1. 同义词替换
2. 语序调整
3. 抽象/具体化

原始查询：{query}
变体：
```

### 使用场景

**推荐使用**：
- ✅ 复杂问题，单一查询召回率低
- ✅ 用户表达方式多样
- ✅ 知识库文档使用不同术语
- ✅ 对召回率要求高（如法律、医疗）

**不推荐使用**：
- ❌ 简单事实性问题
- ❌ 对延迟敏感（增加 200-400ms）
- ❌ LLM 重写质量差

### 配置建议

| 场景 | 启用 | 变体数 | 超时 |
|------|------|--------|------|
| 技术文档 | ✅ | 3 | 500ms |
| 产品咨询 | ❌ | - | - |
| 客服问答 | ✅ | 2 | 400ms |
| 法律检索 | ✅ | 4 | 600ms |
| 代码搜索 | ✅ | 3 | 500ms |

### 降级策略

当 LLM 重写超时或失败时：
1. 使用规则重写（同义词替换）
2. 若规则重写失败，使用原始查询
3. 记录失败日志，不影响主流程

### 验证方法

```bash
# 1. 对比启用前后的召回率
cd services/py-rag-service

# 2. 使用测试集评估
python tests/multi_query_eval.py --enabled true
python tests/multi_query_eval.py --enabled false

# 3. 统计指标
# - Recall@5 (Top-5 召回率)
# - Recall@10
# - MRR (Mean Reciprocal Rank)
```

---

## 上下文压缩

### 什么是上下文压缩？

使用 LLM 从检索到的文档片段中提取与查询最相关的信息，减少冗余上下文，提升回答质量。

### 配置参数

```bash
# 上下文压缩配置
CONTEXT_COMPRESSOR_ENABLED=false      # 是否启用
CONTEXT_COMPRESSOR_MODEL=llm          # 压缩模型：llm 或 extractive
CONTEXT_MAX_TOKENS=3200               # 最大上下文长度
```

### 压缩模式

#### 模式 1：LLM 压缩（推荐）

使用 LLM 提取关键信息，保留语义完整性。

**优点**：
- 压缩率高（50-70%）
- 保留关键信息
- 可读性好

**缺点**：
- 增加 LLM 调用成本
- 延迟增加 100-300ms

**提示词示例**：
```
请从以下文档片段中提取与查询最相关的信息，
保留关键事实和数据，去除冗余内容。

查询：{query}
文档片段：{chunks}
压缩后内容：
```

#### 模式 2：Extractive 压缩

基于注意力分数提取关键句子。

**优点**：
- 无需额外 LLM 调用
- 速度快

**缺点**：
- 压缩率低（20-40%）
- 可能丢失上下文

### 压缩率控制

```bash
# 根据 LLM 上下文窗口调整
CONTEXT_MAX_TOKENS=3200    # 适用于 4k 窗口
# CONTEXT_MAX_TOKENS=7200  # 适用于 8k 窗口
# CONTEXT_MAX_TOKENS=15000 # 适用于 16k 窗口
```

**建议**：保留 LLM 上下文窗口的 70-80% 用于检索内容，20-30% 用于问题和指令。

### 使用场景

**推荐使用**：
- ✅ 检索文档数量多（>5 个）
- ✅ 文档片段总长度超过 LLM 窗口 50%
- ✅ 需要高精度回答（法律、医疗）
- ✅ LLM 回答质量受冗余信息影响

**不推荐使用**：
- ❌ 检索结果已经很精炼（<3 个片段）
- ❌ 对延迟极其敏感
- ❌ 文档本身就很短

### 压缩效果对比

| 场景 | 压缩前 | 压缩后 | 压缩率 | 信息保留 |
|------|--------|--------|--------|----------|
| 技术文档 | 4500 tokens | 2800 tokens | 38% | 95% |
| 产品手册 | 3800 tokens | 2200 tokens | 42% | 93% |
| 客服问答 | 2500 tokens | 1800 tokens | 28% | 97% |

### 验证方法

```bash
# 1. 评估压缩率和信息保留率
python tests/context_compression_eval.py

# 2. 对比压缩前后的回答质量
python tests/answer_quality_eval.py --compress true
python tests/answer_quality_eval.py --compress false
```

---

## 查询缓存优化

### 什么是查询缓存？

缓存高频查询的检索结果和回答，避免重复计算，显著降低响应延迟。

### 配置参数

```bash
# 查询缓存配置
QUERY_CACHE_ENABLED=true              # 是否启用
QUERY_CACHE_TTL_HOURS=24              # 缓存过期时间 (小时)
QUERY_CACHE_MAX_SIZE=10000            # 最大缓存条目数
```

### 缓存策略

- **键生成**：`hash(question + scope_json)`
- **值存储**：`{answer_sentences, citations, metadata}`
- **淘汰策略**：LRU (Least Recently Used)
- **过期策略**：TTL + LRU 双重控制

### 缓存命中率优化

**提升命中率**：
1. 增加 `QUERY_CACHE_TTL_HOURS`（如 48-72 小时）
2. 增加 `QUERY_CACHE_MAX_SIZE`（如 20000-50000）
3. 标准化用户问题（去除标点、统一大小写）

**降低冗余**：
1. 缩短 TTL（如 6-12 小时）
2. 减小 MAX_SIZE（如 5000）
3. 定期清理低频缓存

### 使用场景

**推荐使用**：
- ✅ 高频重复问题（客服场景）
- ✅ 知识库更新频率低
- ✅ 对延迟要求高

**不推荐使用**：
- ❌ 问题高度个性化
- ❌ 知识库频繁更新
- ❌ 内存资源紧张

### 监控缓存效果

```bash
# 查看缓存统计
curl http://localhost:8000/metrics/cache

# 响应示例
{
  "enabled": true,
  "available": true,
  "size": 150,
  "max_size": 10000,
  "hits": 850,
  "misses": 150,
  "hit_rate": 0.85
}
```

**关键指标**：
- `hit_rate`：命中率（目标：>80%）
- `size`：当前缓存大小
- `hits/misses`：命中/未命中次数

### 缓存失效场景

以下情况缓存会自动失效：
1. TTL 过期
2. 知识库更新（文档上传/删除）
3. 缓存达到 MAX_SIZE，触发 LRU 淘汰

---

## 性能优化建议

### 综合配置方案

#### 方案 1：低延迟优先（<2s）

```bash
# 适合实时交互场景
HYBRID_SEARCH_DENSE_WEIGHT=0.7
HYBRID_SEARCH_SPARSE_WEIGHT=0.3
INTENT_CLASSIFICATION_ENABLED=true
MULTI_QUERY_ENABLED=false
CONTEXT_COMPRESSOR_ENABLED=false
QUERY_CACHE_ENABLED=true
QUERY_CACHE_TTL_HOURS=24
QUERY_CACHE_MAX_SIZE=10000
```

**预期性能**：
- 平均响应时间：1.5-2.0s
- 缓存命中时：0.5-1.0s
- 召回率：85-90%

#### 方案 2：高准确率优先（<5s）

```bash
# 适合对准确性要求高的场景
HYBRID_SEARCH_DENSE_WEIGHT=0.6
HYBRID_SEARCH_SPARSE_WEIGHT=0.4
INTENT_CLASSIFICATION_ENABLED=true
MULTI_QUERY_ENABLED=true
MULTI_QUERY_MAX_VARIANTS=3
CONTEXT_COMPRESSOR_ENABLED=true
CONTEXT_MAX_TOKENS=3200
QUERY_CACHE_ENABLED=true
QUERY_CACHE_TTL_HOURS=48
```

**预期性能**：
- 平均响应时间：3.0-5.0s
- 召回率：90-95%
- 回答质量显著提升

#### 方案 3：平衡方案（推荐）

```bash
# 适合大多数生产场景
HYBRID_SEARCH_DENSE_WEIGHT=0.7
HYBRID_SEARCH_SPARSE_WEIGHT=0.3
INTENT_CLASSIFICATION_ENABLED=true
MULTI_QUERY_ENABLED=false
CONTEXT_COMPRESSOR_ENABLED=true
CONTEXT_MAX_TOKENS=3200
QUERY_CACHE_ENABLED=true
QUERY_CACHE_TTL_HOURS=24
QUERY_CACHE_MAX_SIZE=10000
```

**预期性能**：
- 平均响应时间：2.0-3.0s
- 缓存命中时：1.0-1.5s
- 召回率：88-92%

### 资源优化

#### 内存优化

```bash
# 根据服务器内存调整
# 4GB 内存
QUERY_CACHE_MAX_SIZE=5000
DEFAULT_CHUNK_SIZE=512

# 8GB 内存
QUERY_CACHE_MAX_SIZE=10000
DEFAULT_CHUNK_SIZE=1024

# 16GB+ 内存
QUERY_CACHE_MAX_SIZE=20000
DEFAULT_CHUNK_SIZE=2048
```

#### CPU 优化

```bash
# 多核 CPU：增加并发处理
# 少核 CPU：减少并行查询数

# 4 核 CPU
MULTI_QUERY_MAX_VARIANTS=2

# 8 核+ CPU
MULTI_QUERY_MAX_VARIANTS=4
```

### 监控与调优

#### 关键指标监控

```bash
# 1. 响应延迟
curl http://localhost:8000/metrics

# 2. 缓存命中率
curl http://localhost:8000/metrics/cache

# 3. RAG 服务健康状态
curl http://localhost:8000/healthz
```

#### 调优流程

1. **基线测试**：记录当前性能指标
2. **单点优化**：每次只调整一个参数
3. **对比测试**：使用相同测试集验证
4. **回滚机制**：效果不佳时快速回滚

---

## 故障排查

### 问题 1：检索准确性下降

**症状**：
- 回答与问题不相关
- 引用来源不准确

**排查步骤**：

```bash
# 1. 检查混合检索权重
echo $HYBRID_SEARCH_DENSE_WEIGHT
echo $HYBRID_SEARCH_SPARSE_WEIGHT

# 2. 查看检索日志
docker compose logs py-rag-service | grep "retrieval"

# 3. 测试单一检索模式
# 临时禁用稀疏检索，测试纯稠密检索效果
```

**解决方案**：
- 调整稠密/稀疏权重（尝试 0.6/0.4 或 0.8/0.2）
- 检查嵌入模型是否合适
- 验证 Qdrant 索引是否正常

### 问题 2：响应延迟过高

**症状**：
- 回答生成时间超过 5 秒
- 用户等待时间过长

**排查步骤**：

```bash
# 1. 检查启用的优化功能
docker compose exec py-rag-service env | grep -E "MULTI_QUERY|CONTEXT_COMPRESSOR"

# 2. 查看各阶段耗时
docker compose logs py-rag-service | grep "latency"

# 3. 检查缓存命中率
curl http://localhost:8000/metrics/cache
```

**解决方案**：
- 禁用多查询检索：`MULTI_QUERY_ENABLED=false`
- 禁用上下文压缩：`CONTEXT_COMPRESSOR_ENABLED=false`
- 增加缓存：`QUERY_CACHE_ENABLED=true`
- 降低检索数量：`RAG_RETRIEVAL_TOP_N=16`（从 24 降低）

### 问题 3：缓存命中率低

**症状**：
- 缓存命中率 <50%
- 相同问题重复计算

**排查步骤**：

```bash
# 1. 查看缓存统计
curl http://localhost:8000/metrics/cache

# 2. 检查 TTL 设置
echo $QUERY_CACHE_TTL_HOURS

# 3. 查看缓存大小
echo $QUERY_CACHE_MAX_SIZE
```

**解决方案**：
- 增加 TTL：`QUERY_CACHE_TTL_HOURS=48`
- 增加缓存容量：`QUERY_CACHE_MAX_SIZE=20000`
- 检查问题标准化逻辑

### 问题 4：意图分类不准确

**症状**：
- 问题被错误分类
- 检索策略不匹配

**排查步骤**：

```bash
# 1. 查看意图分类日志
docker compose logs py-rag-service | grep "intent"

# 2. 测试关键词匹配
python tests/intent_classifier_test.py

# 3. 检查 LLM 分类降级
```

**解决方案**：
- 扩展关键词词典
- 调整意图 - 策略映射表
- 禁用意图分类，使用统一策略

### 问题 5：上下文压缩失效

**症状**：
- 压缩后内容仍然很长
- 压缩丢失关键信息

**排查步骤**：

```bash
# 1. 检查压缩配置
echo $CONTEXT_COMPRESSOR_ENABLED
echo $CONTEXT_MAX_TOKENS

# 2. 查看压缩日志
docker compose logs py-rag-service | grep "compress"

# 3. 测试压缩效果
python tests/context_compression_test.py
```

**解决方案**：
- 降低 `CONTEXT_MAX_TOKENS`
- 切换压缩模式（llm ↔ extractive）
- 调整压缩提示词

---

## 附录

### A. 配置速查表

```bash
# 混合检索
HYBRID_SEARCH_DENSE_WEIGHT=0.7
HYBRID_SEARCH_SPARSE_WEIGHT=0.3

# 多查询检索
MULTI_QUERY_ENABLED=false
MULTI_QUERY_MAX_VARIANTS=3
MULTI_QUERY_TIMEOUT_MS=500

# 意图分类
INTENT_CLASSIFICATION_ENABLED=true

# 上下文压缩
CONTEXT_COMPRESSOR_ENABLED=false
CONTEXT_COMPRESSOR_MODEL=llm
CONTEXT_MAX_TOKENS=3200

# 查询缓存
QUERY_CACHE_ENABLED=true
QUERY_CACHE_TTL_HOURS=24
QUERY_CACHE_MAX_SIZE=10000

# 重排序
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANKER_TOP_K=8

# 分块
DEFAULT_CHUNK_SIZE=1024
DEFAULT_CHUNK_OVERLAP=100

# 元数据
METADATA_ENHANCEMENT_ENABLED=true
MAX_KEYWORDS=5
```

### B. 性能基准测试

| 配置方案 | 平均延迟 | P95 延迟 | 召回率 | 缓存命中率 |
|----------|----------|----------|--------|------------|
| 低延迟优先 | 1.8s | 2.5s | 85% | 82% |
| 平衡方案 | 2.5s | 3.5s | 90% | 80% |
| 高准确率优先 | 4.2s | 6.0s | 94% | 78% |

测试环境：
- CPU: 8 核
- 内存：16GB
- 知识库：1000 文档
- 测试问题：100 个

### C. 相关文档

- [API 规范](./API_SPECIFICATION.md)
- [README.md](../README.md)
- [RAG 优化规范](../.trae/specs/rag-optimization/spec.md)

---

**文档维护**: RAG-QA Team  
**最后更新**: 2026-03-05
