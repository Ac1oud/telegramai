"""Locate persistent user data separately from a one-file EXE's resources."""

from pathlib import Path
import sys


FROZEN = bool(getattr(sys, "frozen", False))
CONSOLE_MODE = not FROZEN or Path(sys.executable).stem.casefold().endswith('-console')
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
SOURCE_MODE = not FROZEN or (ROOT / ".git").exists()
RESOURCE_ROOT = ROOT if SOURCE_MODE else BUNDLE_ROOT


def ensure_local_config() -> None:
    """A new portable install starts with empty placeholders, never credentials."""
    config = ROOT / ".env"
    if not config.exists():
        template = RESOURCE_ROOT / ".env.example"
        with config.open("x", encoding="utf-8") as target:
            target.write(template.read_text(encoding="utf-8-sig"))
