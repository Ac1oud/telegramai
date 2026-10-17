"""Single EXE entry point for the desktop and its console/JSON workers."""

from __future__ import annotations

import importlib.abc
import importlib.util
import os
from pathlib import Path
import sys


class ProjectModules(importlib.abc.MetaPathFinder):
    """In a Git checkout, run the code installed by the online updater."""

    def __init__(self, root: Path):
        self.root = root

    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"main", "account_manager", "ui_effects", "project_updater", "app_runtime", "version", "gui_worker", "image_references"}:
            source = self.root / f"{fullname}.py"
            if source.is_file():
                return importlib.util.spec_from_file_location(fullname, source)
        return None


def run() -> None:
    # Windowed PyInstaller clears Python streams even when the parent passes
    # pipes. Reattach only those inherited handles; never allocate a console.
    if os.name == "nt" and getattr(sys, "frozen", False):
        import ctypes
        import msvcrt

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [ctypes.c_ulong]
        kernel.GetStdHandle.restype = ctypes.c_void_p
        for name, number, mode in (("stdin", -10, "r"), ("stdout", -11, "w"), ("stderr", -12, "w")):
            if getattr(sys, name) is None:
                handle = kernel.GetStdHandle(number & 0xffffffff)
                if handle and handle != ctypes.c_void_p(-1).value:
                    try:
                        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY if mode == "r" else os.O_WRONLY)
                        setattr(sys, name, open(fd, mode, encoding="utf-8", errors="replace", buffering=1))
                    except OSError:
                        pass
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        if (root / ".git").exists() and (root / "account_manager.py").is_file():
            sys.meta_path.insert(0, ProjectModules(root))
            sys.path.insert(0, str(root))

    from version import VERSION

    if len(sys.argv) > 1 and sys.argv[1] == "--worker-gui":
        sys.argv.pop(1)
        from gui_worker import run_worker

        run_worker()
        return
    if sys.argv[1:] == ["--version"]:
        print(VERSION)
        return
    if len(sys.argv) > 1 and sys.argv[1] in {"--worker", "--worker-console"}:
        interactive = sys.argv.pop(1) == "--worker-console"
        if interactive and os.name == "nt":
            import ctypes

            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 5)
        import main

        try:
            main.main()
        except SystemExit as exc:
            if interactive and exc.code:
                print(str(exc), file=sys.stderr)
            raise
        finally:
            if interactive and sys.stdin and sys.stdin.isatty():
                try:
                    input("\n按 Enter 关闭此终端…")
                except (EOFError, KeyboardInterrupt):
                    pass
        return

    from app_runtime import FROZEN, ensure_local_config
    from account_manager import run_desktop

    if FROZEN:
        ensure_local_config()
    run_desktop()


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    run()
