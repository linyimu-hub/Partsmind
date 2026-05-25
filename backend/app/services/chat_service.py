"""
app/services/chat_service.py
─────────────────────────────
聊天编排服务 — 同步 + 流式两个入口。
"""

import json
import time
import uuid
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import (
    build_agent,
    classify_intent,
    run_vision,
    run_search,
    run_lookup,
    _llm_generate,
)
from app.agent.state import AgentState
from app.agent.prompts.templates import SYSTEM_PROMPT, SYNTHESIZER_PROMPT
from app.core.config import settings
from app.core.exceptions import AgentTimeoutException, NotFoundException
from app.core.logging import get_logger
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import AgentResponse, ChatRequest, SourceReference

logger = get_logger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Session 管理 ────────────────────────────────────────────
    async def _get_or_create_session(
        self, user: User, session_id: UUID | None
    ) -> ChatSession:
        if session_id:
            result = await self.db.execute(
                select(ChatSession).where(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user.id,
                )
            )
            session = result.scalar_one_or_none()
            if not session:
                raise NotFoundException(f"Session {session_id} not found")
            return session

        session = ChatSession(user_id=user.id)
        self.db.add(session)
        await self.db.flush()
        return session

    async def _load_history(self, session_id: UUID) -> list[dict[str, str]]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        )
        messages = result.scalars().all()
        return [
            {"role": m.role, "content": m.content}
            for m in reversed(messages)
        ]

    # ── 同步聊天（原版本，保留作为 fallback） ──────────────────
    async def handle_message(
        self, request: ChatRequest, user: User
    ) -> AgentResponse:
        t_start = time.monotonic()

        session = await self._get_or_create_session(user, request.session_id)
        history = await self._load_history(session.id)

        user_msg = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.message,
        )
        self.db.add(user_msg)
        await self.db.flush()

        if not history:
            title = request.message[:80] + ("…" if len(request.message) > 80 else "")
            session.title = title

        initial_state: AgentState = {
            "user_message": request.message,
            "image_base64": request.image_base64,
            "image_mime_type": request.image_mime_type,
            "session_id": str(session.id),
            "user_id": str(user.id),
            "chat_history": history,
            "search_results": [],
            "sources": [],
            "tools_used": [],
            "needs_human_review": False,
            "retry_count": 0,
        }

        try:
            agent = build_agent(self.db)
            final_state = await agent.ainvoke(
                initial_state,
                config={
                    "recursion_limit": settings.agent_max_iterations,
                    "metadata": {
                        "session_id": str(session.id),
                        "user_id": str(user.id),
                    },
                },
            )
        except Exception as e:
            logger.error("chat_service.agent_failed", error=str(e), session_id=str(session.id))
            raise AgentTimeoutException(f"Agent failed: {e}")

        latency_ms = int((time.monotonic() - t_start) * 1000)
        answer = final_state.get("answer", "I was unable to find an answer.")
        sources_raw = final_state.get("sources", [])
        confidence = final_state.get("confidence", 0.0)
        tools_used = list(set(final_state.get("tools_used", [])))

        assistant_msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer,
            sources=sources_raw,
            confidence=confidence,
            latency_ms=latency_ms,
            tools_used=tools_used,
        )
        self.db.add(assistant_msg)
        await self.db.flush()

        return AgentResponse(
            session_id=session.id,
            message_id=assistant_msg.id,
            content=answer,
            sources=[SourceReference(**s) for s in sources_raw],
            confidence=confidence,
            tools_used=tools_used,
            latency_ms=latency_ms,
            needs_human_review=final_state.get("needs_human_review", False),
        )

    # ── 流式聊天（生成器，SSE 推流） ────────────────────────────
    async def handle_message_stream(self, request: ChatRequest, user: User):
        """
        SSE 事件类型：
          session  → 新会话 ID
          tool     → 当前调用的工具
          sources  → 来源引用
          token    → LLM 生成的字符片段
          done     → 完成，携带最终 metadata
          error    → 出错
        """
        t_start = time.monotonic()

        try:
            # 1. session + 历史
            session = await self._get_or_create_session(user, request.session_id)
            history = await self._load_history(session.id)

            user_msg = ChatMessage(
                session_id=session.id,
                role="user",
                content=request.message,
            )
            self.db.add(user_msg)
            await self.db.flush()

            if not history:
                title = request.message[:80] + ("…" if len(request.message) > 80 else "")
                session.title = title

            yield f"event: session\ndata: {json.dumps({'session_id': str(session.id)})}\n\n"

            # 2. 前置流程（搜索 + lookup）
            state: AgentState = {
                "user_message": request.message,
                "image_base64": request.image_base64,
                "image_mime_type": request.image_mime_type,
                "session_id": str(session.id),
                "user_id": str(user.id),
                "chat_history": history,
                "search_results": [],
                "sources": [],
                "tools_used": [],
                "needs_human_review": False,
                "retry_count": 0,
            }

            yield f"event: tool\ndata: {json.dumps({'tool': 'classify_intent'})}\n\n"
            classify_out = await classify_intent(state, self.db)
            state.update(classify_out)

            if state.get("image_base64"):
                yield f"event: tool\ndata: {json.dumps({'tool': 'vision'})}\n\n"
                vision_out = await run_vision(state, self.db)
                state.update(vision_out)

            yield f"event: tool\ndata: {json.dumps({'tool': 'search'})}\n\n"
            search_out = await run_search(state, self.db)
            state.update(search_out)

            yield f"event: tool\ndata: {json.dumps({'tool': 'lookup'})}\n\n"
            lookup_out = await run_lookup(state, self.db)
            state.update(lookup_out)

            # 3. 构建 sources
            product_details = state.get("product_details", [])
            search_results = state.get("search_results", [])
            document_results = state.get("document_results", [])

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
            for doc in document_results[:5]:
                sources.append({
                    "type": "document",
                    "id": doc["chunk_id"],
                    "name": doc["document_name"],
                    "excerpt": doc["content"][:200],
                    "relevance": round(doc["similarity_score"], 3),
                })

            yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"

            # 4. 构建 prompt
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
                    f"   Specs: {json.dumps(product.get('specs', {}), ensure_ascii=False)}"
                )

            doc_for_prompt = []
            for i, doc in enumerate(document_results[:5], 1):
                doc_for_prompt.append(f"[文档 {i}: {doc['document_name']}]\n{doc['content']}")
            doc_section = "\n\n".join(doc_for_prompt) if doc_for_prompt else "（无相关文档内容）"

            combined_context = "\n\n".join(results_for_prompt) or "No products found."
            combined_context += f"\n\n## 参考文档内容:\n{doc_section}"

            messages = [SystemMessage(content=SYSTEM_PROMPT.format(company_name="源尧兴实业"))]
            for h in history[-10:]:
                if h["role"] == "user":
                    messages.append(HumanMessage(content=h["content"]))
                elif h["role"] == "assistant":
                    messages.append(AIMessage(content=h["content"]))
            messages.append(HumanMessage(
                content=SYNTHESIZER_PROMPT.format(
                    user_message=request.message,
                    image_context="",
                    search_results=combined_context,
                    compatibility_context="",
                )
            ))

            # 5. 流式生成
            yield f"event: tool\ndata: {json.dumps({'tool': 'synthesizer'})}\n\n"

            full_answer = ""
            async for chunk in _llm_generate.astream(messages):
                token = chunk.content
                if token:
                    full_answer += token
                    yield f"event: token\ndata: {json.dumps({'text': token})}\n\n"

            # 6. 保存
            latency_ms = int((time.monotonic() - t_start) * 1000)
            confidence = 0.7
            tools_used = list(set(state.get("tools_used", []) + ["synthesizer"]))

            assistant_msg = ChatMessage(
                session_id=session.id,
                role="assistant",
                content=full_answer,
                sources=sources,
                confidence=confidence,
                latency_ms=latency_ms,
                tools_used=tools_used,
            )
            self.db.add(assistant_msg)
            await self.db.commit()

            yield (
                f"event: done\n"
                f"data: {json.dumps({'message_id': str(assistant_msg.id), 'latency_ms': latency_ms, 'confidence': confidence, 'tools_used': tools_used})}\n\n"
            )

        except Exception as e:
            logger.error("chat_stream.failed", error=str(e))
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
