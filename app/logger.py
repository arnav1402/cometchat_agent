import json
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


def log_trace(session_id, user_message, history_used, retrieval_result, tool_calls, tool_result_sanitized, final_response, flags):
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
