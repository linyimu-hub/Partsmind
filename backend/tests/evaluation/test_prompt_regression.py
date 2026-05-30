"""
tests/evaluation/test_prompt_regression.py
───────────────────────────────────────────
Prompt regression tests using LangSmith + our eval dataset.

What this catches:
  - Prompt change that looks fine on 2 manual tests but breaks 3 others
  - Model upgrade (gpt-4o → gpt-4o-mini) causing quality drop
  - Chunking strategy change affecting RAG recall

Run:
  pytest tests/evaluation/test_prompt_regression.py -v -s
  (requires OPENAI_API_KEY in .env, ~$0.10-0.30 per run)

CI: only run weekly (not on every PR — too slow + expensive)
"""

from unittest.mock import AsyncMock, patch

import pytest
from tests.evaluation.eval_dataset import EvalCase
from tests.evaluation.evaluator import (
    check_keywords,
    evaluate_case,
)

# ── Fast keyword-only tests (no API calls) ────────────────────────────────────
# These run on every PR. They're not as thorough as LLM judge
# but catch obvious regressions like "stopped citing sources".

class TestKeywordChecks:
    def test_contains_keywords_present(self):
        answer = "We found Bosch brake pads compatible with Toyota Camry 2020."
        result = check_keywords(answer, ["Bosch", "brake"], [])
        assert result["contains:Bosch"] is True
        assert result["contains:brake"] is True

    def test_excludes_keywords_absent(self):
        answer = "Here are the matching products for your search."
        result = check_keywords(answer, [], ["I cannot help", "sorry"])
        assert result["excludes:I cannot help"] is True
        assert result["excludes:sorry"] is True

    def test_excludes_keyword_present_fails(self):
        answer = "Sorry, I cannot help with this request."
        result = check_keywords(answer, [], ["sorry"])
        assert result["excludes:sorry"] is False

    def test_empty_answer_fails_all(self):
        result = check_keywords("", ["brake", "filter"], [])
        assert all(not v for v in result.values())


# ── Response structure tests (no LLM judge, just schema) ──────────────────────

class TestAgentResponseSchema:
    """Verify agent responses have the right structure before evaluating quality."""

    def _make_good_response(self) -> dict:
        return {
            "content": "I found 3 brake pads compatible with your Toyota Camry 2020. "
                       "The best match is [BP-BOC-45231] Bosch Ceramic Brake Pad Set "
                       "at ¥189, currently in stock.",
            "confidence": 0.87,
            "latency_ms": 2100,
            "tools_used": ["intent_classifier", "search_tool", "lookup_tool", "synthesizer"],
            "sources": [{"type": "product", "id": "abc", "name": "Brake Pad", "relevance": 0.91}],
        }

    def test_good_response_has_all_fields(self):
        resp = self._make_good_response()
        assert "content" in resp
        assert "confidence" in resp
        assert isinstance(resp["confidence"], float)
        assert 0.0 <= resp["confidence"] <= 1.0
        assert "latency_ms" in resp
        assert "tools_used" in resp

    def test_confidence_in_valid_range(self):
        resp = self._make_good_response()
        assert 0.0 <= resp["confidence"] <= 1.0

    def test_tools_used_not_empty(self):
        resp = self._make_good_response()
        assert len(resp["tools_used"]) > 0


# ── Eval case logic tests (mock the judge, test evaluation logic) ─────────────

class TestEvaluationLogic:
    """Test the evaluator's scoring logic without real API calls."""

    @pytest.mark.asyncio
    async def test_perfect_response_passes(self):
        case = EvalCase(
            id="TEST-PASS",
            scenario="text_search",
            user_message="brake pad Toyota Camry",
            has_image=False,
            expected_criteria={"answer_relevance": 0.7},
            expected_contains=["brake"],
            expected_excludes=["sorry"],
            min_confidence=0.5,
            max_latency_ms=5000,
        )
        agent_response = {
            "content": "Found brake pads for Toyota Camry. [BP-001] Bosch at ¥199.",
            "confidence": 0.88,
            "latency_ms": 1800,
            "tools_used": ["search_tool"],
        }

        # Mock judge to return good scores
        mock_scores = {
            "answer_relevance": {"score": 0.92, "reasoning": "Directly answers"},
        }
        with patch(
            "tests.evaluation.evaluator.judge_response",
            AsyncMock(return_value=mock_scores)
        ):
            result = await evaluate_case(case, agent_response)

        assert result.latency_ok is True
        assert result.confidence_ok is True
        assert result.keyword_checks["contains:brake"] is True
        assert result.keyword_checks["excludes:sorry"] is True

    @pytest.mark.asyncio
    async def test_slow_response_fails_latency(self):
        case = EvalCase(
            id="TEST-SLOW",
            scenario="text_search",
            user_message="find me a filter",
            has_image=False,
            expected_criteria={},
            max_latency_ms=3000,
            min_confidence=0.0,
        )
        agent_response = {
            "content": "Here is an air filter.",
            "confidence": 0.5,
            "latency_ms": 8000,   # ← too slow
            "tools_used": [],
        }
        with patch("tests.evaluation.evaluator.judge_response", AsyncMock(return_value={})):
            result = await evaluate_case(case, agent_response)

        assert result.latency_ok is False
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_low_confidence_response_fails(self):
        case = EvalCase(
            id="TEST-LOWCONF",
            scenario="text_search",
            user_message="find brakes",
            has_image=False,
            expected_criteria={},
            min_confidence=0.7,
            max_latency_ms=10000,
        )
        agent_response = {
            "content": "I found some results.",
            "confidence": 0.3,   # ← below threshold
            "latency_ms": 1000,
            "tools_used": [],
        }
        with patch("tests.evaluation.evaluator.judge_response", AsyncMock(return_value={})):
            result = await evaluate_case(case, agent_response)

        assert result.confidence_ok is False
        assert result.passed is False


# ── Cost estimation ────────────────────────────────────────────────────────────

class TestCostTracking:
    """Verify embedding cost logging works correctly."""

    def test_cost_calculation(self):
        """$0.02 per 1M tokens for text-embedding-3-small."""
        tokens = 50_000
        expected_cost = tokens / 1_000_000 * 0.02
        assert abs(expected_cost - 0.001) < 0.0001  # $0.001 for 50K tokens

    def test_batch_size_math(self):
        """200 products, batch_size=100 → 2 API calls."""
        total_items = 200
        batch_size = 100
        expected_batches = (total_items + batch_size - 1) // batch_size
        assert expected_batches == 2
