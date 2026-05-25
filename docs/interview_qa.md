# PartsMind 面试问答手册

> 按频率和难度排序。每个答案控制在 60-90 秒口述时间内。

---

## 一、项目介绍类（必问）

### Q1: 介绍一下你的这个项目

**标准答案框架（STAR）**：

"这个项目是为汽车零配件供应商做的一个 AI 搜货系统。

**背景**：采购员手里只有一张零件照片，不知道型号，传统方式要翻目录查 1-2 小时。

**我做了什么**：设计并实现了一个 LangGraph Agent，接收图片或文字查询，通过四个工具——GPT-4o 图像识别、向量语义搜索、产品规格查询、车型兼容性验证——多步推理给出带来源引用的答案。整个链路 30 秒内完成。

**技术选择**：后端 FastAPI + PostgreSQL，向量库用 pgvector 的 HNSW 索引，检索用混合搜索加 RRF 融合，文档处理用 Celery 异步队列，最后部署在 Railway，有完整的评估体系。

**结果**：查货时间从 1-2 小时降到 30 秒，系统已在线可访问。"

---

### Q2: 为什么选 LangGraph 而不是直接用 LangChain？

**答**：

"LangChain 的 Chain 是线性管道——数据从 A 流到 B 流到 C，没有分支，没有状态共享。

我的场景需要条件路由：如果用户上传了图片，先走 Vision 工具识别；如果是纯文字查询，直接走搜索。而且所有工具的输出需要共享同一个状态容器——Vision 识别出来的零件名，要传给 Search 工具作为查询词。

LangGraph 的状态机模型完美解决这个问题：定义一个 AgentState TypedDict，每个节点读取状态、输出对状态的 partial update，LangGraph 自动合并。条件边（conditional_edges）实现路由逻辑。

简单说：Chain 适合线性流程，Graph 适合有分支、有状态共享的复杂推理。"

---

## 二、RAG / 检索类

### Q3: 你的搜索用了什么技术？为什么不只用向量搜索？

**答**：

"我用了混合检索，结合两种方式：

**向量语义搜索**（pgvector）：用 text-embedding-3-small 把查询和产品描述都转成 1536 维向量，计算余弦相似度。优点是能捕捉语义——'刹车片'和'brake pad'能匹配上，即使没有相同字词。

**关键词全文搜索**（PostgreSQL tsvector）：精确匹配零件型号、品牌名。当用户输入'BP-BOC-45231'这种型号时，向量搜索反而不擅长，关键词搜索直接命中。

**RRF 融合**：两个结果列表各自排名，用公式 `1/(k + rank)` 计算 RRF 分数后合并。出现在两个列表里的产品会得到双倍加成，排名更靠前。k=60 是 Elasticsearch 官方推荐的标准值。

实测比单一方式召回率提升约 30%。"

---

### Q4: pgvector 和 Pinecone 你怎么选型的？

**答**：

"我选了 pgvector，主要三个理由：

**一、架构简洁**：数据已经在 PostgreSQL，用 pgvector 扩展直接在同一个数据库里建向量索引，不需要维护两套存储，减少网络跳数和运维复杂度。

**二、成本**：Pinecone 免费版有限制，生产版按向量数收费。pgvector 是 PostgreSQL 插件，开源免费。

**三、HNSW 索引性能够用**：我们的产品库是百到万级别，pgvector 的 HNSW 索引（m=16, ef_construction=64）查询延迟在 5-20ms，完全满足需求。如果是亿级向量，我会重新评估 Pinecone 或 Milvus。

权衡就是：Pinecone 有更好的云原生扩展性，但在我们的规模下 over-engineering。"

---

### Q5: Chunk 策略怎么设计的？

**答**：

"目标 chunk 大小是 300 token（约 1200 字符），相邻 chunk 有 50 token（约 200 字符）的重叠。

**为什么 300 token**：太小则单个 chunk 缺少上下文，语义不完整；太大则一个 chunk 包含太多不相关内容，检索精度下降。300 是 RAG 实践中的经验值，也是 LlamaIndex 的默认值。

