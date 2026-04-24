from dataclasses import dataclass
from pathlib import Path

import config
from ingestion.embedder import embed_texts, get_collection


@dataclass
class RetrievedChunk:
    content: str
    file_path: str
    score: float  # 0.0–1.0, higher = more similar


def retrieve(
    query: str,
    chroma_dir: Path,
    collection_name: str,
    top_k: int = config.TOP_K,
) -> list[RetrievedChunk]:
    collection = get_collection(chroma_dir, collection_name)

    if collection.count() == 0:
        return []

    query_vec = embed_texts([query])[0]
    results = collection.query(
        query_embeddings=[query_vec],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks: list[RetrievedChunk] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        # cosine distance [0,2] → similarity [0,1]
        score = max(0.0, min(1.0, 1.0 - dist / 2.0))
        chunks.append(RetrievedChunk(
            content=doc,
            file_path=meta.get("file_path", ""),
            score=score,
        ))

    return chunks
