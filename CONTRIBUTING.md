# Contributing Guide

## Branch naming

```
feat/   — new feature        e.g. feat/image-search-api
fix/    — bug fix             e.g. fix/vision-tool-timeout
chore/  — tooling, deps       e.g. chore/upgrade-langchain
docs/   — documentation       e.g. docs/api-endpoints
test/   — adding tests        e.g. test/agent-evaluation
refactor/ — code restructure  e.g. refactor/search-service
```

## Commit message format (Conventional Commits)

```
<type>(<scope>): <short summary>

[optional body]

[optional footer: BREAKING CHANGE / closes #issue]
```

### Types
| Type | When to use |
|------|-------------|
| `feat` | New user-facing feature |
| `fix` | Bug fix |
| `chore` | Deps, tooling, CI changes |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `refactor` | Code change with no behavior change |
| `perf` | Performance improvement |

### Examples
```
feat(search): add image upload endpoint with vision tool integration

fix(agent): handle openai timeout gracefully with retry logic

chore(deps): upgrade langchain to 0.2.1

test(rag): add integration tests for vector search pipeline
```

## Pull Request rules

1. Every PR requires at least 1 review
2. CI must pass before merge (lint + tests + build)
3. No direct pushes to `main`
4. Squash merge into `main` to keep history clean
5. Delete branch after merge

## Local dev setup

```bash
cp .env.example .env
# fill in OPENAI_API_KEY and SECRET_KEY

docker compose up -d db redis
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```
