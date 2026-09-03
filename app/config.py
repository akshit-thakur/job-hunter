from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
ZEN_EXTENSION_DIR = PROJECT_ROOT / "extensions" / "zen"
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", PROJECT_ROOT / "uploads"))


def load_env_file(path: str | Path | None = None) -> None:
    env_path = Path(path) if path is not None else PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def weekly_target() -> int:
    try:
        return max(1, int(os.getenv("WEEKLY_TARGET", "25")))
    except ValueError:
        return 25
