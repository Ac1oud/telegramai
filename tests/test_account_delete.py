"""在临时目录中验证账号删除确认，不创建窗口或连接 Telegram。"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

# 删除流程无需 Telegram 依赖；单独加载测试模块，避免替换正式模块缓存。
_spec = importlib.util.spec_from_file_location(
    "_account_manager_delete_tests", Path(__file__).resolve().parents[1] / "account_manager.py",
)
account_manager = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {"main": SimpleNamespace(create_profile=Mock())}):
    _spec.loader.exec_module(account_manager)


class AccountDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()
        self.profile_file = self.profiles / "example.env"
        self.profile_file.write_text("TELEGRAM_USERNAME=example\n", encoding="utf-8")
        self.other_file = self.profiles / "other.env"
        self.other_file.write_text("TELEGRAM_USERNAME=other\n", encoding="utf-8")
        self.session_file = self.root / "telegram.session"
        self.session_file.write_bytes(b"test session")
        self.state_file = self.root / "state.sqlite3"
        self.state_file.write_bytes(b"test state")
        self.original_files = {
            path: path.read_bytes()
            for path in (self.profile_file, self.other_file, self.session_file, self.state_file)
        }
        self.manager = SimpleNamespace(
            selected_profile=Mock(return_value="example"),
            child_processes=[],
            refresh_profiles=Mock(),
            status=SimpleNamespace(set=Mock()),
            profile_list=object(),
        )
        self.manager.focus_get = Mock(return_value=self.manager.profile_list)
        self.manager.delete_profile = MethodType(account_manager.AccountManager.delete_profile, self.manager)
        profile_patch = patch.object(account_manager, "PROFILE_DIR", self.profiles)
        profile_patch.start()
        self.addCleanup(profile_patch.stop)
        dialogs_patch = patch.object(account_manager, "messagebox")
        self.dialogs = dialogs_patch.start()
        self.dialogs.NO = "no"
        self.addCleanup(dialogs_patch.stop)

    def assert_original_files_unchanged(self):
        for path, content in self.original_files.items():
            self.assertEqual(path.read_bytes(), content)

    def test_cancel_keeps_all_files_and_selection(self):
        self.dialogs.askyesno.return_value = False
        self.manager.delete_profile()
        self.assert_original_files_unchanged()
        self.manager.refresh_profiles.assert_not_called()
        self.manager.status.set.assert_not_called()
        self.assertEqual(self.dialogs.askyesno.call_args.kwargs["default"], "no")
        self.assertIs(self.dialogs.askyesno.call_args.kwargs["parent"], self.manager)
        self.assertFalse(self.manager._delete_in_progress)

    def test_confirm_removes_only_selected_config(self):
        self.dialogs.askyesno.return_value = True
        self.manager.delete_profile()
        self.assertFalse(self.profile_file.exists())
        for path in (self.other_file, self.session_file, self.state_file):
            self.assertEqual(path.read_bytes(), self.original_files[path])
        self.manager.refresh_profiles.assert_called_once_with()
        self.manager.status.set.assert_called_once()
        self.dialogs.showerror.assert_not_called()

    def test_running_account_cannot_be_deleted(self):
        process = SimpleNamespace(poll=Mock(return_value=None))
        self.manager.child_processes = [("example", "listen", process)]
        self.manager.delete_profile()
        self.assert_original_files_unchanged()
        self.dialogs.askyesno.assert_not_called()
        self.dialogs.showwarning.assert_called_once()
        self.assertIs(self.dialogs.showwarning.call_args.kwargs["parent"], self.manager)
        self.assertFalse(self.manager._delete_in_progress)

    def test_no_selection_does_nothing(self):
        self.manager.selected_profile.return_value = None
        self.manager.delete_profile()
        self.assert_original_files_unchanged()
        self.dialogs.assert_not_called()
        self.dialogs.askyesno.assert_not_called()
        self.dialogs.showinfo.assert_not_called()
        self.manager.refresh_profiles.assert_not_called()

    def test_modal_dialog_cannot_reenter_delete(self):
        def confirm(*_args, **_kwargs):
            self.manager.delete_profile()
            return False

        self.dialogs.askyesno.side_effect = confirm
        self.manager.delete_profile()
        self.dialogs.askyesno.assert_called_once()
        self.assert_original_files_unchanged()
        self.assertFalse(self.manager._delete_in_progress)

    def test_failed_delete_keeps_files_and_releases_confirmation_guard(self):
        self.dialogs.askyesno.return_value = True
        with patch.object(Path, "unlink", side_effect=PermissionError("file is locked")):
            self.manager.delete_profile()
        self.assert_original_files_unchanged()
        self.manager.refresh_profiles.assert_not_called()
        self.dialogs.showerror.assert_called_once()
        self.assertIs(self.dialogs.showerror.call_args.kwargs["parent"], self.manager)
        self.assertFalse(self.manager._delete_in_progress)

    def test_shortcut_only_deletes_when_list_has_focus(self):
        self.manager.delete_profile = Mock()
        shortcut = MethodType(account_manager.AccountManager._delete_profile_shortcut, self.manager)
        event = SimpleNamespace(widget=self.manager.profile_list)
        self.assertEqual(shortcut(event), "break")
        self.manager.delete_profile.assert_called_once_with()

        self.manager.delete_profile.reset_mock()
        self.manager.focus_get.return_value = object()
        self.assertEqual(shortcut(event), "break")
        self.manager.delete_profile.assert_not_called()

        self.manager.focus_get.return_value = self.manager.profile_list
        self.assertEqual(shortcut(SimpleNamespace(widget=object())), "break")
        self.manager.delete_profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
