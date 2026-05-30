<div align="center">

# PartsMind 🔧

**企业级汽车零配件 AI 搜货与智能问答平台**



[![CI](https://github.com/YOUR_USERNAME/partsmind/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/partsmind/actions)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.1-purple)](https://langchain-ai.github.io/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[Live Demo](https://partsmind.railway.app) · [API Docs](https://api.partsmind.railway.app/docs) · [架构文档](docs/architecture/)

</div>

---

## 项目背景

零配件采购员每天面临同一个问题：**手里只有一张零件实物照片，不知道型号，不知道价格，不知道哪里有货**。传统方式是翻纸质目录或打电话，平均耗时 1-2 小时。

PartsMind 将这个过程压缩到 **30 秒**：

1. 拍照上传 → GPT-4o Vision 识别零件类型和属性
2. 自动匹配商品库 → 向量语义搜索 + 关键词混合检索
3. 自然语言追问 → LangGraph Agent 多步推理回答

## 技术亮点

| 特性 | 实现方式 | 价值 |
|------|---------|------|
| **多模态搜索** | GPT-4o Vision + pgvector | 图片直接找货，无需知道型号 |
| **混合检索 RRF** | 语义向量 + 全文检索融合 | 召回率比单一方式提升 ~30% |
| **LangGraph Agent** | 状态机 + 4个工具 + 条件分支 | 复杂多步查询（图片+车型+价格过滤）|
| **异步文档处理** | Celery + Redis 任务队列 | 上传即返回，后台处理不阻塞 |
| **LLM-as-Judge 评估** | GPT-4o 评估 GPT-4o 回答 | 可量化的答案质量指标 |
| **Prompt 版本管理** | 版本注释 + LangSmith 追踪 | Prompt 改动可回滚、可对比 |

## 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    Next.js 14 前端                    │
│         搜索 UI · 对话 UI · Admin 管理面板             │
└──────────────────────┬──────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────┐
│              FastAPI 后端 (Python 3.11)               │
│     JWT Auth · REST API · Pydantic · 结构化日志        │
└──────┬──────────────┬──────────────┬────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────┐ ┌───▼────────────────┐
│ LangGraph   │ │   Celery   │ │   PostgreSQL        │
│   Agent     │ │   Worker   │ │   + pgvector        │
│             │ │            │ ├────────────────────┤
│ ┌─────────┐ │ │ PDF/DOCX   │ │   Redis            │
│ │Vision   │ │ │ 解析→分块   │ │   Cache + Queue    │
│ │Search   │ │ │ →向量化     │ └────────────────────┘
│ │Lookup   │ │ └────────────┘
│ │Compat.  │ │
│ └─────────┘ │
└─────────────┘
```

## 技术栈

**后端**: Python 3.11 · FastAPI · SQLAlchemy (async) · Alembic · Pydantic v2

**AI/Agent**: LangGraph · LangChain · OpenAI GPT-4o · text-embedding-3-small · LangSmith

**数据**: PostgreSQL 16 + pgvector (HNSW index) · Redis 7 · Celery

**前端**: Next.js 14 · TypeScript · Tailwind CSS

**DevOps**: Docker (multi-stage) · GitHub Actions CI/CD · Railway · Nginx · Sentry

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/YOUR_USERNAME/partsmind.git
cd partsmind

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 和 SECRET_KEY

# 3. 启动依赖服务
docker compose up -d db redis

# 4. 初始化数据库
cd backend
pip install -r requirements.txt
alembic upgrade head

# 5. 种入演示数据（200个零件 + 向量嵌入）
python ../scripts/seed/seed_products.py --synthetic --count 200 --embed
python ../scripts/seed/create_admin.py

# 6. 启动服务
uvicorn app.main:app --reload          # 后端: http://localhost:8000/docs
# 新终端:
celery -A app.core.celery_app worker   # 异步任务处理
# 新终端:
cd ../frontend && npm install && npm run dev  # 前端: http://localhost:3000
```

详细部署文档见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 项目结构

```
partsmind/
├── backend/
│   ├── app/
│   │   ├── agent/           # LangGraph Agent 核心
│   │   │   ├── graph.py     # 状态机主体（7个节点）
│   │   │   ├── state.py     # AgentState TypedDict
│   │   │   ├── tools/       # Vision / Search / Lookup / Compatibility
│   │   │   └── prompts/     # 版本化 Prompt 模板
│   │   ├── api/v1/          # FastAPI 路由层
│   │   ├── core/            # Config / Logging / Exceptions / Monitoring
│   │   ├── models/          # SQLAlchemy ORM (5张表 + pgvector)
│   │   ├── schemas/         # Pydantic 请求/响应 Schema
│   │   ├── services/        # 业务逻辑层
│   │   ├── tasks/           # Celery 异步任务
│   │   └── utils/           # Guardrails / Metrics
│   └── tests/
│       ├── unit/            # 纯逻辑测试（无外部依赖）
│       ├── integration/     # 文档处理流水线测试
│       └── evaluation/      # LLM-as-Judge Agent 评估
├── frontend/                # Next.js 14
├── infra/
│   ├── docker/              # 多阶段 Dockerfile
│   ├── nginx/               # 反向代理 + 限速配置
│   └── railway/             # 云部署配置
├── scripts/seed/            # 数据初始化脚本
└── docs/                    # 架构文档 + 部署指南
```

## 评估指标

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| 答案准确率 | > 80% | LLM-as-Judge (10个 golden cases) |
| P95 响应延迟 | < 8s | latency_ms 字段统计 |
| 置信度均值 | > 0.65 | confidence 字段均值 |
| 用户满意度 | > 75% | 点赞率 (thumbs_up / total) |
| 文档入库成功率 | > 99% | DocumentStatus.COMPLETED 比率 |

## License

MIT © 2025
