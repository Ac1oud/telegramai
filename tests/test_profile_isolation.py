import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
with patch.object(sys, "path", [p for p in sys.path if Path(p).name != ".deps"]):
    import main

class ProfileIsolationTests(unittest.TestCase):
    def test_assistant_final_text_never_includes_reasoning_items(self):
        response = type("Response", (), {
            "output": [
                type("Reasoning", (), {"type": "reasoning", "summary": []})(),
                type("Message", (), {"type": "message", "role": "assistant", "content": [
                    type("Text", (), {"type": "output_text", "text": "群聊最终摘要"})(),
                ]})(),
            ],
            "output_text": "内部思考过程\n群聊最终摘要",
        })()
        self.assertEqual(main.assistant_final_text(response, strict=True), "群聊最终摘要")
        empty = type("Response", (), {"output": [], "output_text": "泄漏的推理"})()
        self.assertEqual(main.assistant_final_text(empty, strict=True), "")

    def test_assistant_final_text_supports_sdk_dict_payloads(self):
        response = {
            "output": [
                {"type": "reasoning", "summary": [{"text": "internal"}]},
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "final dict"}
                ]},
            ],
            "output_text": "internal final aggregate",
        }
        self.assertEqual(main.assistant_final_text(response, strict=True), "final dict")

    def test_accounts_never_inherit_global_or_previous_permissions(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            profiles = root / 'profiles'
            profiles.mkdir()
            (root / '.env').write_text('TELEGRAM_API_ID=123\nTELEGRAM_API_HASH=test\nALLOWED_CHAT_IDS=-999\nALLOWED_SENDER_IDS=999\nOWNER_USER_IDS=999\nOWNER_USERNAMES=global_owner\nSESSION_PATH=data/global\nOPENAI_API_KEY=shared-test\nOPENAI_MODEL=shared-model\nOPENAI_IMAGE_MODEL=shared-image\n')
            (profiles / 'a.env').write_text('ALLOWED_CHAT_IDS=-101\nALLOWED_SENDER_IDS=101\nOWNER_USER_IDS=102\nOWNER_USERNAMES=owner_a\nOPENAI_API_KEY=key-a\nOPENAI_MODEL=model-a\nOPENAI_IMAGE_API_KEY=image-key-a\nOPENAI_IMAGE_MODEL=image-a\n')
            (profiles / 'b.env').write_text('ALLOWED_CHAT_IDS=-202\nOPENAI_API_KEY=key-b\nOPENAI_MODEL=model-b\nOPENAI_IMAGE_API_KEY=image-key-b\nOPENAI_IMAGE_MODEL=image-b\n')
            (profiles / 'legacy.env').write_text('ALLOWED_CHAT_IDS=-303\n')
            before = dict(os.environ)
            with patch.object(main, 'ROOT', root), patch.object(main, 'PROFILE_DIR', profiles):
                a = main.Config.load(profile='a')
                b = main.Config.load(profile='b')
                again = main.Config.load(profile='a')
                self.assertEqual(a, again)
                self.assertEqual(a.allowed_chat_ids, {-101})
                self.assertEqual(b.allowed_chat_ids, {-202})
                self.assertFalse(b.allowed_sender_ids | b.owner_user_ids | b.owner_usernames)
                self.assertEqual(a.openai_api_key, 'key-a')
                self.assertEqual(a.openai_model, 'model-a')
                self.assertEqual(a.openai_image_api_key, 'image-key-a')
                self.assertEqual(a.openai_image_model, 'image-a')
                self.assertEqual(b.openai_api_key, 'key-b')
                self.assertEqual(b.openai_model, 'model-b')
                self.assertEqual(b.openai_image_api_key, 'image-key-b')
                self.assertEqual(b.openai_image_model, 'image-b')
                legacy = main.Config.load(profile='legacy')
                self.assertEqual(legacy.openai_api_key, 'shared-test')
                self.assertEqual(legacy.openai_image_model, 'shared-image')
                migrated_text = (profiles / 'legacy.env').read_text(encoding='utf-8')
                self.assertIn("OPENAI_API_KEY='shared-test'", migrated_text)
                self.assertIn("OPENAI_IMAGE_MODEL='shared-image'", migrated_text)
                self.assertEqual(b.session_path, root / 'data/profiles/b/telegram')
                self.assertNotEqual(a.state_path, b.state_path)
                created = main.create_profile('new')
                self.assertIn('ALLOWED_CHAT_IDS=\n', created.read_text(encoding="utf-8"))
                self.assertIn("OPENAI_API_KEY='shared-test'", created.read_text(encoding="utf-8"))
                self.assertIn("OPENAI_MODEL='shared-model'", created.read_text(encoding="utf-8"))
                with self.assertRaisesRegex(ValueError, 'ALLOWED_CHAT_IDS'):
                    main.Config.load(profile='new')
                self.assertFalse(main.Config.load(profile='new', list_chats=True).allowed_chat_ids)
                self.assertEqual(main.Config.load().allowed_chat_ids, {-999})
            self.assertEqual(dict(os.environ), before)

    def test_identity_permissions_reload_after_profile_is_saved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profiles = root / 'profiles'
            profiles.mkdir()
            profile_file = profiles / 'active.env'
            profile_file.write_text(
                'ALLOWED_SENDER_IDS=101\nOWNER_USER_IDS=102\nOWNER_USERNAMES=old_owner\n',
                encoding='utf-8',
            )
            fallback = type('Fallback', (), {
                'allowed_sender_ids': frozenset({1}),
                'owner_user_ids': frozenset({2}),
                'owner_usernames': frozenset({'fallback'}),
            })()
            with patch.object(main, 'ROOT', root), patch.object(main, 'PROFILE_DIR', profiles):
                before = main.load_identity_permissions('active', fallback)
                self.assertEqual(before.owner_user_ids, {102})
                profile_file.write_text(
                    'ALLOWED_SENDER_IDS=201\nOWNER_USER_IDS=202\nOWNER_USERNAMES=@New_Owner\n',
                    encoding='utf-8',
                )
                after = main.load_identity_permissions('active', fallback)
                self.assertEqual(after.allowed_sender_ids, {201})
                self.assertEqual(after.owner_user_ids, {202})
                self.assertEqual(after.owner_usernames, {'new_owner'})

if __name__ == '__main__':
    unittest.main()
