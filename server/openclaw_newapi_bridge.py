#!/usr/bin/env python3
"""Small NewAPI helper for OpenClaw account login.

This service runs on localhost behind nginx. It authenticates against the
existing NewAPI login endpoint, then reads the user's full API token from the
local SQLite database. NewAPI's public token APIs return masked keys, which is
safe for the web UI but not enough for a launcher that must configure an
OpenAI-compatible gateway.
"""

from __future__ import annotations

import http.cookiejar
import hashlib
import json
import os
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


HOST = os.environ.get("OPENCLAW_NEWAPI_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("OPENCLAW_NEWAPI_BRIDGE_PORT", "3016"))
NEWAPI_BASE = os.environ.get("OPENCLAW_NEWAPI_BASE", "http://127.0.0.1:3000").rstrip("/")
DB_PATH = os.environ.get("OPENCLAW_NEWAPI_DB", "/mnt/data/new-api/one-api.db")
BIND_DB_PATH = os.environ.get("OPENCLAW_BIND_DB", "/tmp/openclaw-bind-tickets.db")
BIND_TICKET_TTL_SEC = int(os.environ.get("OPENCLAW_BIND_TICKET_TTL_SEC", "600"))
BIND_PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OpenClaw 网站绑定</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0f172a; color: #f8fafc; }
    main { width: min(460px, calc(100vw - 32px)); border: 1px solid rgba(148, 163, 184, .35); border-radius: 18px; background: rgba(15, 23, 42, .92); box-shadow: 0 24px 80px rgba(0,0,0,.35); padding: 28px; }
    h1 { margin: 0 0 8px; font-size: 24px; line-height: 1.2; }
    p { margin: 0 0 22px; color: #cbd5e1; line-height: 1.65; }
    label { display: block; margin: 14px 0 6px; color: #e2e8f0; font-size: 14px; }
    input { width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid rgba(148, 163, 184, .45); background: rgba(2, 6, 23, .65); color: #f8fafc; padding: 12px 13px; outline: none; font-size: 14px; }
    input:focus { border-color: #34d399; box-shadow: 0 0 0 3px rgba(52, 211, 153, .16); }
    button { width: 100%; margin-top: 18px; border: 0; border-radius: 12px; padding: 12px 14px; background: #10b981; color: #04130e; font-weight: 700; cursor: pointer; }
    button:disabled { opacity: .65; cursor: progress; }
    .result { margin-top: 18px; padding: 14px; border-radius: 12px; background: rgba(16, 185, 129, .12); border: 1px solid rgba(52, 211, 153, .32); display: none; }
    .result strong { display: block; overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; margin-top: 8px; color: #86efac; }
    .error { margin-top: 14px; color: #fca5a5; min-height: 20px; }
    .meta { margin-top: 12px; font-size: 12px; color: #94a3b8; }
  </style>
</head>
<body>
  <main>
    <h1>OpenClaw 网站绑定</h1>
    <p>登录中转站账号，生成一次性绑定码。回到启动器的账号页粘贴绑定码，即可同步模型。</p>
    <form id="bind-form">
      <label for="username">账号</label>
      <input id="username" name="username" autocomplete="username" placeholder="邮箱或用户名" required />
      <label for="password">密码</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required />
      <button id="submit" type="submit">生成绑定码</button>
    </form>
    <div class="result" id="result">
      <span>绑定码</span>
      <strong id="ticket"></strong>
      <div class="meta" id="expires"></div>
    </div>
    <div class="error" id="error"></div>
  </main>
  <script>
    const form = document.getElementById('bind-form');
    const submit = document.getElementById('submit');
    const result = document.getElementById('result');
    const ticketEl = document.getElementById('ticket');
    const expiresEl = document.getElementById('expires');
    const errorEl = document.getElementById('error');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      errorEl.textContent = '';
      result.style.display = 'none';
      const body = {
        username: form.username.value.trim(),
        password: form.password.value,
      };
      try {
        const response = await fetch('/api/openclaw/bind/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const payload = await response.json();
        if (!response.ok || payload.success === false) throw new Error(payload.error || payload.message || '生成失败');
        form.password.value = '';
        ticketEl.textContent = payload.data.ticket;
        const expiresAt = new Date((payload.data.expiresAt || 0) * 1000);
        expiresEl.textContent = Number.isNaN(expiresAt.getTime()) ? '10 分钟内有效' : `有效期至 ${expiresAt.toLocaleString()}`;
        result.style.display = 'block';
        if (navigator.clipboard) navigator.clipboard.writeText(payload.data.ticket).catch(() => {});
      } catch (error) {
        errorEl.textContent = error instanceof Error ? error.message : String(error);
      } finally {
        submit.disabled = false;
      }
    });
  </script>
</body>
</html>"""


def mask_secret(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def request_json(
    opener: urllib.request.OpenerDirector,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    data = None
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{NEWAPI_BASE}{path}",
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"message": raw}
        raise RuntimeError(str(payload.get("message") or payload.get("error") or f"HTTP {error.code}")) from error


def candidate_user_id(login_payload: dict[str, Any]) -> str:
    data = login_payload.get("data")
    if isinstance(data, dict):
        value = data.get("id") or data.get("user_id") or data.get("userId")
        if value:
            return str(value)
    for key in ("id", "user_id", "userId"):
        value = login_payload.get(key)
        if value:
            return str(value)
    return ""


def user_group(login_payload: dict[str, Any]) -> str:
    data = login_payload.get("data")
    if isinstance(data, dict):
        return str(data.get("group") or "default")
    return "default"


def token_usable(row: sqlite3.Row) -> bool:
    if int(row["status"] or 0) != 1:
        return False
    if row["deleted_at"]:
        return False
    if bool(row["unlimited_quota"]):
        return True
    try:
        return int(row["remain_quota"] or 0) > 0
    except (TypeError, ValueError):
        return False


def select_token(user_id: str, preferred_name: str = "") -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            select id, key, name, remain_quota, unlimited_quota, model_limits_enabled,
                   model_limits, status, deleted_at, created_time
            from tokens
            where user_id = ? and deleted_at is null and status = 1
            order by created_time desc, id desc
            """,
            (user_id,),
        ).fetchall()
    if not rows:
        return None

    preferred = [row for row in rows if preferred_name and row["name"] == preferred_name]
    usable = [row for row in rows if token_usable(row)]
    ordered = preferred + [row for row in usable if row not in preferred] + [row for row in rows if row not in preferred and row not in usable]
    row = ordered[0]
    return {
        "id": row["id"],
        "key": row["key"],
        "name": row["name"],
        "remainQuota": row["remain_quota"],
        "unlimitedQuota": bool(row["unlimited_quota"]),
        "modelLimitsEnabled": bool(row["model_limits_enabled"]),
        "modelLimits": row["model_limits"] or "",
    }


def create_token(opener: urllib.request.OpenerDirector, user_id: str, group: str) -> dict[str, Any] | None:
    token_name = f"OpenClaw Launcher {int(time.time())}-{secrets.token_hex(3)}"
    headers = {"New-Api-User": user_id}
    attempts = [
        {"name": token_name, "remain_quota": 0, "expired_time": -1, "unlimited_quota": True, "group": group},
        {"name": token_name, "remain_quota": 500000, "expired_time": -1, "unlimited_quota": False, "group": group},
        {"name": token_name, "expired_time": -1, "group": group},
    ]
    last_error = ""
    for body in attempts:
        try:
            payload = request_json(opener, "/api/token/", method="POST", body=body, headers=headers)
            if payload.get("success") is False:
                last_error = str(payload.get("message") or "token create failed")
                continue
            token = select_token(user_id, token_name)
            if token and token.get("key"):
                token["source"] = "created"
                return token
        except Exception as error:  # Keep trying compatible payloads.
            last_error = str(error)
    if last_error:
        raise RuntimeError(last_error)
    return None


def fetch_models(token: str) -> list[str]:
    opener = urllib.request.build_opener()
    try:
        payload = request_json(opener, "/v1/models", headers={"Authorization": f"Bearer {token}"}, timeout=25)
    except Exception:
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    models: list[str] = []
    for item in data:
        model_id = ""
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
        else:
            model_id = str(item or "").strip()
        if model_id and model_id not in models:
            models.append(model_id)
    return models


def handle_launcher_token(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    username = str(body.get("username") or body.get("email") or "").strip()
    password = str(body.get("password") or "").strip()
    preferred_name = str(body.get("tokenName") or "").strip()
    if not username or not password:
        return 400, {"success": False, "error": "username and password are required"}

    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    login_payload = request_json(opener, "/api/user/login", method="POST", body={"username": username, "password": password})
    if login_payload.get("success") is False:
        return 401, {"success": False, "error": str(login_payload.get("message") or "login failed")}

    user_id = candidate_user_id(login_payload)
    if not user_id:
        return 500, {"success": False, "error": "login succeeded but user id was not returned"}

    token = select_token(user_id, preferred_name)
    source = "existing"
    if not token:
        token = create_token(opener, user_id, user_group(login_payload))
        source = "created"
    if not token or not token.get("key"):
        return 500, {"success": False, "error": "no usable token found or created"}

    key = str(token["key"])
    return 200, {
        "success": True,
        "data": {
            "userId": user_id,
            "account": username,
            "key": key,
            "tokenMasked": mask_secret(key),
            "tokenId": token.get("id"),
            "tokenName": token.get("name"),
            "source": token.get("source") or source,
            "remainQuota": token.get("remainQuota"),
            "unlimitedQuota": token.get("unlimitedQuota"),
            "modelLimitsEnabled": token.get("modelLimitsEnabled"),
            "modelLimits": token.get("modelLimits"),
            "models": fetch_models(key),
        },
    }


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def _bind_connection() -> sqlite3.Connection:
    directory = os.path.dirname(BIND_DB_PATH)
    if directory:
        os.makedirs(directory, mode=0o700, exist_ok=True)
    connection = sqlite3.connect(BIND_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        create table if not exists bind_tickets (
            ticket_hash text primary key,
            payload text not null,
            created_at integer not null,
            expires_at integer not null,
            claimed_at integer
        )
        """
    )
    try:
        os.chmod(BIND_DB_PATH, 0o600)
    except OSError:
        pass
    return connection


def cleanup_bind_tickets(now: int | None = None) -> None:
    now = int(now or time.time())
    connection = _bind_connection()
    try:
        connection.execute(
            "delete from bind_tickets where expires_at < ? or (claimed_at is not null and claimed_at < ?)",
            (now - 60, now - 60),
        )
        connection.commit()
    finally:
        connection.close()


def create_bind_ticket(payload: dict[str, Any], ttl_sec: int = BIND_TICKET_TTL_SEC) -> dict[str, Any]:
    ticket = "ocb_" + secrets.token_urlsafe(24)
    now = int(time.time())
    expires_at = now + int(ttl_sec)
    cleanup_bind_tickets(now)
    connection = _bind_connection()
    try:
        connection.execute(
            """
            insert into bind_tickets(ticket_hash, payload, created_at, expires_at, claimed_at)
            values(?, ?, ?, ?, null)
            """,
            (_ticket_hash(ticket), json.dumps(payload, ensure_ascii=False), now, expires_at),
        )
        connection.commit()
    finally:
        connection.close()
    return {"ticket": ticket, "expiresAt": expires_at}


def _public_bind_payload(data: dict[str, Any], ticket_info: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket": ticket_info["ticket"],
        "expiresAt": ticket_info["expiresAt"],
        "account": data.get("account") or "",
        "userId": data.get("userId") or "",
        "tokenMasked": data.get("tokenMasked") or mask_secret(str(data.get("key") or "")),
        "tokenId": data.get("tokenId"),
        "tokenName": data.get("tokenName") or "",
        "source": data.get("source") or "bridge",
        "models": data.get("models") if isinstance(data.get("models"), list) else [],
    }


def handle_bind_start(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    status, payload = handle_launcher_token(body)
    if status != 200 or payload.get("success") is False:
        return status, payload
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if not data.get("key"):
        return 500, {"success": False, "error": "launcher token payload missing key"}
    ticket_info = create_bind_ticket(payload)
    return 200, {"success": True, "data": _public_bind_payload(data, ticket_info)}


def handle_bind_claim(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    ticket = str(body.get("ticket") or body.get("code") or "").strip()
    if not ticket:
        return 400, {"success": False, "error": "ticket is required"}
    now = int(time.time())
    cleanup_bind_tickets(now)
    connection = _bind_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "select payload, expires_at, claimed_at from bind_tickets where ticket_hash = ?",
            (_ticket_hash(ticket),),
        ).fetchone()
        if not row:
            connection.rollback()
            return 404, {"success": False, "error": "ticket not found"}
        if row["claimed_at"]:
            connection.rollback()
            return 410, {"success": False, "error": "ticket already claimed"}
        if int(row["expires_at"] or 0) < now:
            connection.execute("delete from bind_tickets where ticket_hash = ?", (_ticket_hash(ticket),))
            connection.commit()
            return 410, {"success": False, "error": "ticket expired"}
        connection.execute("delete from bind_tickets where ticket_hash = ?", (_ticket_hash(ticket),))
        connection.commit()
    finally:
        connection.close()
    try:
        payload = json.loads(row["payload"])
    except Exception:
        return 500, {"success": False, "error": "ticket payload corrupted"}
    if not isinstance(payload, dict):
        return 500, {"success": False, "error": "ticket payload invalid"}
    return 200, payload


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep default access logging quiet to avoid accidental sensitive context.
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_html(self, status: int, html: str) -> None:
        raw = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"success": True, "service": "openclaw-newapi-bridge"})
            return
        if self.path in ("/api/openclaw/bind/page", "/openclaw-bind"):
            self._send_html(200, BIND_PAGE_HTML)
            return
        self._send(404, {"success": False, "error": "not found"})

    def do_POST(self) -> None:
        routes = {
            "/api/openclaw/launcher-token": handle_launcher_token,
            "/api/openclaw/bind/start": handle_bind_start,
            "/api/openclaw/bind/claim": handle_bind_claim,
        }
        handler = routes.get(self.path)
        if not handler:
            self._send(404, {"success": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length > 65536:
                self._send(413, {"success": False, "error": "request too large"})
                return
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw) if raw else {}
            status, payload = handler(body)
            self._send(status, payload)
        except Exception as error:
            self._send(500, {"success": False, "error": str(error)})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"openclaw-newapi-bridge listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
