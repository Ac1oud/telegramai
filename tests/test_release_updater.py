"""Release version selection and verified download behavior."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import release_updater as updater


class ReleaseUpdaterTests(unittest.TestCase):
    def test_selects_newest_published_release_ahead_of_current(self):
        releases = [
            {"tag_name": "v27.0.0-alpha", "draft": True},
            {"tag_name": "v26.1.0-alpha", "draft": False},
            {"tag_name": "v26.1.2-alpha", "draft": False},
            {"tag_name": "v26.1.1-alpha", "draft": False},
            {"tag_name": "unversioned", "draft": False},
        ]
        with patch.object(updater, "_request", return_value=json.dumps(releases).encode()):
            latest = updater.check_latest()
        self.assertEqual(latest["tag_name"], "v26.1.2-alpha")

    def test_download_verifies_release_digest_before_writing(self):
        payload = b"verified executable bytes"
        digest = hashlib.sha256(payload).hexdigest()
        release = {"assets": [
            {"name": "TelegramAI.exe", "browser_download_url": "https://github.com/Ac1oud/telegramai/releases/download/v1/TelegramAI.exe", "digest": f"sha256:{digest}"},
            {"name": "SHA256SUMS.txt", "browser_download_url": "https://github.com/Ac1oud/telegramai/releases/download/v1/SHA256SUMS.txt"},
        ]}
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "TelegramAI.exe"
            with patch.object(updater, "_request", side_effect=[b"", payload]):
                staging = updater.download_update(release, executable)
            self.assertEqual(staging.read_bytes(), payload)
            with patch.object(updater, "_request", side_effect=[b"", b"tampered"]):
                with self.assertRaises(updater.ReleaseUpdateError):
                    updater.download_update(release, executable)
            self.assertFalse(executable.exists())

    def test_snooze_is_scoped_to_a_release_tag_and_expires(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "update-state.json"
            with patch.object(updater, "state_path", return_value=path):
                updater.snooze("v26.1.2-alpha", now=100)
                self.assertTrue(updater.is_snoozed("v26.1.2-alpha", now=101))
                self.assertFalse(updater.is_snoozed("v26.1.3-alpha", now=101))
                self.assertFalse(updater.is_snoozed("v26.1.2-alpha", now=100 + updater.SNOOZE_SECONDS + 1))


if __name__ == "__main__":
    unittest.main()
