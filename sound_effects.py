"""Small, optional Windows sound cues used by the desktop and listener."""

from __future__ import annotations

import os
from pathlib import Path

from app_runtime import RESOURCE_ROOT, ROOT

SOUND_FILES = {
    "exit": "exit.wav",
    "running": "running.wav",
    "sure": "sure.wav",
    "wait": "wait.wav",
    "send": "send.wav",
    "image_success": "image success.wav",
}


def play_sound(name: str) -> None:
    """Play a bundled cue asynchronously; missing audio never interrupts work."""
    filename = SOUND_FILES.get(name)
    if filename is None or os.name != "nt":
        return
    try:
        import winsound

        path = RESOURCE_ROOT / "sounds" / filename
        if not path.is_file():
            path = ROOT / "sounds" / filename
        if path.is_file():
            winsound.PlaySound(
                str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
            )
    except (ImportError, OSError):
        return
