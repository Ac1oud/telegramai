"""Portable paths and worker routing must not touch the real account files."""

import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from desktop_entry import ProjectModules


class DesktopRuntimeTests(unittest.TestCase):
    def test_portable_config_is_next_to_exe_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            install, bundle = root / "install", root / "bundle"
            install.mkdir()
            bundle.mkdir()
            (bundle / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
            spec = importlib.util.spec_from_file_location("runtime_under_test", Path(__file__).resolve().parents[1] / "app_runtime.py")
            runtime = importlib.util.module_from_spec(spec)
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(bundle), create=True), patch.object(sys, "executable", str(install / "TelegramAI.exe")):
                spec.loader.exec_module(runtime)
            self.assertEqual(runtime.ROOT, install)
            self.assertEqual(runtime.RESOURCE_ROOT, bundle)
            self.assertFalse(runtime.SOURCE_MODE)
            runtime.ensure_local_config()
            config = install / ".env"
            self.assertEqual(config.read_text(), "OPENAI_API_KEY=\n")
            config.write_text("local configuration only", encoding="utf-8")
            runtime.ensure_local_config()
            self.assertEqual(config.read_text(), "local configuration only")
            self.assertFalse((bundle / ".env").exists())

    def test_source_override_only_loads_project_modules(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "version.py").write_text("VERSION = 'future'\n", encoding="utf-8")
            (root / "os.py").write_text("raise RuntimeError('wrong module')\n", encoding="utf-8")
            finder = ProjectModules(root)
            spec = finder.find_spec("version")
            self.assertEqual(spec.origin, str(root / "version.py"))
            self.assertIsNone(finder.find_spec("os"))
            self.assertIsNone(finder.find_spec("main"))

    def test_frozen_worker_has_explicit_dispatch_argument(self):
        spec = importlib.util.spec_from_file_location("desktop_under_test", Path(__file__).resolve().parents[1] / "account_manager.py")
        manager = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"main": SimpleNamespace(create_profile=lambda: None)}):
            spec.loader.exec_module(manager)
        with patch.object(manager, "FROZEN", True), patch.object(manager, "CONSOLE_MODE", True):
            command = manager.AccountManager._worker_command(None, "example", ["--list-chats-json"])
            self.assertEqual(command[1:], ["--worker", "--profile", "example", "--list-chats-json"])
            command = manager.AccountManager._worker_command(None, "example", [], interactive=True)
            self.assertEqual(command[1], "--worker-console")
        with patch.object(manager, "FROZEN", True), patch.object(manager, "CONSOLE_MODE", False):
            command = manager.AccountManager._worker_command(None, "example", [], interactive=True)
            self.assertEqual(command[1], "--worker-gui")
            command = manager.AccountManager._worker_command(None, "example", ["--list-chats-json"])
            self.assertEqual(command[1], "--worker")


if __name__ == "__main__":
    unittest.main()
