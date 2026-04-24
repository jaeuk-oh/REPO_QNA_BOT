import shutil
from pathlib import Path
from git import Repo, InvalidGitRepositoryError


def clone_or_pull(github_url: str, clone_dir: Path) -> tuple[str, str | None]:
    """Clone fresh or pull existing. Returns (new_head_sha, old_head_sha_or_None)."""
    if not clone_dir.exists():
        clone_dir.mkdir(parents=True, exist_ok=True)
        repo = Repo.clone_from(github_url, str(clone_dir))
        return repo.head.commit.hexsha, None

    try:
        repo = Repo(str(clone_dir))
    except InvalidGitRepositoryError:
        shutil.rmtree(clone_dir, ignore_errors=True)
        clone_dir.mkdir(parents=True, exist_ok=True)
        repo = Repo.clone_from(github_url, str(clone_dir))
        return repo.head.commit.hexsha, None

    old_sha = repo.head.commit.hexsha
    try:
        repo.remotes.origin.pull()
    except Exception:
        # If pull fails (e.g. local diverged), hard reset to remote HEAD
        repo.git.reset("--hard", "origin/HEAD")
    new_sha = repo.head.commit.hexsha
    return new_sha, old_sha


def get_head_sha(clone_dir: Path) -> str:
    return Repo(str(clone_dir)).head.commit.hexsha


def changed_files(clone_dir: Path, old_sha: str, new_sha: str) -> list[str]:
    """Return relative paths that differ between old_sha..new_sha."""
    repo = Repo(str(clone_dir))
    try:
        diff_output = repo.git.diff("--name-only", f"{old_sha}..{new_sha}")
    except Exception:
        # old_sha not reachable (shallow clone etc.) — signal full reindex
        return []
    return [p for p in diff_output.splitlines() if p]


def file_exists_at(clone_dir: Path, rel_path: str) -> bool:
    return (clone_dir / rel_path).is_file()