**为什么要重叠**：避免答案跨越两个 chunk 边界时被截断。比如一个政策文件，前 chunk 最后说'报销上限为'，后 chunk 才说'500元'，如果没有重叠，单独检索任何一个 chunk 都得不到完整答案。

**分割优先级**：段落边界 > 句子边界 > 字符位置。这样保证语义完整性，不会把一个句子劈成两半。"

---

## 三、Agent / LLM 类

### Q6: 你的 Agent 有几个工具？各自是什么？

**答**：

"四个工具，各司其职：

**VisionTool**：调用 GPT-4o Vision，输入 base64 图片，输出结构化 JSON——零件名称、类别、可见的品牌和型号、关键属性、搜索关键词、识别置信度。温度设为 0.1，确保结果稳定。

**SemanticSearchTool**：混合检索，向量+关键词+RRF，返回 top-K 候选产品和相似度分数。

**ProductLookupTool**：根据 Search 返回的 ID 列表，从 PostgreSQL 拉取完整产品详情（规格、价格、库存）。Search 阶段只返回轻量数据，Lookup 阶段才拉 JSONB 字段，减少 DB 压力。

**CompatibilityTool**：纯函数，对比产品的 compatible_vehicles 字段和用户提供的车型信息，返回是否兼容及原因。不需要 LLM，规则判断就够了，零额外成本。"

---

### Q7: 如果 LLM 产生幻觉怎么处理？

**答**：

"我有三层防护：

**第一层——Prompt 约束**：System prompt 里明确写'NEVER invent prices, part numbers, or stock levels'，并要求每个声明必须 cite 来源的产品型号。LLM 倾向于遵守明确规则。

**第二层——置信度评分 + Guardrails**：Confidence gate 节点综合搜索相似度分数和 Vision 识别置信度，计算加权分。如果分数低于 0.72，会设置 needs_human_review=true，并在输出里提示用户验证。Guardrails 模块还会检测：低置信度但包含具体价格的回答，自动加免责声明。

**第三层——评估体系**：LLM-as-Judge 有专门的 factual_grounding 维度，检测答案是否只包含 search results 里有的信息。评分低于阈值触发 prompt review 流程。

没有 100% 消除幻觉的方法，但这三层组合可以把风险控制在可接受范围。"

---

### Q8: 怎么评估 Agent 回答质量？

**答**：

"我建了 LLM-as-Judge 评估框架，三层：

**Golden Dataset**：手写 10 个有代表性的测试用例，覆盖图片搜索、文字搜索、问答、边界情况。每个 case 定义了 expected_contains（必须包含的词）、expected_excludes（不能出现的词）、最低置信度、最大延迟。

**LLM Judge**：用 GPT-4o 评估 GPT-4o 的回答，听起来循环，但实际有效——评估者用不同 prompt 和更严格的 rubric，4个维度各打 0-1 分：答案相关性、来源引用、事实依据、格式清晰度。这是 OpenAI Evals 用的同款方法。

**持续对比**：每次改 Prompt 前后各跑一次 eval，对比 eval_reports JSON。分数提升就合并，下降就回滚。Prompt 版本号写在代码注释里，LangSmith trace 里也带这个版本号，可以直接在 dashboard 里过滤对比。"

---

## 四、工程设计类

### Q9: 为什么文档处理用 Celery 异步队列而不是 FastAPI BackgroundTasks？

**答**：

"两个核心区别：

**可靠性**：FastAPI BackgroundTasks 在当前进程内运行。如果 uvicorn worker 重启（OOM、部署更新），任务直接丢失，没有重试机制。Celery 把任务序列化存在 Redis，worker 挂了之后 Redis 里的任务还在，重启 worker 自动继续。我配置了 task_acks_late=True，只有任务成功完成才从队列里删除。

