from dataclasses import dataclass, field
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter, Language

import config

_LANG_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".jsx": Language.JS,
    ".ts": Language.TS,
    ".tsx": Language.TS,
    ".java": Language.JAVA,
    ".go": Language.GO,
    ".rb": Language.RUBY,
    ".rs": Language.RUST,
    ".cpp": Language.CPP,
    ".c": Language.C,
    ".cs": Language.CSHARP,
    ".scala": Language.SCALA,
    ".swift": Language.SWIFT,
    ".md": Language.MARKDOWN,
    ".rst": Language.RST,
}


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _get_splitter(ext: str) -> RecursiveCharacterTextSplitter:
    lang = _LANG_MAP.get(ext)
    if lang:
        return RecursiveCharacterTextSplitter.from_language(
            language=lang,
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP,
        )
    return RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )


def detect_language(path: Path) -> str:
    return path.suffix.lstrip(".") or "text"


def iter_code_files(clone_dir: Path) -> list[Path]:
    results = []
    for path in clone_dir.rglob("*"):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        # Skip dirs in SKIP_DIRS
        if any(part in config.SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in config.CODE_EXTENSIONS:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        results.append(path)
    return results


def chunk_file(repo_name: str, clone_dir: Path, file_path: Path) -> list[Chunk]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        return []

    if not text.strip():
        return []

    rel_path = file_path.relative_to(clone_dir).as_posix()
    splitter = _get_splitter(file_path.suffix)
    parts = splitter.split_text(text)

    return [
        Chunk(
            id=f"{repo_name}::{rel_path}::{i}",
            # E3: 파일경로를 청크 앞에 붙여 임베딩 — 위치 토큰(api, services, auth)이
            # 검색 벡터에 실리도록. file_path 메타데이터는 그대로(채점/표시용).
            text=f"{rel_path}\n\n{part}",
            metadata={
                "repo": repo_name,
                "file_path": rel_path,
                "chunk_index": i,
                "language": detect_language(file_path),
            },
        )
        for i, part in enumerate(parts)
    ]


def chunk_repo(repo_name: str, clone_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for f in iter_code_files(clone_dir):
        chunks.extend(chunk_file(repo_name, clone_dir, f))
    return chunks


def chunk_files(repo_name: str, clone_dir: Path, rel_paths: list[str]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for rel in rel_paths:
        abs_path = clone_dir / rel
        if abs_path.is_file() and abs_path.suffix in config.CODE_EXTENSIONS:
            chunks.extend(chunk_file(repo_name, clone_dir, abs_path))
    return chunks
