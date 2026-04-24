import time
import logging
from pathlib import Path

import chromadb
from openai import OpenAI, RateLimitError, APIConnectionError

import config
from .chunker import Chunk, chunk_repo, chunk_files

logger = logging.getLogger(__name__)

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

_EMBED_BATCH = 100
_MAX_RETRIES = 5

_chroma_clients: dict[str, chromadb.PersistentClient] = {}


def _get_client(chroma_dir: Path) -> chromadb.PersistentClient:
    key = str(chroma_dir)
    if key not in _chroma_clients:
        _chroma_clients[key] = chromadb.PersistentClient(path=key)
    return _chroma_clients[key]


def get_collection(chroma_dir: Path, collection_name: str):
    client = _get_client(chroma_dir)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed with retry on rate-limit / connection errors."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH):
        batch = texts[i : i + _EMBED_BATCH]
        for attempt in range(_MAX_RETRIES):
            try:
                resp = _openai.embeddings.create(
                    model=config.EMBEDDING_MODEL, input=batch
                )
                all_embeddings.extend([d.embedding for d in resp.data])
                break
            except (RateLimitError, APIConnectionError) as e:
                wait = 2 ** attempt
                logger.warning("Embedding error (%s), retrying in %ss", e, wait)
                time.sleep(wait)
        else:
            raise RuntimeError(f"Embedding failed after {_MAX_RETRIES} attempts")
    return all_embeddings


def index_chunks(chunks: list[Chunk], collection) -> None:
    if not chunks:
        return
    texts = [c.text for c in chunks]
    embeddings = embed_texts(texts)
    collection.upsert(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=texts,
        metadatas=[c.metadata for c in chunks],
    )


def delete_file_chunks(collection, rel_paths: list[str]) -> None:
    if not rel_paths:
        return
    collection.delete(where={"file_path": {"$in": rel_paths}})


def full_index(
    repo_name: str,
    clone_dir: Path,
    chroma_dir: Path,
    collection_name: str,
) -> int:
    client = _get_client(chroma_dir)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    chunks = chunk_repo(repo_name, clone_dir)
    index_chunks(chunks, collection)
    logger.info("full_index %s: %d chunks", repo_name, len(chunks))
    return len(chunks)


def incremental_index(
    repo_name: str,
    clone_dir: Path,
    chroma_dir: Path,
    collection_name: str,
    changed_rel_paths: list[str],
) -> tuple[int, int]:
    collection = get_collection(chroma_dir, collection_name)

    # Separate deletions (file gone) from upserts (file present)
    deletions = [p for p in changed_rel_paths if not (clone_dir / p).exists()]
    upserts = [p for p in changed_rel_paths if (clone_dir / p).exists()]

    # Delete old chunks for both categories before re-inserting
    delete_file_chunks(collection, changed_rel_paths)

    # Re-embed files that still exist
    new_chunks = chunk_files(repo_name, clone_dir, upserts)
    index_chunks(new_chunks, collection)

    logger.info(
        "incremental_index %s: %d deleted files, %d new chunks",
        repo_name, len(deletions), len(new_chunks),
    )
    return len(deletions), len(new_chunks)
