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

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"success": True, "service": "openclaw-newapi-bridge"})
            return
        self._send(404, {"success": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/api/openclaw/launcher-token":
            self._send(404, {"success": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length > 65536:
                self._send(413, {"success": False, "error": "request too large"})
                return
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            body = json.loads(raw) if raw else {}
            status, payload = handle_launcher_token(body)
            self._send(status, payload)
        except Exception as error:
            self._send(500, {"success": False, "error": str(error)})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"openclaw-newapi-bridge listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
