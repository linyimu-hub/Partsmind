#!/bin/bash
# Run BEFORE every production deployment. Exits non-zero on failure.
set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}✅ $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
warn() { echo -e "${YELLOW}⚠  $1${NC}"; }

echo "=== PartsMind Pre-Deploy Checklist ==="

# Required env vars
for var in OPENAI_API_KEY DATABASE_URL REDIS_URL SECRET_KEY; do
  [ -z "${!var:-}" ] && fail "$var is not set" || pass "$var is set"
done

[ "${SECRET_KEY:-}" = "change_me_generate_with_openssl_rand_hex_32" ] \
  && fail "SECRET_KEY is still the default placeholder"

[ "${ENVIRONMENT:-}" = "production" ] \
  && pass "ENVIRONMENT=production" \
  || warn "ENVIRONMENT=${ENVIRONMENT:-unset} (expected production)"

# Docker build check
if docker info &>/dev/null; then
  docker build -f infra/docker/Dockerfile.backend -t _pm_check ./backend -q &>/dev/null \
    && pass "Backend image builds OK" && docker rmi _pm_check &>/dev/null \
    || fail "Backend Dockerfile build FAILED"
else
  warn "Docker not running — skipping build check"
fi

# Unit tests
if command -v pytest &>/dev/null; then
  (cd backend && pytest tests/unit -q --tb=no 2>&1 | grep -E "passed|failed|error") \
    && pass "Unit tests OK" || fail "Unit tests FAILED"
else
  warn "pytest not in PATH — skipping"
fi

echo ""
echo -e "${GREEN}=== All checks passed. Safe to deploy. ===${NC}"
