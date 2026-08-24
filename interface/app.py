import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.title("Aster & Row Support Agent")

if "session_id" not in st.session_state:
    st.session_state.session_id = "streamlit-session"

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message.get("sources"):
            st.caption("Sources: " + ", ".join(f"{s['filename']}#{s['heading']}" for s in message["sources"]))
        if message.get("handoff"):
            st.warning("Human handoff recommended")

user_input = st.chat_input("Ask a support question")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input, "sources": [], "handoff": False})
    with st.chat_message("user"):
        st.write(user_input)

    payload = {"session_id": st.session_state.session_id, "message": user_input}
    response = requests.post(f"{API_BASE}/chat", json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()

    answer = result.get("answer", "")
    sources = result.get("sources", [])
    handoff = bool(result.get("handoff", False))

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "handoff": handoff,
    })

    with st.chat_message("assistant"):
        st.write(answer)
        if sources:
            st.caption("Sources: " + ", ".join(f"{s['filename']}#{s['heading']}" for s in sources))
        if handoff:
            st.warning("Human handoff recommended")
