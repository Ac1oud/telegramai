"""Telegram 多账号桌面启动器；登录凭据保留在本机 profile/session 文件中。"""

from __future__ import annotations

import os
import json
import queue
import re
import signal
import subprocess
import sys
import threading
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib.parse import urlparse

from project_updater import GitUpdater, UpdateError, UpdateStatus
from ui_effects import AnimatedButton, Animator, animate_window_open, animate_window_close, mix_color
from app_runtime import ROOT, RESOURCE_ROOT, FROZEN, SOURCE_MODE, CONSOLE_MODE
from version import VERSION


PROFILE_DIR = ROOT / "profiles"
if not FROZEN:
    sys.path.insert(0, str(ROOT / ".deps"))
from main import create_profile  # noqa: E402


def python_console_executable() -> str:
    """GUI 由 pythonw 启动时，子进程改用 python，以显示登录提示。"""
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        console = executable.with_name("python.exe")
        if console.exists():
            return str(console)
    return str(executable)


class AccountManager(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        animate_window_open(self)
        self.title(f"Telegram AI · {VERSION}")
        self.geometry("820x730")
        self.minsize(760, 720)
        self.python = python_console_executable()
        # Tkinter uses `self.children` internally as a widget dictionary.
        self.child_processes: list[tuple[str, str, subprocess.Popen[bytes]]] = []
        self.profile_names: list[str] = []
        self.update_busy = False
        self.update_results: queue.Queue[UpdateStatus | Exception] = queue.Queue()
        self.update_buttons: list[ttk.Button] = []
        self.protocol("WM_DELETE_WINDOW", self._close_manager)
        self._configure_styles()
        self.motion = Animator(self)
        self._last_selected_profile: str | None = None
        self._load_app_icon()
        self._build_ui()
        self.refresh_profiles()
        self.after(1200, self._refresh_process_status)

    def _configure_styles(self) -> None:
        """统一窗口配色与控件状态，让原生 Tk 界面更清爽。"""
        self.colors = {
            "background": "#F7F5FA",
            "surface": "#FFFFFF",
            "text": "#342B43",
            "muted": "#81768E",
            "accent": "#956DC1",
            "accent_hover": "#A981D0",
            "danger": "#A94E71",
            "border": "#E9E2F0",
        }
        self.configure(background=self.colors["background"])
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.colors["background"])
        style.configure("TLabel", background=self.colors["background"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 9))
        style.configure("TCheckbutton", background=self.colors["background"], foreground=self.colors["text"], font=("Microsoft YaHei UI", 9))
        style.configure("TButton", background="#F3EFF8", foreground="#51445F", padding=(10, 7), borderwidth=0, font=("Microsoft YaHei UI", 9))
        style.map("TButton", background=[("pressed", "#DCCCEB"), ("active", "#E8DDF2")])
        style.configure("App.TFrame", background=self.colors["background"])
        style.configure(
            "Card.TFrame", background=self.colors["surface"], borderwidth=1, relief="solid",
            bordercolor=self.colors["border"], lightcolor=self.colors["border"], darkcolor=self.colors["border"],
        )
        style.configure("CardInner.TFrame", background=self.colors["surface"], borderwidth=0, relief="flat")
        style.configure(
            "Title.TLabel", background=self.colors["background"], foreground=self.colors["text"],
            font=("Microsoft YaHei UI", 21, "bold"),
        )
        style.configure(
            "Subtitle.TLabel", background=self.colors["background"], foreground=self.colors["muted"],
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "CardTitle.TLabel", background=self.colors["surface"], foreground=self.colors["text"],
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "CardHint.TLabel", background=self.colors["surface"], foreground=self.colors["muted"],
            font=("Microsoft YaHei UI", 9),
        )
        style.configure(
            "Primary.TButton", background=self.colors["accent"], foreground="#FFFFFF",
            padding=(12, 10), borderwidth=0, relief="flat", focuscolor="#E4D7F2",
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("pressed", "#9A70B6"), ("active", self.colors["accent_hover"])],
            foreground=[("!disabled", "#FFFFFF")],
        )
        style.configure(
            "Quiet.TButton", background="#F3EFF8", foreground="#51445F",
            padding=(10, 10), borderwidth=0, relief="flat", focuscolor="#CBB5E1",
            font=("Microsoft YaHei UI", 9),
        )
        style.map("Quiet.TButton", background=[("pressed", "#DCCCEB"), ("active", "#E8DDF2")])
        style.configure(
            "Danger.TButton", background="#F9EAF0", foreground=self.colors["danger"],
            padding=(10, 10), borderwidth=0, relief="flat", focuscolor="#E6B7C9",
            font=("Microsoft YaHei UI", 9),
        )
        style.map("Danger.TButton", background=[("pressed", "#F0D3E0"), ("active", "#F5DFE8")])
        style.configure("Vertical.TScrollbar", background="#E9DFEC", troughcolor=self.colors["surface"], borderwidth=0)

    def _load_app_icon(self) -> None:
        """窗口、任务栏和页面共用图标；资源缺失时仍能启动。"""
        self.header_icon: tk.PhotoImage | None = None
        try:
            self.app_icon = tk.PhotoImage(file=str(RESOURCE_ROOT / "assets" / "app-icon-64.png"))
            self.header_icon = self.app_icon
            self.iconphoto(True, self.app_icon)
            if os.name == "nt":
                self.iconbitmap(default=str(RESOURCE_ROOT / "assets" / "app-icon.ico"))
                self.iconbitmap(str(RESOURCE_ROOT / "assets" / "app-icon.ico"))
        except (tk.TclError, OSError):
            pass

    def _new_dialog(self, parent: tk.Misc | None = None) -> tk.Toplevel:
        dialog = tk.Toplevel(parent or self)
        animate_window_open(dialog)
        dialog.protocol("WM_DELETE_WINDOW", lambda: animate_window_close(dialog))
        if hasattr(self, "app_icon"):
            try:
                dialog.iconphoto(False, self.app_icon)
                if os.name == "nt":
                    dialog.iconbitmap(str(RESOURCE_ROOT / "assets" / "app-icon.ico"))
            except tk.TclError:
                pass
        return dialog

    def _draw_header(self, canvas: tk.Canvas) -> None:
        """绘制莫奈风的浅粉、薰衣草紫与淡蓝渐变。"""
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 106)
        if getattr(canvas, "_painted_size", None) == (width, height):
            return
        canvas._painted_size = (width, height)
        canvas.delete("all")
        stops = [(0.0, (248, 222, 231)), (0.52, (235, 222, 244)), (1.0, (220, 231, 246))]
        for x in range(0, width, 3):
            position = x / max(1, width - 1)
            left, right = (stops[0], stops[1]) if position <= stops[1][0] else (stops[1], stops[2])
            amount = (position - left[0]) / (right[0] - left[0])
            color = "#" + "".join(
                f"{round(a + (b - a) * amount):02x}" for a, b in zip(left[1], right[1])
            )
            canvas.create_rectangle(x, 0, x + 3, height, fill=color, outline=color)
        if self.header_icon is not None:
            canvas.create_image(24, height / 2, image=self.header_icon, anchor="w")
        title_x = 106 if self.header_icon is not None else 24
        canvas.create_text(
            title_x, 36, anchor="w", text="Telegram 账号工作台",
            fill=self.colors["text"], font=("Microsoft YaHei UI", 20, "bold"),
        )
        canvas.create_text(
            title_x + 1, 72, anchor="w", text="管理登录会话、监听范围和触发权限",
            fill=self.colors["muted"], font=("Microsoft YaHei UI", 9),
        )
        badge_w = 112
        badge_x = width - badge_w - 18
        canvas.create_rectangle(badge_x, 27, badge_x + badge_w, 48, fill="#F7F2FA", outline="")
        canvas.create_text(
            badge_x + badge_w / 2, 37, text=VERSION,
            fill="#87639F", font=("Microsoft YaHei UI", 8, "bold"),
        )

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, style="App.TFrame", padding=(24, 20, 24, 18))
        frame.pack(fill="both", expand=True)

        header = tk.Canvas(frame, height=106, highlightthickness=0, bd=0)
        header.pack(fill="x", pady=(0, 16))
        header.bind("<Configure>", lambda _event: self._draw_header(header))
        self._draw_header(header)

        account_card = ttk.Frame(frame, style="Card.TFrame", padding=16)
        account_card.pack(fill="both", expand=True)
        account_heading = ttk.Frame(account_card, style="CardInner.TFrame")
        account_heading.pack(fill="x", pady=(0, 10))
        ttk.Label(account_heading, text="账号档案", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(account_heading, text="选中账号后按 Del 可删除配置", style="CardHint.TLabel").pack(side="right")

        list_frame = ttk.Frame(account_card, style="CardInner.TFrame")
        list_frame.pack(fill="both", expand=True)
        self.profile_list = tk.Listbox(
            list_frame,
            height=6,
            exportselection=False,
            activestyle="none",
            bg=self.colors["surface"],
            fg=self.colors["text"],
            selectbackground="#EEE5F5",
            selectforeground="#67468B",
            font=("Microsoft YaHei UI", 11),
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            highlightcolor=self.colors["accent"],
            selectborderwidth=0,
        )
        self.profile_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", style="Vertical.TScrollbar", command=self.profile_list.yview)
        scroll.pack(side="right", fill="y")
        self.profile_list.configure(yscrollcommand=scroll.set)
        self.profile_list.bind("<<ListboxSelect>>", self._selection_changed)
        self.profile_list.bind("<KeyPress-Delete>", lambda _event: "break")
        self.profile_list.bind("<KeyRelease-Delete>", self._delete_profile_shortcut)

        quick_card = ttk.Frame(frame, style="Card.TFrame", padding=16)
        quick_card.pack(fill="x", pady=(14, 0))
        ttk.Label(quick_card, text="快速操作", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        quick_actions = [
            ("手机号登录 / 列群", self.login_and_list),
            ("二维码登录", self.qr_login),
            ("启动监听", self.start_listener),
            ("停止本窗口启动的监听", self.stop_listener),
        ]
        quick_buttons = ttk.Frame(quick_card, style="CardInner.TFrame")
        quick_buttons.pack(fill="x")
        for index, (label, command) in enumerate(quick_actions):
            button_style = "Primary.TButton" if index == 2 else "Quiet.TButton"
            AnimatedButton(quick_buttons, text=label, command=command, style=button_style).grid(
                row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0), pady=2
            )
            quick_buttons.columnconfigure(index, weight=1)

        manage_card = ttk.Frame(frame, style="Card.TFrame", padding=16)
        manage_card.pack(fill="x", pady=(14, 0))
        ttk.Label(manage_card, text="账号与权限", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
        manage_actions = [
            ("新建账号配置", self.new_profile),
            ("导入已有 session", self.import_session),
            ("查看账号文件路径", self.show_profile_paths),
            ("设置显示名称", self.rename_profile),
            ("管理群白名单", self.manage_chat_whitelist),
            ("管理用户白名单", self.manage_sender_whitelist),
            ("刷新", self.refresh_profiles),
            ("删除账号配置", self.delete_profile),
            ("生图设置", self.manage_image_settings),
            ("语言模型管理", self.manage_model_settings),
            ("检查更新", self.check_project_updates),
            ("同步更新", self.sync_project_updates),
        ]
        manage_buttons = ttk.Frame(manage_card, style="CardInner.TFrame")
        manage_buttons.pack(fill="x")
        for index, (label, command) in enumerate(manage_actions):
            button_style = "Danger.TButton" if label == "删除账号配置" else "Quiet.TButton"
            button = AnimatedButton(manage_buttons, text=label, command=command, style=button_style)
            button.grid(
                row=index // 4, column=index % 4, sticky="ew", padx=3, pady=3
            )
            if label in {"检查更新", "同步更新"}:
                self.update_buttons.append(button)
        for column in range(4):
            manage_buttons.columnconfigure(column, weight=1)

        self.status = tk.StringVar(value="就绪")
        footer = ttk.Frame(frame, style="App.TFrame")
        footer.pack(fill="x", pady=(12, 0))
        self.status_dot = tk.Canvas(
            footer, width=12, height=12, bg=self.colors["background"], highlightthickness=0,
        )
        self.status_dot.pack(side="left", padx=(2, 8))
        self.status_dot.create_oval(2, 2, 10, 10, fill=self.colors["accent"], outline="")
        self.status_label = ttk.Label(footer, textvariable=self.status, style="Subtitle.TLabel", wraplength=710)
        self.status_label.pack(side="left", fill="x", expand=True)
        footer.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(300, event.width - 28)))
        self.status.trace_add("write", self._animate_status)

    def _animate_status(self, *_args: str) -> None:
        self.motion.animate(
            "status", 260,
            lambda progress: self.status_label.configure(
                foreground=mix_color(self, self.colors["accent"], self.colors["muted"], progress),
            ),
        )

    def refresh_profiles(self) -> None:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        selected = self.selected_profile()
        self.profile_names = sorted(path.stem for path in PROFILE_DIR.glob("*.env"))
        self.profile_list.delete(0, tk.END)
        for name in self.profile_names:
            display_name = self.get_display_name(name)
            label = name if display_name == name else f"{display_name}（{name}）"
            self.profile_list.insert(tk.END, label)
        if self.profile_names:
            index = self.profile_names.index(selected) if selected in self.profile_names else 0
            self.profile_list.selection_set(index)
            self.profile_list.activate(index)
            self._selection_changed()
        else:
            self.status.set("未找到账号配置。请先新建配置，或从命令行运行 main.py --create-profile 名称。")

    def selected_profile(self) -> str | None:
        selection = self.profile_list.curselection()
        if not selection or selection[0] >= len(self.profile_names):
            return None
        return self.profile_names[selection[0]]

    def manage_image_settings(self) -> None:
        """编辑共享 .env 中的生图开关与服务配置，不在界面显示已保存密钥。"""
        env_file = ROOT / ".env"
        try:
            from dotenv import dotenv_values

            values = dotenv_values(env_file) if env_file.exists() else {}
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("读取生图设置失败", str(exc))
            return

        dialog = self._new_dialog()
        dialog.title("图片生成设置")
        dialog.geometry("620x360")
        dialog.minsize(560, 330)
        dialog.transient(self)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)

        enabled = tk.BooleanVar(value=str(values.get("IMAGE_GENERATION_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "on"})
        ttk.Checkbutton(body, text="启用生图功能", variable=enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        ttk.Label(
            body,
            text="配置保存在项目 .env；保存后重启监听生效。API Key 留空表示保留原值，可勾选清除。",
            wraplength=570,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(body, text="图片 API Key").grid(row=2, column=0, sticky="w", pady=5)
        key_var = tk.StringVar()
        key_entry = ttk.Entry(body, textvariable=key_var, show="•", width=52)
        key_entry.grid(row=2, column=1, sticky="ew", pady=5)
        key_saved = bool(str(values.get("OPENAI_IMAGE_API_KEY") or "").strip())
        ttk.Label(body, text="已保存（隐藏）" if key_saved else "尚未单独设置").grid(
            row=3, column=1, sticky="w", pady=(0, 4)
        )
        clear_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="清除单独保存的图片 API Key", variable=clear_key).grid(
            row=4, column=1, sticky="w", pady=(0, 6)
        )

        base_var = tk.StringVar(value=str(values.get("OPENAI_IMAGE_BASE_URL") or ""))
        model_var = tk.StringVar(value=str(values.get("OPENAI_IMAGE_MODEL") or ""))
        ttk.Label(body, text="服务 API URL（Base URL）").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=base_var, width=52).grid(row=5, column=1, sticky="ew", pady=5)
        ttk.Label(body, text="图片模型名称").grid(row=6, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=model_var, width=52).grid(row=6, column=1, sticky="ew", pady=5)
        body.columnconfigure(1, weight=1)

        def save() -> None:
            base_url = base_var.get().strip()
            parsed_url = urlparse(base_url) if base_url else None
            if base_url and (parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc):
                messagebox.showerror("URL 格式错误", "请输入完整的 http:// 或 https:// API Base URL。", parent=dialog)
                return
            model = model_var.get().strip()
            if enabled.get() and not model:
                messagebox.showerror("缺少模型名称", "启用生图时请填写服务支持的图片模型名称。", parent=dialog)
                return
            try:
                current_text = env_file.read_text(encoding="utf-8-sig") if env_file.exists() else ""
                updates = {
                    "IMAGE_GENERATION_ENABLED": "true" if enabled.get() else "false",
                    "OPENAI_IMAGE_BASE_URL": base_url,
                    "OPENAI_IMAGE_MODEL": model,
                }
                entered_key = key_var.get().strip()
                if clear_key.get():
                    updates["OPENAI_IMAGE_API_KEY"] = ""
                elif entered_key:
                    updates["OPENAI_IMAGE_API_KEY"] = entered_key
                for name, value in updates.items():
                    encoded = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
                    line = f"{name}={encoded}"
                    pattern = re.compile(rf"(?m)^{re.escape(name)}=.*$")
                    if pattern.search(current_text):
                        current_text = pattern.sub(lambda _match, line=line: line, current_text, count=1)
                    else:
                        if current_text and not current_text.endswith("\n"):
                            current_text += "\n"
                        current_text += line + "\n"
                env_file.write_text(current_text, encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("保存生图设置失败", str(exc), parent=dialog)
                return
            self.status.set("生图设置已保存；重启监听后生效。")
            animate_window_close(dialog)

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        AnimatedButton(buttons, text="保存设置", style="Primary.TButton", command=save).pack(side="right")
        AnimatedButton(buttons, text="取消", command=lambda: animate_window_close(dialog)).pack(side="right", padx=(0, 8))

    def manage_model_settings(self) -> None:
        """编辑共享 .env 中的聊天模型名称、API Key 和 API 地址。"""
        env_file = ROOT / ".env"
        try:
            from dotenv import dotenv_values

            values = dotenv_values(env_file) if env_file.exists() else {}
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("读取语言模型设置失败", str(exc))
            return

        dialog = self._new_dialog()
        dialog.title("语言模型管理")
        dialog.geometry("620x350")
        dialog.minsize(560, 320)
        dialog.transient(self)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="设置聊天模型名称、服务 API URL 和 API Key。配置为所有账号共享；保存后重启监听生效。Key 留空保留原值，可勾选清除。",
            wraplength=570,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        model_var = tk.StringVar(value=str(values.get("OPENAI_MODEL") or "gpt-6-luna"))
        base_var = tk.StringVar(value=str(values.get("OPENAI_BASE_URL") or ""))
        key_var = tk.StringVar()
        ttk.Label(body, text="模型名称").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=model_var, width=52).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(body, text="服务 API URL（Base URL）").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=base_var, width=52).grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(body, text="模型 API Key").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(body, textvariable=key_var, show="•", width=52).grid(row=3, column=1, sticky="ew", pady=6)
        key_saved = bool(str(values.get("OPENAI_API_KEY") or "").strip())
        ttk.Label(body, text="已保存（隐藏）" if key_saved else "尚未设置").grid(
            row=4, column=1, sticky="w", pady=(0, 2)
        )
        clear_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="清除已保存的模型 API Key", variable=clear_key).grid(
            row=5, column=1, sticky="w", pady=(0, 6)
        )
        body.columnconfigure(1, weight=1)

        def save() -> None:
            model = model_var.get().strip()
            base_url = base_var.get().strip()
            parsed_url = urlparse(base_url) if base_url else None
            if not model:
                messagebox.showerror("缺少模型名称", "请填写服务商提供的模型名称。", parent=dialog)
                return
            if base_url and (parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc):
                messagebox.showerror("URL 格式错误", "请输入完整的 http:// 或 https:// API Base URL。", parent=dialog)
                return
            try:
                current_text = env_file.read_text(encoding="utf-8-sig") if env_file.exists() else ""
                updates = {"OPENAI_MODEL": model, "OPENAI_BASE_URL": base_url}
                entered_key = key_var.get().strip()
                if clear_key.get():
                    updates["OPENAI_API_KEY"] = ""
                elif entered_key:
                    updates["OPENAI_API_KEY"] = entered_key
                for name, value in updates.items():
                    encoded = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
                    line = f"{name}={encoded}"
                    pattern = re.compile(rf"(?m)^{re.escape(name)}=.*$")
                    if pattern.search(current_text):
                        current_text = pattern.sub(lambda _match, line=line: line, current_text, count=1)
                    else:
                        if current_text and not current_text.endswith("\n"):
                            current_text += "\n"
                        current_text += line + "\n"
                env_file.write_text(current_text, encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("保存语言模型设置失败", str(exc), parent=dialog)
                return
            self.status.set("语言模型设置已保存；重启监听后生效。")
            animate_window_close(dialog)

        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        AnimatedButton(buttons, text="保存设置", style="Primary.TButton", command=save).pack(side="right")
        AnimatedButton(buttons, text="取消", command=lambda: animate_window_close(dialog)).pack(side="right", padx=(0, 8))

    def check_project_updates(self) -> None:
        """在后台检查 GitHub 更新，避免网络等待阻塞界面。"""
        self._start_project_update(sync=False)

    def sync_project_updates(self) -> None:
        self._start_project_update(sync=True)

    def _start_project_update(self, *, sync: bool) -> None:
        if self.update_busy:
            return
        if FROZEN and not SOURCE_MODE:
            messagebox.showinfo(
                "下载 EXE 更新", f"当前版本：{VERSION}\n\n将打开 GitHub Releases。下载新版 TelegramAI.exe，关闭程序后替换原文件；旁边的账号配置和会话继续保留。",
                parent=self,
            )
            webbrowser.open("https://github.com/Ac1oud/telegramai/releases")
            return
        if sync and any(process.poll() is None for _profile, _action, process in self.child_processes):
            messagebox.showwarning("请先停止监听", "同步前请先停止所有监听或登录终端（包括从其他窗口启动的进程）。")
            return
        self.update_busy = True
        for button in self.update_buttons:
            button.state(["disabled"])
        self.status.set("正在同步更新…" if sync else "正在连接 GitHub 检查更新…")

        def worker() -> None:
            try:
                updater = GitUpdater(ROOT)
                self.update_results.put(updater.sync() if sync else updater.check())
            except Exception as exc:
                self.update_results.put(exc)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_project_update)

    def _poll_project_update(self) -> None:
        # 所有 Tk 操作均在主线程；后台线程只通过队列传递结果。
        try:
            result = self.update_results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_project_update)
            return
        self.update_busy = False
        for button in self.update_buttons:
            button.state(["!disabled"])
        if isinstance(result, Exception):
            text = str(result) if isinstance(result, UpdateError) else "更新失败，请检查 Git 仓库状态后重试。"
            self.status.set(text)
            messagebox.showerror("更新失败", text)
            return
        text = result.message()
        self.status.set(text.split("\n")[0])
        messagebox.showinfo("同步完成" if result.updated else "检查完成", text)

    @staticmethod
    def get_display_name(profile: str) -> str:
        """读取账号的自定义显示名；旧配置默认使用配置名。"""
        profile_file = PROFILE_DIR / f"{profile}.env"
        text = profile_file.read_text(encoding="utf-8-sig")
        match = re.search(r"(?m)^DISPLAY_NAME=(.*)$", text)
        value = match.group(1).strip().strip("\"'") if match else ""
        return value or profile

    def rename_profile(self) -> None:
        profile = self.selected_profile()
        if not profile:
            messagebox.showinfo("设置显示名称", "请先选择一个账号配置。")
            return
        current_name = self.get_display_name(profile)
        display_name = simpledialog.askstring(
            "设置显示名称",
            f"为 {profile} 设置列表显示名称（留空恢复默认名称）：",
            initialvalue=current_name,
            parent=self,
        )
        if display_name is None:
            return
        display_name = display_name.strip()
        if len(display_name) > 40 or "\n" in display_name or "\r" in display_name:
            messagebox.showerror("名称无效", "显示名称最多 40 个字符，且不能包含换行。")
            return
        profile_file = PROFILE_DIR / f"{profile}.env"
        text = profile_file.read_text(encoding="utf-8-sig")
        line = f'DISPLAY_NAME="{display_name}"' if display_name else "DISPLAY_NAME="
        if re.search(r"(?m)^DISPLAY_NAME=.*$", text):
            text = re.sub(r"(?m)^DISPLAY_NAME=.*$", lambda _match: line, text, count=1)
        else:
            text = text.rstrip() + "\n" + line + "\n"
        profile_file.write_text(text, encoding="utf-8")
        self.refresh_profiles()
        self.status.set(f"已更新 {profile} 的列表显示名称。")

    def _selection_changed(self, _event: object | None = None) -> None:
        profile = self.selected_profile()
        if not profile:
            return
        if profile != self._last_selected_profile:
            self._last_selected_profile = profile
            self.motion.animate(
                "account-selection", 200,
                lambda progress: self.profile_list.configure(
                    selectbackground=mix_color(self, "#D9C7EE", "#EEE5F5", progress),
                ),
            )
        text = (PROFILE_DIR / f"{profile}.env").read_text(encoding="utf-8-sig")
        session_match = re.search(r"(?m)^SESSION_PATH=(.+)$", text)
        session_value = session_match.group(1).strip() if session_match else f"data/profiles/{profile}/telegram"
        session = Path(session_value)
        if not session.is_absolute():
            session = ROOT / session
        authorized_session_exists = Path(f"{session}.session").exists()
        state = "已有本地 session" if authorized_session_exists else "尚未授权，首次使用需登录"
        chat_match = re.search(r"(?m)^ALLOWED_CHAT_IDS=(.*)$", text)
        chat_count = len([value for value in chat_match.group(1).split(",") if value.strip()]) if chat_match else 0
        sender_match = re.search(r"(?m)^ALLOWED_SENDER_IDS=(.*)$", text)
        sender_count = len([value for value in sender_match.group(1).split(",") if value.strip()]) if sender_match else 0
        sender_status = f"触发用户限 {sender_count} 人" if sender_count else "触发用户不限"
        owner_match = re.search(r"(?m)^OWNER_USER_IDS=(.*)$", text)
        owner_count = len([value for value in owner_match.group(1).split(",") if value.strip()]) if owner_match else 0
        owner_names_match = re.search(r"(?m)^OWNER_USERNAMES=(.*)$", text)
        owner_names_count = len([value for value in owner_names_match.group(1).split(",") if value.strip()]) if owner_names_match else 0
        self.status.set(
            f"当前选择：{profile}    {state}    白名单群 {chat_count} 个    {sender_status}    主人 {owner_count} ID / {owner_names_count} 用户名"
        )

    def _worker_command(self, profile: str, args: list[str], *, interactive: bool = False) -> list[str]:
        if FROZEN:
            mode = ("--worker-console" if CONSOLE_MODE else "--worker-gui") if interactive else "--worker"
            return [sys.executable, mode, "--profile", profile, *args]
        return [self.python, str(ROOT / "main.py"), "--profile", profile, *args]

    def _launch(self, profile: str, action: str, args: list[str]) -> None:
        if self.update_busy:
            messagebox.showinfo("更新进行中", "请等待更新操作结束后，再启动登录或监听进程。")
            return
        python_path = os.environ.copy()
        python_path["PYTHONPATH"] = str(ROOT / ".deps")
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
        if FROZEN and not CONSOLE_MODE:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        process = subprocess.Popen(
            self._worker_command(profile, args, interactive=True),
            cwd=ROOT,
            env=python_path,
            creationflags=flags,
        )
        self.child_processes.append((profile, action, process))
        surface = "操作窗口" if FROZEN and not CONSOLE_MODE else "终端"
        self.status.set(f"已为 {profile} 打开“{action}”{surface}；请按提示完成操作。")

    def login_and_list(self) -> None:
        profile = self.selected_profile()
        if profile:
            self._launch(profile, "手机号登录 / 列群", ["--list-chats"])

    def qr_login(self) -> None:
        profile = self.selected_profile()
        if profile:
            self._launch(profile, "二维码登录", ["--qr-login"])

    def start_listener(self) -> None:
        profile = self.selected_profile()
        if profile:
            running = any(p == profile and action == "监听" and proc.poll() is None for p, action, proc in self.child_processes)
            if running:
                messagebox.showinfo("已在运行", f"{profile} 的监听进程已由此窗口启动。")
                return
            self._launch(profile, "监听", [])

    def stop_listener(self) -> None:
        profile = self.selected_profile()
        running = [proc for p, action, proc in self.child_processes if p == profile and action == "监听" and proc.poll() is None]
        if not running:
            messagebox.showinfo("没有监听进程", "此窗口没有启动该账号的监听进程。")
            return
        for proc in running:
            proc.terminate()
        self.status.set(f"已请求停止 {profile} 的监听进程。")

    def _close_manager(self) -> None:
        """关闭窗口时一并关闭由本窗口启动的终端子进程。"""
        if self.update_busy:
            messagebox.showinfo("更新进行中", "请等待更新操作结束后再关闭窗口。")
            return
        running = [proc for _profile, _action, proc in self.child_processes if proc.poll() is None]
        for proc in running:
            try:
                proc.terminate()
            except OSError:
                pass
        for proc in running:
            try:
                proc.wait(timeout=0.8)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
        animate_window_close(self)

    def new_profile(self) -> None:
        name = simpledialog.askstring("新建账号配置", "配置名（英文字母、数字、下划线或连字符）：", parent=self)
        if not name:
            return
        phone = simpledialog.askstring("手机号（可选）", "手机号国际格式，例如 +1...；留空可之后用二维码登录：", parent=self)
        try:
            path = create_profile(name)
            if phone:
                phone = re.sub(r"[\s()-]", "", phone)
                if not re.fullmatch(r"\+[1-9]\d{6,14}", phone):
                    path.unlink(missing_ok=True)
                    raise ValueError("手机号请用国际格式，例如 +13099324665")
                text = path.read_text(encoding="utf-8")
                text = re.sub(r"(?m)^TELEGRAM_PHONE=.*$", f"TELEGRAM_PHONE={phone}", text)
                path.write_text(text, encoding="utf-8")
            self.refresh_profiles()
            index = self.profile_names.index(name)
            self.profile_list.selection_clear(0, tk.END)
            self.profile_list.selection_set(index)
            self.profile_list.activate(index)
            self._selection_changed()
            messagebox.showinfo("配置已创建", f"{name} 已创建独立 session。模型 API 密钥不会复制到账号配置。")
        except Exception as exc:
            messagebox.showerror("创建失败", str(exc))

    def import_session(self) -> None:
        selected_file = filedialog.askopenfilename(
            parent=self,
            title="选择以前登录的 Telegram session 文件",
            initialdir=ROOT / "data",
            filetypes=[("Telegram session", "*.session")],
        )
        if not selected_file:
            return
        session_file = Path(selected_file).resolve()
        data_dir = (ROOT / "data").resolve()
        try:
            session_file.relative_to(data_dir)
        except ValueError:
            messagebox.showerror("无法导入", "请从本项目的 data 目录选择 session 文件。")
            return
        if session_file.suffix.lower() != ".session":
            messagebox.showerror("无法导入", "请选择扩展名为 .session 的文件。")
            return

        session_base = session_file.with_suffix("")
        for profile_file in PROFILE_DIR.glob("*.env"):
            match = re.search(r"(?m)^SESSION_PATH=(.*)$", profile_file.read_text(encoding="utf-8-sig"))
            if not match:
                continue
            configured = match.group(1).strip().strip("\"'")
            configured_path = Path(configured)
            if not configured_path.is_absolute():
                configured_path = ROOT / configured_path
            if configured_path.resolve() == session_base:
                messagebox.showinfo("已经导入", f"此 session 已登记为 {profile_file.stem}。")
                return

        default_name = f"imported_{session_base.name}"
        name = simpledialog.askstring(
            "登记旧账号",
            "给这个账号配置起个名字：",
            initialvalue=default_name,
            parent=self,
        )
        if not name:
            return
        try:
            profile_file = create_profile(name)
            relative_session = session_base.relative_to(ROOT).as_posix()
            text = profile_file.read_text(encoding="utf-8")
            text = re.sub(
                r"(?m)^SESSION_PATH=.*$",
                f'SESSION_PATH="{relative_session}"',
                text,
            )
            profile_file.write_text(text, encoding="utf-8")
            self.refresh_profiles()
            index = self.profile_names.index(name)
            self.profile_list.selection_clear(0, tk.END)
            self.profile_list.selection_set(index)
            self.profile_list.activate(index)
            self._selection_changed()
            messagebox.showinfo(
                "导入完成",
                f"{name} 已加入切换界面。原 session 文件保留在原处；不要同时运行同一账号的两个进程。",
            )
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))

    def _profile_paths(self, profile: str) -> tuple[Path, Path, Path]:
        """返回配置、session 与状态数据库的绝对路径。"""
        profile_file = PROFILE_DIR / f"{profile}.env"
        text = profile_file.read_text(encoding="utf-8-sig")
        values: dict[str, str] = {}
        for key in ("SESSION_PATH", "STATE_PATH"):
            match = re.search(rf"(?m)^{key}=(.*)$", text)
            value = match.group(1).strip().strip("\"'") if match else ""
            path = Path(value) if value else Path("data/profiles") / profile / key.lower()
            if not path.is_absolute():
                path = ROOT / path
            values[key] = str(path.resolve())
        return profile_file.resolve(), Path(values["SESSION_PATH"] + ".session"), Path(values["STATE_PATH"])

    def show_profile_paths(self) -> None:
        profile = self.selected_profile()
        if not profile:
            messagebox.showinfo("查看路径", "请先选择一个账号配置。")
            return
        try:
            profile_path, session_path, state_path = self._profile_paths(profile)
            messagebox.showinfo(
                f"{profile} 的本地文件路径",
                f"配置文件：\n{profile_path}\n\nTelegram session：\n{session_path}"
                f"\n\n状态数据库：\n{state_path}",
            )
        except Exception as exc:
            messagebox.showerror("读取路径失败", str(exc))

    def _delete_profile_shortcut(self, event: tk.Event) -> str:
        """仅账号列表响应 Del；松开时处理，避免 Windows 长按重复弹窗。"""
        if event.widget is self.profile_list and self.focus_get() is self.profile_list:
            self.delete_profile()
        return "break"

    def delete_profile(self) -> None:
        """快捷键与按钮共用确认流程，只移除配置，保留账号数据。"""
        if self.__dict__.get("_delete_in_progress", False):
            return
        profile = self.selected_profile()
        if not profile:
            return
        self._delete_in_progress = True
        try:
            running = [
                proc for name, _action, proc in self.child_processes
                if name == profile and proc.poll() is None
            ]
            if running:
                messagebox.showwarning(
                    "账号正在运行", "请先停止此账号由本窗口启动的进程，再删除配置。", parent=self,
                )
                return
            if not messagebox.askyesno(
                "确认删除账号配置",
                f"确定从切换器中移除 {profile} 吗？\n\n"
                "只删除 profiles 下的配置文件；Telegram session 和状态数据库会保留在原处。",
                icon="warning",
                default=messagebox.NO,
                parent=self,
            ):
                return
            try:
                (PROFILE_DIR / f"{profile}.env").unlink()
                self.refresh_profiles()
                self.status.set(f"已从切换器移除 {profile}；session 和状态数据库保留。")
            except Exception as exc:
                messagebox.showerror("删除失败", str(exc), parent=self)
        finally:
            self._delete_in_progress = False

    def manage_chat_whitelist(self) -> None:
        """可视化查看、添加和移除当前账号配置允许监听的群组 ID。"""
        profile = self.selected_profile()
        if not profile:
            messagebox.showinfo("群白名单", "请先选择一个账号配置。")
            return
        profile_file = PROFILE_DIR / f"{profile}.env"
        text = profile_file.read_text(encoding="utf-8-sig")
        match = re.search(r"(?m)^ALLOWED_CHAT_IDS=(.*)$", text)
        raw_ids = match.group(1).strip().strip("\"'") if match else ""
        try:
            chat_ids = list(dict.fromkeys(int(value.strip()) for value in raw_ids.split(",") if value.strip()))
        except ValueError:
            messagebox.showerror("白名单格式错误", f"{profile} 配置中的群组 ID 不是逗号分隔的数字。")
            return

        dialog = self._new_dialog()
        dialog.title(f"{self.get_display_name(profile)} - 群白名单")
        dialog.geometry("480x360")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(
            dialog,
            text=f"账号：{self.get_display_name(profile)}（{profile}）\n仅保存至本账号配置；列表中的群才会被监听。修改后需重启该账号监听。",
            wraplength=440,
        ).pack(anchor="w", padx=12, pady=(12, 8))
        body = ttk.Frame(dialog, padding=(12, 0, 12, 8))
        body.pack(fill="both", expand=True)
        listing = tk.Listbox(body, height=10, selectmode=tk.EXTENDED, exportselection=False)
        listing.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=listing.yview)
        scrollbar.pack(side="right", fill="y")
        listing.configure(yscrollcommand=scrollbar.set)

        def refresh_ids() -> None:
            listing.delete(0, tk.END)
            for chat_id in chat_ids:
                listing.insert(tk.END, str(chat_id))

        def add_ids() -> None:
            value = simpledialog.askstring(
                "添加群组 ID",
                "输入群组 ID；可一次输入多个，用逗号分隔。\n可先点“手机号登录 / 列群”获取 ID。",
                parent=dialog,
            )
            if not value:
                return
            pieces = [part.strip() for part in value.split(",") if part.strip()]
            if not pieces or any(not re.fullmatch(r"-?\d+", part) for part in pieces):
                messagebox.showerror("ID 格式错误", "群组 ID 必须是数字；多个 ID 请用英文逗号分隔。", parent=dialog)
                return
            for piece in pieces:
                chat_id = int(piece)
                if chat_id not in chat_ids:
                    chat_ids.append(chat_id)
            refresh_ids()

        def remove_ids() -> None:
            selected = list(listing.curselection())
            if not selected:
                messagebox.showinfo("移除群组", "请先在列表中选中要移除的群组。", parent=dialog)
                return
            for index in reversed(selected):
                del chat_ids[index]
            refresh_ids()

        def save_ids() -> None:
            nonlocal text
            text = profile_file.read_text(encoding="utf-8-sig")
            line = "ALLOWED_CHAT_IDS=" + ",".join(str(chat_id) for chat_id in chat_ids)
            if re.search(r"(?m)^ALLOWED_CHAT_IDS=.*$", text):
                text = re.sub(r"(?m)^ALLOWED_CHAT_IDS=.*$", lambda _match: line, text, count=1)
            else:
                text = text.rstrip() + "\n" + line + "\n"
            profile_file.write_text(text, encoding="utf-8")
            self.status.set(f"已保存 {profile} 的群白名单，共 {len(chat_ids)} 个群；重启监听后生效。")
            animate_window_close(dialog)

        fetch_status = tk.StringVar(value="可从当前账号 session 获取群名称和 ID。")
        ttk.Label(dialog, textvariable=fetch_status, wraplength=440).pack(anchor="w", padx=12, pady=(0, 8))

        def show_group_picker(groups: list[dict[str, object]]) -> None:
            picker = self._new_dialog(dialog)
            picker.title("选择要加入白名单的群")
            picker.geometry("520x400")
            picker.transient(dialog)
            picker.grab_set()
            ttk.Label(
                picker,
                text="群名和 ID 来自当前账号已加入的群；可多选后加入白名单。",
                wraplength=480,
            ).pack(anchor="w", padx=12, pady=(12, 8))
            picker_body = ttk.Frame(picker, padding=(12, 0, 12, 8))
            picker_body.pack(fill="both", expand=True)
            group_list = tk.Listbox(picker_body, selectmode=tk.EXTENDED, exportselection=False)
            group_list.pack(side="left", fill="both", expand=True)
            group_scroll = ttk.Scrollbar(picker_body, orient="vertical", command=group_list.yview)
            group_scroll.pack(side="right", fill="y")
            group_list.configure(yscrollcommand=group_scroll.set)
            for group in groups:
                group_list.insert(tk.END, f"{group.get('name', '(无群名)')}    [{group.get('id')}]")

            def add_selected_groups() -> None:
                selected = list(group_list.curselection())
                if not selected:
                    messagebox.showinfo("选择群组", "请先选择要加入白名单的群。", parent=picker)
                    return
                for index in selected:
                    group_id = int(groups[index]["id"])
                    if group_id not in chat_ids:
                        chat_ids.append(group_id)
                refresh_ids()
                animate_window_close(picker)
                fetch_status.set(f"已选择 {len(selected)} 个群；点“保存”后写入当前账号配置。")

            picker_controls = ttk.Frame(picker, padding=(12, 0, 12, 12))
            picker_controls.pack(fill="x")
            AnimatedButton(picker_controls, text="加入白名单", command=add_selected_groups).pack(side="right")

        def fetch_groups() -> None:
            active = [
                action for running_profile, action, proc in self.child_processes
                if running_profile == profile and proc.poll() is None
            ]
            if active:
                messagebox.showwarning(
                    "账号正在使用",
                    "请先停止该账号由此窗口启动的进程，再获取群列表，避免多个进程同时打开同一 session。",
                    parent=dialog,
                )
                return
            fetch_button.configure(state="disabled")
            fetch_status.set("正在连接 Telegram 并读取群列表…")

            def worker() -> None:
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT / ".deps")
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                try:
                    result = subprocess.run(
                        self._worker_command(profile, ["--list-chats-json"]),
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=90,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                    )
                    if result.returncode == 0:
                        groups = json.loads(result.stdout)
                        error = None if isinstance(groups, list) else "Telegram 没有返回有效的群列表。"
                    else:
                        groups = None
                        details = [line.strip() for line in result.stderr.splitlines() if line.strip()]
                        detail = details[-1] if details else f"进程退出码 {result.returncode}，没有返回错误详情。"
                        detail = re.sub(
                            r"(?i)(api[_-]?(?:key|hash)|password|token)\s*[:=]\s*\S+",
                            r"\1=***",
                            detail,
                        )[:400]
                        lowered = detail.lower()
                        if "database is locked" in lowered or "database locked" in lowered:
                            error = "读取失败：这个账号的 session 正被另一个进程使用。请先彻底停止该账号的监听，再重试。"
                        elif "not authorized" in lowered or "尚未授权" in detail or "尚未登录" in detail:
                            error = f"读取失败：该配置的 Telegram session 尚未登录。详情：{detail}"
                        else:
                            error = f"读取失败（退出码 {result.returncode}）：{detail}"
                except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                    groups = None
                    error = str(exc)

                def finish() -> None:
                    fetch_button.configure(state="normal")
                    if error:
                        fetch_status.set(error)
                        messagebox.showerror("获取群列表失败", error, parent=dialog)
                        return
                    if not groups:
                        fetch_status.set("当前账号没有可显示的群组。")
                        messagebox.showinfo("群列表为空", "当前账号没有获取到群组。", parent=dialog)
                        return
                    fetch_status.set(f"已获取 {len(groups)} 个群；选择后可加入白名单。")
                    show_group_picker(groups)

                self.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        refresh_ids()
        controls = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        controls.pack(fill="x")
        fetch_button = AnimatedButton(controls, text="获取群 ID", command=fetch_groups)
        fetch_button.pack(side="left", padx=(0, 6))
        AnimatedButton(controls, text="添加群组 ID", command=add_ids).pack(side="left", padx=(0, 6))
        AnimatedButton(controls, text="移除选中项", command=remove_ids).pack(side="left")
        AnimatedButton(controls, text="保存", command=save_ids).pack(side="right")

    def manage_sender_whitelist(self) -> None:
        """分别管理可触发用户与主人身份，并支持联系人多选导入。"""
        profile = self.selected_profile()
        if not profile:
            messagebox.showinfo("用户白名单", "请先选择一个账号配置。")
            return
        profile_file = PROFILE_DIR / f"{profile}.env"
        text = profile_file.read_text(encoding="utf-8-sig")
        try:
            def read_ids(key: str) -> list[int]:
                match = re.search(rf"(?m)^{key}=(.*)$", text)
                raw = match.group(1).strip().strip("\"'") if match else ""
                return list(dict.fromkeys(int(value.strip()) for value in raw.split(",") if value.strip()))

            sender_ids = read_ids("ALLOWED_SENDER_IDS")
            owner_ids = read_ids("OWNER_USER_IDS")
            names_match = re.search(r"(?m)^OWNER_USERNAMES=(.*)$", text)
            raw_names = names_match.group(1).strip().strip("\"'") if names_match else ""
            owner_usernames = list(dict.fromkeys(
                name.strip().lstrip("@").casefold()
                for name in raw_names.split(",")
                if name.strip().lstrip("@")
            ))
            if any(not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", name) for name in owner_usernames):
                raise ValueError("用户名格式无效")
        except ValueError:
            messagebox.showerror("白名单格式错误", f"{profile} 配置中的用户 ID 或主人用户名格式有误。")
            return

        dialog = self._new_dialog()
        dialog.title(f"{self.get_display_name(profile)} - 用户权限白名单")
        dialog.geometry("760x450")
        dialog.minsize(700, 400)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(
            dialog,
            text="分别设置谁能 @/回复触发智能体，以及哪些用户被识别为主人。两份名单互不替代；触发名单留空表示群白名单内所有成员都可触发。主人数字 ID 最稳定，用户名可改、仅作备用匹配。可按 Ctrl/Shift 多选；保存后重启监听生效。",
            wraplength=720,
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        columns = ttk.Frame(dialog, padding=(12, 0, 12, 8))
        columns.grid(row=1, column=0, sticky="nsew")

        def populate(listing: tk.Listbox, values: list[int]) -> None:
            listing.delete(0, tk.END)
            for value in values:
                listing.insert(tk.END, str(value))

        def make_panel(parent: ttk.Frame, title: str, values: list[int]) -> tuple[ttk.Frame, tk.Listbox]:
            panel = ttk.LabelFrame(parent, text=title, padding=8)
            panel.pack(side="left", fill="both", expand=True, padx=(0, 6) if title.startswith("可") else (6, 0))
            list_frame = ttk.Frame(panel)
            list_frame.pack(fill="both", expand=True)
            listing = tk.Listbox(list_frame, height=8, selectmode=tk.EXTENDED, exportselection=False)
            listing.pack(side="left", fill="both", expand=True)
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listing.yview)
            scrollbar.pack(side="right", fill="y")
            listing.configure(yscrollcommand=scrollbar.set)
            populate(listing, values)
            return panel, listing

        trigger_panel, trigger_list = make_panel(columns, "可触发智能体", sender_ids)
        owner_panel = ttk.LabelFrame(columns, text="主人身份", padding=8)
        owner_panel.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ttk.Label(owner_panel, text="数字 ID（优先、稳定）").pack(anchor="w")
        owner_id_frame = ttk.Frame(owner_panel)
        owner_id_frame.pack(fill="both", expand=True)
        owner_list = tk.Listbox(owner_id_frame, height=3, selectmode=tk.EXTENDED, exportselection=False)
        owner_list.pack(side="left", fill="both", expand=True)
        owner_id_scroll = ttk.Scrollbar(owner_id_frame, orient="vertical", command=owner_list.yview)
        owner_id_scroll.pack(side="right", fill="y")
        owner_list.configure(yscrollcommand=owner_id_scroll.set)
        populate(owner_list, owner_ids)
        ttk.Label(owner_panel, text="用户名备用匹配（可变更，建议同时保留数字 ID）").pack(anchor="w", pady=(8, 0))
        owner_name_frame = ttk.Frame(owner_panel)
        owner_name_frame.pack(fill="both", expand=True)
        owner_name_list = tk.Listbox(owner_name_frame, height=2, selectmode=tk.EXTENDED, exportselection=False)
        owner_name_list.pack(side="left", fill="both", expand=True)
        owner_name_scroll = ttk.Scrollbar(owner_name_frame, orient="vertical", command=owner_name_list.yview)
        owner_name_scroll.pack(side="right", fill="y")
        owner_name_list.configure(yscrollcommand=owner_name_scroll.set)
        def populate_usernames() -> None:
            owner_name_list.delete(0, tk.END)
            for username_value in owner_usernames:
                owner_name_list.insert(tk.END, f"@{username_value}")
        populate_usernames()

        def add_ids_to(values: list[int], listing: tk.Listbox, label: str) -> None:
            value = simpledialog.askstring(
                f"添加到{label}", "输入 Telegram 用户数字 ID；支持用英文逗号或换行一次添加多个。",
                parent=dialog,
            )
            if not value:
                return
            pieces = [part.strip() for part in re.split(r"[,，\s]+", value) if part.strip()]
            if not pieces or any(not re.fullmatch(r"\d+", part) or int(part) <= 0 for part in pieces):
                messagebox.showerror("ID 格式错误", "用户 ID 必须是正整数。", parent=dialog)
                return
            values.extend(user_id for user_id in map(int, pieces) if user_id not in values)
            populate(listing, values)

        def remove_selected(values: list[int], listing: tk.Listbox, label: str) -> None:
            selected = set(listing.curselection())
            if not selected:
                messagebox.showinfo("移除用户", f"请先在“{label}”中多选要移除的用户。", parent=dialog)
                return
            values[:] = [value for index, value in enumerate(values) if index not in selected]
            populate(listing, values)

        AnimatedButton(trigger_panel, text="添加多个 ID", command=lambda: add_ids_to(sender_ids, trigger_list, "可触发名单")).pack(fill="x", pady=(8, 3))
        AnimatedButton(trigger_panel, text="移除选中项", command=lambda: remove_selected(sender_ids, trigger_list, "可触发名单")).pack(fill="x")
        AnimatedButton(owner_panel, text="添加多个主人 ID", command=lambda: add_ids_to(owner_ids, owner_list, "主人名单")).pack(fill="x", pady=(6, 3))
        AnimatedButton(owner_panel, text="移除选中的 ID", command=lambda: remove_selected(owner_ids, owner_list, "主人名单")).pack(fill="x")

        def add_owner_usernames() -> None:
            value = simpledialog.askstring(
                "添加主人用户名",
                "输入 Telegram 用户名；可带 @，多个用逗号分隔。用户名可能更改，建议同时保留数字 ID。",
                parent=dialog,
            )
            if not value:
                return
            pieces = [part.strip().lstrip("@").casefold() for part in re.split(r"[,，\s]+", value) if part.strip()]
            if any(not re.fullmatch(r"[a-zA-Z0-9_]{5,32}", name) for name in pieces):
                messagebox.showerror("用户名格式错误", "Telegram 用户名需为 5–32 位英文字母、数字或下划线。", parent=dialog)
                return
            owner_usernames.extend(name for name in pieces if name not in owner_usernames)
            populate_usernames()

        def remove_owner_usernames() -> None:
            selected = set(owner_name_list.curselection())
            if not selected:
                messagebox.showinfo("移除用户名", "请先多选要移除的主人用户名。", parent=dialog)
                return
            owner_usernames[:] = [name for index, name in enumerate(owner_usernames) if index not in selected]
            populate_usernames()

        AnimatedButton(owner_panel, text="添加主人用户名", command=add_owner_usernames).pack(fill="x", pady=(6, 3))
        AnimatedButton(owner_panel, text="移除选中的用户名", command=remove_owner_usernames).pack(fill="x")

        fetch_status = tk.StringVar(value="可读取当前账号 Telegram 联系人，批量加入任一名单。")
        ttk.Label(dialog, textvariable=fetch_status, wraplength=720).grid(
            row=2, column=0, sticky="ew", padx=12, pady=(0, 4)
        )

        def add_contact_picker(contacts: list[dict[str, object]]) -> None:
            picker = self._new_dialog(dialog)
            picker.title("选择 Telegram 联系人")
            picker.geometry("580x430")
            picker.transient(dialog)
            picker.grab_set()
            ttk.Label(picker, text="按 Ctrl/Shift 多选联系人；只显示姓名、用户名和 Telegram 数字 ID。", wraplength=540).pack(anchor="w", padx=12, pady=(12, 8))
            contact_body = ttk.Frame(picker, padding=(12, 0, 12, 8))
            contact_body.pack(fill="both", expand=True)
            listing = tk.Listbox(contact_body, selectmode=tk.EXTENDED, exportselection=False)
            listing.pack(side="left", fill="both", expand=True)
            scrollbar = ttk.Scrollbar(contact_body, orient="vertical", command=listing.yview)
            listing.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            for contact in contacts:
                username = f" @{contact['username']}" if contact.get("username") else ""
                listing.insert(tk.END, f"{contact['name']}{username}    [{contact['id']}]")

            def import_selected(target: list[int], target_list: tk.Listbox, target_name: str) -> None:
                indexes = list(listing.curselection())
                if not indexes:
                    messagebox.showinfo("选择联系人", "请先多选要加入的联系人。", parent=picker)
                    return
                target.extend(
                    int(contacts[index]["id"])
                    for index in indexes
                    if int(contacts[index]["id"]) not in target
                )
                populate(target_list, target)
                if target is owner_ids:
                    owner_usernames.extend(
                        username_value
                        for index in indexes
                        if (username_value := str(contacts[index].get("username") or "").strip().lstrip("@").casefold())
                        and username_value not in owner_usernames
                    )
                    populate_usernames()
                fetch_status.set(f"已将所选联系人加入“{target_name}”；点保存后写入配置。")
                animate_window_close(picker)

            buttons = ttk.Frame(picker, padding=(12, 0, 12, 12))
            buttons.pack(fill="x")
            AnimatedButton(buttons, text="加入可触发名单", command=lambda: import_selected(sender_ids, trigger_list, "可触发名单")).pack(side="left", padx=(0, 8))
            AnimatedButton(buttons, text="加入主人名单", command=lambda: import_selected(owner_ids, owner_list, "主人名单")).pack(side="left")

        def fetch_contacts() -> None:
            active = [
                proc for running_profile, _action, proc in self.child_processes
                if running_profile == profile and proc.poll() is None
            ]
            if active:
                messagebox.showwarning("账号正在使用", "请先停止该账号由此窗口启动的监听，再读取联系人，避免同时打开同一 session。", parent=dialog)
                return
            fetch_button.configure(state="disabled")
            fetch_status.set("正在连接 Telegram 并读取联系人 ID…")

            def worker() -> None:
                env = os.environ.copy()
                env["PYTHONPATH"] = str(ROOT / ".deps")
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                try:
                    result = subprocess.run(
                        self._worker_command(profile, ["--list-contacts-json"]),
                        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=90, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
                    )
                    if result.returncode == 0:
                        contacts = json.loads(result.stdout)
                        error = None if isinstance(contacts, list) else "Telegram 没有返回有效联系人列表。"
                    else:
                        contacts = None
                        lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
                        error = lines[-1] if lines else f"读取失败，进程退出码 {result.returncode}。"
                        error = error[:400]
                except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
                    contacts, error = None, str(exc)

                def finish() -> None:
                    fetch_button.configure(state="normal")
                    if error:
                        fetch_status.set(error)
                        messagebox.showerror("读取联系人失败", error, parent=dialog)
                    elif not contacts:
                        fetch_status.set("当前账号联系人列表为空。")
                        messagebox.showinfo("联系人为空", "Telegram 没有返回联系人。", parent=dialog)
                    else:
                        fetch_status.set(f"已获取 {len(contacts)} 位联系人；选择后可多选加入名单。")
                        add_contact_picker(contacts)
                self.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        controls = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        controls.grid(row=3, column=0, sticky="ew")
        fetch_button = AnimatedButton(controls, text="获取联系人用户 ID", command=fetch_contacts)
        fetch_button.pack(side="left")

        def save_user_lists() -> None:
            updated = text
            for key, values in (
                ("ALLOWED_SENDER_IDS", sender_ids),
                ("OWNER_USER_IDS", owner_ids),
                ("OWNER_USERNAMES", owner_usernames),
            ):
                line = key + "=" + ",".join(str(value) for value in values)
                if re.search(rf"(?m)^{key}=.*$", updated):
                    updated = re.sub(rf"(?m)^{key}=.*$", lambda _match, line=line: line, updated, count=1)
                else:
                    updated = updated.rstrip() + "\n" + line + "\n"
            profile_file.write_text(updated, encoding="utf-8")
            self.status.set(
                f"已保存 {profile} 用户名单：可触发 {len(sender_ids)} 人，主人 {len(owner_ids)} 个 ID / {len(owner_usernames)} 个用户名；重启监听后生效。"
            )
            animate_window_close(dialog)

        AnimatedButton(controls, text="保存两份名单", style="Primary.TButton", command=save_user_lists).pack(side="right")

    def _refresh_process_status(self) -> None:
        self.child_processes = [(p, a, proc) for p, a, proc in self.child_processes if proc.poll() is None]
        self.after(1200, self._refresh_process_status)


def run_desktop() -> None:
    if os.name == "nt":
        # 将本程序的任务栏图标与通用 Python 进程分组区分。
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Ac1oud.TelegramAI.AccountManager")
        except (AttributeError, OSError):
            pass
    AccountManager().mainloop()


if __name__ == "__main__":
    run_desktop()
