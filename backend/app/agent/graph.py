"""
app/agent/graph.py
──────────────────
PartsMind LangGraph Agent — the orchestration core.

Architecture:
  Each node is a pure async function: (state) → partial state update
  LangGraph merges the update into the full state automatically.

  Nodes:
    classify_intent     → determines routing
    run_vision          → image → part identification
    run_search          → vector + keyword search
    run_lookup          → fetch full product details
    check_compatibility → vehicle fitment check
    synthesize          → generate final answer with citations
    confidence_gate     → score result, flag if human review needed

  Conditional edges:
    after classify_intent → route to vision | search | both
    after synthesize      → route to gate (always, but gate may loop back)

LangSmith tracing is automatic when LANGCHAIN_TRACING_V2=true.
Every node execution, LLM call, and tool call is captured.
"""

import json
import time
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state import AgentState
from app.agent.prompts.templates import (
    SYSTEM_PROMPT,
    INTENT_CLASSIFIER_PROMPT,
    SYNTHESIZER_PROMPT,
    LOW_CONFIDENCE_PROMPT,
    PROMPT_VERSIONS,
)
from app.agent.tools.vision_tool import run_vision_tool
from app.agent.tools.search_tool import hybrid_search, semantic_search, embed_text
from app.agent.tools.document_search_tool import search_documents
from app.agent.tools.lookup_tool import lookup_products, check_vehicle_compatibility
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── LLM instances ──────────────────────────────────────────────────────────────
# Separate instances for different temperature needs
_llm_precise = ChatOpenAI(
    model=settings.openai_model,
    temperature=0.0,
    max_tokens=600,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
)

_llm_generate = ChatOpenAI(
    model=settings.openai_model,
    temperature=0.2,
    max_tokens=settings.openai_max_tokens,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
)

# ── Node: Intent Classifier ────────────────────────────────────────────────────
async def classify_intent(state: AgentState, db: AsyncSession) -> dict[str, Any]:
    """
    Classify user intent and extract structured filters.
    Returns: intent, and sets up filters for downstream tools.
    """
    prompt = INTENT_CLASSIFIER_PROMPT.format(
        user_message=state["user_message"],
        has_image=bool(state.get("image_base64")),
    )

    response = await _llm_precise.ainvoke([HumanMessage(content=prompt)])
    raw = response.content

    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        classification = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("classify_intent.parse_failed", raw=raw[:200])
        # Fallback: if image present → image_search, else text_search
        classification = {
            "intent": "image_search" if state.get("image_base64") else "text_search",
            "confidence": 0.5,
            "extracted_filters": {},
            "search_keywords": [state["user_message"]],
        }

    logger.info(
        "classify_intent.done",
        intent=classification.get("intent"),
        confidence=classification.get("confidence"),
    )

    return {
        "intent": classification["intent"],
        "tools_used": ["intent_classifier"],
        "_filters": classification.get("extracted_filters", {}),      # temp storage
        "_keywords": classification.get("search_keywords", []),       # temp storage
    }


# ── Node: Vision Tool ──────────────────────────────────────────────────────────
async def run_vision(state: AgentState, db: AsyncSession) -> dict[str, Any]:
    """Run GPT-4o Vision to identify the part in the image."""
    image_b64 = state.get("image_base64")
    if not image_b64:
        return {"identified_part": None}

    try:
        identified = await run_vision_tool(
            image_base64=image_b64,
            mime_type=state.get("image_mime_type", "image/jpeg"),
        )
        return {
            "identified_part": identified,
            "tools_used": ["vision_tool"],
        }
    except Exception as e:
        logger.error("run_vision.failed", error=str(e))
        return {"identified_part": None, "error": f"Image identification failed: {e}"}


# ── Node: Semantic Search ──────────────────────────────────────────────────────
async def run_search(state: AgentState, db: AsyncSession) -> dict[str, Any]:
    """
    Build search query from intent + vision output, run hybrid search on both
    products AND documents (RAG over knowledge base).
    """
    filters = state.get("_filters", {})

    if state.get("identified_part"):
        part = state["identified_part"]
        query_parts = [part.get("part_name", "")]
        query_parts.extend(part.get("search_terms", []))
        if part.get("brand_visible"):
            query_parts.append(part["brand_visible"])
        search_query = " ".join(filter(None, query_parts))
    else:
        keywords = state.get("_keywords", [state["user_message"]])
        search_query = " ".join(keywords)
        # ── 查询改写：结合对话历史 ──
    history = state.get("chat_history", [])
    if history and len(state["user_message"]) < 30:
        # 短查询且有历史，用LLM改写成完整查询
        last_assistant = ""
        for h in reversed(history):
            if h["role"] == "assistant":
                last_assistant = h["content"][:300]
                break
        if last_assistant:
            rewrite_prompt = (
                f"基于以下对话，把用户当前的简短问题改写为完整的搜索查询。\n\n"
                f"AI上一轮回答：{last_assistant}\n"
                f"用户当前问题：{state['user_message']}\n\n"
                f"输出完整的搜索查询（一句话，包含所有关键信息，不要解释）："
            )
            try:
                rewrite_resp = await _llm_precise.ainvoke([HumanMessage(content=rewrite_prompt)])
                rewritten = rewrite_resp.content.strip().strip('"')
                if rewritten and len(rewritten) > len(state["user_message"]):
                    logger.info("query_rewrite", original=state["user_message"], rewritten=rewritten)
                    search_query = rewritten
            except Exception as e:
                logger.warning("query_rewrite.failed", error=str(e))

    # 搜产品
    product_results = await hybrid_search(
        db=db,
        query=search_query,
        top_k=settings.rag_top_k,
        category=filters.get("category"),
        brand=filters.get("brand"),
        max_price=filters.get("max_price"),
    )

    # 搜文档（RAG over knowledge base）
    doc_results = await search_documents(
        db=db,
        query=search_query,
        top_k=3,
    )

    logger.info(
        "run_search.done",
        query=search_query[:80],
        products=len(product_results),
        documents=len(doc_results),
    )

    return {
        "search_results": product_results,
        "document_results": doc_results,
        "search_query_used": search_query,
        "tools_used": ["search_tool", "document_search"],
    }


