import re

from app.rag.retriever import retrieve
from app.llm.llm_client import chat_completion
from app.core.prompts import SYSTEM_PROMPT, build_user_prompt
from app.core.session import get_session, resolve_reference, update_session, _extract_order_id
from app.tools.order_lookup import lookup_order
from app.core.safety import validate_output
from app.core.logger import log_trace


def _resolve_order_id_for_turn(message: str, session: dict | None = None) -> str | None:
    direct_id = _extract_order_id(message)
    if direct_id:
        return direct_id

    if session and session.get("last_order_id"):
        lowered = message.lower()
        if re.search(r"\b(it|this|that|they)\b", lowered) or re.search(r"\b(my order|this order|that order)\b", lowered):
            return str(session["last_order_id"]).upper()
    return None


def _is_order_related(message: str, session: dict | None = None) -> bool:
    lowered = message.lower()
    if re.search(r"\bord-\d+\b", lowered):
        return True
    if re.search(r"\b(where is|when will|status|delivered|shipped|tracking|arrive|cancelled|returned)\b", lowered):
        return True
    if session and session.get("last_order_id") and re.search(r"\b(it|this|that|they|my order|this order|that order)\b", lowered):
        return True
    return False


def handle_turn(session_id: str, user_message: str) -> dict:
    session_id = str(session_id)
    session = get_session(session_id)
    history_used = list(session.get("history", []))
    retrieval_result = None
    tool_result = None
    tool_calls = []
    sources = []
    handoff = False
    safe_answer = "I’m unable to answer safely from the available information and recommend a human handoff."

    try:
        resolved_message = resolve_reference(session_id, user_message)
        print(f"[DEBUG][agent] route | session={session_id} | message={resolved_message!r} | order_related={_is_order_related(resolved_message, session)}")

        if _is_order_related(resolved_message, session):
            order_id = _resolve_order_id_for_turn(resolved_message, session)
            if order_id is None:
                clarification = "Could you provide your order ID so I can look that up?"
                print(f"[DEBUG][agent] missing-order-id branch | session={session_id} | message={resolved_message!r}")
                update_session(session_id, user_message, clarification, None)
                log_trace(
                    session_id,
                    user_message,
                    history_used,
                    None,
                    [],
                    None,
                    clarification,
                    {"conflict": False, "insufficient": False, "handoff": False, "errors": []},
                )
                return {"answer": clarification, "sources": [], "handoff": False}

            tool_calls = [{"name": "lookup_order", "args": {"raw_id": order_id}}]
            tool_result = lookup_order(order_id)
            retrieval_result = {"chunks": [], "conflict": False, "insufficient": False}
            prompt = build_user_prompt(resolved_message, retrieval_result, tool_result)
        else:
            retrieval_result = retrieve(resolved_message)
            tool_result = None
            prompt = build_user_prompt(resolved_message, retrieval_result)

        history_msgs = [{"role": msg["role"], "content": msg["content"]} for msg in session.get("history", [])]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history_msgs,
            {"role": "user", "content": prompt},
        ]

        answer = chat_completion(messages)

        ok, validated = validate_output(answer, retrieval_result, tool_result)
        if not ok:
            print(f"[DEBUG][agent] safety fallback | session={session_id} | reason={validated!r}")
            answer = validated
            handoff = True
            sources = []
        else:
            sources = [
                {"filename": c["filename"], "heading": c["heading"]}
                for c in (retrieval_result or {}).get("chunks", [])
            ]
            if retrieval_result:
                handoff = bool(retrieval_result.get("conflict") or retrieval_result.get("insufficient"))

        if not sources and tool_result and isinstance(tool_result, dict) and tool_result.get("order"):
            sources = []

        update_session(session_id, user_message, answer, retrieval_result)
        log_trace(
            session_id,
            user_message,
            history_used,
            retrieval_result,
            tool_calls,
            tool_result,
            answer,
            {"conflict": bool((retrieval_result or {}).get("conflict")), "insufficient": bool((retrieval_result or {}).get("insufficient")), "handoff": handoff, "errors": []},
        )
        return {"answer": answer, "sources": sources, "handoff": handoff}

    except Exception as exc:
        print(f"[DEBUG][agent] exception fallback | session={session_id} | message={user_message!r} | error={exc!r}")
        safe_answer = "I’m unable to answer safely from the available information and recommend a human handoff."
        handoff = True
        log_trace(
            session_id,
            user_message,
            history_used,
            retrieval_result,
            tool_calls,
            tool_result,
            safe_answer,
            {"conflict": False, "insufficient": True, "handoff": True, "errors": [str(exc)]},
        )
        return {"answer": safe_answer, "sources": [], "handoff": True}