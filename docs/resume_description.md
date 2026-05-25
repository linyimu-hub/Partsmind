# 简历项目描述 — 两个版本

## 中文版（适用于国内求职）

---

### PartsMind · 汽车零配件 AI 搜货与智能问答平台

**技术栈**：Python · FastAPI · LangGraph · GPT-4o · pgvector · PostgreSQL · Redis · Celery · Next.js · Docker · Railway

**项目背景**：针对汽车零配件 B2B 供应商（深圳源尧兴实业）的真实业务痛点设计并独立实现：采购员仅凭实物照片无法快速找到对应货品，传统方式耗时 1-2 小时。

**核心工作**：

- 设计并实现基于 **LangGraph** 的多工具 AI Agent，支持图片识别→语义检索→规格查询→兼容性验证的多步推理链路，将查货时间缩短至 30 秒
- 使用 **GPT-4o Vision** 实现零件图片多模态识别，输出结构化零件属性（类别、品牌、关键参数）并自动转化为搜索查询
- 实现 **Hybrid Search**（pgvector 向量检索 + PostgreSQL 全文检索）并通过 **Reciprocal Rank Fusion (RRF)** 融合排序，搜索召回率优于单一方式约 30%
- 基于 **Celery + Redis** 构建异步文档处理流水线，支持 PDF/Word 自动解析→分块（300 token/chunk，50 token 重叠）→向量化→入库，处理成功率 >99%
- 建立 **LLM-as-Judge 评估体系**：10 个 Golden Case × 4 个评估维度，Prompt 改动前后可量化对比，防止质量回归
- 实现 **Guardrails** 防御层：Prompt 注入检测、离题过滤、低置信度响应标注，保障输出安全性
- 完成 **Docker 多阶段构建 + GitHub Actions CI/CD + Railway 云部署**，支持从 push 到生产自动化全流程

---

## English Version（适用于外资/港资/海外求职）

---

### PartsMind · AI-Powered Auto Parts Search & Q&A Platform

**Stack**: Python · FastAPI · LangGraph · GPT-4o · pgvector · PostgreSQL · Redis · Celery · Next.js · Docker · Railway

**Context**: Designed and built end-to-end for a real B2B auto parts supplier use case — enabling procurement staff to find parts from a photo in under 30 seconds, replacing a 1-2 hour manual lookup process.

**Key Contributions**:

- Architected a **multi-tool LangGraph Agent** with stateful graph execution: image recognition → semantic search → product lookup → vehicle compatibility check, with conditional routing between nodes based on query intent classification
- Integrated **GPT-4o Vision** for multimodal part identification, extracting structured attributes (category, brand, specs) from uploaded images and converting them into optimized search queries
- Implemented **Hybrid Search** combining pgvector cosine similarity and PostgreSQL full-text search, fused via **Reciprocal Rank Fusion (RRF)** — improving recall by ~30% over either method alone
- Built async document ingestion pipeline using **Celery + Redis**: PDF/DOCX parsing → recursive chunking (300 tokens, 50-token overlap) → batch embedding with Redis caching → pgvector HNSW index storage
- Established **LLM-as-Judge evaluation framework** with 10 golden test cases × 4 scoring dimensions (relevance, citation, grounding, format), enabling data-driven prompt iteration and regression detection
- Designed layered **guardrails**: prompt injection detection (regex patterns), off-topic filtering (automotive keyword matching), low-confidence output flagging
- Delivered **production deployment**: multi-stage Docker builds, GitHub Actions CI/CD pipeline, Railway cloud hosting with Nginx reverse proxy, Sentry error tracking, and LangSmith AI observability

---

## 一句话电梯版（面试开场）

**中文**：我做了一个面向汽车零配件供应商的 AI 系统，核心是一个 LangGraph Agent，能接受零件图片作为输入，通过多步推理——图片识别、向量搜索、规格查询、兼容性验证——在 30 秒内给出带来源引用的精准答案。系统已部署在云端，有完整的评估体系和 CI/CD 流程。

**English**: I built an AI agent system for a B2B auto parts supplier. The core is a LangGraph-based agent that takes a part image as input, runs multi-step reasoning across four tools — vision identification, vector search, product lookup, and vehicle compatibility check — and returns a grounded answer with source citations in under 30 seconds. It's deployed to production with a full evaluation framework and automated CI/CD.