# ── Node: Product Lookup ───────────────────────────────────────────────────────
async def run_lookup(state: AgentState, db: AsyncSession) -> dict[str, Any]:
    """
    Fetch full product details for top search candidates.
    Also runs compatibility check if vehicle info was provided.
    """
    search_results = state.get("search_results", [])
    if not search_results:
        return {"product_details": [], "compatibility_results": []}

    # Take top 5 for detail lookup (balance between thoroughness and latency)
    top_ids = [str(r["id"]) for r in search_results[:5]]
    product_details = await lookup_products(db, top_ids)

    # Run compatibility check if vehicle filters present
    filters = state.get("_filters", {})
    compatibility_results = []

    vehicle_make = filters.get("vehicle_make")
    vehicle_model = filters.get("vehicle_model")
    vehicle_year = filters.get("vehicle_year")

    if any([vehicle_make, vehicle_model, vehicle_year]):
        for product in product_details:
            compat = check_vehicle_compatibility(
                product, vehicle_make, vehicle_model, vehicle_year
            )
            compatibility_results.append({
                "product_id": product["id"],
                "product_name": product["name"],
                **compat,
            })

    return {
        "product_details": product_details,
        "compatibility_results": compatibility_results,
        "tools_used": ["lookup_tool"],
    }


# ── Node: Synthesizer ──────────────────────────────────────────────────────────
async def synthesize(state: AgentState, db: AsyncSession) -> dict[str, Any]:
    """
    Generate the final answer combining product search + document RAG.
    """
    product_details = state.get("product_details", [])
    search_results = state.get("search_results", [])
    document_results = state.get("document_results", [])
    compatibility_results = state.get("compatibility_results", [])
    identified_part = state.get("identified_part")

    image_context = ""
    if identified_part:
        image_context = (
            f"Image analysis identified: {identified_part.get('part_name')} "
            f"(confidence: {identified_part.get('identification_confidence', 0):.0%})\n"
            f"Key attributes: {json.dumps(identified_part.get('key_attributes', {}))}"
        )

    # 产品搜索结果
    results_for_prompt = []
    for i, product in enumerate(product_details[:5], 1):
        score = next(
            (r["similarity_score"] for r in search_results if str(r["id"]) == product["id"]),
            0.0,
        )
        results_for_prompt.append(
            f"{i}. [{product['part_number']}] {product['name']}\n"
            f"   Brand: {product.get('brand', 'N/A')} | "
            f"Price: ¥{product.get('price', 'N/A')} | "
            f"Stock: {'In stock' if product.get('in_stock') else 'Out of stock'}\n"
            f"   Relevance: {score:.0%}\n"
            f"   Specs: {json.dumps(product.get('specs', {}), ensure_ascii=False)}"
        )

    # 文档检索结果（RAG）
    doc_for_prompt = []
    for i, doc in enumerate(document_results[:3], 1):
        doc_for_prompt.append(
            f"[文档 {i}: {doc['document_name']}]\n{doc['content']}"
        )
    doc_section = "\n\n".join(doc_for_prompt) if doc_for_prompt else "（无相关文档内容）"

    compat_context = ""
    if compatibility_results:
        compat_lines = []
        for c in compatibility_results:
            status = "✓" if c.get("compatible") else "✗" if c.get("compatible") is False else "?"
            compat_lines.append(f"  {status} {c['product_name']}: {c['reason']}")
        compat_context = "Vehicle compatibility:\n" + "\n".join(compat_lines)

    # 把文档内容加到 search_results 段里
    combined_context = "\n\n".join(results_for_prompt) or "No products found."
    combined_context += f"\n\n## 参考文档内容:\n{doc_section}"

    system_msg = SystemMessage(
        content=SYSTEM_PROMPT.format(company_name="源尧兴实业")
    )
    
    # 构建包含历史对话的消息列表
    messages = [system_msg]
    
    # 加入历史对话（最近5轮，避免context过长）
    history = state.get("chat_history", [])
    for h in history[-10:]:   # 最近10条消息（5轮对话）
        if h["role"] == "user":
            messages.append(HumanMessage(content=h["content"]))
        elif h["role"] == "assistant":
            from langchain_core.messages import AIMessage
            messages.append(AIMessage(content=h["content"]))
    
    # 当前问题
    user_msg = HumanMessage(
        content=SYNTHESIZER_PROMPT.format(
            user_message=state["user_message"],
            image_context=image_context,
            search_results=combined_context,
            compatibility_context=compat_context,
        )
    )
    messages.append(user_msg)

    response = await _llm_generate.ainvoke(messages)

    response = await _llm_generate.ainvoke([system_msg, user_msg])
    answer = response.content

    # 构建 sources（产品 + 文档）
    sources = []
    for product in product_details[:5]:
        score = next(
            (r["similarity_score"] for r in search_results if str(r["id"]) == product["id"]),
            0.0,
        )
        sources.append({
            "type": "product",
            "id": product["id"],
            "name": product["name"],
            "part_number": product["part_number"],
            "relevance": round(float(score), 3),
            "url": product.get("image_url"),
        })

    for doc in document_results[:3]:
        sources.append({
            "type": "document",
            "id": doc["chunk_id"],
            "name": doc["document_name"],
            "excerpt": doc["content"][:200],
            "relevance": round(doc["similarity_score"], 3),
        })

    logger.info("synthesize.done", answer_len=len(answer), sources=len(sources))

    return {
        "answer": answer,
        "sources": sources,
        "tools_used": ["synthesizer"],
    }


