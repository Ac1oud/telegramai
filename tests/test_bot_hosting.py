import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

from bot_hosting import BotHostingService, load_config, save_config


class BotHostingTests(unittest.TestCase):
    def test_config_round_trip_stays_in_selected_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data" / "bot-hosting.json"
            save_config(path, {"bot_token": "local-token", "turnstile_enabled": True})
            self.assertEqual(load_config(path), {"bot_token": "local-token", "turnstile_enabled": True})

    def test_unverified_user_receives_short_lived_ticket_link(self):
        service = BotHostingService({"turnstile_enabled": True, "verify_url": "https://example.test/verify"})
        service.api_call = lambda _token, _method, payload: payload
        with patch("bot_hosting._api", return_value={"message_id": 1}):
            service._handle({"chat": {"id": 100}, "from": {"id": 100}, "text": "/start"})
        self.assertEqual(len(service.tickets), 1)
        self.assertEqual(service.tickets[next(iter(service.tickets))][0], 100)
        self.assertEqual(service.config.get("bot_username"), None)

    def test_plain_message_forwards_to_operator_and_records_reply_mapping(self):
        service = BotHostingService({"operator_chat_id": 900})
        calls = []
        def fake_api(_token, method, payload):
            calls.append((method, payload))
            return {"message_id": 77 if method == "forwardMessage" else 78}
        service.api_call = fake_api
        service._handle({"chat": {"id": 100}, "from": {"id": 100}, "message_id": 5, "text": "hello"})
        self.assertEqual(service.operator_map, {77: 100})
        self.assertEqual(calls[0][0], "forwardMessage")

    def test_operator_reply_is_copied_back_to_original_chat(self):
        service = BotHostingService({"operator_chat_id": 900})
        calls = []
        service.api_call = lambda _token, method, payload: calls.append((method, payload)) or {}
        update = {"message": {"chat": {"id": 900}, "from": {"id": 900}, "message_id": 78,
                               "reply_to_message": {"message_id": 77}}}
        service.operator_map[77] = 100
        with patch.object(service, "_send", wraps=service._send):
            replied = update["message"]
            service._send("copyMessage", {"chat_id": service.operator_map[replied["reply_to_message"]["message_id"]],
                                          "from_chat_id": 900, "message_id": replied["message_id"]})
        self.assertEqual(calls[0][0], "copyMessage")
        self.assertEqual(calls[0][1]["chat_id"], 100)

    def test_remote_ticket_failure_is_written_to_status_log(self):
        messages = []
        service = BotHostingService({"verify_api_url": "https://verify.test", "verify_api_key": "key",
                                     "turnstile_enabled": True}, on_status=messages.append)
        service._send = lambda *_args: {}
        error = HTTPError("https://verify.test/api/tickets", 502, "Bad Gateway", {}, BytesIO(b"worker offline"))
        with patch("bot_hosting.urllib.request.urlopen", side_effect=error):
            service._handle({"chat": {"id": 100}, "from": {"id": 100}, "text": "/start"})
        self.assertTrue(any("验证服务不可用" in entry and "HTTP 502" in entry and "worker offline" in entry for entry in messages))


if __name__ == "__main__":
    unittest.main()
