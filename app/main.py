from fastapi import FastAPI
from pydantic import BaseModel

from app.core.agent import handle_turn

app = FastAPI(title="CometChat Support Agent")


class ChatPayload(BaseModel):
    session_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(payload: ChatPayload):
    result = handle_turn(payload.session_id, payload.message)
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "handoff": result["handoff"],
    }
