import re
from pathlib import Path

import frontmatter

from app.config import KNOWLEDGE_BASE_DIR
from app.safety import scan_for_injection


def _derive_doc_type(metadata: dict) -> str:
    audience = str(metadata.get("audience", "")).strip().lower()
    policy_authority = str(metadata.get("policy_authority", "")).strip().lower()
    customer_answering = metadata.get("customer_answering")

    if audience == "internal" or customer_answering is False:
        return "internal"
    if policy_authority == "official":
        return "policy"
    return "non_policy"


def _chunk_by_headings(filename: str, text: str, status: str, doc_type: str, policy_authority: str) -> list[dict]:
    normalized = text.strip()
    if not normalized:
        return []

    chunks = []
    parts = re.split(r"(?m)^##\s+", normalized)
    if len(parts) == 1:
        heading = "Overview"
        payload = normalized
        chunks.append({
            "filename": filename,
            "heading": heading,
            "status": status,
            "doc_type": doc_type,
            "policy_authority": policy_authority,
            "text": payload,
            "injection_flagged": scan_for_injection(payload),
        })
        return chunks

    for part in parts[1:]:
        lines = part.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        payload = "\n".join(lines[1:]).strip()
        if not payload:
            continue
        chunks.append({
            "filename": filename,
            "heading": heading,
            "status": status,
            "doc_type": doc_type,
            "policy_authority": policy_authority,
            "text": f"## {heading}\n\n{payload}",
            "injection_flagged": scan_for_injection(payload),
        })

    return chunks


def load_and_chunk_all() -> list[dict]:
    base_dir = Path(KNOWLEDGE_BASE_DIR)
    chunks = []
    for path in sorted(base_dir.glob("*.md")):
        if not path.is_file():
            continue
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
        metadata = dict(post.metadata or {})
        status = str(metadata.get("status", "unknown")).strip().lower()
        doc_type = _derive_doc_type(metadata)
        policy_authority = str(metadata.get("policy_authority", "none")).strip().lower()
        content = post.content or ""
        chunks.extend(_chunk_by_headings(path.name, content, status, doc_type, policy_authority))
    return chunks


def print_summary_table() -> None:
    chunks = load_and_chunk_all()
    headers = ["filename", "status", "doc_type", "heading", "injection_flagged"]
    rows = [
        [c["filename"], c["status"], c["doc_type"], c["heading"], str(c["injection_flagged"])]
        for c in chunks
    ]

    widths = [max(len(str(header)), max(len(str(row[i])) for row in [*rows, headers])) for i, header in enumerate(headers)]
    def fmt_row(row):
        return " | ".join(str(value).ljust(widths[i]) for i, value in enumerate(row))

    print(fmt_row(headers))
    print("-+-".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print(fmt_row(row))


if __name__ == "__main__":
    print_summary_table()
