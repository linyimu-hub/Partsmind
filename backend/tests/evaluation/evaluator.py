"""
tests/evaluation/evaluator.py
──────────────────────────────
LLM-as-Judge evaluator for PartsMind Agent responses.

Pattern: Use GPT-4o to evaluate GPT-4o's answers.
  - Evaluator is given the question, the answer, and scoring rubrics
  - Returns structured scores (0.0–1.0) per dimension
  - This is the same approach used by OpenAI Evals, LangSmith, and RAGAS

Why LLM-as-Judge?
  Human evaluation is gold standard but slow and expensive.
  Rule-based checks (keyword matching) miss nuance.
  LLM-as-Judge is scalable, consistent, and surprisingly accurate
  when given clear rubrics — studies show 80%+ agreement with humans.

Output:
  EvalResult per test case → EvalReport for the full run
  Reports saved as JSON + printed as summary table
"""

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from tests.evaluation.eval_dataset import EVAL_DATASET, EvalCase

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_client = AsyncOpenAI(api_key=settings.openai_api_key)


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    dimension: str
    score: float          # 0.0–1.0
    reasoning: str        # why this score
    passed: bool          # score >= threshold


@dataclass
class EvalResult:
    case_id: str
    scenario: str
    user_message: str
    agent_answer: str
    agent_confidence: float
    latency_ms: int
    tools_used: list[str]

    dimension_scores: list[DimensionScore] = field(default_factory=list)
    keyword_checks: dict[str, bool] = field(default_factory=dict)
    latency_ok: bool = True
    confidence_ok: bool = True
    overall_score: float = 0.0
    passed: bool = False
    error: str | None = None


@dataclass
class EvalReport:
    run_id: str
    timestamp: str
    prompt_versions: dict[str, str]
    total_cases: int
    passed_cases: int
    pass_rate: float
    avg_overall_score: float
    avg_latency_ms: float
    results: list[EvalResult] = field(default_factory=list)
    scores_by_scenario: dict[str, float] = field(default_factory=dict)
    failure_cases: list[str] = field(default_factory=list)


# ── LLM Judge ─────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """\
You are an expert evaluator for an automotive parts AI assistant.

Evaluate the AI's answer on the following dimensions.
Score each dimension from 0.0 to 1.0.

Question asked: {question}
AI answer: {answer}

Scoring rubrics:

answer_relevance (0.0-1.0):
  1.0 = Directly and completely answers the question
  0.7 = Answers the main question but misses minor aspects
  0.4 = Partially relevant, significant gaps
  0.0 = Completely irrelevant or off-topic

source_citation (0.0-1.0):
  1.0 = Cites specific product names or part numbers
  0.5 = Mentions products generally without specifics
  0.0 = No product citation at all

factual_grounding (0.0-1.0):
  1.0 = All claims are grounded in search results, no hallucination
  0.5 = Mostly grounded, minor speculative statements
  0.0 = Invents facts, prices, or specs not in the context

response_format (0.0-1.0):
  1.0 = Clear, well-structured, practical for purchasing decisions
  0.5 = Readable but could be better organized
  0.0 = Hard to read or understand

