import json
import logging
import os
import threading
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

import config
from config import RepoConfig, META_PATH
from ingestion import (
    clone_or_pull,
    changed_files,
    file_exists_at,
    full_index,
    incremental_index,
    get_collection,
)

logger = logging.getLogger(__name__)

_meta_lock = threading.Lock()


def load_meta() -> dict[str, str]:
    if META_PATH.exists():
        try:
            return json.loads(META_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_meta(meta: dict[str, str]) -> None:
    tmp = META_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2))
    os.replace(tmp, META_PATH)


def _update_meta(repo_name: str, sha: str) -> None:
    """Atomically update one repo's sha in meta.json under lock."""
    with _meta_lock:
        meta = load_meta()
        meta[repo_name] = sha
        save_meta(meta)


def initial_index_if_empty(repo: RepoConfig) -> None:
    """Run full index if collection is empty or not yet in meta."""
    meta = load_meta()
    collection = get_collection(repo.chroma_dir, repo.collection_name)
    already_indexed = repo.name in meta and collection.count() > 0

    if already_indexed:
        logger.info("Skipping initial index for %s (already indexed)", repo.name)
        return

    logger.info("Initial indexing for %s ...", repo.name)
    new_sha, _ = clone_or_pull(repo.github_url, repo.clone_dir)
    full_index(repo.name, repo.clone_dir, repo.chroma_dir, repo.collection_name)
    _update_meta(repo.name, new_sha)
    logger.info("Initial index complete for %s (sha=%s)", repo.name, new_sha[:8])


def reindex_repo(repo: RepoConfig) -> dict:
    meta = load_meta()
    last_indexed_sha = meta.get(repo.name)

    new_sha, _ = clone_or_pull(repo.github_url, repo.clone_dir)

    # Check if collection exists and has data
    collection = get_collection(repo.chroma_dir, repo.collection_name)
    if collection.count() == 0 or last_indexed_sha is None:
        logger.info("Full reindex for %s (empty or no meta)", repo.name)
        count = full_index(repo.name, repo.clone_dir, repo.chroma_dir, repo.collection_name)
        _update_meta(repo.name, new_sha)
        return {"repo": repo.name, "status": "full_reindex", "chunks": count}

    if new_sha == last_indexed_sha:
        logger.info("No changes for %s, skipping", repo.name)
        return {"repo": repo.name, "status": "skipped"}

    # Get changed files since last indexed sha
    diffs = changed_files(repo.clone_dir, last_indexed_sha, new_sha)
    if not diffs:
        # Shallow clone or unreachable sha — fall back to full reindex
        logger.warning("Cannot diff %s, falling back to full reindex", repo.name)
        count = full_index(repo.name, repo.clone_dir, repo.chroma_dir, repo.collection_name)
        _update_meta(repo.name, new_sha)
        return {"repo": repo.name, "status": "full_reindex_fallback", "chunks": count}

    # Filter to code files only
    code_diffs = [
        p for p in diffs
        if Path(p).suffix in config.CODE_EXTENSIONS
    ]

    if not code_diffs:
        logger.info("No code file changes for %s", repo.name)
        _update_meta(repo.name, new_sha)
        return {"repo": repo.name, "status": "skipped_no_code_changes"}

    deleted, added = incremental_index(
        repo.name, repo.clone_dir, repo.chroma_dir, repo.collection_name, code_diffs
    )
    _update_meta(repo.name, new_sha)
    return {
        "repo": repo.name,
        "status": "incremental",
        "deleted_files": deleted,
        "added_chunks": added,
    }


def reindex_all(repos: list[RepoConfig]) -> list[dict]:
    results = []
    for repo in repos:
        try:
            result = reindex_repo(repo)
            logger.info("Reindex result: %s", result)
            results.append(result)
        except Exception as e:
            logger.exception("Reindex failed for %s: %s", repo.name, e)
            results.append({"repo": repo.name, "status": "error", "error": type(e).__name__})
    return results


def start_scheduler(repos: list[RepoConfig]) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1}
    )
    scheduler.add_job(
        reindex_all,
        trigger="interval",
        days=config.REINDEX_INTERVAL_DAYS,
        args=[repos],
        id="reindex_all",
    )
    scheduler.start()
    logger.info(
        "Scheduler started: reindex every %d day(s)", config.REINDEX_INTERVAL_DAYS
    )
    return scheduler
