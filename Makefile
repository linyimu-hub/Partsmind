# PartsMind — Developer shortcuts
# Usage: make <target>

.PHONY: up down logs shell-backend migrate seed test lint

# ── Docker ───────────────────────────────────────────────────────────────────
up:
	docker compose up -d db redis
	@echo "✅ DB + Redis running. Start backend: make dev-backend"

down:
	docker compose down

logs:
	docker compose logs -f backend worker

# ── Local dev (without Docker backend) ───────────────────────────────────────
dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-worker:
	cd backend && celery -A app.core.celery_app worker -Q ingestion,default --loglevel=info

dev-frontend:
	cd frontend && npm run dev

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	cd backend && alembic upgrade head

migrate-down:
	cd backend && alembic downgrade -1

migrate-new:
	cd backend && alembic revision --autogenerate -m "$(msg)"

# ── Data seeding ──────────────────────────────────────────────────────────────
seed:
	cd backend && python ../scripts/seed/seed_products.py --synthetic --count 200 --embed

seed-admin:
	cd backend && python ../scripts/seed/create_admin.py

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	cd backend && pytest -v

test-unit:
	cd backend && pytest tests/unit -v

test-integration:
	cd backend && pytest tests/integration -v

test-cov:
	cd backend && pytest --cov=app --cov-report=html && open htmlcov/index.html

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	cd backend && ruff check . && ruff format --check .

format:
	cd backend && ruff format . && ruff check --fix .

typecheck:
	cd backend && mypy app --ignore-missing-imports

# ── Full stack (Docker) ───────────────────────────────────────────────────────
stack-up:
	docker compose up -d

stack-down:
	docker compose down -v

stack-logs:
	docker compose logs -f
