# PartsMind 评估体系文档

## 评估目标

| 指标 | MVP目标 | 测量方式 |
|------|---------|---------|
| 答案准确率 | > 80% | LLM-as-Judge overall_score ≥ 0.65 |
| 来源引用率 | 100% | source_citation score ≥ 0.8 |
| P95 延迟 | < 8s | latency_ms 第95百分位 |
| 置信度校准 | > 0.6 均值 | confidence 字段均值 |
| 用户满意度 | > 75% 点赞 | thumbs_up / total_feedback |
| 嵌入成本 | < $0.01/天 | embedding_tokens × $0.02/1M |

## 三层测试体系

### Layer 1: 单元测试（每次 push）
- 运行时间: ~15s
- 覆盖: Tools逻辑、Auth、Chunker、RRF算法、Guardrails
- 命令: `pytest tests/unit -v`

### Layer 2: 集成测试（每个 PR）
- 运行时间: ~60s
- 覆盖: 文档解析流水线、API端点、DB操作
- 需要: PostgreSQL + Redis（GitHub Actions service）
- 命令: `pytest tests/integration -v`

### Layer 3: Agent 评估（每周 + 每次 Prompt 改动后）
- 运行时间: ~5min，花费 ~$0.20
- 覆盖: 10个测试用例 × 4个评估维度 × LLM Judge
- 命令: `pytest tests/evaluation -v -s`
- 产出: `eval_reports/eval_YYYYMMDD_HHMMSS.json`

## Prompt 迭代工作流

```
1. 发现问题（用户反馈 / Admin面板 failures）
   ↓
2. 将失败案例加入 EVAL_DATASET
   ↓
3. 修改 templates.py 中的 prompt（更新版本号注释）
   ↓
4. 运行 pytest tests/evaluation -v -s
   ↓
5. 对比新旧 eval_reports JSON
   - overall_score 提升 → 合并
   - overall_score 下降 → 回滚
   ↓
6. 更新 PROMPT_VERSIONS 字典
```

## 失败案例分析工作流

每周从 Admin 面板 `/admin/analytics/failures` 获取：
- 低置信度回答（confidence < 0.55）
- 被用户点踩的回答

分析模式：
- 是否某类查询反复失败？（ → 加入 EVAL_DATASET）
- 是否某类产品找不到？（ → 补充数据）
- 是否 Prompt 指令理解有偏差？（ → 修改 Prompt）

## LangSmith 追踪

每个 Agent 请求在 LangSmith 中有完整的：
- 完整 trace（每个节点的输入输出）
- Token 用量
- 延迟分解
- 错误堆栈

访问: https://smith.langchain.com → Project: partsmind-dev
