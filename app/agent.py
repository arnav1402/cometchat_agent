from app.retriever import retrieve
from app.tools.order_lookup import lookup_order
from app.llm_client import chat_completion
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.session import get_session, update_session
from app.logger import log_trace


def handle_turn(session_id: str, user_message: str) -> dict:
    state = get_session(session_id)

    # (intent classification / order-id extraction / reference resolution
    #  happens here — omitted for brevity, per earlier session.py plan)

    retrieval = retrieve(user_message)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *state["history"],
        {"role": "user", "content": build_user_prompt(user_message, retrieval)},
    ]

    answer = chat_completion(messages)

    result = {
        "answer": answer,
        "sources": [
            {"filename": c["filename"], "heading": c["heading"]}
            for c in retrieval["chunks"]
        ],
        "handoff": retrieval["conflict"] or retrieval["insufficient"],
    }

    update_session(session_id, user_message, answer)
    log_trace(session_id, user_message, retrieval, None, answer, result["handoff"])

    return result