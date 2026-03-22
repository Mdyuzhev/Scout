"""Diser RAG — indexer: .md files -> chunks -> ChromaDB."""

import re
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from loguru import logger

from . import config

_BRIEF_ID_RE = re.compile(r"(SW\d+-\d+)")


def _parse_metadata(filepath: Path, briefs_dir: str) -> dict:
    """Extract metadata from file path."""
    rel = filepath.relative_to(briefs_dir)
    parts = rel.parts
    swarm = parts[0] if len(parts) > 1 else "root"
    domain = config.DOMAIN_MAP.get(swarm, "general")

    stem = filepath.stem
    m = _BRIEF_ID_RE.search(stem)
    brief_id = m.group(1) if m else stem
    topic = _BRIEF_ID_RE.sub("", stem).strip("_- ")
    if not topic:
        topic = stem

    return {
        "swarm": swarm,
        "brief_id": brief_id,
        "topic": topic,
        "domain": domain,
        "source": filepath.name,
    }


def _chunk_by_h2(text: str) -> list[tuple[str, str]]:
    """Split markdown by H2 headers. Returns (section_num, text) pairs."""
    parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    chunks = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        if len(part) < 50:
            continue
        chunks.append((str(i), part))
    return chunks


def index(
    briefs_dir: str | None = None,
    swarm_filter: str | None = None,
) -> dict:
    """Index .md files into ChromaDB. Returns stats."""
    briefs_dir = briefs_dir or config.BRIEFS_DIR
    chroma_path = config.CHROMA_PATH

    Path(chroma_path).mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=chroma_path)
    ef = SentenceTransformerEmbeddingFunction(model_name=config.EMBEDDING_MODEL)
    collection = client.get_or_create_collection(
        name=config.COLLECTION,
        embedding_function=ef,
        metadata={"embedding_model": config.EMBEDDING_MODEL},
    )

    existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()

    base = Path(briefs_dir)
    if not base.exists():
        logger.error(f"Briefs dir not found: {briefs_dir}")
        return {"indexed": 0, "skipped": 0, "total_chunks": collection.count(), "error": f"dir not found: {briefs_dir}"}

    if swarm_filter:
        md_files = sorted((base / swarm_filter).rglob("*.md"))
    else:
        md_files = sorted(base.rglob("*.md"))

    indexed = 0
    skipped = 0
    batch_ids: list[str] = []
    batch_docs: list[str] = []
    batch_metas: list[dict] = []

    for fp in md_files:
        meta = _parse_metadata(fp, briefs_dir)
        text = fp.read_text(encoding="utf-8", errors="replace")
        chunks = _chunk_by_h2(text)
        if not chunks:
            chunks = [("0", text)]

        file_skipped = True
        for section_num, chunk_text in chunks:
            doc_id = f"{meta['brief_id']}__s{section_num}"
            if doc_id in existing_ids:
                skipped += 1
                continue

            file_skipped = False
            chunk_meta = {**meta, "section": section_num}
            batch_ids.append(doc_id)
            batch_docs.append(chunk_text)
            batch_metas.append(chunk_meta)

            if len(batch_ids) >= 50:
                collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
                indexed += len(batch_ids)
                batch_ids, batch_docs, batch_metas = [], [], []

        if file_skipped:
            logger.debug(f"Skipped (already indexed): {fp.name}")

    if batch_ids:
        collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
        indexed += len(batch_ids)

    total = collection.count()
    logger.info(f"Indexing done: indexed={indexed}, skipped={skipped}, total_chunks={total}")
    return {"indexed": indexed, "skipped": skipped, "total_chunks": total}


def index_text(
    text: str,
    brief_id: str,
    swarm: str,
    topic: str,
    domain: str | None = None,
) -> dict:
    """Index a single brief from text string (no filesystem read).

    Called by scout_save_brief via POST /index_brief — no disk access needed.
    Returns: indexed, skipped, total_chunks, brief_id.
    """
    chroma_path = config.CHROMA_PATH
    Path(chroma_path).mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=chroma_path)
    ef = SentenceTransformerEmbeddingFunction(model_name=config.EMBEDDING_MODEL)
    collection = client.get_or_create_collection(
        name=config.COLLECTION,
        embedding_function=ef,
        metadata={"embedding_model": config.EMBEDDING_MODEL},
    )

    existing_ids = set(collection.get()["ids"]) if collection.count() > 0 else set()
    resolved_domain = domain or config.DOMAIN_MAP.get(swarm, "general")

    chunks = _chunk_by_h2(text)
    if not chunks:
        chunks = [("0", text)]

    meta_base = {
        "swarm":    swarm,
        "brief_id": brief_id,
        "topic":    topic,
        "domain":   resolved_domain,
        "source":   f"{brief_id}_{topic}.md",
    }

    ids, docs, metas = [], [], []
    skipped = 0
    for section_num, chunk_text in chunks:
        doc_id = f"{brief_id}__s{section_num}"
        if doc_id in existing_ids:
            skipped += 1
            continue
        ids.append(doc_id)
        docs.append(chunk_text)
        metas.append({**meta_base, "section": section_num})

    if ids:
        collection.add(ids=ids, documents=docs, metadatas=metas)

    total = collection.count()
    logger.info(
        "index_text: brief_id={} indexed={} skipped={} total={}",
        brief_id, len(ids), skipped, total,
    )
    return {
        "indexed":      len(ids),
        "skipped":      skipped,
        "total_chunks": total,
        "brief_id":     brief_id,
    }
