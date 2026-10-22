"""Small, optional Windows sound cues used by the desktop and listener."""

from __future__ import annotations

import os
from pathlib import Path

from app_runtime import RESOURCE_ROOT, ROOT

SOUND_NAMES = {"exit", "running", "sure", "wait", "send"}


def play_sound(name: str) -> None:
    """Play a bundled cue asynchronously; missing audio never interrupts work."""
    if name not in SOUND_NAMES or os.name != "nt":
        return
    try:
        import winsound

        path = RESOURCE_ROOT / "sounds" / f"{name}.wav"
        if not path.is_file():
            path = ROOT / "sounds" / f"{name}.wav"
        if path.is_file():
            winsound.PlaySound(
                str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
    except (ImportError, OSError):
        return
