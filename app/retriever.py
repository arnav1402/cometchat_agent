import re

from app.vector_store import get_index
from app.embeddings import embed_query
from app.config import TOP_K, SIMILARITY_THRESHOLD


def retrieve(query: str, k: int = TOP_K) -> dict:
    index = get_index()
    query_vec = embed_query(query)

    raw = index.query(
        vector=query_vec,
        top_k=k * 2,
        include_metadata=True,
    )

    results = []
    for match in raw.get("matches", []):
        meta = match.get("metadata", {})
        results.append({
            "text": meta.get("text", ""),
            "filename": meta.get("filename", "unknown"),
            "heading": meta.get("heading", "Overview"),
            "status": meta.get("status", "unknown"),
            "doc_type": meta.get("doc_type", "non_policy"),
            "policy_authority": meta.get("policy_authority", "none"),
            "injection_flagged": meta.get("injection_flagged", False),
            "score": match.get("score", 0.0),
        })

    results = [r for r in results if r["doc_type"] != "internal"]
    results.sort(key=lambda r: (r["status"] != "active", -r["score"]))

    top = results[:k]
    active_official = [
        r for r in top if r["status"] == "active" and r["policy_authority"] == "official"
    ]
    conflict = _detect_conflict(active_official)

    top_score = top[0]["score"] if top else 0.0
    second_score = top[1]["score"] if len(top) > 1 else 0.0
    relevance_gap = top_score - second_score if top else 0.0
    insufficient = len(top) == 0 or top_score < SIMILARITY_THRESHOLD or (len(top) > 1 and top_score < 0.5 and relevance_gap < 0.05)

    return {"chunks": top, "conflict": conflict, "insufficient": insufficient}


def _detect_conflict(chunks: list[dict]) -> bool:
    if len(chunks) < 2:
        return False

    filenames = {c["filename"] for c in chunks}
    if len(filenames) <= 1:
        return False

    counts_by_file = {}
    for chunk in chunks:
        numbers = set(re.findall(r"(\d+)\s*(?:calendar\s*)?days?", chunk["text"], flags=re.IGNORECASE))
        if numbers:
            counts_by_file.setdefault(chunk["filename"], set()).update(numbers)

    if len(counts_by_file) <= 1:
        return False

    unique_counts = set().union(*counts_by_file.values())
    return len(unique_counts) > 1