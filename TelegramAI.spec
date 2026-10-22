# Run: python -m PyInstaller --noconfirm TelegramAI.spec
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

root = Path(SPECPATH)
namespace = {}
exec((root / "version.py").read_text(encoding="utf-8"), namespace)
version = namespace["VERSION"]
version_tuple = namespace["WINDOWS_VERSION"]
metadata = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple, mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("FileDescription", "Telegram AI Account Workbench"),
        StringStruct("FileVersion", version), StringStruct("ProductVersion", version),
        StringStruct("ProductName", "Telegram AI"), StringStruct("OriginalFilename", "TelegramAI.exe"),
    ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
)

# Explicit allowlist: never include .env, profiles, data, sessions or local tools.
resources = [
    (str(root / "assets" / "app-icon-64.png"), "assets"),
    (str(root / "assets" / "app-icon.ico"), "assets"),
    (str(root / ".env.example"), "."),
]
a = Analysis([str(root / "desktop_entry.py")], pathex=[str(root)],
    binaries=[], datas=resources,
    hiddenimports=["account_manager", "main", "ui_effects", "project_updater", "release_updater", "app_runtime", "version", "gui_worker", "image_references"],
    hookspath=[], runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TelegramAI",
    debug=False, strip=False, upx=False, console=False,
    icon=str(root / "assets" / "app-icon.ico"), version=metadata,
)
console_exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="TelegramAI-console",
    debug=False, strip=False, upx=False, console=True,
    icon=str(root / "assets" / "app-icon.ico"), version=metadata,
)
