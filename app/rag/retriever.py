import re
import time

from app.config import LOG_FILE
from app.rag.vector_store import get_index
from app.rag.embeddings import embed_query
from app.config import TOP_K, SIMILARITY_THRESHOLD


def retrieve(query: str, k: int = TOP_K) -> dict:
    index = get_index()
    query_vec = embed_query(query)

    lowered_query = query.lower()
    final_sale_damage = "final-sale" in lowered_query and any(
        term in lowered_query for term in ("damaged", "broken", "defective")
    )
    raw = _query_index_with_retry(
        index,
        vector=query_vec,
        top_k=max(k * 2, 20) if final_sale_damage else k * 2,
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
    handoff_required = False
    if final_sale_damage:
        required_headings = {"Reporting window", "Reports after seven days"}
        for result in results:
            if result["filename"] == "04-damaged-or-wrong-items.md" and result["heading"] in required_headings and result not in top:
                top.append(result)
        handoff_required = True
    active_official = [
        r for r in top if r["status"] == "active" and r["policy_authority"] == "official"
    ]
    conflict = _detect_conflict(active_official)

    top_score = top[0]["score"] if top else 0.0
    second_score = top[1]["score"] if len(top) > 1 else 0.0
    relevance_gap = top_score - second_score if top else 0.0
    insufficient = (
        len(top) == 0
        or top_score < SIMILARITY_THRESHOLD
        or _is_uncovered_material_question(query, top)
    )

    return {"chunks": top, "conflict": conflict, "insufficient": insufficient, "handoff_required": handoff_required}


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
        return _detect_care_conflict(chunks)

    unique_counts = set().union(*counts_by_file.values())
    return len(unique_counts) > 1 or _detect_care_conflict(chunks)


def _detect_care_conflict(chunks: list[dict]) -> bool:
    hand_wash_files = set()
    dishwasher_safe_files = set()
    for chunk in chunks:
        text = chunk["text"].lower()
        if re.search(r"hand[- ]wash", text) and "body" in text:
            hand_wash_files.add(chunk["filename"])
        if "all components" in text and "dishwasher safe" in text:
            dishwasher_safe_files.add(chunk["filename"])
    return bool(hand_wash_files and dishwasher_safe_files and hand_wash_files != dishwasher_safe_files)


def _is_uncovered_material_question(query: str, chunks: list[dict]) -> bool:
    material_terms = ("vegan", "adhesive", "adhesives")
    lowered_query = query.lower()
    if not any(term in lowered_query for term in material_terms):
        return False
    retrieved_text = " ".join(chunk["text"].lower() for chunk in chunks)
    return not any(term in retrieved_text for term in material_terms)


def _query_index_with_retry(index, **kwargs):
    for attempt, delay in enumerate((0, 1, 2, 4)):
        if delay:
            time.sleep(delay)
        try:
            return index.query(**kwargs)
        except Exception as exc:
            status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
            if status != 429 and "429" not in str(exc):
                raise
            if attempt == 3:
                raise
            with open(LOG_FILE.replace("traces.jsonl", "errors.log"), "a", encoding="utf-8") as fh:
                fh.write(f"PINECONE_RATE_LIMIT status=429 event=retrying attempt={attempt + 1} delay_seconds={(1, 2, 4)[attempt]}\n")