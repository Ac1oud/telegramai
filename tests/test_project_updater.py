"""用真实的临时 Git 仓库验证更新及本地数据保护。"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from project_updater import GitUpdater, UpdateError


class GitUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote = root / "remote.git"
        self.publisher = root / "publisher"
        self.client = root / "client"
        self.git(root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(root, "clone", str(self.remote), str(self.publisher))
        self.write(self.publisher, ".gitignore", ".env\ndata/\nprofiles/\n*.log\n")
        self.write(self.publisher, "app.py", "version = 1\n")
        self.write(self.publisher, "requirements.txt", "")
        self.commit(self.publisher)
        self.git(self.publisher, "push", "-u", "origin", "main")
        self.git(root, "clone", str(self.remote), str(self.client))
        self.updater = GitUpdater(self.client)

    @staticmethod
    def git(path, *args):
        result = subprocess.run(
            ["git", "-C", str(path), "-c", "user.name=Updater Test", "-c", "user.email=test@example.invalid", *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    @staticmethod
    def write(root, name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def commit(self, path):
        self.git(path, "add", ".")
        self.git(path, "commit", "-m", "Test version")

    def publish(self, name="app.py", value="version = 2\n"):
        self.write(self.publisher, name, value)
        self.commit(self.publisher)
        self.git(self.publisher, "push")

    def test_latest_does_not_change_checkout(self):
        result = self.updater.sync()
        self.assertFalse(result.updated)
        self.assertEqual((result.ahead, result.behind), (0, 0))

    def test_check_and_fast_forward_preserve_private_files(self):
        private = {".env": "local test configuration", "profiles/local.env": "local profile", "data/account.session": "local session"}
        for name, value in private.items():
            self.write(self.client, name, value)
        self.publish()
        status = self.updater.check()
        self.assertEqual(status.behind, 1)
        self.assertEqual((self.client / "app.py").read_text(), "version = 1\n")
        result = self.updater.sync()
        self.assertTrue(result.updated)
        self.assertFalse(result.dependencies_changed)
        self.assertEqual(self.git(self.client, "rev-parse", "HEAD"), result.target)
        for name, value in private.items():
            self.assertEqual((self.client / name).read_text(), value)

    def test_changed_dependencies_are_reported(self):
        self.publish("requirements.txt", "example-package==1.0\n")
        self.assertTrue(self.updater.sync().dependencies_changed)

    def test_dirty_and_untracked_files_block_update(self):
        self.publish()
        self.write(self.client, "app.py", "local edit\n")
        with self.assertRaises(UpdateError):
            self.updater.sync()
        self.assertEqual((self.client / "app.py").read_text(), "local edit\n")
        self.git(self.client, "restore", "app.py")
        self.write(self.client, "new.py", "new local code\n")
        with self.assertRaises(UpdateError):
            self.updater.sync()

    def test_diverged_history_is_not_merged(self):
        self.write(self.client, "local.py", "local commit\n")
        self.commit(self.client)
        before = self.git(self.client, "rev-parse", "HEAD")
        self.publish()
        status = self.updater.check()
        self.assertEqual((status.ahead, status.behind), (1, 1))
        with self.assertRaises(UpdateError):
            self.updater.sync()
        self.assertEqual(self.git(self.client, "rev-parse", "HEAD"), before)

    def test_local_commits_are_reported_without_reset(self):
        self.write(self.client, "local.py", "local commit\n")
        self.commit(self.client)
        status = self.updater.sync()
        self.assertEqual((status.ahead, status.behind, status.updated), (1, 0, False))

    def test_remote_private_file_is_rejected(self):
        self.write(self.publisher, ".env", "remote configuration")
        self.git(self.publisher, "add", "--force", ".env")
        self.git(self.publisher, "commit", "-m", "Invalid remote configuration")
        self.git(self.publisher, "push")
        with self.assertRaises(UpdateError):
            self.updater.sync()
        self.assertFalse((self.client / ".env").exists())

    def test_ignored_file_collision_is_preserved(self):
        self.write(self.client, "local.log", "keep this local content")
        self.write(self.publisher, "local.log", "remote content")
        self.git(self.publisher, "add", "--force", "local.log")
        self.git(self.publisher, "commit", "-m", "Remote collision")
        self.git(self.publisher, "push")
        with self.assertRaises(UpdateError):
            self.updater.sync()
        self.assertEqual((self.client / "local.log").read_text(), "keep this local content")

    def test_missing_upstream_and_unreachable_remote(self):
        self.git(self.client, "branch", "--unset-upstream")
        with self.assertRaises(UpdateError):
            self.updater.check()
        self.git(self.client, "branch", "--set-upstream-to=origin/main")
        self.git(self.client, "remote", "set-url", "origin", str(self.remote / "missing"))
        with self.assertRaises(UpdateError):
            self.updater.check()


if __name__ == "__main__":
    unittest.main()
