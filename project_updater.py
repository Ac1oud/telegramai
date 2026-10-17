"""Git 在线更新；只允许快进，保留本机配置与未提交的代码。"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class UpdateError(RuntimeError):
    """可以直接向用户显示的更新错误。"""


@dataclass(frozen=True)
class UpdateStatus:
    current: str
    target: str
    ahead: int
    behind: int
    updated: bool = False
    dependencies_changed: bool = False

    def message(self) -> str:
        version = f"当前版本：{self.current[:8]}"
        if self.updated:
            text = f"已更新到 {self.target[:8]}。请关闭并重新打开账号管理器，然后启动监听。"
            if self.dependencies_changed:
                text += "\n\n依赖文件已变化，请先按 README 的说明重新安装 requirements.txt。"
            return text
        if self.ahead and self.behind:
            return f"{version}\n本地领先 {self.ahead} 个提交，远程另有 {self.behind} 个提交。请先在 Git 中处理分支分歧。"
        if self.behind:
            return f"{version}\n发现 {self.behind} 个新提交，最新版本：{self.target[:8]}。点击“同步更新”获取。"
        if self.ahead:
            return f"{version}\n本地领先 {self.ahead} 个提交，尚未推送到远程；没有待下载的更新。"
        return f"{version}\n当前项目已经是最新版本。"


class GitUpdater:
    def __init__(self, root: Path):
        self.root = root

    def _git(self, *args: str, error: str) -> str:
        env = os.environ.copy()
        # GUI 中不弹出不可见的凭据输入提示；首次登录在终端完成。
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise UpdateError("未找到 Git。请安装 Git for Windows，重新打开账号管理器后重试。") from exc
        except subprocess.TimeoutExpired as exc:
            raise UpdateError("连接更新源超时，请检查网络或 Git 代理设置后重试。") from exc
        except OSError as exc:
            raise UpdateError("无法运行 Git，请检查安装和项目目录权限。") from exc
        if result.returncode:
            raise UpdateError(error)
        return result.stdout.strip()

    def check(self) -> UpdateStatus:
        upstream = self._git(
            "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}",
            error="当前分支未连接更新源。请按 README 克隆仓库或配置 origin/main 跟踪分支。",
        )
        self._git(
            "fetch", "--prune", error="连接 GitHub 失败。请检查网络和仓库权限；私有仓库请先在终端运行 git fetch origin 完成登录。",
        )
        current = self._git("rev-parse", "HEAD", error="无法读取当前版本。")
        target = self._git("rev-parse", upstream, error="找不到远程分支，请检查仓库分支设置。")
        counts = self._git("rev-list", "--left-right", "--count", f"{current}...{target}", error="无法比较版本。")
        ahead, behind = (int(value) for value in counts.split())
        return UpdateStatus(current, target, ahead, behind)

    def _require_clean(self) -> None:
        if self._git("status", "--porcelain", "--untracked-files=all", error="无法读取工作区状态。"):
            raise UpdateError("本地有未提交的代码或新文件。请先提交或备份这些修改，再同步更新。")

    def sync(self) -> UpdateStatus:
        self._require_clean()
        status = self.check()
        if status.ahead and status.behind:
            raise UpdateError(status.message())
        if not status.behind:
            return status
        changed = self._git("diff", "--name-only", "-z", status.current, status.target, error="无法读取更新文件列表。")
        # 防止远程提交把本机敏感路径纳入版本管理。
        files = self._git("ls-tree", "-r", "--name-only", "-z", status.target, error="无法检查更新内容。")
        for name in filter(None, files.split("\0")):
            path = Path(name)
            if (
                path.parts[0].lower() in {"data", "profiles", ".deps", ".venv"}
                or (path.name.lower().startswith(".env") and path.name != ".env.example")
                or ".session" in path.name.lower()
                or ".sqlite3" in path.name.lower()
            ):
                raise UpdateError("远程版本包含本机配置或会话路径，已停止更新。请先从仓库中移除这些文件。")
        self._require_clean()
        self._git(
            "merge", "--ff-only", "--no-overwrite-ignore", status.target,
            error="无法安全快进更新。请检查本地修改、被忽略文件冲突或分支分歧后重试。",
        )
        return UpdateStatus(status.current, status.target, status.ahead, status.behind, True, "requirements.txt" in changed.split("\0"))