**扩展性**：Celery worker 可以独立扩展。文档处理高峰期可以加 worker 实例，不影响 API 响应。用 BackgroundTasks 的话，文档处理会和 API 请求争抢同一个进程的线程池。

**监控**：Celery 有 Flower 监控面板，可以看每个 task 的状态、耗时、失败原因。BackgroundTasks 没有内置监控。

代价是引入了 Redis 依赖和 worker 进程，架构更复杂——这个 trade-off 在生产场景是值得的。"

---

### Q10: 说说你的数据库设计，为什么 compatible_vehicles 用 JSONB？

**答**：

"compatible_vehicles 存的是这样的数据：

```json
[
  {"make": "Toyota", "model": "Camry", "year_from": 2018, "year_to": 2023},
  {"make": "Honda", "model": "Accord", "year_from": 2019, "year_to": 2024}
]
```

如果拆成关系表，需要一张 compatible_vehicles 表，JOIN 查询。我选 JSONB 的原因：

**Schema 灵活性**：不同品牌的车型描述字段不同，有的有发动机型号，有的有驱动方式，强行统一 schema 反而麻烦。JSONB 允许每行有不同的字段。

**查询够用**：我的兼容性查询是应用层做的（Python 函数），不需要在 DB 里 WHERE compatible_vehicles 里某个字段。如果需要 DB 层过滤，PostgreSQL JSONB 支持 GIN 索引，`@>` 操作符可以索引查询。

**性能**：产品表不是高频写入，JSONB 的存储开销可以接受。

另外，specs 字段也是 JSONB，因为不同品类的零件规格字段完全不同——刹车片有材质和位置，火花塞有间隙和螺纹尺寸。这种异构数据 JSONB 是最合适的选择。"

---

## 五、加分题（架构级）

### Q11: 如果并发用户从 50 增加到 5000，你怎么扩展？

**答**：

"分三层来讲：

**计算层**：FastAPI + uvicorn 水平扩展，Railway 可以加实例。Celery worker 独立扩展，多加几个 worker 处理文档队列。这部分相对容易，都是无状态服务。

**数据库层**：这是瓶颈。PostgreSQL 单实例在高并发读场景下可以加 **PgBouncer 连接池**（我的 AsyncSession 已经配了 pool_size=10, max_overflow=20，这是第一步）。向量搜索如果成为瓶颈，可以考虑把 pgvector 换成专用向量数据库如 Milvus，或者在 PostgreSQL 前加 **Read Replica**。

**LLM 层**：GPT-4o 有速率限制。缓解方案：对相同查询做 Redis 缓存（TTL 1小时），高频重复问题直接走缓存；同时实现 LLM 请求队列，防止突发流量打爆 OpenAI 限额。

**如果是 50000 用户**：需要重新评估整个架构，引入消息队列（Kafka）做请求削峰，考虑私有化部署 LLM（Llama 3 70B）降低 token 成本。"

---

### Q12: 项目中你遇到的最难的技术问题是什么？怎么解决的？

**答**（选一个真实遇到的问题来讲）：

"最难的是 **LangGraph 状态管理和工具输出合并**。

问题是这样的：tools_used 是一个 list，每个节点都要向这个 list 追加自己用了哪个工具。我一开始用普通字段，LangGraph 的行为是后续节点的输出直接覆盖前面的，导致最终 tools_used 只有最后一个节点的记录。

排查了两小时，看 LangGraph 文档才发现——对于需要**追加**而不是**替换**的字段，必须用 `Annotated[list[str], operator.add]` 来注解 TypedDict 字段。这告诉 LangGraph 这个字段的 reducer 是 list 的 add 操作，而不是默认的替换。

修改之后，所有工具都能正确追加到 tools_used，最终日志里能看到完整的工具调用链：`['intent_classifier', 'vision_tool', 'search_tool', 'lookup_tool', 'synthesizer']`。

这个踩坑让我真正理解了 LangGraph 的 State Reducer 机制，之后设计 sources 字段（也需要追加）就直接用了同样的方式。"
