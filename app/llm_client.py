"""
Groq LLM wrapper. Keeps agent.py decoupled from the provider SDK so you
could swap providers later without touching orchestration logic.
"""

from groq import Groq
from app.config import GROQ_API_KEY, LLM_MODEL

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def chat_completion(messages: list[dict], temperature: float = 0.2, max_tokens: int = 800) -> str:
    """messages: standard OpenAI-style [{role, content}, ...] list.
    Groq's chat completions API is OpenAI-compatible."""
    client = get_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content