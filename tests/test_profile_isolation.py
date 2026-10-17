import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
with patch.object(sys, "path", [p for p in sys.path if Path(p).name != ".deps"]):
    import main

class ProfileIsolationTests(unittest.TestCase):
    def test_accounts_never_inherit_global_or_previous_permissions(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            profiles = root / 'profiles'
            profiles.mkdir()
            (root / '.env').write_text('TELEGRAM_API_ID=123\nTELEGRAM_API_HASH=test\nALLOWED_CHAT_IDS=-999\nALLOWED_SENDER_IDS=999\nOWNER_USER_IDS=999\nOWNER_USERNAMES=global_owner\nSESSION_PATH=data/global\nOPENAI_API_KEY=shared-test\n')
            (profiles / 'a.env').write_text('ALLOWED_CHAT_IDS=-101\nALLOWED_SENDER_IDS=101\nOWNER_USER_IDS=102\nOWNER_USERNAMES=owner_a\n')
            (profiles / 'b.env').write_text('ALLOWED_CHAT_IDS=-202\nOPENAI_API_KEY=wrong-profile-key\n')
            before = dict(os.environ)
            with patch.object(main, 'ROOT', root), patch.object(main, 'PROFILE_DIR', profiles):
                a = main.Config.load(profile='a')
                b = main.Config.load(profile='b')
                again = main.Config.load(profile='a')
                self.assertEqual(a, again)
                self.assertEqual(a.allowed_chat_ids, {-101})
                self.assertEqual(b.allowed_chat_ids, {-202})
                self.assertFalse(b.allowed_sender_ids | b.owner_user_ids | b.owner_usernames)
                self.assertEqual(b.openai_api_key, 'shared-test')
                self.assertEqual(b.session_path, root / 'data/profiles/b/telegram')
                self.assertNotEqual(a.state_path, b.state_path)
                created = main.create_profile('new')
                self.assertIn('ALLOWED_CHAT_IDS=\n', created.read_text(encoding="utf-8"))
                with self.assertRaisesRegex(ValueError, 'ALLOWED_CHAT_IDS'):
                    main.Config.load(profile='new')
                self.assertFalse(main.Config.load(profile='new', list_chats=True).allowed_chat_ids)
                self.assertEqual(main.Config.load().allowed_chat_ids, {-999})
            self.assertEqual(dict(os.environ), before)

if __name__ == '__main__':
    unittest.main()
