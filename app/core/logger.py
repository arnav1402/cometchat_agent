import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import LOG_FILE

_FORBIDDEN_LOG_FIELDS = {
    "customer",
    "email",
    "shipping_address",
    "internal",
    "warehouse_note",
    "support_tags",
    "risk_score",
    "customer_safe_message",
}

_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)(customer(?:'s)?\s+(?:name|email|address)|shipping_address|internal(?:\s+note)?|risk[_ ]score|warehouse_note|support_tags)"
)


def _sanitize_for_log(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, child in value.items():
            if key in _FORBIDDEN_LOG_FIELDS:
                continue
            sanitized[key] = _sanitize_for_log(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    return value


def _sanitize_text(value: str, limit: int | None = None) -> str:
    sanitized = _EMAIL_PATTERN.sub("[REDACTED]", str(value))
    sanitized = _SENSITIVE_TEXT_PATTERN.sub("[REDACTED]", sanitized)
    if limit is not None:
        sanitized = sanitized[:limit]
    return sanitized


def log_trace(session_id, user_message, history_used, retrieval_result, tool_calls, tool_result_sanitized, final_response, flags):
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    timestamp_text = timestamp.isoformat()

    retrieved = []
    if retrieval_result:
        for chunk in retrieval_result.get("chunks", []):
            retrieved.append({
                "filename": chunk.get("filename"),
                "heading": chunk.get("heading"),
                "status": chunk.get("status"),
                "doc_type": chunk.get("doc_type"),
                "score": chunk.get("score"),
            })

    entry = {
        "timestamp": timestamp_text,
        "session_id": str(session_id),
        "user_message": user_message,
        "history_used": history_used,
        "retrieved": retrieved,
        "tool_calls": tool_calls,
        "tool_result": _sanitize_for_log(tool_result_sanitized),
        "final_response": final_response,
        "conflict": bool(flags.get("conflict") if isinstance(flags, dict) else False),
        "insufficient": bool(flags.get("insufficient") if isinstance(flags, dict) else False),
        "handoff": bool(flags.get("handoff") if isinstance(flags, dict) else False),
        "errors": list(flags.get("errors", [])) if isinstance(flags, dict) else [],
    }

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    conversation_path = log_path.with_name("conversation.log")
    conversation_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    conversation_line = (
        f"[{conversation_timestamp}] session={_sanitize_text(session_id)} | "
        f"USER: {_sanitize_text(user_message)} | AGENT: {_sanitize_text(final_response, 200)} | "
        f"handoff={bool(flags.get('handoff')) if isinstance(flags, dict) else False}\n"
    )
    with conversation_path.open("a", encoding="utf-8") as fh:
        fh.write(conversation_line)

    sanitized_tool_result = _sanitize_for_log(tool_result_sanitized)
    tool_calls_path = log_path.with_name("tool_calls.log")
    with tool_calls_path.open("a", encoding="utf-8") as fh:
        for tool_call in tool_calls or []:
            tool_entry = {
                "timestamp": timestamp_text,
                "session_id": _sanitize_text(session_id),
                "tool_name": tool_call.get("name"),
                "tool_args": _sanitize_for_log(tool_call.get("args", {})),
                "tool_result": sanitized_tool_result,
            }
            fh.write(json.dumps(tool_entry, ensure_ascii=False) + "\n")

    errors = flags.get("errors", []) if isinstance(flags, dict) else []
    handoff = bool(flags.get("handoff")) if isinstance(flags, dict) else False
    if errors or handoff:
        errors_path = log_path.with_name("errors.log")
        reason = "; ".join(_sanitize_text(error) for error in errors) or "handoff triggered"
        error_entry = (
            f"[{conversation_timestamp}] session={_sanitize_text(session_id)} | "
            f"USER: {_sanitize_text(user_message)} | reason: {reason}"
        )
        traceback_text = flags.get("traceback") if isinstance(flags, dict) else None
        if traceback_text:
            error_entry += f"\n{_sanitize_text(traceback_text)}"
        with errors_path.open("a", encoding="utf-8") as fh:
            fh.write(error_entry + "\n")
