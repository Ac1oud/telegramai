"""Standalone window for the Telegram bot hosting worker."""
from __future__ import annotations
import json, sys, threading, tkinter as tk
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
from app_runtime import RESOURCE_ROOT
from bot_hosting import BotHostingService

def run_bot_worker() -> None:
    config_path = Path(sys.argv[sys.argv.index("--bot-config") + 1])
    config = json.loads(config_path.read_text(encoding="utf-8"))
    root = tk.Tk(); root.title("Telegram AI · 双向机器人托管"); root.geometry("780x540")
    try: root.iconbitmap(str(RESOURCE_ROOT / "assets/app-icon.ico"))
    except tk.TclError: pass
    output = ScrolledText(root, font=("Consolas", 10), state="disabled", wrap="word")
    output.pack(fill="both", expand=True, padx=12, pady=12)
    status = tk.StringVar(value="正在启动托管…")
    tk.Label(root, textvariable=status, anchor="w").pack(fill="x", padx=12, pady=(0, 12))
    def log(text):
        def append():
            if not root.winfo_exists(): return
            status.set(str(text)); output.configure(state="normal"); output.insert("end", str(text) + "\n"); output.see("end"); output.configure(state="disabled")
        root.after(0, append)
    service = BotHostingService(config, on_status=log)
    def start():
        try: service.start()
        except Exception as exc: log(f"启动失败：{exc}")
    def close():
        service.stop(); root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    threading.Thread(target=start, daemon=True).start()
    root.mainloop()
