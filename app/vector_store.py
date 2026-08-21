"""
Pinecone-backed vector store. Metadata schema per vector:
  {filename, heading, status, doc_type, policy_authority, injection_flagged}
Chunk text itself is stored as metadata too (Pinecone doesn't store raw docs
separately), truncated defensively if very long.
"""

from pinecone import Pinecone, ServerlessSpec

from app.config import (
    PINECONE_API_KEY, PINECONE_INDEX_NAME, PINECONE_METRIC,
    PINECONE_CLOUD, PINECONE_REGION, EMBEDDING_DIMENSION,
)
from app.embeddings import embed_texts
from app.ingest import load_and_chunk_all

_pc = None


def get_pinecone_client() -> Pinecone:
    global _pc
    if _pc is None:
        _pc = Pinecone(api_key=PINECONE_API_KEY)
    return _pc


def ensure_index():
    pc = get_pinecone_client()
    existing = [idx["name"] for idx in pc.list_indexes()]
    if PINECONE_INDEX_NAME not in existing:
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric=PINECONE_METRIC,
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )
    return pc.Index(PINECONE_INDEX_NAME)


def build_index():
    index = ensure_index()
    chunks = load_and_chunk_all()

    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts)

    upserts = []
    for i, (c, vec) in enumerate(zip(chunks, vectors)):
        upserts.append({
            "id": f"{c['filename']}::{i}",
            "values": vec,
            "metadata": {
                "filename": c["filename"],
                "heading": c["heading"],
                "status": c["status"],
                "doc_type": c["doc_type"],
                "policy_authority": c["policy_authority"],
                "injection_flagged": c["injection_flagged"],
                "text": c["text"][:2000],  # Pinecone metadata size limit safeguard
            },
        })

    # batch upsert
    BATCH = 100
    for i in range(0, len(upserts), BATCH):
        index.upsert(vectors=upserts[i:i + BATCH])

    print(f"Indexed {len(upserts)} chunks into Pinecone index '{PINECONE_INDEX_NAME}'.")
    return index


def get_index():
    return ensure_index()


if __name__ == "__main__":
    build_index()