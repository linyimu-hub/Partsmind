"""
app/utils/guardrails.py
────────────────────────
Input/output safety guardrails for the Agent.

Why guardrails?
  Without them, users can:
  - Inject prompts ("Ignore all instructions and...")
  - Ask completely off-topic questions (wastes tokens + money)
  - Crash the agent with malformed inputs

Layers:
  1. Input validation  — check before sending to agent
  2. Output validation — check before returning to user
  3. Rate limiting     — prevent abuse (in middleware)

This is lightweight — for production, consider:
  - LlamaGuard or OpenAI Moderation API for content safety
  - Dedicated PII detection (spaCy NER)
"""

import re
from dataclasses import dataclass

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Prompt injection patterns ──────────────────────────────────────────────────
# Common patterns used to jailbreak or hijack LLM behavior
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"forget\s+(everything|all|your\s+instructions)",
    r"you\s+are\s+now\s+(a\s+)?(?!partsmind)",  # "you are now DAN"
    r"act\s+as\s+(?!a\s+parts?\s+specialist)",
    r"(system|admin|root)\s*:\s*",              # fake system message prefix
    r"<\s*system\s*>",                          # XML-style injection
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"reveal\s+(your\s+)?(instructions|prompt|system)",
]

# ── Off-topic detection ────────────────────────────────────────────────────────
# If the message matches NONE of these automotive keywords,
# and is longer than 20 chars (not just "hello"), it's probably off-topic.
AUTOMOTIVE_KEYWORDS = [
    # Chinese
    "零件", "配件", "汽车", "车", "发动机", "刹车", "轮胎", "变速箱",
    "滤清器", "火花塞", "悬挂", "转向", "灯", "电池", "机油",
    # English
    "part", "brake", "filter", "engine", "tire", "transmission",
    "suspension", "spark", "oil", "coolant", "belt", "bearing",
    "gasket", "sensor", "pump", "alternator", "starter", "battery",
    "headlight", "wiper", "clutch", "axle", "caliper", "rotor",
    # Makes / models (common ones)
    "toyota", "honda", "ford", "bmw", "mercedes", "volkswagen",
    "nissan", "hyundai", "mazda", "凯美瑞", "雅阁", "civic", "camry",
    # Part numbers often start with letters+digits
]

# Short messages, greetings, and follow-ups are always OK
SHORT_MESSAGE_THRESHOLD = 30
GREETING_PATTERNS = [
    r"^(hi|hello|hey|你好|您好|嗨|怎么样)\b",
    r"^(thanks|thank you|谢谢|非常感谢)\b",
    r"^(yes|no|ok|okay|好的|是的|不是|明白)\b",
    r"^\?+$",   # just question marks
]


@dataclass
class GuardrailResult:
    allowed: bool
    reason: str | None = None       # why it was blocked (for logging)
    user_message: str | None = None # what to tell the user


def check_input(message: str) -> GuardrailResult:
    """
    Validate user input before sending to the agent.
    Returns GuardrailResult(allowed=True) if OK to proceed.
    """
    msg_lower = message.lower().strip()

    # ── Prompt injection check ────────────────────────────────────
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            logger.warning("guardrail.injection_detected", pattern=pattern, msg=message[:100])
            return GuardrailResult(
                allowed=False,
                reason="prompt_injection",
                user_message="I can only help with automotive parts questions.",
            )

    # ── Length check ──────────────────────────────────────────────
    if len(message) > 2000:
        return GuardrailResult(
            allowed=False,
            reason="too_long",
            user_message="Your message is too long. Please keep it under 2000 characters.",
        )

    # ── Short message / greeting — always allow ───────────────────
    if len(message) <= SHORT_MESSAGE_THRESHOLD:
        return GuardrailResult(allowed=True)

    for pattern in GREETING_PATTERNS:
        if re.match(pattern, msg_lower):
            return GuardrailResult(allowed=True)

    # ── Off-topic check ───────────────────────────────────────────
    has_automotive_keyword = any(kw in msg_lower for kw in AUTOMOTIVE_KEYWORDS)

    # Also allow if message looks like a part number (letters + digits)
    looks_like_part_number = bool(re.search(r'\b[A-Z]{2,}-[A-Z0-9]{3,}-\d{4,}\b', message))

    if not has_automotive_keyword and not looks_like_part_number:
        logger.info("guardrail.off_topic", msg=message[:100])
        return GuardrailResult(
            allowed=False,
            reason="off_topic",
            user_message=(
                "I'm PartsMind, specialized in automotive parts. "
                "I can help you find parts, check compatibility, or answer "
                "questions about auto components. What part are you looking for?"
            ),
        )

    return GuardrailResult(allowed=True)


def check_output(answer: str, confidence: float) -> GuardrailResult:
    """
    Validate agent output before returning to user.
    Catches hallucinations we can detect heuristically.
    """
    # ── Fabricated prices ─────────────────────────────────────────
    # If confidence is very low but answer contains specific prices,
    # it might be hallucinating. Flag for human review.
    has_price = bool(re.search(r'[¥$€]\s*\d+', answer))
    if has_price and confidence < 0.4:
        logger.warning("guardrail.low_conf_with_price", confidence=confidence)
        # Don't block — just add disclaimer
        return GuardrailResult(
            allowed=True,
            reason="low_confidence_price",
            user_message=answer + "\n\n⚠ Note: Please verify pricing with our team before ordering.",
        )

    # ── Empty answer ──────────────────────────────────────────────
    if not answer.strip():
        return GuardrailResult(
            allowed=False,
            reason="empty_answer",
            user_message=(
                "I wasn't able to find relevant information. "
                "Please try rephrasing your question or contact our support team."
            ),
        )

    return GuardrailResult(allowed=True)
