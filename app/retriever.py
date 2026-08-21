from app.vector_store import get_index
from app.embeddings import embed_query
from app.config import TOP_K, SIMILARITY_THRESHOLD


def retrieve(query: str, k: int = TOP_K) -> dict:
    index = get_index()
    query_vec = embed_query(query)

    raw = index.query(
        vector=query_vec,
        top_k=k * 2,          # overfetch, then filter/rank
        include_metadata=True,
    )

    results = []
    for match in raw["matches"]:
        meta = match["metadata"]
        results.append({
            "text": meta.get("text", ""),
            "filename": meta["filename"],
            "heading": meta["heading"],
            "status": meta["status"],
            "doc_type": meta["doc_type"],
            "policy_authority": meta["policy_authority"],
            "injection_flagged": meta.get("injection_flagged", False),
            "score": match["score"],   # cosine similarity, higher = better
        })

    # Landmine rule 1: internal/non-customer content never surfaces as an answer source
    results = [r for r in results if r["doc_type"] != "internal"]

    # Landmine rule 2: active docs ranked above superseded, then by score
    results.sort(key=lambda r: (r["status"] != "active", -r["score"]))

    top = results[:k]

    active_official = [
        r for r in top if r["status"] == "active" and r["policy_authority"] == "official"
    ]
    conflict = _detect_conflict(active_official)
    insufficient = len(top) == 0 or top[0]["score"] < SIMILARITY_THRESHOLD

    return {"chunks": top, "conflict": conflict, "insufficient": insufficient}


def _detect_conflict(chunks: list[dict]) -> bool:
    filenames = {c["filename"] for c in chunks}
    return len(filenames) > 1 and _numbers_disagree(chunks)


def _numbers_disagree(chunks: list[dict]) -> bool:
    import re
    day_counts = set()
    for c in chunks:
        for m in re.findall(r"(\d+)\s*(?:calendar\s*)?days?", c["text"]):
            day_counts.add(m)
    return len(day_counts) > 1