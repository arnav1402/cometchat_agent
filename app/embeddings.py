"""
Local embedding wrapper (sentence-transformers). Loaded once, reused for
both indexing and query-time embedding so vector spaces match.
"""

from sentence_transformers import SentenceTransformer
from app.config import EMBEDDING_MODEL

_model = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_model()
    return model.encode(texts, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]