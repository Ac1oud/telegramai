"""Release version selection and verified download behavior."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import release_updater as updater


class ReleaseUpdaterTests(unittest.TestCase):
    def test_request_falls_back_to_direct_connection(self):
        failed = unittest.mock.Mock()
        failed.open.side_effect = urllib.error.URLError("proxy unavailable")
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = updater.API
        response.read.return_value = b"[]"
        direct = unittest.mock.Mock()
        direct.open.return_value = response
        with patch.object(updater, "_openers", return_value=[failed, direct]):
            self.assertEqual(updater._request(updater.API), b"[]")

    def test_https_updates_try_system_proxy_then_direct(self):
        proxy_handlers = [object(), object()]
        with patch.object(updater.urllib.request, "getproxies", return_value={"http": "http://proxy.example:8080"}), \
             patch.object(updater.urllib.request, "ProxyHandler", side_effect=proxy_handlers) as make_handler, \
             patch.object(updater.urllib.request, "HTTPSHandler", return_value="https"), \
             patch.object(updater.ssl, "create_default_context", return_value="context"), \
             patch.object(updater.certifi, "where", return_value="ca.pem"), \
             patch.object(updater.urllib.request, "build_opener", side_effect=["proxy", "direct"]):
            self.assertEqual(updater._openers(), ["proxy", "direct"])
        self.assertEqual(make_handler.call_args_list[0].args[0], {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"})
        self.assertEqual(make_handler.call_args_list[1].args[0], {})

    def test_private_or_missing_release_is_reported_as_visibility_problem(self):
        error = urllib.error.HTTPError(updater.API, 404, "Not Found", {}, None)
        with patch.object(updater, "_openers") as openers:
            opener = openers.return_value = [unittest.mock.Mock()]
            opener[0].open.side_effect = error
            with self.assertRaisesRegex(updater.ReleaseUpdateError, "HTTP 404.*设为公开"):
                updater._request(updater.API)

    def test_selects_newest_published_release_ahead_of_current(self):
        releases = [
            {"tag_name": "v27.0.0-alpha", "draft": True},
            {"tag_name": "v26.1.0-alpha", "draft": False},
            {"tag_name": "v26.1.10-alpha", "draft": False},
            {"tag_name": "v26.1.1-alpha", "draft": False},
            {"tag_name": "unversioned", "draft": False},
        ]
        with patch.object(updater, "_request", return_value=json.dumps(releases).encode()):
            latest = updater.check_latest()
        self.assertEqual(latest["tag_name"], "v26.1.10-alpha")

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

    def test_manual_check_bypasses_snooze(self):
        releases = [{"tag_name": "v26.1.10-alpha", "draft": False}]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "update-state.json"
            with patch.object(updater, "state_path", return_value=path), \
                 patch.object(updater, "_request", return_value=json.dumps(releases).encode()):
                updater.snooze("v26.1.10-alpha", now=100)
                self.assertIsNone(updater.check_latest(now=101))
                self.assertEqual(updater.check_latest(now=101, ignore_snooze=True)["tag_name"], "v26.1.10-alpha")


if __name__ == "__main__":
    unittest.main()
