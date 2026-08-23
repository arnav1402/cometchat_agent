import re
from typing import Any

from app.config import MAX_HISTORY_TURNS

_SESSIONS: dict[str, dict[str, Any]] = {}


def _new_session() -> dict[str, Any]:
    return {
        "history": [],
        "last_topic": None,
        "last_order_id": None,
        "last_retrieved_refs": [],
    }


def get_session(session_id: str) -> dict[str, Any]:
    session_key = str(session_id or "default")
    if session_key not in _SESSIONS:
        _SESSIONS[session_key] = _new_session()
    return _SESSIONS[session_key]


def _trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    max_turns = max(1, MAX_HISTORY_TURNS)
    return history[-(max_turns * 2) :]


def _extract_order_id(text: str) -> str | None:
    match = re.search(r"\bORD-\d+\b", text, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _infer_topic(text: str) -> str | None:
    lowered = text.strip().lower()
    if not lowered:
        return None
    if re.search(r"\b(return|returns|refund)\b", lowered):
        return "returns"
    if re.search(r"\b(ships?|shipping|international|domestic|delivery|arrive|delivered|tracking)\b", lowered):
        return "shipping"
    if re.search(r"\b(cancel|cancellation|change|address|order change|modify)\b", lowered):
        return "order changes"
    if re.search(r"\b(warranty|damaged|wrong item|defect)\b", lowered):
        return "warranty"
    if re.search(r"\b(trailplus|membership)\b", lowered):
        return "membership"
    return None


def _is_elliptical(message: str) -> bool:
    lowered = message.strip().lower()
    if not lowered:
        return False
    prefixes = (
        "what about",
        "how about",
        "and",
        "also",
        "when will it",
        "when will this",
        "when will that",
        "where is it",
        "where is this",
        "where is that",
        "what about it",
        "what about this",
        "what about that",
    )
    return any(lowered.startswith(prefix) for prefix in prefixes) or len(lowered.split()) <= 5


def _should_update_context(session: dict[str, Any], user_msg: str, retrieval_result: dict | None, order_id: str | None) -> bool:
    lower = user_msg.strip().lower()
    if order_id:
        return bool(re.search(r"\b(where is|when will|status|arrive|ship|delivered|tracking)\b", lower))
    if not retrieval_result:
        return False
    if retrieval_result.get("conflict") or retrieval_result.get("insufficient"):
        return False
    if not _infer_topic(user_msg):
        return False
    return not _is_elliptical(user_msg)


def resolve_reference(session_id: str, user_message: str) -> str:
    state = get_session(session_id)
    message = user_message.strip()
    if not message:
        return message

    lowered = message.lower()
    if not _is_elliptical(message):
        return message

    last_order_id = state.get("last_order_id")
    last_topic = state.get("last_topic")

    if last_order_id and re.search(r"\b(it|this|that|they)\b", lowered):
        if "arrive" in lowered or "ship" in lowered or "status" in lowered or "deliver" in lowered:
            return f"When will {last_order_id} arrive?"
        if "where" in lowered:
            return f"Where is {last_order_id}?"

    if last_topic:
        if lowered.startswith("what about") or lowered.startswith("how about"):
            return f"{message} {last_topic}"
        if lowered.startswith("and"):
            return f"{last_topic} {message}"
        return f"{last_topic} — {message}"

    return message


def update_session(session_id: str, user_msg: str, answer: str, retrieval_result: dict | None = None) -> dict[str, Any]:
    session = get_session(session_id)
    session["history"] = _trim_history(session.get("history", []) + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": answer},
    ])

    if retrieval_result:
        session["last_retrieved_refs"] = [
            (chunk.get("filename"), chunk.get("heading"))
            for chunk in retrieval_result.get("chunks", [])
            if chunk.get("filename") and chunk.get("heading")
        ]

    current_order_id = _extract_order_id(user_msg)
    current_topic = _infer_topic(user_msg)
    if _should_update_context(session, user_msg, retrieval_result, current_order_id):
        if current_order_id:
            session["last_order_id"] = current_order_id
        if current_topic:
            session["last_topic"] = current_topic

    return session
