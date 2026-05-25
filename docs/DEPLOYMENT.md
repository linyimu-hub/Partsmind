# PartsMind 生产部署指南

## 快速路径（30分钟上线）

### 前置要求
- GitHub 账号
- Railway 账号（railway.app，免费注册，$5免费额度/月）
- OpenAI API Key

---

## Step 1：Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/partsmind.git
cd partsmind
```

## Step 2：本地验证（先跑通本地）

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，至少填写：
# OPENAI_API_KEY=sk-...
# SECRET_KEY=$(openssl rand -hex 32)   ← 运行这个命令生成

# 启动依赖服务
docker compose up -d db redis

# 安装后端依赖
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 运行数据库迁移
alembic upgrade head

# 创建管理员账号
python ../scripts/seed/create_admin.py

# 种入演示数据（200个合成零件 + 向量嵌入）
python ../scripts/seed/seed_products.py --synthetic --count 200 --embed

# 启动后端
uvicorn app.main:app --reload
# 验证: http://localhost:8000/docs

cd ..
# 启动 Celery worker（新终端）
cd backend && celery -A app.core.celery_app worker --loglevel=info

# 启动前端（新终端）
cd frontend && npm install && npm run dev
# 验证: http://localhost:3000
```

---

## Step 3：Railway 部署

### 3.1 创建 Railway 项目

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 在项目根目录初始化
railway init
# 输入项目名: partsmind
```

### 3.2 添加托管数据库

在 Railway Dashboard：
1. New Service → Database → **PostgreSQL**
   - 记下 `DATABASE_URL`（Railway 格式需转换为 asyncpg）
2. New Service → Database → **Redis**
   - 记下 `REDIS_URL`

> ⚠ Railway 提供的 DATABASE_URL 格式是 `postgresql://...`
> 需要改为 `postgresql+asyncpg://...` 才能用于 FastAPI

### 3.3 部署后端

```bash
# 创建后端 service
railway service create backend

# 设置环境变量（所有 .env 里的变量都要设置）
railway variables set \
  OPENAI_API_KEY="sk-..." \
  SECRET_KEY="$(openssl rand -hex 32)" \
  ENVIRONMENT="production" \
  DATABASE_URL="postgresql+asyncpg://..." \
  REDIS_URL="redis://..." \
  LANGCHAIN_TRACING_V2="true" \
  LANGCHAIN_API_KEY="ls__..."

# 部署
railway up --service backend
```

### 3.4 运行数据库迁移（部署后第一次）

```bash
railway run --service backend python -m alembic upgrade head
railway run --service backend python scripts/seed/create_admin.py
railway run --service backend python scripts/seed/seed_products.py --synthetic --count 200 --embed
```

### 3.5 部署 Celery Worker

```bash
railway service create worker
railway up --service worker
```

### 3.6 部署前端

```bash
railway service create frontend

railway variables set \
  NEXT_PUBLIC_API_URL="https://your-backend.railway.app"

railway up --service frontend
```

### 3.7 配置自定义域名（可选）

Railway Dashboard → 你的 frontend service → Settings → Custom Domain
输入: `partsmind.yourdomain.com`

Railway 自动颁发 Let's Encrypt HTTPS 证书。

---

## Step 4：验证上线

```bash
# 基础健康检查
curl https://your-backend.railway.app/health

# 预期响应:
# {"status": "ok", "environment": "production"}

# 完整功能验证
curl -X POST https://your-backend.railway.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@partsmind.com","password":"Admin123!"}'
```

---

## 上线 Checklist

运行自动检查脚本：
```bash
bash infra/scripts/pre_deploy_check.sh
```

手动验证清单：
- [ ] `/health` 返回 `{"status":"ok"}`
- [ ] 登录接口正常返回 JWT token
- [ ] 上传一张图片，搜索结果正常返回
- [ ] 发送聊天消息，Agent 正确响应
- [ ] Admin 面板能看到统计数据
- [ ] LangSmith 项目有 trace 记录
- [ ] Sentry 项目已连接（可选）
- [ ] 环境变量中无任何默认占位符

---

## 成本估算（月度）

| 资源 | 用量 | 估算成本 |
|------|------|---------|
| Railway (backend+worker+frontend) | Hobby plan | $5/月 |
| Railway PostgreSQL | 1GB storage | $5/月 |
| Railway Redis | 256MB | $3/月 |
| OpenAI GPT-4o | 1000次对话 × ~500 tokens | ~$5/月 |
| OpenAI Embeddings | 200产品 + 文档 | ~$0.01 一次性 |
| LangSmith | 开发者免费版 | $0 |
| **合计** | | **~$18/月** |

> 演示阶段可进一步降低：使用 gpt-4o-mini（成本降低90%），
> Railway Hobby 计划有 $5 免费额度

---

## 常见问题

**Q: asyncpg 连接失败**
A: 检查 DATABASE_URL 格式是否为 `postgresql+asyncpg://` 而非 `postgresql://`

**Q: Celery worker 连接 Redis 失败**
A: Railway 内网连接用 `redis://redis.railway.internal:6379`，不是外网 URL

**Q: 前端 API 请求跨域报错**
A: 在后端 `ALLOWED_ORIGINS` 环境变量中加入前端的 Railway 域名

**Q: 上传文件报 413**
A: 检查 Nginx `client_max_body_size` 是否设置为 55M
