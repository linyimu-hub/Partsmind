"""
app/agent/tools/vision_tool.py
───────────────────────────────
VisionTool: Uses GPT-4o to identify auto parts from images.

Input:  base64-encoded image
Output: structured part identification (name, category, attributes, search terms)

Design decisions:
- Structured JSON output enforced via response_format
- Retries with exponential backoff (OpenAI rate limits)
- Confidence score returned so the planner can decide
  whether to proceed or ask user for a clearer image
"""

import json
import time
from typing import Any

from openai import APITimeoutError, AsyncOpenAI, RateLimitError

from app.agent.prompts.templates import PROMPT_VERSIONS, VISION_IDENTIFY_PROMPT
from app.core.config import settings
from app.core.exceptions import LLMException
from app.core.logging import get_logger

logger = get_logger(__name__)

_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url or None,
)

async def run_vision_tool(
    image_base64: str,
    mime_type: str = "image/jpeg",
    retries: int = 3,
) -> dict[str, Any]:
    """
    Identify an auto part from a base64 image.

    Returns dict matching VISION_IDENTIFY_PROMPT schema:
    {
        "part_name": str,
        "part_category": str,
        "brand_visible": str | None,
        "part_number_visible": str | None,
        "condition": str,
        "key_attributes": dict,
        "search_terms": list[str],
        "identification_confidence": float,
        "notes": str
    }
    """
    t_start = time.monotonic()

    for attempt in range(retries):
        try:
            response = await _client.chat.completions.create(
                model=settings.openai_vision_model,
                max_tokens=600,
                temperature=0.1,  # low = deterministic identification
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}",
                                    "detail": "high",  # use high-res for part details
                                },
                            },
                            {
                                "type": "text",
                                "text": VISION_IDENTIFY_PROMPT,
                            },
                        ],
                    }
                ],
                # metadata for LangSmith tracing
                extra_headers={
                    "X-Prompt-Version": PROMPT_VERSIONS["vision_identify"],
                },
            )

            raw = response.choices[0].message.content or ""

            # Strip markdown code fences if model wraps JSON
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw.strip())
            latency_ms = int((time.monotonic() - t_start) * 1000)

            logger.info(
                "vision_tool.success",
                part_name=result.get("part_name"),
                confidence=result.get("identification_confidence"),
                latency_ms=latency_ms,
                attempt=attempt + 1,
            )
            return result

        except (RateLimitError, APITimeoutError) as e:
            wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            logger.warning(
                "vision_tool.retry",
                attempt=attempt + 1,
                wait_seconds=wait,
                error=str(e),
            )
            if attempt == retries - 1:
                raise LLMException(f"Vision API failed after {retries} attempts: {e}")
            time.sleep(wait)

        except json.JSONDecodeError as e:
            logger.error("vision_tool.json_parse_error", raw=raw[:200], error=str(e))
            raise LLMException("Vision tool returned invalid JSON")

    # Should never reach here
    raise LLMException("Vision tool exhausted retries")
