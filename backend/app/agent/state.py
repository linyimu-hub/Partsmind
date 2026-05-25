"""
app/agent/state.py
──────────────────
LangGraph AgentState — the single data container that flows
through every node in the graph.

Design rules:
1. ALL fields are Optional with defaults — nodes only populate
   what they produce, others remain None.
2. Use TypedDict (not dataclass/Pydantic) — LangGraph requirement.
3. Annotate list fields with `Annotated[list, add]` so LangGraph
   APPENDS to them rather than replacing on each node update.

Data flow example:
  __start__     → fills: user_message, image_base64, session_id
  intent        → fills: intent
  vision_tool   → fills: identified_part
  search_tool   → fills: search_results
  lookup_tool   → fills: product_details
  synthesizer   → fills: answer, sources
  conf_gate     → fills: confidence, needs_human_review, tools_used
  __end__       → reads: answer, sources, confidence, ...
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict
import operator


class AgentState(TypedDict, total=False):
    # ── Input ──────────────────────────────────────────────────
    user_message: str
    image_base64: str | None          # base64-encoded image (optional)
    image_mime_type: str | None       # "image/jpeg" | "image/png"
    session_id: str | None
    user_id: str | None

    # Conversation history for multi-turn context
    # Annotated with operator.add so each node appends, not replaces
    chat_history: Annotated[list[dict[str, str]], operator.add]

    # ── Intent classification ──────────────────────────────────
    # "image_search" | "text_search" | "qa" | "hybrid"
    intent: str | None

    # ── Vision tool output ─────────────────────────────────────
    identified_part: dict[str, Any] | None
    # e.g. {"name": "brake pad", "brand": "Bosch", "part_number": "BP-123",
    #        "attributes": {"material": "ceramic", "position": "front"}}

    # ── Search tool output ─────────────────────────────────────
    search_results: list[dict[str, Any]]      # raw candidates from pgvector
    document_results: list[dict[str, Any]]
    search_query_used: str | None             # for debugging / observability

    # ── Lookup tool output ────────────────────────────────────
    product_details: list[dict[str, Any]]     # enriched with price, stock, specs
    compatibility_results: list[dict[str, Any]]

    # ── Synthesizer output ────────────────────────────────────
    answer: str | None
    sources: Annotated[list[dict[str, Any]], operator.add]

    # ── Confidence gate output ────────────────────────────────
    confidence: float | None
    needs_human_review: bool
    tools_used: Annotated[list[str], operator.add]

    # ── Error handling ────────────────────────────────────────
    error: str | None
    retry_count: int
