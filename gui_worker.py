"""Windowed worker interaction without cmd.exe or a console host."""

import builtins
import getpass
import io
import queue
import sys
import threading
import tkinter as tk
from tkinter import simpledialog
from tkinter.scrolledtext import ScrolledText

from app_runtime import RESOURCE_ROOT


class WindowOutput(io.TextIOBase):
    def __init__(self, events):
        self.events = events

    @property
    def encoding(self):
        return "utf-8"

    def writable(self):
        return True

    def isatty(self):
        # Existing interactive media selection can use our dialog input.
        return True

    def write(self, text):
        length = len(text)
        if text:
            text = str(text).replace("\x1b[40m  \x1b[0m", "██").replace("\x1b[47m  \x1b[0m", "  ")
            self.events.put(("output", str(text)))
        return length

    def flush(self):
        pass


def run_worker():
    root = tk.Tk()
    profile = sys.argv[sys.argv.index("--profile") + 1] if "--profile" in sys.argv else "账号"
    root.title(f"Telegram AI · {profile} · 运行状态")
    root.geometry("760x520")
    try:
        root.iconbitmap(str(RESOURCE_ROOT / "assets/app-icon.ico"))
    except tk.TclError:
        pass
    output = ScrolledText(root, font=("Consolas", 10), background="white", foreground="black", wrap="none", state="disabled")
    output.pack(fill="both", expand=True, padx=12, pady=12)
    tk.Label(root, text="验证码与密码通过弹窗输入；关闭此窗口将停止本次任务。", anchor="w").pack(fill="x", padx=12, pady=(0, 12))
    events = queue.Queue()
    stream = WindowOutput(events)
    poll_id = None
    qr_window = None

    def show_qr(matrix):
        nonlocal qr_window
        if qr_window is not None and qr_window.winfo_exists():
            qr_window.destroy()
        qr_window = tk.Toplevel(root)
        qr_window.title("Telegram AI · 扫码登录")
        qr_window.resizable(False, False)
        size = len(matrix)
        scale = max(3, min(8, 440 // size))
        canvas = tk.Canvas(qr_window, width=size * scale, height=size * scale, background="white", highlightthickness=0)
        canvas.pack(padx=16, pady=16)
        for y, row in enumerate(matrix):
            for x, dark in enumerate(row):
                if dark:
                    canvas.create_rectangle(x * scale, y * scale, (x + 1) * scale, (y + 1) * scale, fill="black", outline="")

    def enqueue_qr(url):
        import qrcode

        qr = qrcode.QRCode(border=4)
        qr.add_data(url)
        qr.make(fit=True)
        events.put(("qr", qr.get_matrix()))

    def ask(prompt="", secret=False):
        response = queue.Queue(maxsize=1)
        events.put(("input", (str(prompt), secret, response)))
        answer = response.get()
        if answer is None:
            raise EOFError("用户取消输入")
        return answer

    def poll():
        nonlocal poll_id
        poll_id = None
        # Bound each batch so a busy listener cannot starve the Tk event loop.
        for _ in range(100):
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == "input":
                prompt, secret, response = value
                answer = simpledialog.askstring("Telegram AI · 输入", prompt, show="*" if secret else "", parent=root)
                response.put(answer)
            elif kind == "qr":
                show_qr(value)
            elif kind == "finished":
                if qr_window is not None and qr_window.winfo_exists():
                    qr_window.destroy()
            else:
                output.configure(state="normal")
                output.insert("end", value)
                if int(output.index("end-1c").split(".")[0]) > 2000:
                    output.delete("1.0", "500.0")
                output.see("end")
                output.configure(state="disabled")
        if root.winfo_exists():
            poll_id = root.after(40, poll)

    old_streams = sys.stdin, sys.stdout, sys.stderr
    old_input, old_getpass = builtins.input, getpass.getpass
    sys.stdin = sys.stdout = sys.stderr = stream
    builtins.input = ask
    getpass.getpass = lambda prompt="Password: ", stream=None: ask(prompt, secret=True)

    def task():
        try:
            import main

            main.print_login_qr = enqueue_qr
            main.main()
        except (Exception, SystemExit) as exc:
            if not isinstance(exc, SystemExit) or exc.code:
                events.put(("output", f"\n任务结束：{exc}\n"))
        finally:
            events.put(("finished", None))
            events.put(("output", "\n任务已结束，可关闭此窗口。\n"))

    threading.Thread(target=task, daemon=True).start()
    poll_id = root.after(40, poll)
    try:
        root.mainloop()
    finally:
        if poll_id is not None:
            try:
                root.after_cancel(poll_id)
            except tk.TclError:
                pass
        sys.stdin, sys.stdout, sys.stderr = old_streams
        builtins.input, getpass.getpass = old_input, old_getpass
