import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
with patch.object(sys, "path", [p for p in sys.path if Path(p).name != ".deps"]):
    import main

class ProfileIsolationTests(unittest.TestCase):
    def test_global_instructions_default_to_the_editable_main_prompt(self):
        self.assertIn("角色表达风格", main.DEFAULT_MODEL_INSTRUCTIONS)
        self.assertIn("global_model_instructions", main.Config.__dataclass_fields__)
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            (root / ".env").write_text(
                "TELEGRAM_API_ID=123\nTELEGRAM_API_HASH=test\nALLOWED_CHAT_IDS=-1001\n",
                encoding="utf-8",
            )
            with patch.object(main, "ROOT", root), patch.object(main, "PROFILE_DIR", root / "profiles"):
                self.assertEqual(main.Config.load().global_model_instructions, main.DEFAULT_MODEL_INSTRUCTIONS)

    def test_dotenv_writer_roundtrips_multiline_prompts_without_orphan_lines(self):
        from account_manager import _write_profile_settings

        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / "profile.env"
            env_file.write_text(
                "MODEL_SYSTEM_PROMPT='legacy first line\nlegacy tail'\nOPENAI_MODEL='keep-model'\n",
                encoding="utf-8",
            )
            expected = "第一行\n第二行包含 ' 引号和 \\ 路径"
            _write_profile_settings(env_file, {
                "MODEL_SYSTEM_PROMPT": expected,
                "MODEL_PERSONA_PROMPT": "新的人设\n第二行",
            })
            values = main.read_env_file(env_file)
            self.assertEqual(values["MODEL_SYSTEM_PROMPT"], expected)
            self.assertEqual(values["MODEL_PERSONA_PROMPT"], "新的人设\n第二行")
            self.assertEqual(values["OPENAI_MODEL"], "keep-model")
            self.assertNotIn("legacy tail", env_file.read_text(encoding="utf-8"))
            self.assertEqual(env_file.read_text(encoding="utf-8").count("MODEL_SYSTEM_PROMPT="), 1)

    def test_prompt_settings_reload_for_the_next_trigger_without_listener_restart(self):
        from account_manager import _write_profile_settings

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            profiles = root / "profiles"
            profiles.mkdir()
            (root / ".env").write_text(
                "TELEGRAM_API_ID=123\nTELEGRAM_API_HASH=test\nALLOWED_CHAT_IDS=-1001\n"
                "GLOBAL_MODEL_INSTRUCTIONS=global-old\nGLOBAL_SPEAKING_RULES=[]\n",
                encoding="utf-8",
            )
            profile_file = profiles / "a.env"
            profile_file.write_text(
                "ALLOWED_CHAT_IDS=-1001\nMODEL_SYSTEM_PROMPT=account-old\n"
                "ACCOUNT_SPEAKING_RULES=account-rule-old\nGLOBAL_RULE_EXCEPTIONS=[]\n",
                encoding="utf-8",
            )
            with patch.object(main, "ROOT", root), patch.object(main, "PROFILE_DIR", profiles):
                config = main.Config.load(profile="a")
                self.assertIn("account-old", main.compose_reply_instructions(config))

                _write_profile_settings(profile_file, {
                    "MODEL_SYSTEM_PROMPT": "account-new",
                    "ACCOUNT_SPEAKING_RULES": "account-rule-new",
                })
                _write_profile_settings(root / ".env", {
                    "GLOBAL_MODEL_INSTRUCTIONS": "global-new",
                })
                refreshed = main.reload_prompt_settings(config)

                instructions = main.compose_reply_instructions(refreshed)
                self.assertIn("account-new", instructions)
                self.assertIn("account-rule-new", instructions)
                self.assertNotIn("global-new", instructions)

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
            global_rules = json.dumps([
                {"id": "rule-a", "text": "global style rule A"},
                {"id": "rule-b", "text": "global style rule B"},
            ])
            (root / '.env').write_text(
                'TELEGRAM_API_ID=123\nTELEGRAM_API_HASH=test\nALLOWED_CHAT_IDS=-999\nALLOWED_SENDER_IDS=999\nOWNER_USER_IDS=999\nOWNER_USERNAMES=global_owner\nSESSION_PATH=data/global\nOPENAI_API_KEY=shared-test\nOPENAI_MODEL=shared-model\nOPENAI_IMAGE_MODEL=shared-image\n'
                f'GLOBAL_MODEL_INSTRUCTIONS=global-style\nGLOBAL_SPEAKING_RULES=\'{global_rules}\'\n',
            )
            (profiles / 'a.env').write_text(
                'ALLOWED_CHAT_IDS=-101\nALLOWED_SENDER_IDS=101\nOWNER_USER_IDS=102\nOWNER_USERNAMES=owner_a\n'
                'OPENAI_API_KEY=key-a\nOPENAI_MODEL=model-a\nOPENAI_IMAGE_API_KEY=image-key-a\nOPENAI_IMAGE_MODEL=image-a\n'
                'MODEL_SYSTEM_PROMPT=account-style\nMODEL_PERSONA_PROMPT=account-persona\n'
                'ACCOUNT_SPEAKING_RULES=account-supplement\nGLOBAL_RULE_EXCEPTIONS=\'["rule-a"]\'\n'
            )
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
                self.assertEqual(a.global_model_instructions, 'global-style')
                self.assertEqual(a.global_speaking_rules, (("rule-a", "global style rule A"), ("rule-b", "global style rule B")))
                self.assertEqual(a.global_rule_exceptions, {"rule-a"})
                a_instructions = main.compose_reply_instructions(a)
                self.assertNotIn("global-style", a_instructions)
                self.assertIn("account-style", a_instructions)
                self.assertNotIn("global style rule A", a_instructions)
                self.assertIn("global style rule B", a_instructions)
                self.assertIn("account-supplement", a_instructions)
                self.assertLess(a_instructions.index("global style rule B"), a_instructions.index("account-supplement"))
                b_instructions = main.compose_reply_instructions(b)
                self.assertIn("global-style", b_instructions)
                self.assertIn("global style rule A", b_instructions)
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
