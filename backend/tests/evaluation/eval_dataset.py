"""
tests/evaluation/eval_dataset.py
──────────────────────────────────
Golden evaluation dataset for PartsMind Agent.

Structure:
  EvalCase: one test case — input + expected output criteria
  EVAL_DATASET: the full set of cases, organized by scenario type

Why this matters:
  When you change a prompt (e.g. SYNTHESIZER_PROMPT v1.3 → v1.4),
  you run this eval and compare scores. If score drops, you revert.
  This is how production AI teams prevent regressions.

Scoring dimensions (each 0.0–1.0):
  - answer_relevance:   does the answer address the question?
  - source_citation:    does it cite specific products?
  - factual_grounding:  does it avoid hallucinating specs?
  - confidence_calibration: is confidence score appropriate?
  - response_format:    is the answer well-structured?
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalCase:
    id: str
    scenario: str           # "image_search" | "text_search" | "qa" | "edge_case"
    user_message: str
    has_image: bool
    expected_criteria: dict[str, Any]
    # What we expect to see in a good answer
    expected_contains: list[str] = field(default_factory=list)
    # What we never want to see
    expected_excludes: list[str] = field(default_factory=list)
    min_confidence: float = 0.5
    max_latency_ms: int = 8000


EVAL_DATASET: list[EvalCase] = [

    # ── Text search scenarios ──────────────────────────────────────────────────
    EvalCase(
        id="TS-001",
        scenario="text_search",
        user_message="我需要找丰田凯美瑞2020款的前刹车片",
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.8,
            "source_citation": 0.9,   # must cite product part numbers
            "factual_grounding": 0.85,
        },
        expected_contains=["刹车片", "凯美瑞"],
        expected_excludes=["抱歉，我无法", "我不知道"],
        min_confidence=0.6,
        max_latency_ms=6000,
    ),
    EvalCase(
        id="TS-002",
        scenario="text_search",
        user_message="Bosch oil filter for Honda Civic 2019",
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.8,
            "source_citation": 0.85,
        },
        expected_contains=["Bosch", "filter"],
        expected_excludes=["I cannot", "I don't know"],
        min_confidence=0.55,
    ),
    EvalCase(
        id="TS-003",
        scenario="text_search",
        user_message="ceramic brake pads under 200 yuan",
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.75,
            "source_citation": 0.8,
        },
        expected_contains=["ceramic", "brake"],
        min_confidence=0.5,
    ),

    # ── Q&A scenarios ─────────────────────────────────────────────────────────
    EvalCase(
        id="QA-001",
        scenario="qa",
        user_message="刹车片和刹车盘有什么区别？我需要同时换吗？",
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.85,
            "factual_grounding": 0.9,
        },
        expected_contains=["刹车片", "刹车盘"],
        expected_excludes=["我不确定", "请联系人工"],
        min_confidence=0.6,
    ),
    EvalCase(
        id="QA-002",
        scenario="qa",
        user_message="What is the difference between OEM and aftermarket parts?",
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.8,
            "factual_grounding": 0.85,
        },
        expected_contains=["OEM", "aftermarket"],
        min_confidence=0.6,
    ),

    # ── Image search scenarios ─────────────────────────────────────────────────
    EvalCase(
        id="IMG-001",
        scenario="image_search",
        user_message="这是什么零件？帮我找同款",
        has_image=True,
        expected_criteria={
            "answer_relevance": 0.75,
            "source_citation": 0.8,
        },
        expected_contains=["找到", "零件"],
        min_confidence=0.45,   # lower — vision identification uncertain
        max_latency_ms=10000,  # vision adds latency
    ),

    # ── Hybrid scenarios ──────────────────────────────────────────────────────
    EvalCase(
        id="HYB-001",
        scenario="hybrid",
        user_message="图片里的这个零件，我需要适配2021款本田雅阁的",
        has_image=True,
        expected_criteria={
            "answer_relevance": 0.8,
            "source_citation": 0.85,
        },
        expected_contains=["雅阁", "适配"],
        min_confidence=0.5,
        max_latency_ms=12000,
    ),

    # ── Edge cases ────────────────────────────────────────────────────────────
    EvalCase(
        id="EDGE-001",
        scenario="edge_case",
        user_message="你好",      # too vague — should ask for clarification
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.5,
        },
        expected_excludes=["Part number:", "¥"],  # should NOT return product results
        min_confidence=0.0,    # low confidence expected and acceptable
    ),
    EvalCase(
        id="EDGE-002",
        scenario="edge_case",
        user_message="飞机发动机涡轮叶片",  # out of domain
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.4,
        },
        # Should say it can't find the item, not hallucinate
        expected_contains=["找不到", "没有找到", "not found", "couldn't find"],
        min_confidence=0.0,
    ),
    EvalCase(
        id="EDGE-003",
        scenario="edge_case",
        user_message="帮我查一下库存还有多少 BP-BOC-45231",  # specific part number
        has_image=False,
        expected_criteria={
            "answer_relevance": 0.85,
            "source_citation": 1.0,   # MUST cite the exact part
            "factual_grounding": 0.9,
        },
        expected_contains=["库存", "BP-BOC-45231"],
        min_confidence=0.7,
    ),
]