# ── Node: Confidence Gate ──────────────────────────────────────────────────────
async def confidence_gate(state: AgentState, db: AsyncSession) -> dict[str, Any]:
    """
    Score the response confidence and decide if human review is needed.

    Confidence is a composite of:
    - Search result quality (top similarity score)
    - Vision identification confidence (if applicable)
    - Whether any results were found at all
    """
    search_results = state.get("search_results", [])
    identified_part = state.get("identified_part")

    # Component scores
    search_score = search_results[0]["similarity_score"] if search_results else 0.0
    vision_score = (
        identified_part.get("identification_confidence", 1.0)
        if identified_part else 1.0
    )
    has_results = 1.0 if search_results else 0.0

    # Weighted composite (tunable)
    confidence = round(
        0.5 * search_score + 0.3 * vision_score + 0.2 * has_results,
        3,
    )

    needs_review = confidence < settings.rag_similarity_threshold

    if needs_review:
        logger.warning(
            "confidence_gate.low_confidence",
            confidence=confidence,
            threshold=settings.rag_similarity_threshold,
        )

    return {
        "confidence": confidence,
        "needs_human_review": needs_review,
    }


# ── Conditional edge: after intent classification ──────────────────────────────
def route_after_intent(state: AgentState) -> str:
    """Route to the appropriate first tool based on intent."""
    intent = state.get("intent", "text_search")
    if intent == "image_search" and state.get("image_base64"):
        return "vision"
    return "search"   # text_search | qa | hybrid all start with search


def route_after_vision(state: AgentState) -> str:
    """Always proceed to search after vision (vision output feeds search query)."""
    return "search"


# ── Graph construction ─────────────────────────────────────────────────────────
def build_agent(db: AsyncSession) -> Any:
    """
    Construct and compile the LangGraph agent.
    db is injected here so all nodes share the same session.

    Returns a compiled graph (callable like a function).
    """
    # Wrap nodes to inject db dependency
    # LangGraph passes only state to nodes; we close over db here.
    async def _classify(state: AgentState) -> dict:
        return await classify_intent(state, db)

    async def _vision(state: AgentState) -> dict:
        return await run_vision(state, db)

    async def _search(state: AgentState) -> dict:
        return await run_search(state, db)

    async def _lookup(state: AgentState) -> dict:
        return await run_lookup(state, db)

    async def _synthesize(state: AgentState) -> dict:
        return await synthesize(state, db)

    async def _gate(state: AgentState) -> dict:
        return await confidence_gate(state, db)

    # Build graph
    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("classify", _classify)
    builder.add_node("vision", _vision)
    builder.add_node("search", _search)
    builder.add_node("lookup", _lookup)
    builder.add_node("synthesize", _synthesize)
    builder.add_node("gate", _gate)

    # Edges
    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_intent,
        {"vision": "vision", "search": "search"},
    )
    builder.add_conditional_edges(
        "vision",
        route_after_vision,
        {"search": "search"},
    )
    builder.add_edge("search", "lookup")
    builder.add_edge("lookup", "synthesize")
    builder.add_edge("synthesize", "gate")
    builder.add_edge("gate", END)

    return builder.compile()