Return ONLY this JSON:
{{
  "answer_relevance": {{"score": <float>, "reasoning": "<one sentence>"}},
  "source_citation": {{"score": <float>, "reasoning": "<one sentence>"}},
  "factual_grounding": {{"score": <float>, "reasoning": "<one sentence>"}},
  "response_format": {{"score": <float>, "reasoning": "<one sentence>"}}
}}
"""


async def judge_response(question: str, answer: str) -> dict[str, Any]:
    """Call GPT-4o to score an agent response."""
    response = await _client.chat.completions.create(
        model="gpt-4o",
        temperature=0.0,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": JUDGE_PROMPT.format(question=question, answer=answer),
        }],
    )
    raw = response.choices[0].message.content or "{}"
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)


# ── Keyword checker ────────────────────────────────────────────────────────────

def check_keywords(
    answer: str,
    expected_contains: list[str],
    expected_excludes: list[str],
) -> dict[str, bool]:
    """Simple keyword checks — fast, deterministic, no API call needed."""
    answer_lower = answer.lower()
    results = {}
    for kw in expected_contains:
        results[f"contains:{kw}"] = kw.lower() in answer_lower
    for kw in expected_excludes:
        results[f"excludes:{kw}"] = kw.lower() not in answer_lower
    return results


# ── Main evaluator ────────────────────────────────────────────────────────────

async def evaluate_case(
    case: EvalCase,
    agent_response: dict[str, Any],  # from ChatService / Agent
) -> EvalResult:
    """
    Evaluate one agent response against one eval case.
    agent_response should contain: content, confidence, latency_ms, tools_used
    """
    answer = agent_response.get("content", "")
    confidence = agent_response.get("confidence", 0.0)
    latency_ms = agent_response.get("latency_ms", 0)
    tools_used = agent_response.get("tools_used", [])

    result = EvalResult(
        case_id=case.id,
        scenario=case.scenario,
        user_message=case.user_message,
        agent_answer=answer,
        agent_confidence=confidence,
        latency_ms=latency_ms,
        tools_used=tools_used,
    )

    # ── LLM judge scoring ────────────────────────────────────────
    try:
        judge_scores = await judge_response(case.user_message, answer)

        for dimension, threshold in case.expected_criteria.items():
            if dimension in judge_scores:
                score_data = judge_scores[dimension]
                score = score_data["score"]
                result.dimension_scores.append(DimensionScore(
                    dimension=dimension,
                    score=score,
                    reasoning=score_data.get("reasoning", ""),
                    passed=score >= threshold,
                ))

    except Exception as e:
        result.error = f"Judge failed: {e}"
        logger.error("evaluator.judge_failed", case_id=case.id, error=str(e))

    # ── Keyword checks ───────────────────────────────────────────
    result.keyword_checks = check_keywords(
        answer, case.expected_contains, case.expected_excludes
    )

    # ── Latency check ────────────────────────────────────────────
    result.latency_ok = latency_ms <= case.max_latency_ms

    # ── Confidence check ─────────────────────────────────────────
    result.confidence_ok = confidence >= case.min_confidence

    # ── Overall score ─────────────────────────────────────────────
    dim_scores = [ds.score for ds in result.dimension_scores]
    keyword_score = (
        sum(result.keyword_checks.values()) / len(result.keyword_checks)
        if result.keyword_checks else 1.0
    )
    latency_score = 1.0 if result.latency_ok else 0.0

    if dim_scores:
        result.overall_score = round(
            0.6 * (sum(dim_scores) / len(dim_scores))
            + 0.25 * keyword_score
            + 0.15 * latency_score,
            3,
        )
    else:
        result.overall_score = 0.0

    result.passed = (
        result.overall_score >= 0.65
        and result.latency_ok
        and result.confidence_ok
        and all(result.keyword_checks.values())
    )

    return result


async def run_evaluation(
    agent_fn,                      # async callable(user_message, has_image) → response dict
    cases: list[EvalCase] | None = None,
    output_dir: str = "eval_reports",
) -> EvalReport:
    """
    Run the full evaluation suite against the agent.

    agent_fn signature:
        async def agent_fn(user_message: str, has_image: bool) -> dict:
            return {"content": "...", "confidence": 0.8, "latency_ms": 1200, "tools_used": [...]}

    Example (in a test):
        async def mock_agent(msg, has_image):
            response = await chat_service.handle_message(...)
            return {"content": response.content, ...}
        report = await run_evaluation(mock_agent)
    """
    from app.agent.prompts.templates import PROMPT_VERSIONS

    cases = cases or EVAL_DATASET
    run_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print(f"\n{'='*60}")
    print(f"PartsMind Agent Evaluation — {run_id}")
    print(f"Cases: {len(cases)}")
    print(f"{'='*60}\n")

    results: list[EvalResult] = []

    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case.id} ({case.scenario}): {case.user_message[:60]}...")
        _t0 = time.monotonic()

        try:
            agent_response = await agent_fn(case.user_message, case.has_image)
            result = await evaluate_case(case, agent_response)
        except Exception as e:
            logger.error("evaluator.case_failed", case_id=case.id, error=str(e))
            result = EvalResult(
                case_id=case.id, scenario=case.scenario,
                user_message=case.user_message, agent_answer="",
                agent_confidence=0.0, latency_ms=0, tools_used=[],
                error=str(e), passed=False, overall_score=0.0,
            )

        results.append(result)
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"   {status} | score={result.overall_score:.2f} | "
              f"latency={result.latency_ms}ms | confidence={result.agent_confidence:.2f}")

        if result.error:
            print(f"   ⚠ Error: {result.error}")

    # ── Build report ──────────────────────────────────────────────
    passed = [r for r in results if r.passed]
    scores_by_scenario: dict[str, list[float]] = {}
    for r in results:
        scores_by_scenario.setdefault(r.scenario, []).append(r.overall_score)

    report = EvalReport(
        run_id=run_id,
        timestamp=datetime.now().isoformat(),
        prompt_versions=PROMPT_VERSIONS,
        total_cases=len(cases),
        passed_cases=len(passed),
        pass_rate=round(len(passed) / len(cases), 3),
        avg_overall_score=round(sum(r.overall_score for r in results) / len(results), 3),
        avg_latency_ms=round(sum(r.latency_ms for r in results) / len(results), 1),
        results=results,
        scores_by_scenario={
            scenario: round(sum(scores) / len(scores), 3)
            for scenario, scores in scores_by_scenario.items()
        },
        failure_cases=[r.case_id for r in results if not r.passed],
    )

    # ── Print summary ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Pass rate:      {report.pass_rate:.0%} ({report.passed_cases}/{report.total_cases})")
    print(f"Avg score:      {report.avg_overall_score:.3f}")
    print(f"Avg latency:    {report.avg_latency_ms:.0f}ms")
    print("\nBy scenario:")
    for scenario, score in report.scores_by_scenario.items():
        print(f"  {scenario:<20} {score:.3f}")
    if report.failure_cases:
        print(f"\nFailed cases: {', '.join(report.failure_cases)}")
    print(f"{'='*60}\n")

    # ── Save report ────────────────────────────────────────────────
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    report_path = out_dir / f"{run_id}.json"
    report_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    print(f"Report saved: {report_path}")

    return report
