import re


_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?prior\s+instructions?",
    r"system\s+instruction\s*:",
    r"reveal\s+(your\s+)?(hidden\s+)?prompt",
    r"ignore\s+all\s+prior\s+rules",
    r"do\s+not\s+follow\s+(the\s+)?previous\s+instructions?",
    r"override\s+(all\s+)?instructions?",
    r"you\s+are\s+now\s+",
    r"developer\s+message\s*:",
    r"hidden\s+instructions?",
]

_FORBIDDEN_RESPONSE_PATTERNS = [
    r"customer\s+name",
    r"customer\s+email",
    r"shipping\s+address",
    r"warehouse\s+note",
    r"risk\s+score",
    r"support\s+tags",
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
]

_ACTION_VERBS = (
    "refund",
    "refunds",
    "cancel",
    "cancelled",
    "cancellation",
    "replacement",
    "address change",
    "change address",
    "escalate",
    "escalation",
    "return approved",
)


def scan_for_injection(text: str) -> bool:
    """Return True when the text contains instruction-like prompt injection content."""
    if not text:
        return False
    lowered = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return True
    return False


def validate_output(response_text: str, retrieval_result: dict | None, tool_result: dict | None) -> tuple[bool, str]:
    text = (response_text or "").strip()
    lowered = text.lower()

    safe_refusal_phrases = [
        "i can't confirm completed actions",
        "i cannot confirm completed actions",
        "i can’t confirm completed actions",
        "i cannot verify that an action was completed",
    ]
    if any(phrase in lowered for phrase in safe_refusal_phrases):
        return True, text

    action_confirmed = False
    if isinstance(tool_result, dict):
        action_confirmed = tool_result.get("action_confirmed") is True

    completion_patterns = [
        r"\b(?:i|we|the system|the agent)\s+(?:have|has|am|are|did|will)\s+(?:approved|processed|issued|completed|cancelled|refunded|replaced|escalated)\b",
        r"\b(?:i|we|the system|the agent)\s+(?:approved|processed|issued|completed|cancelled|refunded|replaced|escalated)\b",
        r"\b(?:refund|cancel(?:led|lation)?|replacement|address change|change address|escalat(?:e|ion))\b.*\b(?:approved|completed|processed|issued|done)\b",
    ]
    if not action_confirmed and any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in completion_patterns):
        return False, "I can’t confirm completed actions. This request needs a human review and I recommend a handoff."

    for pattern in _FORBIDDEN_RESPONSE_PATTERNS:
        if re.search(pattern, lowered, flags=re.IGNORECASE):
            return False, "I can’t expose internal or sensitive customer details. I recommend a human handoff."

    if "system prompt" in lowered or "hidden instructions" in lowered or "developer message" in lowered:
        return False, "I can’t reveal hidden instructions or system prompts. I recommend a human handoff."

    for chunk in (retrieval_result or {}).get("chunks", []):
        if scan_for_injection(chunk.get("text", "")):
            return False, "I found unsafe prompt-injection content in the retrieved sources and I recommend a human handoff."

    return True, text
