import re
import time
from datetime import datetime, timezone
from pathlib import Path

from groq import Groq
from app.config import GROQ_API_KEY, LLM_MODEL, LOG_FILE

_client = None
_MAX_RATE_LIMIT_RETRIES = 3
_BACKOFF_SECONDS = (2, 4, 8)

def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def chat_completion(messages: list[dict], temperature: float = 0.2, max_tokens: int = 350) -> str:
    client = get_client()
    completion_options = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    model_name = LLM_MODEL.lower()
    if "qwen" in model_name:
        completion_options["reasoning_effort"] = "none"
    elif "gpt-oss" in model_name:
        completion_options["reasoning_format"] = "hidden"

    for attempt in range(_MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = client.chat.completions.create(**completion_options)
            if attempt:
                _log_rate_limit_event("recovered", attempt, None)
            return response.choices[0].message.content
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == _MAX_RATE_LIMIT_RETRIES:
                if _is_rate_limit_error(exc):
                    _log_rate_limit_event("exhausted", attempt, exc)
                raise
            delay = _retry_after_seconds(exc) or _BACKOFF_SECONDS[attempt]
            _log_rate_limit_event("retrying", attempt + 1, exc, delay)
            time.sleep(delay)


def _is_rate_limit_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "RateLimitError" or getattr(exc, "status_code", None) == 429


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) if response else {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            pass
    match = re.search(r"try again in\s+(?:(\d+)m)?([\d.]+)s", str(exc), flags=re.IGNORECASE)
    if match:
        return int(match.group(1) or 0) * 60 + float(match.group(2))
    return None


def _log_rate_limit_event(event: str, attempt: int, exc: Exception | None, delay: float | None = None) -> None:
    details = f"status=429 event={event} attempt={attempt}"
    if delay is not None:
        details += f" delay_seconds={delay:g}"
    if exc is not None:
        details += f" error={str(exc).splitlines()[0]}"
    path = Path(LOG_FILE).with_name("errors.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] RATE_LIMIT {details}\n")