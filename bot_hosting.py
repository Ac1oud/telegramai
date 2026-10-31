"""Local Telegram Bot API relay with optional Cloudflare Turnstile gating."""
from __future__ import annotations

import json
import html
import secrets
import logging
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG = logging.getLogger(__name__)


def _api(token: str, method: str, payload: dict) -> dict:
    data = urllib.parse.urlencode(payload).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data)
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            result = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise RuntimeError(
            "无法连接 Telegram Bot API。请检查网络、代理和 Bot Token；原始错误：" + str(exc)
        ) from exc
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram Bot API 请求失败"))
    return result.get("result") or {}


def verify_turnstile(secret: str, response_token: str, remote_ip: str = "") -> bool:
    if not secret or not response_token:
        return False
    body = urllib.parse.urlencode({"secret": secret, "response": response_token, "remoteip": remote_ip}).encode()
    request = urllib.request.Request("https://challenges.cloudflare.com/turnstile/v0/siteverify", data=body)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return bool(json.loads(response.read().decode()).get("success"))
    except Exception:
        LOG.exception("Turnstile 校验失败")
        return False


class BotHostingService:
    def __init__(self, config: dict, on_status=None):
        self.config = config
        self.on_status = on_status or (lambda _: None)
        self.api_call = _api
        self.stop_event = threading.Event()
        self.thread = None
        self.httpd = None
        self.operator_map: dict[int, int] = {}
        self.verified: set[int] = set()
        self.tickets: dict[str, tuple[int, float]] = {}
        self.remote_tickets: dict[int, str] = {}

    def _remote_enabled(self) -> bool:
        return bool(str(self.config.get("verify_api_url", "")).strip() and str(self.config.get("verify_api_key", "")).strip())

    def _remote_request(self, method: str, path: str, payload: dict | None = None):
        base = str(self.config.get("verify_api_url", "")).strip().rstrip("/")
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(base + path, data=data, method=method,
                                         headers={"X-Verify-Key": str(self.config.get("verify_api_key", "")),
                                                  "Content-Type": "application/json",
                                                  "Accept": "application/json",
                                                  "User-Agent": "TelegramAI-Verification/1.0"})
        url = base + path
        self.on_status(f"验证服务请求：{method} {url}")
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read().decode("utf-8")
                self.on_status(f"验证服务响应：HTTP {response.status}")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"验证服务 HTTP {exc.code}：{detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"验证服务连接失败：{exc}") from exc

    def _remote_ticket(self, user_id: int) -> str:
        result = self._remote_request("POST", "/api/tickets", {"user_id": str(user_id)})
        if not result.get("ticket") or not result.get("url"):
            raise RuntimeError(f"验证服务返回缺少 ticket/url：{result}")
        self.remote_tickets[user_id] = str(result["ticket"])
        return str(result["url"])

    def _remote_verified(self, user_id: int) -> bool:
        ticket = self.remote_tickets.get(user_id, "")
        if not ticket:
            return False
        query = urllib.parse.urlencode({"ticket": ticket})
        return bool(self._remote_request("GET", "/api/status?" + query).get("verified"))

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        if self.running:
            return
        token = str(self.config.get("bot_token", "")).strip()
        if not token:
            raise ValueError("请先填写 Bot API Token")
        me = _api(token, "getMe", {})
        self.config["bot_username"] = me.get("username", "")
        self.stop_event.clear()
        if self.config.get("turnstile_enabled"):
            self._start_verification_server()
        self.thread = threading.Thread(target=self._poll, name="telegram-bot-host", daemon=True)
        self.thread.start()
        self.on_status(f"托管运行中：@{self.config.get('bot_username') or 'bot'}")

    def stop(self):
        self.stop_event.set()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self.on_status("托管已停止")

    def _send(self, method, payload):
        return self.api_call(str(self.config.get("bot_token", "")), method, payload)

    def _poll(self):
        offset = 0
        while not self.stop_event.is_set():
            try:
                updates = self._send("getUpdates", {"timeout": 20, "offset": offset, "allowed_updates": json.dumps(["message"])})
                for update in updates:
                    offset = max(offset, int(update.get("update_id", 0)) + 1)
                    message = update.get("message") or {}
                    chat_id = int((message.get("chat") or {}).get("id", 0))
                    operator = int(self.config.get("operator_chat_id") or 0)
                    if chat_id == operator and int((message.get("from") or {}).get("id", 0)) != operator:
                        continue
                    replied = ((message.get("reply_to_message") or {}).get("message_id"))
                    if chat_id == operator and replied is not None and int(replied) in self.operator_map:
                        self.on_status(f"管理员回复：回传给用户 {self.operator_map[int(replied)]}")
                        self._send("copyMessage", {"chat_id": self.operator_map[int(replied)], "from_chat_id": operator, "message_id": message["message_id"]})
                    else:
                        self._handle(message)
            except Exception as exc:
                LOG.warning("Bot 轮询失败：%s", exc)
                self.on_status(f"轮询暂时失败：{exc}")
                self.stop_event.wait(4)

    def _handle(self, message):
        chat = message.get("chat") or {}
        user_id = int((message.get("from") or {}).get("id", 0))
        chat_id = int(chat.get("id", 0))
        text = str(message.get("text") or message.get("caption") or "").strip()
        if not user_id or not chat_id:
            return
        if chat_id == int(self.config.get("operator_chat_id") or 0):
            return
        if self.config.get("turnstile_enabled") and user_id not in self.verified and self._remote_enabled():
            try:
                if self._remote_verified(user_id):
                    self.verified.add(user_id)
                    self.on_status(f"远程验证已通过：用户 {user_id}")
            except Exception as exc:
                self.on_status(f"验证状态查询失败：{exc}")
        if text.startswith("/start"):
            self.on_status(f"收到 /start：用户 {user_id}")
            if self.config.get("turnstile_enabled") and user_id not in self.verified:
                if self._remote_enabled():
                    try:
                        link = self._remote_ticket(user_id)
                    except Exception as exc:
                        self.on_status(f"验证服务不可用：{exc}")
                        LOG.warning("远程验证服务不可用：%s", exc)
                        self._send("sendMessage", {"chat_id": chat_id, "text": "验证服务暂时不可用，请稍后重试。"})
                        return
                    self._send("sendMessage", {"chat_id": chat_id, "text": f"请在 10 分钟内完成验证：{link}"})
                    self.on_status(f"已发送远程验证链接：用户 {user_id}")
                    return
                ticket = secrets.token_urlsafe(24)
                self.tickets[ticket] = (user_id, time.time() + 600)
                url = str(self.config.get("verify_url", "")).strip().rstrip("/")
                link = f"{url}?ticket={urllib.parse.quote(ticket)}" if url else ""
                self._send("sendMessage", {"chat_id": chat_id, "text": f"请在 10 分钟内完成验证：{link}" if link else "验证页地址未配置，请联系管理员。"})
                self.on_status(f"已发送本地验证链接：用户 {user_id}")
                return
            self._send("sendMessage", {"chat_id": chat_id, "text": "已连接人工传话，请发送消息。"})
            return
        if self.config.get("turnstile_enabled") and user_id not in self.verified:
            self.on_status(f"拦截未验证消息：用户 {user_id}")
            self._send("sendMessage", {"chat_id": chat_id, "text": "请先完成 Cloudflare 人机验证。发送 /start 获取验证入口。"})
            return
        operator = int(self.config.get("operator_chat_id") or 0)
        if not operator:
            self._send("sendMessage", {"chat_id": chat_id, "text": "托管尚未配置管理员 Chat ID。"})
            return
        if not text and not any(key in message for key in ("photo", "video", "document", "audio", "voice", "sticker", "animation")):
            return
        forwarded = self._send("forwardMessage", {"chat_id": operator, "from_chat_id": chat_id, "message_id": message.get("message_id")})
        operator_message_id = int(forwarded.get("message_id", 0))
        self.operator_map[operator_message_id] = chat_id
        self.on_status(f"消息已转发：用户 {user_id} -> 管理员 {operator}，映射消息 {operator_message_id}")
        self._send("sendMessage", {"chat_id": chat_id, "text": "消息已转交，等待回复。"})

    def _start_verification_server(self):
        secret = str(self.config.get("turnstile_secret", "")).strip()
        site_key = str(self.config.get("turnstile_site_key", "")).strip()
        if not secret or not site_key:
            raise ValueError("启用验证需要填写 Turnstile Site Key 和 Secret Key")
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                ticket = (query.get("ticket") or [""])[0]
                record = service.tickets.get(ticket)
                if not record or record[1] < time.time():
                    self.send_error(400, "验证链接无效或已过期")
                    return
                markup = ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>人机验证</title>"
                          "<script src='https://challenges.cloudflare.com/turnstile/v0/api.js' async defer></script>"
                          "<form method='post'><input type='hidden' name='ticket' value='" + html.escape(ticket, quote=True) + "'>"
                          "<div class='cf-turnstile' data-sitekey='" + html.escape(site_key, quote=True) + "'></div>"
                          "<button>验证并继续</button></form></html>")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(markup.encode())

            def do_POST(self):
                size = min(int(self.headers.get("Content-Length", "0")), 8192)
                fields = urllib.parse.parse_qs(self.rfile.read(size).decode("utf-8", "replace"))
                response_token = (fields.get("cf-turnstile-response") or [""])[0]
                ticket = (fields.get("ticket") or [""])[0]
                record = service.tickets.get(ticket)
                if record and record[1] >= time.time() and verify_turnstile(secret, response_token, self.client_address[0]):
                    service.tickets.pop(ticket, None)
                    service.verified.add(record[0])
                    content, status = "验证通过。返回 Telegram 并发送 /start。", 200
                else:
                    content, status = "验证失败，请重试。", 400
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode())

            def log_message(self, *_args):
                return

        bind = str(self.config.get("verify_bind", "127.0.0.1"))
        port = int(self.config.get("verify_port", 8765))
        if not 1024 <= port <= 65535:
            raise ValueError("验证服务端口需为 1024–65535")
        service.httpd = ThreadingHTTPServer((bind, port), Handler)
        threading.Thread(target=service.httpd.serve_forever, name="turnstile-web", daemon=True).start()


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(path: Path, config: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = dict(config)
    path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
