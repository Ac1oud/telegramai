"""Public GitHub Release checks and portable Windows EXE replacement."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from version import RELEASE_TAG, VERSION


API = "https://api.github.com/repos/Ac1oud/telegramai/releases?per_page=20"
USER_AGENT = "TelegramAI-Updater"
SNOOZE_SECONDS = 24 * 60 * 60


class ReleaseUpdateError(RuntimeError):
    """An update error safe to show in the desktop UI."""


def _version_key(tag: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", tag)
    if not parts:
        raise ReleaseUpdateError("GitHub 返回了无法识别的版本号。")
    return tuple(int(part) for part in parts)


def _opener():
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy}))
    return urllib.request.build_opener()


def _request(url: str, *, binary: bool = False) -> bytes:
    if not url.startswith("https://api.github.com/") and not url.startswith("https://github.com/"):
        raise ReleaseUpdateError("更新地址不是受信任的 GitHub 地址。")
    request = urllib.request.Request(url, headers={
        "Accept": "application/octet-stream" if binary else "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    })
    try:
        with _opener().open(request, timeout=30 if not binary else 180) as response:
            final_host = response.geturl().split("/", 3)[2].lower()
            if final_host not in {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}:
                raise ReleaseUpdateError("GitHub 更新下载跳转到了不受信任的地址。")
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ReleaseUpdateError("连接 GitHub 更新服务失败，请检查网络后重试。") from exc


def check_latest(*, now: float | None = None) -> dict | None:
    """Return a newer public release, unless this tag is currently snoozed."""
    try:
        releases = json.loads(_request(API).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseUpdateError("GitHub 更新信息格式无效。") from exc
    if not isinstance(releases, list):
        raise ReleaseUpdateError("GitHub 没有返回有效的 Release 列表。")
    current = _version_key(RELEASE_TAG)
    candidates = []
    for item in releases:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        try:
            _version_key(str(item.get("tag_name", "")))
        except ReleaseUpdateError:
            continue
        candidates.append(item)
    candidates.sort(key=lambda item: _version_key(str(item["tag_name"])), reverse=True)
    latest = next((item for item in candidates if _version_key(str(item.get("tag_name", ""))) > current), None)
    if latest and is_snoozed(str(latest.get("tag_name", "")), now=now):
        return None
    return latest


def is_snoozed(tag: str, *, now: float | None = None) -> bool:
    state = _read_state()
    return state.get("snoozed_tag") == tag and float(state.get("snoozed_until", 0)) > (time.time() if now is None else now)


def snooze(tag: str, *, now: float | None = None) -> None:
    state = {"snoozed_tag": tag, "snoozed_until": (time.time() if now is None else now) + SNOOZE_SECONDS}
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError as exc:
        raise ReleaseUpdateError("无法保存稍后提醒设置，请检查本机用户目录权限。") from exc


def state_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or tempfile.gettempdir()
    return Path(base) / "TelegramAI" / "update-state.json"


def _read_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def download_update(release: dict, executable: Path) -> Path:
    """Download the matching portable EXE and verify its published SHA-256."""
    name = executable.name
    assets = {asset.get("name"): asset for asset in release.get("assets", []) if isinstance(asset, dict)}
    asset = assets.get(name)
    sums = assets.get("SHA256SUMS.txt")
    if not asset or not asset.get("browser_download_url") or not sums or not sums.get("browser_download_url"):
        raise ReleaseUpdateError(f"此版本缺少 {name} 或 SHA256SUMS.txt，暂时无法安全更新。")
    checksum_text = _request(sums["browser_download_url"], binary=True).decode("utf-8", errors="replace")
    expected = None
    digest = asset.get("digest", "")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        expected = digest.partition(":")[2].lower()
    if not expected:
        match = re.search(rf"(?m)^([0-9a-fA-F]{{64}})\s+\*?{re.escape(name)}\s*$", checksum_text)
        expected = match.group(1).lower() if match else None
    if not expected or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ReleaseUpdateError("Release 没有提供有效的 EXE SHA-256 校验值。")
    blob = _request(asset["browser_download_url"], binary=True)
    if hashlib.sha256(blob).hexdigest() != expected:
        raise ReleaseUpdateError("下载文件校验失败，文件未应用。请稍后重试。")
    staging = executable.with_name(executable.name + ".update")
    try:
        staging.write_bytes(blob)
    except OSError as exc:
        raise ReleaseUpdateError("无法写入新版 EXE。请将程序放在可写文件夹后重试。") from exc
    return staging


def launch_replacement(executable: Path, staging: Path) -> None:
    """Wait for this GUI to exit, atomically replace it, then restart it."""
    helper = executable.with_name("TelegramAI-update.ps1")
    backup = executable.with_name(executable.name + ".previous")
    script = r'''param([int]$ParentId, [string]$Executable, [string]$Staging, [string]$Backup)
$ErrorActionPreference = 'Stop'
while (Get-Process -Id $ParentId -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 250 }
try {
    if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Force }
    Move-Item -LiteralPath $Executable -Destination $Backup
    Move-Item -LiteralPath $Staging -Destination $Executable
    Start-Process -FilePath $Executable -ArgumentList '--update-complete'
} catch {
    if (Test-Path -LiteralPath $Backup) {
        if (Test-Path -LiteralPath $Executable) { Remove-Item -LiteralPath $Executable -Force }
        Move-Item -LiteralPath $Backup -Destination $Executable
        Start-Process -FilePath $Executable -ArgumentList '--update-failed'
    }
}
'''
    try:
        helper.write_text(script, encoding="utf-8")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(helper),
             str(os.getpid()), str(executable), str(staging), str(backup)],
            close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise ReleaseUpdateError("无法启动 EXE 替换程序；新版已下载但尚未安装。") from exc
