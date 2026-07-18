import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT: Path = Path(__file__).parent.resolve()
DATA_DIR: Path = PROJECT_ROOT / "data"
REPOS_DIR: Path = DATA_DIR / "repos"
CHROMA_DIR: Path = DATA_DIR / "chroma"
META_PATH: Path = DATA_DIR / "meta.json"

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"
CHAT_MODEL: str = "gpt-4o-mini" #성능 별로면 gpt-5o-mini

CHUNK_SIZE: int = 1000
CHUNK_OVERLAP: int = 200
TOP_K: int = 10  # E1: 5→10, multi-hop 답변 완성률↑ (eval v0→combo)

REINDEX_INTERVAL_DAYS: int = 2

CODE_EXTENSIONS: set[str] = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift",
    ".kt", ".scala", ".md", ".rst", ".yaml", ".yml", ".toml",
}

SKIP_DIRS: set[str] = {
    ".git", "node_modules", "venv", ".venv",
    "dist", "build", "__pycache__", ".next", "target",
    ".omc", ".vscode", ".idea", ".pytest_cache",
}


@dataclass(frozen=True)
class RepoConfig:
    name: str
    github_url: str
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str

    @property
    def clone_dir(self) -> Path:
        return REPOS_DIR / self.name

    @property
    def chroma_dir(self) -> Path:
        return CHROMA_DIR / self.name

    @property
    def display_name(self) -> str:
        return self.github_url.rstrip("/").split("/")[-1]

    @property
    def collection_name(self) -> str:
        return self.name.replace("-", "_")


# ── Repo registry ────────────────────────────────────────────────────────────
# Add a new entry here + three env vars per repo to register a new bot.
_REPO_DEFINITIONS: list[tuple[str, str]] = [
    ("REPO_A", "https://github.com/jaeuk-oh/Leadership-Training-Service"),
    ("REPO_B", "https://github.com/jaeuk-oh/English-Exam-Maker"),
    ("REPO_C", "https://github.com/jaeuk-oh/Translate-Quote-System")
]


def load_repos() -> list[RepoConfig]:
    repos = []
    for name, url in _REPO_DEFINITIONS:
        repos.append(RepoConfig(
            name=name,
            github_url=url,
            slack_bot_token=os.getenv(f"SLACK_BOT_TOKEN_{name}", ""),
            slack_app_token=os.getenv(f"SLACK_APP_TOKEN_{name}", ""),
            slack_signing_secret=os.getenv(f"SLACK_SIGNING_SECRET_{name}", ""),
        ))
    return repos


def ensure_dirs() -> None:
    for repo_def in _REPO_DEFINITIONS:
        name = repo_def[0]
        (REPOS_DIR / name).mkdir(parents=True, exist_ok=True)
        (CHROMA_DIR / name).mkdir(parents=True, exist_ok=True)


def validate() -> None:
    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY is not set")
    for repo in load_repos():
        name = repo.name
        attr_to_env = {
            "slack_bot_token": f"SLACK_BOT_TOKEN_{name}",
            "slack_app_token": f"SLACK_APP_TOKEN_{name}",
            # signing_secret is optional: unused in Socket Mode
        }
        missing = [env for attr, env in attr_to_env.items() if not getattr(repo, attr)]
        if missing:
            raise EnvironmentError(f"Missing env vars for {repo.name}: {missing}")
