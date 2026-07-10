#!/usr/bin/env python3
"""Small online activation server for OpenClaw Launcher."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import secrets
import shutil
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


LOGGER = logging.getLogger("openclaw-license")
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LICENSE_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    )


def bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid integer env %s=%r; using %s", name, raw, default)
        value = default
    return max(minimum, min(value, maximum))


BASE_DIR = "/opt/openclaw-license"
DB_PATH = os.environ.get("LICENSE_DB", os.path.join(BASE_DIR, "license.db"))
BACKUP_DIR = os.environ.get("LICENSE_BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
PRIVATE_KEY_FILE = os.environ.get("LICENSE_PRIVATE_KEY_FILE", os.path.join(BASE_DIR, "private_key.b64"))
ADMIN_TOKEN_FILE = os.environ.get("LICENSE_ADMIN_TOKEN_FILE", os.path.join(BASE_DIR, "admin_token.txt"))
LOGO_FILE = os.environ.get("LICENSE_LOGO_FILE", os.path.join(BASE_DIR, "logo.ico"))
HOST = os.environ.get("LICENSE_HOST", "0.0.0.0")
PORT = int(os.environ.get("LICENSE_PORT", "18791"))
COMMERCIAL_FEATURES = [
    "acquisition.workbench",
    "acquisition.feishu",
    "matrix.devices",
    "templates.cloud",
    "publishing.draft",
    "diagnostics.export",
]
DEFAULT_FEATURES = ["openclaw", "image", "video", "storyboard", *COMMERCIAL_FEATURES]
VIP_DEFAULT_FEATURES = [*DEFAULT_FEATURES, "phoneAgent", "desktopAgent"]
PUBLIC_COMMERCIAL_URL = os.environ.get("LICENSE_PUBLIC_URL", "https://license.heang.top/").strip()
PUBLIC_SUPPORT_URL = os.environ.get("LICENSE_SUPPORT_URL", PUBLIC_COMMERCIAL_URL).strip()
DEFAULT_GATEWAY_BASE_URL = os.environ.get("MEMBER_GATEWAY_BASE_URL", "").strip().rstrip("/")
DEFAULT_GATEWAY_IMAGE_BASE_URL = os.environ.get("MEMBER_GATEWAY_IMAGE_BASE_URL", "").strip().rstrip("/")
DEFAULT_GATEWAY_VIDEO_BASE_URL = os.environ.get("MEMBER_GATEWAY_VIDEO_BASE_URL", "").strip().rstrip("/")
DEFAULT_GATEWAY_TOKEN = os.environ.get("MEMBER_GATEWAY_TOKEN", "").strip()
DEFAULT_GATEWAY_IMAGE_TOKEN = os.environ.get("MEMBER_GATEWAY_IMAGE_TOKEN", "").strip()
DEFAULT_GATEWAY_VIDEO_TOKEN = os.environ.get("MEMBER_GATEWAY_VIDEO_TOKEN", "").strip()
DEFAULT_GATEWAY_DEFAULT_MODEL = os.environ.get("MEMBER_GATEWAY_DEFAULT_MODEL", "").strip()
DEFAULT_GATEWAY_IMAGE_MODEL = os.environ.get("MEMBER_GATEWAY_IMAGE_MODEL", "").strip()
DEFAULT_GATEWAY_VIDEO_MODEL = os.environ.get("MEMBER_GATEWAY_VIDEO_MODEL", "").strip()
DEFAULT_GATEWAY_MODELS = [
    item.strip()
    for item in os.environ.get("MEMBER_GATEWAY_MODELS", "").replace("\uFF0C", ",").split(",")
    if item.strip()
]
DEFAULT_PUBLIC_SETTINGS = {
    "cardSiteEnabled": True,
    "cardSiteLabel": "购买授权码",
    "cardSiteUrl": "",
    "supportUrl": PUBLIC_SUPPORT_URL,
}
PUBLISH_RELAY_TOKEN = (
    os.environ.get("OPENCLAW_PUBLISH_RELAY_TOKEN")
    or os.environ.get("PUBLISH_RELAY_TOKEN")
    or ""
).strip()
PUBLISH_RELAY_DEFAULT_LEASE_MS = 30_000
PUBLISH_RELAY_DEFAULT_WAIT_MS = 15_000
PUBLISH_RELAY_MAX_ATTEMPTS = max(1, min(int(os.environ.get("PUBLISH_RELAY_MAX_ATTEMPTS", "5") or "5"), 20))
PUBLISH_RELAY_BACKOFF_MS = 2_000
PUBLISH_RELAY_MAX_BACKOFF_MS = 5 * 60_000
MAX_BULK_CODE_HASHES = bounded_int_env("LICENSE_MAX_BULK_CODE_HASHES", 1000, 1, 5000)
MAX_CODE_SECRET_EXPORT = 500
AUDIT_SECRET_KEYS = {
    "fullcode",
    "code",
    "accesstoken",
    "imageaccesstoken",
    "videoaccesstoken",
    "imagetoken",
    "videotoken",
    "gatewaytoken",
    "gatewayimagetoken",
    "gatewayvideotoken",
    "gatewayaccesstoken",
    "gatewayimageaccesstoken",
    "gatewayvideoaccesstoken",
    "apikey",
    "sessiontoken",
    "token",
}
LOGIN_RATE_LIMIT_ATTEMPTS = bounded_int_env("LICENSE_LOGIN_RATE_LIMIT_ATTEMPTS", 10, 1, 100)
LOGIN_RATE_LIMIT_WINDOW_SECONDS = bounded_int_env("LICENSE_LOGIN_RATE_LIMIT_WINDOW_SECONDS", 600, 60, 86_400)
LOGIN_RATE_LIMIT_LOCKOUT_SECONDS = bounded_int_env("LICENSE_LOGIN_RATE_LIMIT_LOCKOUT_SECONDS", 900, 60, 86_400)
REGISTER_RATE_LIMIT_ATTEMPTS = bounded_int_env("LICENSE_REGISTER_RATE_LIMIT_ATTEMPTS", 8, 1, 100)
REGISTER_RATE_LIMIT_WINDOW_SECONDS = bounded_int_env("LICENSE_REGISTER_RATE_LIMIT_WINDOW_SECONDS", 600, 60, 86_400)
REGISTER_RATE_LIMIT_LOCKOUT_SECONDS = bounded_int_env("LICENSE_REGISTER_RATE_LIMIT_LOCKOUT_SECONDS", 900, 60, 86_400)
DEFAULT_ADMIN_CORS_ORIGINS = {
    "http://127.0.0.1:18791",
    "http://localhost:18791",
    "http://118.145.98.220",
    "http://118.145.98.220:80",
    "https://118.145.98.220",
    "https://license.heang.top",
}
ADMIN_CORS_ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get("LICENSE_ADMIN_CORS_ORIGINS", "").split(",")
    if origin.strip()
} or DEFAULT_ADMIN_CORS_ORIGINS
RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMITS: dict[str, dict[str, Any]] = {}
ADMIN_HTML_FALLBACK = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>OpenClaw Admin</title></head>
<body><h1>OpenClaw Admin</h1><p>admin_console.html is missing. Please deploy it with server.py.</p></body>
</html>
"""


def load_admin_html() -> str:
    candidate_paths = [
        os.path.join(os.path.dirname(__file__), "admin_console.html"),
        os.path.join(BASE_DIR, "admin_console.html"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as file:
                return file.read()
    return ADMIN_HTML_FALLBACK


ADMIN_HTML = load_admin_html()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def now_ms() -> int:
    return int(time.time() * 1000)


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def code_hash(code: str) -> str:
    normalized = code.strip().upper()
    return hashlib.sha256(f"openclaw-license-v1:{normalized}".encode("utf-8")).hexdigest()


def load_private_key() -> Ed25519PrivateKey:
    key_text = os.environ.get("LICENSE_PRIVATE_KEY_B64")
    if not key_text:
        with open(PRIVATE_KEY_FILE, "r", encoding="utf-8") as file:
            key_text = file.read().strip()
    raw = base64.b64decode(key_text)
    return Ed25519PrivateKey.from_private_bytes(raw)


def load_admin_token() -> str | None:
    token = os.environ.get("LICENSE_ADMIN_TOKEN")
    if token:
        return token.strip()
    try:
        with open(ADMIN_TOKEN_FILE, "r", encoding="utf-8") as file:
            token = file.read().strip()
        return token or None
    except FileNotFoundError:
        return None
    except (PermissionError, OSError) as error:
        LOGGER.warning("Unable to read admin token file %s: %s", ADMIN_TOKEN_FILE, error)
        return None


ADMIN_SESSION_TTL_DAYS = max(1, min(int(os.environ.get("LICENSE_ADMIN_SESSION_TTL_DAYS", "30")), 3650))
ACCOUNT_ROLE_MERCHANT = "merchant"
ACCOUNT_ROLE_SUPER_ADMIN = "super_admin"
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_DISABLED = "disabled"
INVITE_CODE_STATUS_ACTIVE = "active"
INVITE_CODE_STATUS_DISABLED = "disabled"
INVITE_CODE_STATUS_USED = "used"
INVITE_CODE_STATUS_EXPIRED = "expired"
INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def normalize_username(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_account_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    if role in {"super", "admin", "super_admin", "superadmin"}:
        return ACCOUNT_ROLE_SUPER_ADMIN
    return ACCOUNT_ROLE_MERCHANT


def normalize_account_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"disabled", "inactive", "false", "0", "off"}:
        return ACCOUNT_STATUS_DISABLED
    return ACCOUNT_STATUS_ACTIVE


def role_rank(role: str) -> int:
    return {ACCOUNT_ROLE_MERCHANT: 1, ACCOUNT_ROLE_SUPER_ADMIN: 2}.get(normalize_account_role(role), 0)


def password_hash(password: str, *, salt: bytes | None = None, iterations: int = 210_000) -> str:
    if not str(password or ""):
        raise ValueError("password is required")
    salt_bytes = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt_bytes, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{base64.b64encode(salt_bytes).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = str(encoded or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual, expected)
    except Exception:
        return False


def admin_session_token_hash(token: str) -> str:
    return hashlib.sha256(f"openclaw-admin-session-v1:{str(token).strip()}".encode("utf-8")).hexdigest()


def generate_admin_session_token() -> str:
    return secrets.token_urlsafe(36)


def add_days_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()


def add_days_date(days: int) -> str:
    """Date-only (YYYY-MM-DD) expiry, matching admin-created codes. The launcher
    validates a license `expires` with date.fromisoformat(), which rejects full
    ISO timestamps — so codes must use this format, not add_days_iso()."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def normalize_code_expires(value: str) -> str:
    """A code's `expires` must be a date-only YYYY-MM-DD the launcher can parse
    with date.fromisoformat() (4-digit year, 1-9999). Trim a stray time part if
    present, then validate — so a typo like '33333-03-31' or an ISO timestamp
    can't mint a code that activates server-side but the client rejects."""
    raw = str(value or "").strip()
    if not raw:
        raise ActivationError("到期日期不能为空")
    candidate = raw.split("T", 1)[0].strip()  # tolerate full ISO timestamps
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        raise ActivationError(f"到期日期格式无效，需要 YYYY-MM-DD：{raw}")
    if parsed <= date.today():
        raise ActivationError("到期日期必须晚于今天")
    return candidate


def extract_bearer_token(headers: Any) -> str:
    auth = str(headers.get("Authorization", "") or "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def request_admin_token(headers: Any) -> str:
    return (
        extract_bearer_token(headers)
        or str(headers.get("X-Admin-Session", "") or "").strip()
        or str(headers.get("X-Admin-Token", "") or "").strip()
    )


def account_row_public(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    keys = set(row.keys())
    return {
        "accountId": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "role": row["role"],
        "status": row["status"],
        "note": row["note"] if "note" in keys else "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "lastLoginAt": row["last_login_at"] if "last_login_at" in keys else "",
        "lastLoginIp": row["last_login_ip"] if "last_login_ip" in keys else "",
        "codeCount": int(row["code_count"]) if "code_count" in keys and row["code_count"] is not None else 0,
        "activeCodeCount": int(row["active_code_count"]) if "active_code_count" in keys and row["active_code_count"] is not None else 0,
        "disabledCodeCount": int(row["disabled_code_count"]) if "disabled_code_count" in keys and row["disabled_code_count"] is not None else 0,
        "memberCodeCount": int(row["member_code_count"]) if "member_code_count" in keys and row["member_code_count"] is not None else 0,
        "usedCodeCount": int(row["used_code_count"]) if "used_code_count" in keys and row["used_code_count"] is not None else 0,
        "activationCount": int(row["activation_count"]) if "activation_count" in keys and row["activation_count"] is not None else 0,
        "activationLimitCount": int(row["activation_limit_count"]) if "activation_limit_count" in keys and row["activation_limit_count"] is not None else 0,
        "lastCodeCreatedAt": row["last_code_created_at"] if "last_code_created_at" in keys else "",
        "lastActivationAt": row["last_activation_at"] if "last_activation_at" in keys else "",
    }


def get_account_by_username(username: str) -> sqlite3.Row | None:
    normalized = normalize_username(username)
    if not normalized:
        return None
    with connect() as conn:
        row = conn.execute(
            "select * from accounts where username = ?",
            (normalized,),
        ).fetchone()
    return row


def get_account_by_id(account_id: int) -> sqlite3.Row | None:
    if int(account_id or 0) <= 0:
        return None
    with connect() as conn:
        row = conn.execute(
            "select * from accounts where id = ?",
            (int(account_id),),
        ).fetchone()
    return row


def list_account_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select a.*,
                   count(c.code_hash) as code_count,
                   coalesce(sum(case when c.disabled = 0 then 1 else 0 end), 0) as active_code_count,
                   coalesce(sum(case when c.disabled != 0 then 1 else 0 end), 0) as disabled_code_count,
                   coalesce(sum(case when c.member_mode = 1 then 1 else 0 end), 0) as member_code_count,
                   coalesce(sum(case when coalesce(c.activations, 0) > 0 then 1 else 0 end), 0) as used_code_count,
                   coalesce(sum(coalesce(c.activations, 0)), 0) as activation_count,
                   coalesce(sum(coalesce(c.max_activations, 0)), 0) as activation_limit_count,
                   coalesce(max(c.created_at), '') as last_code_created_at,
                   coalesce(max(c.last_activated_at), '') as last_activation_at
            from accounts a
            left join (
                select c.code_hash, c.owner_account_id, c.disabled, c.member_mode,
                       c.max_activations, c.created_at,
                       count(a.id) as activations,
                       max(a.activated_at) as last_activated_at
                from codes c
                left join activations a on a.code_hash = c.code_hash
                group by c.code_hash
            ) c on c.owner_account_id = a.id
            group by a.id
            order by case a.role when ? then 0 else 1 end, a.created_at desc
            """,
            (ACCOUNT_ROLE_SUPER_ADMIN,),
        ).fetchall()
    return [account_row_public(row) for row in rows if account_row_public(row)]


def account_summary_row(account_id: int) -> dict[str, Any] | None:
    row = get_account_by_id(account_id)
    return account_row_public(row) if row else None


def normalize_invite_code(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def generate_invite_code() -> str:
    groups = []
    for _ in range(4):
        groups.append("".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(4)))
    return "INV-" + "-".join(groups)


def invite_row_public(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    keys = set(row.keys())
    max_uses = max(1, int(row["max_uses"] or 1))
    used_count = max(0, int(row["used_count"] or 0))
    status = str(row["status"] or INVITE_CODE_STATUS_ACTIVE)
    expires_at = str(row["expires_at"] or "")
    now = utc_now()
    if status == INVITE_CODE_STATUS_ACTIVE:
        if expires_at and expires_at < now:
            status = INVITE_CODE_STATUS_EXPIRED
        elif used_count >= max_uses:
            status = INVITE_CODE_STATUS_USED
    remaining = max(0, max_uses - used_count)
    return {
        "inviteId": row["id"],
        "inviteCode": row["invite_code"],
        "role": row["role"],
        "status": status,
        "note": row["note"] if "note" in keys else "",
        "maxUses": max_uses,
        "usedCount": used_count,
        "remainingUses": remaining,
        "createdBy": int(row["created_by"] or 0),
        "createdByUsername": row["created_by_username"] if "created_by_username" in keys else "",
        "createdByDisplayName": row["created_by_display_name"] if "created_by_display_name" in keys else "",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "expiresAt": expires_at,
        "lastUsedAt": row["last_used_at"] if "last_used_at" in keys else "",
        "lastUsedIp": row["last_used_ip"] if "last_used_ip" in keys else "",
        "lastUsedUsername": row["last_used_username"] if "last_used_username" in keys else "",
        "lastUsedAccountId": int(row["last_used_account_id"] or 0) if "last_used_account_id" in keys and row["last_used_account_id"] is not None else 0,
    }


def count_invites(*, active_only: bool = False) -> int:
    with connect() as conn:
        if active_only:
            row = conn.execute(
                """
                select count(*)
                from invite_codes
                where status = ?
                  and used_count < max_uses
                  and (expires_at = '' or expires_at > ?)
                """,
                (INVITE_CODE_STATUS_ACTIVE, utc_now()),
            ).fetchone()
        else:
            row = conn.execute("select count(*) from invite_codes").fetchone()
        return int(row[0] or 0)


def list_invite_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select i.*,
                   coalesce(acc.username, '') as created_by_username,
                   coalesce(acc.display_name, '') as created_by_display_name
            from invite_codes i
            left join accounts acc on acc.id = i.created_by
            order by i.created_at desc
            """
        ).fetchall()
    invites: list[dict[str, Any]] = []
    for row in rows:
        public = invite_row_public(row)
        if public:
            invites.append(public)
    return invites


def get_invite_by_code(invite_code: str) -> sqlite3.Row | None:
    normalized = normalize_invite_code(invite_code)
    if not normalized:
        return None
    with connect() as conn:
        row = conn.execute("select * from invite_codes where invite_code = ?", (normalized,)).fetchone()
    return row


def _create_account_record_on_connection(
    conn: sqlite3.Connection,
    *,
    username: str,
    display_name: str = "",
    password: str = "",
    role: str = ACCOUNT_ROLE_MERCHANT,
    status: str = ACCOUNT_STATUS_ACTIVE,
    note: str = "",
    created_by: int = 0,
) -> tuple[dict[str, Any], str]:
    normalized_username = normalize_username(username)
    if not normalized_username:
        raise ActivationError("用户名不能为空")
    normalized_role = normalize_account_role(role)
    normalized_status = normalize_account_status(status)
    visible_name = str(display_name or "").strip() or normalized_username
    provided_password = str(password or "").strip()
    if provided_password and len(provided_password) < 8:
        raise ActivationError("密码至少需要 8 个字符")
    clear_password = provided_password or secrets.token_urlsafe(10)
    hashed_password = password_hash(clear_password)
    now = utc_now()
    existing = conn.execute("select id from accounts where username = ?", (normalized_username,)).fetchone()
    if existing:
        raise ActivationError("用户名已存在", 409)
    conn.execute(
        """
        insert into accounts (
            username, display_name, password_hash, role, status, note,
            created_by, created_at, updated_at, last_login_at, last_login_ip
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '')
        """,
        (
            normalized_username,
            visible_name,
            hashed_password,
            normalized_role,
            normalized_status,
            note[:500],
            int(created_by or 0),
            now,
            now,
        ),
    )
    row = conn.execute("select * from accounts where username = ?", (normalized_username,)).fetchone()
    if not row:
        raise ActivationError("创建账号失败", 500)
    return account_row_public(row) or {}, "" if provided_password else clear_password


def create_invite_record(
    *,
    note: str = "",
    max_uses: int = 1,
    expires_at: str = "",
    created_by: int = 0,
) -> tuple[dict[str, Any], str]:
    normalized_note = str(note or "").strip()
    normalized_expires_at = str(expires_at or "").strip()
    normalized_max_uses = max(1, min(int(max_uses or 1), 100))
    if normalized_expires_at and normalized_expires_at < utc_now():
        raise ActivationError("到期时间不能早于当前时间")
    now = utc_now()
    with connect() as conn:
        for _ in range(8):
            invite_code = generate_invite_code()
            try:
                conn.execute(
                    """
                    insert into invite_codes (
                        invite_code, role, status, max_uses, used_count, note,
                        created_by, created_at, updated_at, expires_at,
                        last_used_at, last_used_ip, last_used_username, last_used_account_id
                    )
                    values (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, '', '', '', 0)
                    """,
                    (
                        invite_code,
                        ACCOUNT_ROLE_MERCHANT,
                        INVITE_CODE_STATUS_ACTIVE,
                        normalized_max_uses,
                        normalized_note[:500],
                        int(created_by or 0),
                        now,
                        now,
                        normalized_expires_at,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    """
                    select i.*,
                           coalesce(acc.username, '') as created_by_username,
                           coalesce(acc.display_name, '') as created_by_display_name
                    from invite_codes i
                    left join accounts acc on acc.id = i.created_by
                    where i.invite_code = ?
                    """,
                    (invite_code,),
                ).fetchone()
                return invite_row_public(row) or {}, invite_code
            except sqlite3.IntegrityError:
                conn.rollback()
    raise ActivationError("生成邀请码失败", 500)


def toggle_invite_record(invite_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        existing = conn.execute("select * from invite_codes where id = ?", (int(invite_id),)).fetchone()
        if not existing:
            return None
        now = utc_now()
        current_status = str(existing["status"] or INVITE_CODE_STATUS_ACTIVE)
        if current_status == INVITE_CODE_STATUS_USED:
            raise ActivationError("邀请码已用完，不能再次启用")
        if current_status == INVITE_CODE_STATUS_EXPIRED:
            raise ActivationError("邀请码已过期，不能直接启用")
        next_status = INVITE_CODE_STATUS_DISABLED if current_status == INVITE_CODE_STATUS_ACTIVE else INVITE_CODE_STATUS_ACTIVE
        conn.execute(
            "update invite_codes set status = ?, updated_at = ? where id = ?",
            (next_status, now, int(invite_id)),
        )
        conn.commit()
    return invite_row_public(get_invite_by_code(str(existing["invite_code"])))


def register_account_with_invite(
    *,
    invite_code: str,
    username: str,
    display_name: str = "",
    password: str = "",
    request_ip: str = "",
    user_agent: str = "",
) -> tuple[dict[str, Any], str, str]:
    normalized_invite_code = normalize_invite_code(invite_code)
    if not normalized_invite_code:
        raise ActivationError("请输入邀请码")
    normalized_username = normalize_username(username)
    if not normalized_username:
        raise ActivationError("用户名不能为空")
    normalized_display_name = str(display_name or "").strip() or normalized_username
    provided_password = str(password or "").strip()
    if len(provided_password) < 8:
        raise ActivationError("密码至少需要 8 个字符")

    now = utc_now()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        invite_row = conn.execute("select * from invite_codes where invite_code = ?", (normalized_invite_code,)).fetchone()
        if not invite_row:
            raise ActivationError("邀请码不存在", 404)
        if str(invite_row["status"] or INVITE_CODE_STATUS_ACTIVE) == INVITE_CODE_STATUS_DISABLED:
            raise ActivationError("邀请码已停用", 403)
        if str(invite_row["expires_at"] or "") and str(invite_row["expires_at"]) < now:
            conn.execute(
                "update invite_codes set status = ?, updated_at = ? where id = ?",
                (INVITE_CODE_STATUS_EXPIRED, now, int(invite_row["id"])),
            )
            conn.commit()
            raise ActivationError("邀请码已过期", 403)
        max_uses = max(1, int(invite_row["max_uses"] or 1))
        used_count = max(0, int(invite_row["used_count"] or 0))
        if used_count >= max_uses:
            conn.execute(
                "update invite_codes set status = ?, updated_at = ? where id = ?",
                (INVITE_CODE_STATUS_USED, now, int(invite_row["id"])),
            )
            conn.commit()
            raise ActivationError("邀请码已使用", 403)
        account, _ = _create_account_record_on_connection(
            conn,
            username=normalized_username,
            display_name=normalized_display_name,
            password=provided_password,
            role=ACCOUNT_ROLE_MERCHANT,
            status=ACCOUNT_STATUS_ACTIVE,
            note=f"invite:{normalized_invite_code}",
            created_by=int(invite_row["created_by"] or 0),
        )
        account_id = int(account.get("accountId") or 0)
        if account_id <= 0:
            raise ActivationError("创建账号失败", 500)
        next_used_count = used_count + 1
        next_status = INVITE_CODE_STATUS_USED if next_used_count >= max_uses else INVITE_CODE_STATUS_ACTIVE
        conn.execute(
            """
            update invite_codes
            set used_count = ?,
                status = ?,
                last_used_at = ?,
                last_used_ip = ?,
                last_used_username = ?,
                last_used_account_id = ?,
                updated_at = ?
            where id = ?
            """,
            (
                next_used_count,
                next_status,
                now,
                request_ip[:80],
                normalized_username[:80],
                account_id,
                now,
                int(invite_row["id"]),
            ),
        )
        conn.commit()

    add_audit_log(
        action="accounts.register",
        target_type="account",
        target_id=normalized_username,
        before={},
        after=account,
        actor=f"invite:{normalized_invite_code[-8:]}",
        request_ip=request_ip,
        backup_path="",
    )
    return account, normalized_invite_code, ""


def create_account_record(
    *,
    username: str,
    display_name: str = "",
    password: str = "",
    role: str = ACCOUNT_ROLE_MERCHANT,
    status: str = ACCOUNT_STATUS_ACTIVE,
    note: str = "",
    created_by: int = 0,
) -> tuple[dict[str, Any], str]:
    with connect() as conn:
        account, temp_password = _create_account_record_on_connection(
            conn,
            username=username,
            display_name=display_name,
            password=password,
            role=role,
            status=status,
            note=note,
            created_by=created_by,
        )
        conn.commit()
    return account, temp_password


def update_account_record(
    *,
    account_id: int,
    display_name: str | None = None,
    role: str | None = None,
    status: str | None = None,
    password: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    with connect() as conn:
        existing = conn.execute("select * from accounts where id = ?", (int(account_id),)).fetchone()
        if not existing:
            return None
        new_display_name = str(display_name).strip() if display_name is not None else str(existing["display_name"] or "")
        new_role = normalize_account_role(role) if role is not None else str(existing["role"] or ACCOUNT_ROLE_MERCHANT)
        new_status = normalize_account_status(status) if status is not None else str(existing["status"] or ACCOUNT_STATUS_ACTIVE)
        new_note = str(note).strip() if note is not None else str(existing["note"] or "")
        new_password_hash = str(existing["password_hash"] or "")
        if password is not None and str(password).strip():
            clear_password = str(password).strip()
            if len(clear_password) < 8:
                raise ActivationError("密码至少需要 8 个字符")
            new_password_hash = password_hash(clear_password)
        conn.execute(
            """
            update accounts
            set display_name = ?,
                password_hash = ?,
                role = ?,
                status = ?,
                note = ?,
                updated_at = ?
            where id = ?
            """,
            (
                new_display_name or str(existing["username"] or ""),
                new_password_hash,
                new_role,
                new_status,
                new_note[:500],
                utc_now(),
                int(account_id),
            ),
        )
        conn.commit()
    return account_summary_row(int(account_id))


def admin_context_from_row(row: sqlite3.Row, *, auth_type: str, token: str = "") -> dict[str, Any]:
    display_name = str(row["display_name"] or "").strip() or str(row["username"] or "admin")
    account_id = int(row["id"])
    role = str(row["role"] or ACCOUNT_ROLE_MERCHANT)
    return {
        "authType": auth_type,
        "accountId": account_id,
        "username": str(row["username"] or ""),
        "displayName": display_name,
        "role": role,
        "status": str(row["status"] or ACCOUNT_STATUS_ACTIVE),
        "actor": f"{str(row['username'] or 'admin')}#{account_id}",
        "sessionToken": token,
    }


def load_admin_context_from_session(token: str) -> dict[str, Any] | None:
    session_token = str(token or "").strip()
    if not session_token:
        return None
    session_hash = admin_session_token_hash(session_token)
    now = utc_now()
    with connect() as conn:
        row = conn.execute(
            """
            select s.session_hash, s.account_id, s.created_at, s.updated_at, s.expires_at,
                   s.revoked_at, s.request_ip, s.user_agent,
                   a.id, a.username, a.display_name, a.password_hash, a.role, a.status, a.note,
                   a.created_at, a.updated_at, a.last_login_at, a.last_login_ip
            from admin_sessions s
            join accounts a on a.id = s.account_id
            where s.session_hash = ?
            """,
            (session_hash,),
        ).fetchone()
        if not row:
            return None
        if row["revoked_at"] or row["expires_at"] < now or row["status"] != ACCOUNT_STATUS_ACTIVE:
            return None
        conn.execute(
            "update admin_sessions set updated_at = ? where session_hash = ?",
            (now, session_hash),
        )
        conn.commit()
    return admin_context_from_row(row, auth_type="session", token=session_token)


def load_legacy_admin_context(token: str) -> dict[str, Any] | None:
    expected = load_admin_token()
    provided = str(token or "").strip()
    if not expected or not provided:
        return None
    if not secrets.compare_digest(provided, expected):
        return None
    digest = hashlib.sha256(provided.encode("utf-8")).hexdigest()[:10]
    return {
        "authType": "legacy",
        "accountId": 0,
        "username": "legacy-admin",
        "displayName": "Legacy Admin",
        "role": ACCOUNT_ROLE_SUPER_ADMIN,
        "status": ACCOUNT_STATUS_ACTIVE,
        "actor": f"legacy:{digest}",
        "sessionToken": provided,
    }


def create_admin_session(account_id: int, *, request_ip: str = "", user_agent: str = "") -> tuple[str, str]:
    raw_token = generate_admin_session_token()
    session_hash = admin_session_token_hash(raw_token)
    now = utc_now()
    expires_at = add_days_iso(ADMIN_SESSION_TTL_DAYS)
    with connect() as conn:
        conn.execute(
            """
            insert into admin_sessions (
                session_hash, account_id, created_at, updated_at, expires_at,
                revoked_at, request_ip, user_agent
            )
            values (?, ?, ?, ?, ?, '', ?, ?)
            """,
            (session_hash, int(account_id), now, now, expires_at, request_ip[:80], user_agent[:240]),
        )
        conn.commit()
    return raw_token, expires_at


def revoke_admin_session(token: str) -> bool:
    session_token = str(token or "").strip()
    if not session_token:
        return False
    session_hash = admin_session_token_hash(session_token)
    with connect() as conn:
        result = conn.execute(
            "update admin_sessions set revoked_at = ?, updated_at = ? where session_hash = ? and revoked_at = ''",
            (utc_now(), utc_now(), session_hash),
        )
        conn.commit()
    return result.rowcount > 0


def count_accounts() -> int:
    with connect() as conn:
        return int(conn.execute("select count(*) from accounts").fetchone()[0] or 0)


def count_active_super_admins() -> int:
    with connect() as conn:
        return int(
            conn.execute(
                "select count(*) from accounts where role = ? and status = ?",
                (ACCOUNT_ROLE_SUPER_ADMIN, ACCOUNT_STATUS_ACTIVE),
            ).fetchone()[0]
            or 0
        )


def auth_status_snapshot() -> dict[str, Any]:
    accounts = count_accounts()
    invites = count_invites()
    active_invites = count_invites(active_only=True)
    return {
        "hasAccounts": accounts > 0,
        "accountCount": accounts,
        "inviteCount": invites,
        "activeInviteCount": active_invites,
        "registrationMode": "invite",
        "inviteRegistrationEnabled": True,
        "bootstrapAvailable": bool(load_admin_token()) and accounts == 0,
        "sessionTtlDays": ADMIN_SESSION_TTL_DAYS,
    }


def public_key_b64() -> str:
    public = load_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public).decode("ascii")


def normalize_code_hashes(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ActivationError("批量更新需要授权码列表")
    if len(value) > MAX_BULK_CODE_HASHES:
        raise ActivationError(f"批量更新一次最多支持 {MAX_BULK_CODE_HASHES} 个授权码", 400)
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        item_hash = str(item or "").strip().lower()
        if not item_hash:
            continue
        if len(item_hash) != 64 or any(ch not in "0123456789abcdef" for ch in item_hash):
            raise ActivationError("授权码哈希格式不正确", 400)
        if item_hash not in seen:
            seen.add(item_hash)
            normalized.append(item_hash)
    return normalized


def rate_limit_storage_key(scope: str, key: str) -> str:
    return f"{scope}:{key.strip().lower()[:160]}"


def rate_limit_check(scope: str, key: str) -> None:
    now = time.time()
    storage_key = rate_limit_storage_key(scope, key)
    with RATE_LIMIT_LOCK:
        entry = RATE_LIMITS.get(storage_key)
        if not entry:
            return
        locked_until = float(entry.get("locked_until") or 0)
        if locked_until > now:
            raise ActivationError("请求过于频繁，请稍后再试", 429)
        window_start = float(entry.get("window_start") or 0)
        window_seconds = float(entry.get("window_seconds") or 0)
        if window_seconds and now - window_start > window_seconds:
            RATE_LIMITS.pop(storage_key, None)


def rate_limit_record_failure(scope: str, key: str, *, limit: int, window_seconds: int, lockout_seconds: int) -> None:
    now = time.time()
    storage_key = rate_limit_storage_key(scope, key)
    with RATE_LIMIT_LOCK:
        entry = RATE_LIMITS.get(storage_key)
        if not entry or now - float(entry.get("window_start") or 0) > window_seconds:
            entry = {"window_start": now, "count": 0, "locked_until": 0, "window_seconds": window_seconds}
        entry["count"] = int(entry.get("count") or 0) + 1
        if int(entry["count"]) >= limit:
            entry["locked_until"] = now + lockout_seconds
        RATE_LIMITS[storage_key] = entry


def rate_limit_clear(scope: str, key: str) -> None:
    with RATE_LIMIT_LOCK:
        RATE_LIMITS.pop(rate_limit_storage_key(scope, key), None)


def rate_limit_consume(scope: str, key: str, *, limit: int, window_seconds: int, lockout_seconds: int) -> None:
    rate_limit_check(scope, key)
    now = time.time()
    storage_key = rate_limit_storage_key(scope, key)
    with RATE_LIMIT_LOCK:
        entry = RATE_LIMITS.get(storage_key)
        if not entry or now - float(entry.get("window_start") or 0) > window_seconds:
            entry = {"window_start": now, "count": 0, "locked_until": 0, "window_seconds": window_seconds}
        count = int(entry.get("count") or 0)
        if count >= limit:
            entry["locked_until"] = now + lockout_seconds
            RATE_LIMITS[storage_key] = entry
            raise ActivationError("请求过于频繁，请稍后再试", 429)
        entry["count"] = count + 1
        if int(entry["count"]) >= limit:
            entry["locked_until"] = now + lockout_seconds
        RATE_LIMITS[storage_key] = entry


def admin_cors_origin_allowed(origin: str) -> bool:
    normalized = origin.strip().rstrip("/")
    if not normalized:
        return False
    if normalized in ADMIN_CORS_ALLOWED_ORIGINS:
        return True
    parsed = urlparse(normalized)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}


def is_admin_request_path(path: str) -> bool:
    return urlparse(path).path.startswith("/admin")


def sign_license(payload: dict[str, Any]) -> dict[str, Any]:
    private_key = load_private_key()
    signature = private_key.sign(canonical(payload))
    license_data = dict(payload)
    license_data["signature"] = base64.b64encode(signature).decode("ascii")
    return license_data


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if name not in columns:
        conn.execute(f"alter table {table} add column {name} {definition}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists codes (
            code_hash text primary key,
            code_label text not null,
            full_code text not null default '',
            licensee text not null,
            edition text not null,
            features_json text not null,
            expires text not null,
            max_activations integer not null default 1,
            disabled integer not null default 0,
            member_mode integer not null default 0,
            plan text not null default '',
            gateway_base_url text not null default '',
            gateway_image_base_url text not null default '',
            gateway_video_base_url text not null default '',
            gateway_token text not null default '',
            gateway_image_token text not null default '',
            gateway_video_token text not null default '',
            gateway_default_model text not null default '',
            gateway_image_model text not null default '',
            gateway_video_model text not null default '',
            gateway_models_json text not null default '[]',
            quotas_json text not null default '{}',
            created_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists activations (
            id integer primary key autoincrement,
            code_hash text not null,
            install_id text not null,
            device_id text not null,
            license_json text not null,
            activated_at text not null,
            unique(code_hash, install_id)
        )
        """
    )
    conn.execute(
        """
        create table if not exists accounts (
            id integer primary key autoincrement,
            username text not null unique,
            display_name text not null default '',
            password_hash text not null,
            role text not null default 'merchant',
            status text not null default 'active',
            note text not null default '',
            created_by integer not null default 0,
            created_at text not null,
            updated_at text not null,
            last_login_at text not null default '',
            last_login_ip text not null default ''
        )
        """
    )
    conn.execute(
        """
        create table if not exists admin_sessions (
            session_hash text primary key,
            account_id integer not null,
            created_at text not null,
            updated_at text not null,
            expires_at text not null,
            revoked_at text not null default '',
            request_ip text not null default '',
            user_agent text not null default ''
        )
        """
    )
    conn.execute(
        """
        create table if not exists invite_codes (
            id integer primary key autoincrement,
            invite_code text not null unique,
            role text not null default 'merchant',
            status text not null default 'active',
            max_uses integer not null default 1,
            used_count integer not null default 0,
            note text not null default '',
            created_by integer not null default 0,
            created_at text not null,
            updated_at text not null,
            expires_at text not null default '',
            last_used_at text not null default '',
            last_used_ip text not null default '',
            last_used_username text not null default '',
            last_used_account_id integer not null default 0
        )
        """
    )
    conn.execute(
        """
        create table if not exists audit_logs (
            id integer primary key autoincrement,
            actor text not null default '',
            action text not null,
            target_type text not null default '',
            target_id text not null default '',
            before_json text not null default '{}',
            after_json text not null default '{}',
            request_ip text not null default '',
            backup_path text not null default '',
            created_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists plans (
            plan_key text primary key,
            display_name text not null,
            duration_days integer not null default 31,
            features_json text not null default '[]',
            gateway_base_url text not null default '',
            gateway_image_base_url text not null default '',
            gateway_video_base_url text not null default '',
            gateway_token text not null default '',
            gateway_image_token text not null default '',
            gateway_video_token text not null default '',
            gateway_default_model text not null default '',
            gateway_image_model text not null default '',
            gateway_video_model text not null default '',
            gateway_models_json text not null default '[]',
            quotas_json text not null default '{}',
            disabled integer not null default 0,
            created_at text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists settings (
            key text primary key,
            value_json text not null default '{}',
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists beta_claims (
            id integer primary key autoincrement,
            day text not null,
            ip text not null,
            full_code text not null,
            expires text not null,
            created_at text not null,
            unique(day, ip)
        )
        """
    )
    conn.execute(
        """
        create table if not exists prompt_templates (
            id integer primary key autoincrement,
            kind text not null,
            title text not null,
            prompt text not null,
            params_json text not null default '{}',
            cover_url text not null default '',
            tags text not null default '',
            sort integer not null default 0,
            enabled integer not null default 1,
            created_at text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists account_gateway_settings (
            account_id integer primary key,
            gateway_base_url text not null default '',
            gateway_image_base_url text not null default '',
            gateway_video_base_url text not null default '',
            gateway_token text not null default '',
            gateway_image_token text not null default '',
            gateway_video_token text not null default '',
            gateway_default_model text not null default '',
            gateway_image_model text not null default '',
            gateway_video_model text not null default '',
            gateway_models_json text not null default '[]',
            created_at text not null,
            updated_at text not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists publish_relay_packets (
            seq integer primary key autoincrement,
            packet_id text not null unique,
            channel_id text not null,
            packet_json text not null,
            status text not null default 'pending',
            attempts integer not null default 0,
            created_at text not null,
            updated_at text not null,
            leased_by text not null default '',
            lease_id text not null default '',
            lease_until_ms integer not null default 0,
            next_available_at_ms integer not null default 0,
            completed_at text not null default '',
            result_json text not null default '',
            last_error text not null default ''
        )
        """
    )
    conn.execute(
        "create index if not exists idx_publish_relay_channel_status on publish_relay_packets (channel_id, status, seq)"
    )
    ensure_column(conn, "codes", "owner_account_id", "integer not null default 0")
    ensure_column(conn, "codes", "full_code", "text not null default ''")
    ensure_column(conn, "codes", "member_mode", "integer not null default 0")
    ensure_column(conn, "codes", "plan", "text not null default ''")
    ensure_column(conn, "codes", "gateway_base_url", "text not null default ''")
    ensure_column(conn, "codes", "gateway_image_base_url", "text not null default ''")
    ensure_column(conn, "codes", "gateway_video_base_url", "text not null default ''")
    ensure_column(conn, "codes", "gateway_token", "text not null default ''")
    ensure_column(conn, "codes", "gateway_image_token", "text not null default ''")
    ensure_column(conn, "codes", "gateway_video_token", "text not null default ''")
    ensure_column(conn, "codes", "gateway_default_model", "text not null default ''")
    ensure_column(conn, "codes", "gateway_image_model", "text not null default ''")
    ensure_column(conn, "codes", "gateway_video_model", "text not null default ''")
    ensure_column(conn, "codes", "gateway_models_json", "text not null default '[]'")
    ensure_column(conn, "codes", "quotas_json", "text not null default '{}'")
    ensure_column(conn, "plans", "gateway_base_url", "text not null default ''")
    ensure_column(conn, "plans", "gateway_image_base_url", "text not null default ''")
    ensure_column(conn, "plans", "gateway_video_base_url", "text not null default ''")
    ensure_column(conn, "plans", "gateway_token", "text not null default ''")
    ensure_column(conn, "plans", "gateway_image_token", "text not null default ''")
    ensure_column(conn, "plans", "gateway_video_token", "text not null default ''")
    ensure_column(conn, "plans", "gateway_default_model", "text not null default ''")
    ensure_column(conn, "plans", "gateway_image_model", "text not null default ''")
    ensure_column(conn, "plans", "gateway_video_model", "text not null default ''")
    ensure_column(conn, "plans", "gateway_models_json", "text not null default '[]'")
    ensure_column(conn, "plans", "quotas_json", "text not null default '{}'")
    seed_default_settings(conn)
    seed_default_plans(conn)
    conn.commit()


def seed_default_settings(conn: sqlite3.Connection) -> None:
    row = conn.execute("select 1 from settings where key = ?", ("public",)).fetchone()
    if row:
        return
    conn.execute(
        "insert into settings (key, value_json, updated_at) values (?, ?, ?)",
        ("public", json.dumps(DEFAULT_PUBLIC_SETTINGS, ensure_ascii=False, sort_keys=True), utc_now()),
    )


def seed_default_plans(conn: sqlite3.Connection) -> None:
    existing = conn.execute("select count(*) from plans").fetchone()[0]
    if existing:
        for plan_key in ("monthly", "quarterly", "yearly", "vip_monthly"):
            row = conn.execute(
                "select features_json from plans where plan_key = ?",
                (plan_key,),
            ).fetchone()
            if not row:
                continue
            try:
                current = json.loads(row["features_json"])
            except (TypeError, json.JSONDecodeError):
                current = []
            if not isinstance(current, list):
                current = []
            merged = list(dict.fromkeys([*(str(item) for item in current if str(item)), *COMMERCIAL_FEATURES]))
            if merged != current:
                conn.execute(
                    "update plans set features_json = ?, updated_at = ? where plan_key = ?",
                    (json.dumps(merged, ensure_ascii=False), utc_now(), plan_key),
                )
        return
    now = utc_now()
    defaults = [
        ("monthly", "月卡", 31, DEFAULT_FEATURES, {"image": 100, "video": 20}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
        ("quarterly", "季卡", 93, DEFAULT_FEATURES, {"image": 300, "video": 60}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
        ("yearly", "年卡", 366, DEFAULT_FEATURES, {"image": 1200, "video": 240}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
        ("vip_monthly", "VIP 月卡", 31, VIP_DEFAULT_FEATURES, {"image": 300, "video": 80, "phoneAgent": True, "desktopAgent": True}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
    ]
    for plan_key, display_name, duration_days, features, quotas, gateway_image_model, gateway_video_model in defaults:
        conn.execute(
            """
            insert into plans (
                plan_key, display_name, duration_days, features_json, gateway_base_url,
                gateway_image_base_url, gateway_video_base_url,
                gateway_token, gateway_image_token, gateway_video_token,
                gateway_default_model, gateway_image_model, gateway_video_model,
                gateway_models_json, quotas_json,
                disabled, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                plan_key,
                display_name,
                duration_days,
                json.dumps(features, ensure_ascii=False),
                DEFAULT_GATEWAY_BASE_URL,
                DEFAULT_GATEWAY_IMAGE_BASE_URL,
                DEFAULT_GATEWAY_VIDEO_BASE_URL,
                DEFAULT_GATEWAY_TOKEN,
                DEFAULT_GATEWAY_IMAGE_TOKEN,
                DEFAULT_GATEWAY_VIDEO_TOKEN,
                DEFAULT_GATEWAY_DEFAULT_MODEL,
                gateway_image_model,
                gateway_video_model,
                json.dumps(DEFAULT_GATEWAY_MODELS, ensure_ascii=False),
                json.dumps(quotas, ensure_ascii=False),
                now,
                now,
            ),
        )


def clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(maximum, max(minimum, parsed))


def normalize_string(value: Any) -> str:
    return str(value or "").strip()


def publish_relay_backoff_ms(attempts: int) -> int:
    factor = max(1, 2 ** max(0, attempts - 1))
    return min(PUBLISH_RELAY_MAX_BACKOFF_MS, PUBLISH_RELAY_BACKOFF_MS * factor)


def publish_relay_packet_id() -> str:
    return f"relay_{secrets.token_hex(6)}"


def publish_relay_lease_id() -> str:
    return f"lease_{secrets.token_hex(6)}"


def publish_relay_auth_required() -> bool:
    return True


def publish_relay_configured() -> bool:
    return bool(PUBLISH_RELAY_TOKEN)


def publish_relay_request_token(headers: Any) -> str:
    direct = normalize_string(headers.get("X-OpenClaw-Relay-Token", ""))
    if direct:
        return direct
    auth = normalize_string(headers.get("Authorization", ""))
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def publish_relay_token_valid(headers: Any) -> bool:
    if not PUBLISH_RELAY_TOKEN:
        return False
    provided = publish_relay_request_token(headers)
    return bool(provided) and secrets.compare_digest(provided, PUBLISH_RELAY_TOKEN)


def publish_relay_record_from_row(row: sqlite3.Row, include_packet: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row["packet_id"],
        "channelId": row["channel_id"],
        "status": row["status"],
        "attempts": row["attempts"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "leasedBy": row["leased_by"],
        "leaseId": row["lease_id"],
        "leaseUntil": row["lease_until_ms"] or None,
        "nextAvailableAt": row["next_available_at_ms"] or None,
        "completedAt": row["completed_at"] or None,
        "lastError": row["last_error"] or "",
    }
    if include_packet:
        try:
            payload["packet"] = json.loads(row["packet_json"] or "{}")
        except json.JSONDecodeError as error:
            LOGGER.warning("Invalid publish relay packet JSON for %s: %s", row["packet_id"], error)
            payload["packet"] = {}
    if row["result_json"]:
        try:
            payload["result"] = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError as error:
            LOGGER.warning("Invalid publish relay result JSON for %s: %s", row["packet_id"], error)
            payload["result"] = row["result_json"]
    return payload


def publish_relay_fetch(conn: sqlite3.Connection, packet_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "select * from publish_relay_packets where packet_id = ?",
        (packet_id,),
    ).fetchone()


def publish_relay_enqueue(packet: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ActivationError("Invalid JSON body", 400)
    channel_id = normalize_string(packet.get("channelId") or packet.get("channel_id"))
    if not channel_id:
        raise ActivationError("Missing required field: channelId", 400)
    schema = normalize_string(packet.get("schema"))
    if schema not in {"openclaw.publish.packet.v1", "openclaw.phone.screenshot.v1"}:
        raise ActivationError("Unsupported packet schema", 400)

    packet_id = publish_relay_packet_id()
    timestamp = utc_now()
    with connect() as conn:
        conn.execute(
            """
            insert into publish_relay_packets (
                packet_id, channel_id, packet_json, status, attempts,
                created_at, updated_at, leased_by, lease_id, lease_until_ms,
                next_available_at_ms, completed_at, result_json, last_error
            )
            values (?, ?, ?, 'pending', 0, ?, ?, '', '', 0, 0, '', '', '')
            """,
            (packet_id, channel_id, json.dumps(packet, ensure_ascii=False), timestamp, timestamp),
        )
        conn.commit()
        row = publish_relay_fetch(conn, packet_id)
        assert row is not None
        return publish_relay_record_from_row(row, include_packet=True)


def publish_relay_claim(channel_id: str, client_id: str, lease_ms: int) -> dict[str, Any] | None:
    channel_id = normalize_string(channel_id)
    client_id = normalize_string(client_id) or "default-client"
    lease_ms = clamp_int(lease_ms, 1_000, 15 * 60_000, PUBLISH_RELAY_DEFAULT_LEASE_MS)
    if not channel_id:
        raise ActivationError("Missing channelId", 400)

    current_ms = now_ms()
    with connect() as conn:
        rows = conn.execute(
            """
            select * from publish_relay_packets
            where channel_id = ? and status not in ('done', 'failed')
            order by seq asc
            """,
            (channel_id,),
        ).fetchall()
        for row in rows:
            if row["status"] == "leased" and int(row["lease_until_ms"] or 0) > current_ms:
                continue
            if int(row["next_available_at_ms"] or 0) > current_ms:
                continue
            if int(row["attempts"] or 0) >= PUBLISH_RELAY_MAX_ATTEMPTS:
                conn.execute(
                    """
                    update publish_relay_packets
                    set status = 'failed', updated_at = ?, completed_at = ?,
                        last_error = case when last_error = '' then 'Max retry attempts reached' else last_error end
                    where packet_id = ?
                    """,
                    (utc_now(), utc_now(), row["packet_id"]),
                )
                conn.commit()
                continue

            lease_id = publish_relay_lease_id()
            conn.execute(
                """
                update publish_relay_packets
                set status = 'leased', attempts = attempts + 1, leased_by = ?,
                    lease_id = ?, lease_until_ms = ?, updated_at = ?
                where packet_id = ?
                """,
                (client_id, lease_id, current_ms + lease_ms, utc_now(), row["packet_id"]),
            )
            conn.commit()
            claimed = publish_relay_fetch(conn, row["packet_id"])
            assert claimed is not None
            return publish_relay_record_from_row(claimed, include_packet=True)
    return None


def publish_relay_wait_for_packet(channel_id: str, client_id: str, lease_ms: int, wait_ms: int) -> dict[str, Any] | None:
    wait_ms = clamp_int(wait_ms, 0, 15 * 60_000, PUBLISH_RELAY_DEFAULT_WAIT_MS)
    deadline = now_ms() + wait_ms
    while True:
        claimed = publish_relay_claim(channel_id, client_id, lease_ms)
        if claimed:
            return claimed
        if wait_ms <= 0 or now_ms() >= deadline:
            return None
        time.sleep(min(0.5, max(0.25, (deadline - now_ms()) / 1000.0)))


def publish_relay_complete(body: dict[str, Any]) -> dict[str, Any]:
    packet_id = normalize_string(body.get("packetId") or body.get("id"))
    lease_id = normalize_string(body.get("leaseId") or body.get("lease_id"))
    client_id = normalize_string(body.get("clientId") or body.get("client_id"))
    success = bool(body.get("success"))
    if not packet_id:
        raise ActivationError("Missing packetId", 400)

    with connect() as conn:
        row = publish_relay_fetch(conn, packet_id)
        if row is None:
            raise ActivationError(f"Packet not found: {packet_id}", 404)
        if lease_id and row["lease_id"] and lease_id != row["lease_id"]:
            raise ActivationError("Lease id mismatch", 409)
        if client_id and row["leased_by"] and client_id != row["leased_by"]:
            raise ActivationError("Client id mismatch", 409)

        result = body.get("result", body.get("response"))
        result_json = json.dumps(result, ensure_ascii=False) if result is not None else ""
        error = "" if success else normalize_string(body.get("error") or body.get("message"))
        current_ms = now_ms()
        timestamp = utc_now()
        if success:
            conn.execute(
                """
                update publish_relay_packets
                set status = 'done', updated_at = ?, completed_at = ?,
                    lease_id = '', leased_by = '', lease_until_ms = 0,
                    next_available_at_ms = 0, result_json = ?, last_error = ''
                where packet_id = ?
                """,
                (timestamp, timestamp, result_json, packet_id),
            )
        else:
            attempts = int(row["attempts"] or 0)
            retryable = attempts < PUBLISH_RELAY_MAX_ATTEMPTS
            conn.execute(
                """
                update publish_relay_packets
                set status = ?, updated_at = ?, completed_at = ?,
                    lease_id = '', leased_by = '', lease_until_ms = 0,
                    next_available_at_ms = ?, result_json = ?, last_error = ?
                where packet_id = ?
                """,
                (
                    "pending" if retryable else "failed",
                    timestamp,
                    "" if retryable else timestamp,
                    current_ms + publish_relay_backoff_ms(attempts) if retryable else 0,
                    result_json,
                    error,
                    packet_id,
                ),
            )
        conn.commit()
        updated = publish_relay_fetch(conn, packet_id)
        assert updated is not None
        return publish_relay_record_from_row(updated)


def publish_relay_status(packet_id: str, include_packet: bool = True) -> dict[str, Any]:
    packet_id = normalize_string(packet_id)
    if not packet_id:
        raise ActivationError("Missing packetId", 400)
    with connect() as conn:
        row = publish_relay_fetch(conn, packet_id)
        if row is None:
            raise ActivationError(f"Packet not found: {packet_id}", 404)
        return publish_relay_record_from_row(row, include_packet=include_packet)


def publish_relay_stats(channel_id: str = "") -> dict[str, Any]:
    channel_id = normalize_string(channel_id)
    current_ms = now_ms()
    params: tuple[Any, ...] = ()
    where = ""
    if channel_id:
        where = "where channel_id = ?"
        params = (channel_id,)
    with connect() as conn:
        rows = conn.execute(f"select status, lease_until_ms, next_available_at_ms from publish_relay_packets {where}", params).fetchall()
    pending = 0
    leased = 0
    done = 0
    failed = 0
    for row in rows:
        status = row["status"]
        if status == "done":
            done += 1
        elif status == "failed":
            failed += 1
        elif status == "leased" and int(row["lease_until_ms"] or 0) > current_ms:
            leased += 1
        elif int(row["next_available_at_ms"] or 0) <= current_ms:
            pending += 1
    return {
        "channelId": channel_id or None,
        "total": len(rows),
        "pending": pending,
        "leased": leased,
        "done": done,
        "failed": failed,
    }


def make_code(edition: str = "PRO") -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    chunks = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return f"OC-{edition.upper()}-" + "-".join(chunks)


def parse_features(raw: str) -> list[str]:
    features = [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    return features or DEFAULT_FEATURES


def parse_models(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return list(DEFAULT_GATEWAY_MODELS)
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except json.JSONDecodeError:
            pass
    return [item.strip() for item in text.replace("，", ",").split(",") if item.strip()]


def parse_json_object(raw: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = str(raw or "").strip()
    if not text:
        return dict(default or {})
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return dict(default or {})
    return data if isinstance(data, dict) else dict(default or {})


def is_super_admin_context(context: dict[str, Any] | None) -> bool:
    return bool(context) and str(context.get("role") or "").strip() == ACCOUNT_ROLE_SUPER_ADMIN


def context_account_id(context: dict[str, Any] | None) -> int:
    if not context:
        return 0
    try:
        return int(context.get("accountId") or 0)
    except (TypeError, ValueError):
        return 0


def code_row_owned_by_context(row: sqlite3.Row, context: dict[str, Any] | None) -> bool:
    if not context or is_super_admin_context(context):
        return True
    return int(row["owner_account_id"] or 0) == context_account_id(context)


def create_code_records(
    *,
    count: int,
    licensee: str,
    edition: str,
    features: list[str],
    expires: str,
    max_activations: int,
    member_mode: bool = False,
    plan: str = "",
    gateway_base_url: str = "",
    gateway_image_base_url: str = "",
    gateway_video_base_url: str = "",
    gateway_token: str = "",
    gateway_image_token: str = "",
    gateway_video_token: str = "",
    gateway_default_model: str = "",
    gateway_image_model: str = "",
    gateway_video_model: str = "",
    gateway_models: list[str] | None = None,
    quotas: dict[str, Any] | None = None,
    owner_account_id: int = 0,
) -> list[str]:
    count = max(1, min(int(count), 100))
    max_activations = max(1, min(int(max_activations), 20))
    expires = normalize_code_expires(expires)
    codes: list[str] = []
    with connect() as conn:
        for _ in range(count):
            code = make_code(edition)
            conn.execute(
                """
                insert into codes (
                    code_hash, code_label, full_code, licensee, edition, features_json, expires,
                    max_activations, disabled, member_mode, plan, gateway_base_url, gateway_token,
                    gateway_image_base_url, gateway_video_base_url,
                    gateway_image_token, gateway_video_token,
                    gateway_default_model, gateway_image_model, gateway_video_model,
                    gateway_models_json, quotas_json, owner_account_id, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code_hash(code),
                    code[-9:],
                    code,
                    licensee,
                    edition,
                    json.dumps(features, ensure_ascii=False),
                    expires,
                    max_activations,
                    1 if member_mode else 0,
                    plan.strip(),
                    gateway_base_url.strip().rstrip("/"),
                    gateway_token.strip(),
                    gateway_image_base_url.strip().rstrip("/"),
                    gateway_video_base_url.strip().rstrip("/"),
                    gateway_image_token.strip(),
                    gateway_video_token.strip(),
                    gateway_default_model.strip(),
                    gateway_image_model.strip(),
                    gateway_video_model.strip(),
                    json.dumps(gateway_models or [], ensure_ascii=False),
                    json.dumps(quotas or {}, ensure_ascii=False),
                    int(owner_account_id or 0),
                    utc_now(),
                ),
            )
            codes.append(code)
        conn.commit()
    return codes


# --- Daily beta-code claim (public, IP-limited, admin-configurable) ----------
BETA_CONFIG_KEY = "beta_claim"
BETA_DEFAULTS = {"enabled": True, "dailyQuota": 10, "validDays": 7, "edition": "trial", "licensee": "内测用户", "planTemplate": ""}


def beta_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_beta_config() -> dict[str, Any]:
    cfg = dict(BETA_DEFAULTS)
    with connect() as conn:
        row = conn.execute("select value_json from settings where key = ?", (BETA_CONFIG_KEY,)).fetchone()
    if row:
        try:
            cfg.update(json.loads(row["value_json"]) or {})
        except Exception:
            pass
    cfg["enabled"] = bool(cfg.get("enabled", True))
    cfg["dailyQuota"] = max(0, int(cfg.get("dailyQuota", 10)))
    cfg["validDays"] = max(1, int(cfg.get("validDays", 7)))
    return cfg


def set_beta_config(patch: dict[str, Any]) -> dict[str, Any]:
    cfg = get_beta_config()
    if "enabled" in patch:
        cfg["enabled"] = bool(patch["enabled"])
    if "dailyQuota" in patch:
        cfg["dailyQuota"] = max(0, min(int(patch["dailyQuota"]), 100000))
    if "validDays" in patch:
        cfg["validDays"] = max(1, min(int(patch["validDays"]), 3650))
    if "planTemplate" in patch:
        raw_tpl = str(patch.get("planTemplate") or "").strip()
        cfg["planTemplate"] = normalize_plan_key(raw_tpl) if raw_tpl else ""
    with connect() as conn:
        conn.execute(
            "insert into settings (key, value_json, updated_at) values (?, ?, ?) "
            "on conflict(key) do update set value_json = excluded.value_json, updated_at = excluded.updated_at",
            (BETA_CONFIG_KEY, json.dumps(cfg, ensure_ascii=False), utc_now()),
        )
        conn.commit()
    return cfg


def beta_owner_account_id() -> int:
    with connect() as conn:
        row = conn.execute(
            "select id from accounts where role = ? and status = ? order by id asc limit 1",
            (ACCOUNT_ROLE_SUPER_ADMIN, ACCOUNT_STATUS_ACTIVE),
        ).fetchone()
    return int(row["id"]) if row else 0


def beta_claims_count_today() -> int:
    with connect() as conn:
        row = conn.execute("select count(*) as c from beta_claims where day = ?", (beta_today(),)).fetchone()
    return int(row["c"]) if row else 0


def beta_status_snapshot() -> dict[str, Any]:
    cfg = get_beta_config()
    used = beta_claims_count_today()
    return {
        "enabled": cfg["enabled"],
        "quota": cfg["dailyQuota"],
        "remaining": max(0, cfg["dailyQuota"] - used),
        "validDays": cfg["validDays"],
    }


def beta_claim_code(ip: str) -> dict[str, Any]:
    cfg = get_beta_config()
    if not cfg["enabled"]:
        raise ActivationError("内测码发放暂时关闭，稍后再来", status=403)

    def _existing() -> sqlite3.Row | None:
        with connect() as conn:
            return conn.execute(
                "select full_code, expires from beta_claims where day = ? and ip = ?",
                (beta_today(), ip),
            ).fetchone()

    def _result(code: str, expires: str, repeat: bool) -> dict[str, Any]:
        return {
            "code": code,
            "expires": expires,
            "repeat": repeat,
            "remaining": max(0, cfg["dailyQuota"] - beta_claims_count_today()),
            "validDays": cfg["validDays"],
        }

    row = _existing()
    if row:
        return _result(row["full_code"], row["expires"], True)
    if beta_claims_count_today() >= cfg["dailyQuota"]:
        raise ActivationError("今日内测码已领完，明天再来", status=429)

    owner_id = beta_owner_account_id()
    # 若配置了套餐模板，内测码继承该模板的网关与功能；否则退回账号网关默认值。
    plan_key = str(cfg.get("planTemplate") or "").strip()
    plan_row = get_plan_row(normalize_plan_key(plan_key)) if plan_key else None
    if plan_row is not None and not bool(plan_row["disabled"]):
        gw = {
            "gatewayBaseUrl": plan_row["gateway_base_url"],
            "gatewayImageBaseUrl": plan_row["gateway_image_base_url"],
            "gatewayVideoBaseUrl": plan_row["gateway_video_base_url"],
            "gatewayToken": plan_row["gateway_token"],
            "gatewayImageToken": plan_row["gateway_image_token"],
            "gatewayVideoToken": plan_row["gateway_video_token"],
            "gatewayDefaultModel": plan_row["gateway_default_model"],
            "gatewayImageModel": plan_row["gateway_image_model"],
            "gatewayVideoModel": plan_row["gateway_video_model"],
        }
        features = load_json_value(plan_row["features_json"], DEFAULT_FEATURES) or list(DEFAULT_FEATURES)
    else:
        gw = apply_account_gateway_defaults({}, owner_id, explicit_body={})
        features = list(DEFAULT_FEATURES)
    expires = add_days_date(cfg["validDays"])
    codes = create_code_records(
        count=1,
        licensee=str(cfg.get("licensee") or "内测用户"),
        edition=str(cfg.get("edition") or "trial"),
        features=features,
        expires=expires,
        max_activations=1,
        gateway_base_url=str(gw.get("gatewayBaseUrl") or ""),
        gateway_image_base_url=str(gw.get("gatewayImageBaseUrl") or gw.get("gateway_image_base_url") or ""),
        gateway_video_base_url=str(gw.get("gatewayVideoBaseUrl") or gw.get("gateway_video_base_url") or ""),
        gateway_token=str(gw.get("gatewayToken") or ""),
        gateway_image_token=str(gw.get("gatewayImageToken") or gw.get("gateway_image_token") or ""),
        gateway_video_token=str(gw.get("gatewayVideoToken") or gw.get("gateway_video_token") or ""),
        gateway_default_model=str(gw.get("gatewayDefaultModel") or ""),
        gateway_image_model=str(gw.get("gatewayImageModel") or gw.get("gateway_image_model") or ""),
        gateway_video_model=str(gw.get("gatewayVideoModel") or gw.get("gateway_video_model") or ""),
        # 关键：有网关时必须 member_mode=1，否则激活时网关不会写进签名 license，
        # 客户端就看不到 URL/apikey。
        member_mode=bool(str(gw.get("gatewayBaseUrl") or "").strip()),
        plan=normalize_plan_key(plan_key) if plan_row is not None else "",
        owner_account_id=owner_id,
    )
    code = codes[0]
    try:
        with connect() as conn:
            conn.execute(
                "insert into beta_claims (day, ip, full_code, expires, created_at) values (?, ?, ?, ?, ?)",
                (beta_today(), ip, code, expires, utc_now()),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        # Concurrent claim from the same IP — return whatever landed.
        row = _existing()
        if row:
            return _result(row["full_code"], row["expires"], True)
        raise
    return _result(code, expires, False)


# --- Prompt template library (public read, admin-managed) --------------------
TEMPLATE_KINDS = ("image", "video")
DEFAULT_TEMPLATES = [
    {
        "kind": "image",
        "title": "产品白底图",
        "prompt": "一张高清产品摄影，纯白背景，柔和棚拍光，居中构图，电商主图风格，细节锐利",
        "params": {"size": "1024x1024"},
        "tags": "电商,产品",
        "sort": 10,
    },
    {
        "kind": "image",
        "title": "国风插画",
        "prompt": "中国风工笔插画，青绿山水，留白，细腻线条，雅致配色，高分辨率",
        "params": {"size": "1024x1536"},
        "tags": "插画,国风",
        "sort": 20,
    },
    {
        "kind": "video",
        "title": "城市夜景延时",
        "prompt": "繁华都市夜景，车流光轨，霓虹灯，延时摄影质感，电影级色调，运镜平稳",
        "params": {"mode": "t2v", "resolution": "720P", "ratio": "16:9", "duration": 5},
        "tags": "城市,延时",
        "sort": 10,
    },
]


def template_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "kind": str(row["kind"] or ""),
        "title": str(row["title"] or ""),
        "prompt": str(row["prompt"] or ""),
        "params": load_json_value(row["params_json"], {}) or {},
        "coverUrl": str(row["cover_url"] or ""),
        "tags": [t.strip() for t in str(row["tags"] or "").split(",") if t.strip()],
        "sort": int(row["sort"] or 0),
        "enabled": bool(row["enabled"]),
        "updatedAt": str(row["updated_at"] or ""),
    }


def seed_default_templates() -> None:
    """Populate a few starter templates the first time the table is empty, so the
    client library is never blank out of the box."""
    with connect() as conn:
        existing = conn.execute("select count(*) as c from prompt_templates").fetchone()["c"]
        if existing:
            return
        now = utc_now()
        for tpl in DEFAULT_TEMPLATES:
            conn.execute(
                """
                insert into prompt_templates (kind, title, prompt, params_json, cover_url, tags, sort, enabled, created_at, updated_at)
                values (?, ?, ?, ?, '', ?, ?, 1, ?, ?)
                """,
                (
                    tpl["kind"], tpl["title"], tpl["prompt"],
                    json.dumps(tpl.get("params") or {}, ensure_ascii=False),
                    tpl.get("tags", ""), int(tpl.get("sort", 0)), now, now,
                ),
            )
        conn.commit()


def list_templates(kind: str = "", *, only_enabled: bool = False) -> list[dict[str, Any]]:
    clauses = []
    args: list[Any] = []
    if kind in TEMPLATE_KINDS:
        clauses.append("kind = ?")
        args.append(kind)
    if only_enabled:
        clauses.append("enabled = 1")
    where = (" where " + " and ".join(clauses)) if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"select * from prompt_templates{where} order by kind asc, sort asc, id asc", args
        ).fetchall()
    return [template_public(r) for r in rows]


def save_template(body: dict[str, Any]) -> dict[str, Any]:
    kind = str(body.get("kind", "")).strip().lower()
    if kind not in TEMPLATE_KINDS:
        raise ActivationError("kind 必须是 image 或 video")
    title = str(body.get("title", "")).strip()
    prompt = str(body.get("prompt", "")).strip()
    if not title or not prompt:
        raise ActivationError("标题和提示词不能为空")
    params = body.get("params")
    if isinstance(params, str):
        params = parse_json_object(params)
    if not isinstance(params, dict):
        params = {}
    cover_url = str(body.get("coverUrl", "")).strip()
    tags_value = body.get("tags", "")
    tags = ",".join(t.strip() for t in tags_value if str(t).strip()) if isinstance(tags_value, list) else str(tags_value or "").strip()
    sort = int(body.get("sort", 0) or 0)
    enabled = 1 if body.get("enabled", True) else 0
    now = utc_now()
    template_id = int(body.get("id", 0) or 0)
    with connect() as conn:
        if template_id > 0:
            conn.execute(
                """
                update prompt_templates set kind=?, title=?, prompt=?, params_json=?, cover_url=?, tags=?, sort=?, enabled=?, updated_at=?
                where id=?
                """,
                (kind, title, prompt, json.dumps(params, ensure_ascii=False), cover_url, tags, sort, enabled, now, template_id),
            )
        else:
            cur = conn.execute(
                """
                insert into prompt_templates (kind, title, prompt, params_json, cover_url, tags, sort, enabled, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (kind, title, prompt, json.dumps(params, ensure_ascii=False), cover_url, tags, sort, enabled, now, now),
            )
            template_id = int(cur.lastrowid)
        conn.commit()
        row = conn.execute("select * from prompt_templates where id=?", (template_id,)).fetchone()
    return template_public(row)


def delete_template(template_id: int) -> None:
    with connect() as conn:
        conn.execute("delete from prompt_templates where id=?", (int(template_id),))
        conn.commit()


def update_code_record(body: dict[str, Any], current_account: dict[str, Any] | None = None) -> None:
    code_hash_value = str(body.get("codeHash", "")).strip()
    if not code_hash_value:
        raise ActivationError("缺少授权码标识")

    licensee = str(body.get("licensee", "OpenClaw Customer")).strip() or "OpenClaw Customer"
    edition = str(body.get("edition", "pro")).strip() or "pro"
    expires = str(body.get("expires", "")).strip()
    if not expires:
        raise ActivationError("请填写到期时间")
    expires = normalize_code_expires(expires)

    max_activations = max(1, min(int(body.get("maxActivations", 1)), 999))
    features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
    member_mode = bool(body.get("memberMode"))
    plan = str(body.get("plan", "")).strip()
    gateway_base_url = str(body.get("gatewayBaseUrl", "")).strip().rstrip("/")
    gateway_image_base_url = str(body.get("gatewayImageBaseUrl") or body.get("gateway_image_base_url") or "").strip().rstrip("/")
    gateway_video_base_url = str(body.get("gatewayVideoBaseUrl") or body.get("gateway_video_base_url") or "").strip().rstrip("/")
    gateway_token = str(body.get("gatewayToken", "")).strip()
    gateway_image_token = str(body.get("gatewayImageToken") or body.get("gateway_image_token") or "").strip()
    gateway_video_token = str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or "").strip()
    gateway_default_model = str(body.get("gatewayDefaultModel", "")).strip()
    gateway_image_model = str(body.get("gatewayImageModel") or body.get("gateway_image_model") or "").strip()
    gateway_video_model = str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or "").strip()
    gateway_models = parse_models(body.get("gatewayModels", ""))
    quotas = parse_json_object(body.get("quotas", ""))

    with connect() as conn:
        existing = conn.execute(
            """
            select owner_account_id, gateway_image_base_url, gateway_video_base_url,
                   gateway_token, gateway_image_token, gateway_video_token,
                   gateway_image_model, gateway_video_model
            from codes
            where code_hash = ?
            """,
            (code_hash_value,),
        ).fetchone()
        if not existing:
            raise ActivationError("授权码不存在", 404)
        if current_account and not code_row_owned_by_context(existing, current_account):
            raise ActivationError("无权修改该授权码", 403)
        if not gateway_image_base_url:
            gateway_image_base_url = str(existing["gateway_image_base_url"] or "")
        if not gateway_video_base_url:
            gateway_video_base_url = str(existing["gateway_video_base_url"] or "")
        if not gateway_token:
            gateway_token = str(existing["gateway_token"] or "")
        if not gateway_image_token:
            gateway_image_token = str(existing["gateway_image_token"] or "")
        if not gateway_video_token:
            gateway_video_token = str(existing["gateway_video_token"] or "")
        if not gateway_image_model:
            gateway_image_model = str(existing["gateway_image_model"] or "")
        if not gateway_video_model:
            gateway_video_model = str(existing["gateway_video_model"] or "")
        result = conn.execute(
            """
            update codes
            set licensee = ?,
                edition = ?,
                features_json = ?,
                expires = ?,
                max_activations = ?,
                member_mode = ?,
                plan = ?,
                gateway_base_url = ?,
                gateway_image_base_url = ?,
                gateway_video_base_url = ?,
                gateway_token = ?,
                gateway_image_token = ?,
                gateway_video_token = ?,
                gateway_default_model = ?,
                gateway_image_model = ?,
                gateway_video_model = ?,
                gateway_models_json = ?,
                quotas_json = ?
            where code_hash = ?
            """,
            (
                licensee,
                edition,
                json.dumps(features, ensure_ascii=False),
                expires,
                max_activations,
                1 if member_mode else 0,
                plan,
                gateway_base_url,
                gateway_image_base_url,
                gateway_video_base_url,
                gateway_token,
                gateway_image_token,
                gateway_video_token,
                gateway_default_model,
                gateway_image_model,
                gateway_video_model,
                json.dumps(gateway_models or [], ensure_ascii=False),
                json.dumps(quotas or {}, ensure_ascii=False),
                code_hash_value,
            ),
        )
        conn.commit()
        if result.rowcount == 0:
            raise ActivationError("授权码不存在", 404)


def bulk_update_code_records(body: dict[str, Any], current_account: dict[str, Any] | None = None) -> int:
    code_hashes = normalize_code_hashes(body.get("codeHashes"))
    if not isinstance(code_hashes, list):
        raise ActivationError("批量更新需要授权码列表")

    updated = 0
    with connect() as conn:
        rows = conn.execute(
            f"select * from codes where code_hash in ({','.join(['?'] * len(code_hashes))})",
            tuple(code_hashes),
        ).fetchall() if code_hashes else []

    for row in rows:
        if current_account and not code_row_owned_by_context(row, current_account):
            raise ActivationError("无权修改该授权码", 403)
        merged = {
            "codeHash": row["code_hash"],
            "licensee": row["licensee"],
            "edition": row["edition"],
            "features": str(body.get("features") or "").strip() or ",".join(load_json_value(row["features_json"], DEFAULT_FEATURES)),
            "expires": str(body.get("expires") or "").strip() or row["expires"],
            "maxActivations": body.get("maxActivations") or row["max_activations"],
            "memberMode": body.get("memberMode") if "memberMode" in body else bool(row["member_mode"]),
            "plan": str(body.get("plan") or "").strip() or row["plan"] or "monthly",
            "gatewayBaseUrl": str(body.get("gatewayBaseUrl") or "").strip() or row["gateway_base_url"],
            "gatewayImageBaseUrl": str(body.get("gatewayImageBaseUrl") or body.get("gateway_image_base_url") or "").strip() or row["gateway_image_base_url"],
            "gatewayVideoBaseUrl": str(body.get("gatewayVideoBaseUrl") or body.get("gateway_video_base_url") or "").strip() or row["gateway_video_base_url"],
            "gatewayToken": str(body.get("gatewayToken") or "").strip(),
            "gatewayImageToken": str(body.get("gatewayImageToken") or body.get("gateway_image_token") or "").strip(),
            "gatewayVideoToken": str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or "").strip(),
            "gatewayDefaultModel": str(body.get("gatewayDefaultModel") or "").strip() or row["gateway_default_model"],
            "gatewayImageModel": str(body.get("gatewayImageModel") or body.get("gateway_image_model") or "").strip() or row["gateway_image_model"],
            "gatewayVideoModel": str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or "").strip() or row["gateway_video_model"],
            "gatewayModels": str(body.get("gatewayModels") or "").strip() or ",".join(load_json_value(row["gateway_models_json"], [])),
            "quotas": str(body.get("quotas") or "").strip() or row["quotas_json"] or "{}",
        }
        update_code_record(merged, current_account=current_account)
        updated += 1
    return updated


def normalize_plan_key(value: Any) -> str:
    plan_key = str(value or "").strip().lower().replace(" ", "_")
    if not plan_key:
        raise ActivationError("缺少套餐标识")
    if any(not (ch.isalnum() or ch in {"_", "-"}) for ch in plan_key):
        raise ActivationError("套餐标识只能包含字母、数字、下划线和中划线")
    return plan_key[:80]


def plan_row_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "planKey": row["plan_key"],
        "displayName": row["display_name"],
        "durationDays": row["duration_days"],
        "features": load_json_value(row["features_json"], DEFAULT_FEATURES),
        "gatewayBaseUrl": row["gateway_base_url"],
        "gatewayImageBaseUrl": row["gateway_image_base_url"],
        "gatewayVideoBaseUrl": row["gateway_video_base_url"],
        "gatewayConfigured": bool(row["gateway_base_url"] and row["gateway_token"]),
        "gatewayImageConfigured": bool((row["gateway_image_base_url"] or row["gateway_base_url"]) and (row["gateway_image_token"] or row["gateway_token"])),
        "gatewayVideoConfigured": bool((row["gateway_video_base_url"] or row["gateway_base_url"]) and (row["gateway_video_token"] or row["gateway_token"])),
        "gatewayDefaultModel": row["gateway_default_model"],
        "gatewayImageModel": row["gateway_image_model"],
        "gatewayVideoModel": row["gateway_video_model"],
        "gatewayModels": load_json_value(row["gateway_models_json"], []),
        "quotas": load_json_value(row["quotas_json"], {}),
        "disabled": bool(row["disabled"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_plan_rows(include_disabled: bool = False) -> list[dict[str, Any]]:
    where = "" if include_disabled else "where disabled = 0"
    with connect() as conn:
        rows = conn.execute(
            f"""
            select *
            from plans
            {where}
            order by disabled asc, plan_key asc
            """
        ).fetchall()
    return [plan_row_public(row) for row in rows]


def get_plan_row(plan_key: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("select * from plans where plan_key = ?", (plan_key,)).fetchone()


def public_settings() -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("select value_json from settings where key = ?", ("public",)).fetchone()
    value = load_json_value(row["value_json"], {}) if row else {}
    settings = dict(DEFAULT_PUBLIC_SETTINGS)
    if isinstance(value, dict):
        settings.update(value)
    settings["cardSiteEnabled"] = bool(settings.get("cardSiteEnabled"))
    settings["cardSiteLabel"] = str(settings.get("cardSiteLabel") or "购买授权码").strip() or "购买授权码"
    settings["cardSiteUrl"] = str(settings.get("cardSiteUrl") or "").strip()
    settings["supportUrl"] = str(settings.get("supportUrl") or PUBLIC_SUPPORT_URL).strip() or PUBLIC_SUPPORT_URL
    return settings


def client_public_config() -> dict[str, Any]:
    settings = public_settings()
    enabled = bool(settings.get("cardSiteEnabled")) and bool(settings.get("cardSiteUrl"))
    card_url = str(settings.get("cardSiteUrl") or "").strip() if enabled else ""
    return {
        "purchaseUrl": card_url or PUBLIC_COMMERCIAL_URL,
        "supportUrl": str(settings.get("supportUrl") or PUBLIC_SUPPORT_URL).strip() or PUBLIC_SUPPORT_URL,
        "cardSite": {
            "enabled": enabled,
            "label": settings.get("cardSiteLabel") or "购买授权码",
            "url": card_url,
        }
    }


def update_public_settings(body: dict[str, Any]) -> dict[str, Any]:
    settings = public_settings()
    if "cardSiteEnabled" in body:
        settings["cardSiteEnabled"] = bool(body.get("cardSiteEnabled"))
    if "cardSiteLabel" in body:
        settings["cardSiteLabel"] = str(body.get("cardSiteLabel") or "购买授权码").strip() or "购买授权码"
    if "cardSiteUrl" in body:
        card_site_url = str(body.get("cardSiteUrl") or "").strip()
        if card_site_url and not card_site_url.lower().startswith(("http://", "https://")):
            raise ActivationError("发卡网站链接必须以 http:// 或 https:// 开头")
        settings["cardSiteUrl"] = card_site_url
    if "supportUrl" in body:
        settings["supportUrl"] = validate_gateway_url(str(body.get("supportUrl") or ""), "客服链接") or PUBLIC_SUPPORT_URL
    with connect() as conn:
        conn.execute(
            """
            insert into settings (key, value_json, updated_at)
            values (?, ?, ?)
            on conflict(key) do update set
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            ("public", json.dumps(settings, ensure_ascii=False, sort_keys=True), utc_now()),
        )
        conn.commit()
    return settings


def parse_optional_models(raw: Any, fallback: list[str] | None = None) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return list(fallback or [])
    return parse_models(text)


def validate_gateway_url(value: str, label: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if normalized and not normalized.lower().startswith(("http://", "https://")):
        raise ActivationError(f"{label} 必须以 http:// 或 https:// 开头")
    return normalized


def default_account_gateway_settings(account_id: int = 0, *, include_secrets: bool = False) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "accountId": int(account_id or 0),
        "gatewayBaseUrl": "",
        "gatewayImageBaseUrl": "",
        "gatewayVideoBaseUrl": "",
        "gatewayDefaultModel": "",
        "gatewayImageModel": "",
        "gatewayVideoModel": "",
        "gatewayModels": [],
        "gatewayConfigured": False,
        "gatewayImageConfigured": False,
        "gatewayVideoConfigured": False,
        "updatedAt": "",
    }
    if include_secrets:
        settings.update(
            {
                "gatewayToken": "",
                "gatewayImageToken": "",
                "gatewayVideoToken": "",
            }
        )
    else:
        settings.update(
            {
                "gatewayTokenConfigured": False,
                "gatewayImageTokenConfigured": False,
                "gatewayVideoTokenConfigured": False,
            }
        )
    return settings


def account_gateway_settings_public(
    row: sqlite3.Row | None,
    *,
    account_id: int = 0,
    include_secrets: bool = False,
) -> dict[str, Any]:
    if not row:
        return default_account_gateway_settings(account_id, include_secrets=include_secrets)
    base_url = str(row["gateway_base_url"] or "")
    image_base_url = str(row["gateway_image_base_url"] or "")
    video_base_url = str(row["gateway_video_base_url"] or "")
    token_value = str(row["gateway_token"] or "")
    image_token = str(row["gateway_image_token"] or "")
    video_token = str(row["gateway_video_token"] or "")
    settings: dict[str, Any] = {
        "accountId": int(row["account_id"] or account_id or 0),
        "gatewayBaseUrl": base_url,
        "gatewayImageBaseUrl": image_base_url,
        "gatewayVideoBaseUrl": video_base_url,
        "gatewayDefaultModel": str(row["gateway_default_model"] or ""),
        "gatewayImageModel": str(row["gateway_image_model"] or ""),
        "gatewayVideoModel": str(row["gateway_video_model"] or ""),
        "gatewayModels": load_json_value(row["gateway_models_json"], []),
        "gatewayConfigured": bool(base_url and token_value),
        "gatewayImageConfigured": bool((image_base_url or base_url) and (image_token or token_value)),
        "gatewayVideoConfigured": bool((video_base_url or base_url) and (video_token or token_value)),
        "updatedAt": str(row["updated_at"] or ""),
    }
    if include_secrets:
        settings.update(
            {
                "gatewayToken": token_value,
                "gatewayImageToken": image_token,
                "gatewayVideoToken": video_token,
            }
        )
    else:
        settings.update(
            {
                "gatewayTokenConfigured": bool(token_value),
                "gatewayImageTokenConfigured": bool(image_token),
                "gatewayVideoTokenConfigured": bool(video_token),
            }
        )
    return settings


def get_account_gateway_settings(account_id: int, *, include_secrets: bool = False) -> dict[str, Any]:
    normalized_account_id = int(account_id or 0)
    if normalized_account_id <= 0:
        return default_account_gateway_settings(normalized_account_id, include_secrets=include_secrets)
    with connect() as conn:
        row = conn.execute(
            "select * from account_gateway_settings where account_id = ?",
            (normalized_account_id,),
        ).fetchone()
    return account_gateway_settings_public(
        row,
        account_id=normalized_account_id,
        include_secrets=include_secrets,
    )


def upsert_account_gateway_settings(account_id: int, body: dict[str, Any]) -> dict[str, Any]:
    normalized_account_id = int(account_id or 0)
    if normalized_account_id <= 0:
        raise ActivationError("缺少账号 ID", 400)
    account = get_account_by_id(normalized_account_id)
    if not account or account["status"] != ACCOUNT_STATUS_ACTIVE:
        raise ActivationError("账号不存在或已停用", 404)

    existing = get_account_gateway_settings(normalized_account_id, include_secrets=True)
    gateway_base_url = validate_gateway_url(body.get("gatewayBaseUrl") or existing.get("gatewayBaseUrl") or "", "通用 Base URL")
    gateway_image_base_url = validate_gateway_url(body.get("gatewayImageBaseUrl") or body.get("gateway_image_base_url") or existing.get("gatewayImageBaseUrl") or "", "图片 Base URL")
    gateway_video_base_url = validate_gateway_url(body.get("gatewayVideoBaseUrl") or body.get("gateway_video_base_url") or existing.get("gatewayVideoBaseUrl") or "", "视频 Base URL")
    gateway_token = str(body.get("gatewayToken") or existing.get("gatewayToken") or "").strip()
    gateway_image_token = str(body.get("gatewayImageToken") or body.get("gateway_image_token") or existing.get("gatewayImageToken") or "").strip()
    gateway_video_token = str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or existing.get("gatewayVideoToken") or "").strip()
    gateway_default_model = str(body.get("gatewayDefaultModel") or existing.get("gatewayDefaultModel") or "").strip()
    gateway_image_model = str(body.get("gatewayImageModel") or body.get("gateway_image_model") or existing.get("gatewayImageModel") or "").strip()
    gateway_video_model = str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or existing.get("gatewayVideoModel") or "").strip()
    gateway_models = parse_optional_models(body.get("gatewayModels"), existing.get("gatewayModels") or [])
    now = utc_now()

    with connect() as conn:
        row = conn.execute(
            "select created_at from account_gateway_settings where account_id = ?",
            (normalized_account_id,),
        ).fetchone()
        created_at = str(row["created_at"]) if row else now
        conn.execute(
            """
            insert into account_gateway_settings (
                account_id, gateway_base_url, gateway_image_base_url, gateway_video_base_url,
                gateway_token, gateway_image_token, gateway_video_token,
                gateway_default_model, gateway_image_model, gateway_video_model,
                gateway_models_json, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(account_id) do update set
                gateway_base_url = excluded.gateway_base_url,
                gateway_image_base_url = excluded.gateway_image_base_url,
                gateway_video_base_url = excluded.gateway_video_base_url,
                gateway_token = excluded.gateway_token,
                gateway_image_token = excluded.gateway_image_token,
                gateway_video_token = excluded.gateway_video_token,
                gateway_default_model = excluded.gateway_default_model,
                gateway_image_model = excluded.gateway_image_model,
                gateway_video_model = excluded.gateway_video_model,
                gateway_models_json = excluded.gateway_models_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized_account_id,
                gateway_base_url,
                gateway_image_base_url,
                gateway_video_base_url,
                gateway_token,
                gateway_image_token,
                gateway_video_token,
                gateway_default_model,
                gateway_image_model,
                gateway_video_model,
                json.dumps(gateway_models, ensure_ascii=False),
                created_at,
                now,
            ),
        )
        conn.commit()
    return get_account_gateway_settings(normalized_account_id, include_secrets=False)


def has_explicit_gateway_value(body: dict[str, Any], *names: str) -> bool:
    return any(str(body.get(name) or "").strip() for name in names)


def apply_account_gateway_defaults(
    body: dict[str, Any],
    account_id: int,
    *,
    explicit_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_account_id = int(account_id or 0)
    if normalized_account_id <= 0:
        return body
    settings = get_account_gateway_settings(normalized_account_id, include_secrets=True)
    if not any(
        str(settings.get(name) or "").strip()
        for name in (
            "gatewayBaseUrl",
            "gatewayImageBaseUrl",
            "gatewayVideoBaseUrl",
            "gatewayToken",
            "gatewayImageToken",
            "gatewayVideoToken",
            "gatewayDefaultModel",
            "gatewayImageModel",
            "gatewayVideoModel",
        )
    ) and not settings.get("gatewayModels"):
        return body

    source = explicit_body or body
    merged = dict(body)
    field_names = [
        ("gatewayBaseUrl", ("gatewayBaseUrl", "gateway_base_url")),
        ("gatewayImageBaseUrl", ("gatewayImageBaseUrl", "gateway_image_base_url")),
        ("gatewayVideoBaseUrl", ("gatewayVideoBaseUrl", "gateway_video_base_url")),
        ("gatewayToken", ("gatewayToken", "gateway_token")),
        ("gatewayImageToken", ("gatewayImageToken", "gateway_image_token")),
        ("gatewayVideoToken", ("gatewayVideoToken", "gateway_video_token")),
        ("gatewayDefaultModel", ("gatewayDefaultModel", "gateway_default_model")),
        ("gatewayImageModel", ("gatewayImageModel", "gateway_image_model")),
        ("gatewayVideoModel", ("gatewayVideoModel", "gateway_video_model")),
    ]
    for canonical_name, aliases in field_names:
        value = settings.get(canonical_name)
        if value and not has_explicit_gateway_value(source, *aliases):
            merged[canonical_name] = value
    if settings.get("gatewayModels") and not has_explicit_gateway_value(source, "gatewayModels", "gateway_models"):
        merged["gatewayModels"] = ",".join(settings.get("gatewayModels") or [])
    if "memberMode" not in source and (
        settings.get("gatewayConfigured")
        or settings.get("gatewayImageConfigured")
        or settings.get("gatewayVideoConfigured")
    ):
        merged["memberMode"] = True
    return merged


def upsert_plan_record(body: dict[str, Any]) -> dict[str, Any]:
    plan_key = normalize_plan_key(body.get("planKey") or body.get("plan") or body.get("key"))
    display_name = str(body.get("displayName") or body.get("name") or plan_key).strip() or plan_key
    duration_days = max(1, min(int(body.get("durationDays") or 31), 3660))
    features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
    gateway_base_url = str(body.get("gatewayBaseUrl", "")).strip().rstrip("/")
    gateway_image_base_url = str(body.get("gatewayImageBaseUrl") or body.get("gateway_image_base_url") or "").strip().rstrip("/")
    gateway_video_base_url = str(body.get("gatewayVideoBaseUrl") or body.get("gateway_video_base_url") or "").strip().rstrip("/")
    gateway_token = str(body.get("gatewayToken", "")).strip()
    gateway_image_token = str(body.get("gatewayImageToken") or body.get("gateway_image_token") or "").strip()
    gateway_video_token = str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or "").strip()
    gateway_default_model = str(body.get("gatewayDefaultModel", "")).strip()
    gateway_image_model = str(body.get("gatewayImageModel") or body.get("gateway_image_model") or "").strip()
    gateway_video_model = str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or "").strip()
    gateway_models = parse_models(body.get("gatewayModels", ""))
    quotas = parse_json_object(body.get("quotas", ""))
    disabled = 1 if body.get("disabled") else 0
    now = utc_now()

    with connect() as conn:
        existing = conn.execute(
            """
            select gateway_image_base_url, gateway_video_base_url,
                   gateway_token, gateway_image_token, gateway_video_token,
                   gateway_image_model, gateway_video_model, created_at
            from plans
            where plan_key = ?
            """,
            (plan_key,),
        ).fetchone()
        if existing and not gateway_image_base_url:
            gateway_image_base_url = str(existing["gateway_image_base_url"] or "")
        if existing and not gateway_video_base_url:
            gateway_video_base_url = str(existing["gateway_video_base_url"] or "")
        if existing and not gateway_token:
            gateway_token = str(existing["gateway_token"] or "")
        if existing and not gateway_image_token:
            gateway_image_token = str(existing["gateway_image_token"] or "")
        if existing and not gateway_video_token:
            gateway_video_token = str(existing["gateway_video_token"] or "")
        if existing and not gateway_image_model:
            gateway_image_model = str(existing["gateway_image_model"] or "")
        if existing and not gateway_video_model:
            gateway_video_model = str(existing["gateway_video_model"] or "")
        created_at = str(existing["created_at"]) if existing else now
        conn.execute(
            """
            insert into plans (
                plan_key, display_name, duration_days, features_json, gateway_base_url,
                gateway_image_base_url, gateway_video_base_url,
                gateway_token, gateway_image_token, gateway_video_token,
                gateway_default_model, gateway_image_model, gateway_video_model,
                gateway_models_json, quotas_json,
                disabled, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(plan_key) do update set
                display_name = excluded.display_name,
                duration_days = excluded.duration_days,
                features_json = excluded.features_json,
                gateway_base_url = excluded.gateway_base_url,
                gateway_image_base_url = excluded.gateway_image_base_url,
                gateway_video_base_url = excluded.gateway_video_base_url,
                gateway_token = excluded.gateway_token,
                gateway_image_token = excluded.gateway_image_token,
                gateway_video_token = excluded.gateway_video_token,
                gateway_default_model = excluded.gateway_default_model,
                gateway_image_model = excluded.gateway_image_model,
                gateway_video_model = excluded.gateway_video_model,
                gateway_models_json = excluded.gateway_models_json,
                quotas_json = excluded.quotas_json,
                disabled = excluded.disabled,
                updated_at = excluded.updated_at
            """,
            (
                plan_key,
                display_name,
                duration_days,
                json.dumps(features, ensure_ascii=False),
                gateway_base_url,
                gateway_image_base_url,
                gateway_video_base_url,
                gateway_token,
                gateway_image_token,
                gateway_video_token,
                gateway_default_model,
                gateway_image_model,
                gateway_video_model,
                json.dumps(gateway_models or [], ensure_ascii=False),
                json.dumps(quotas or {}, ensure_ascii=False),
                disabled,
                created_at,
                now,
            ),
        )
        conn.commit()
    row = get_plan_row(plan_key)
    if not row:
        raise ActivationError("套餐模板不存在")
    return plan_row_public(row)


def disable_plan_record(plan_key: str) -> dict[str, Any] | None:
    plan_key = normalize_plan_key(plan_key)
    before = get_plan_row(plan_key)
    if not before:
        return None
    with connect() as conn:
        conn.execute("update plans set disabled = 1, updated_at = ? where plan_key = ?", (utc_now(), plan_key))
        conn.commit()
    after = get_plan_row(plan_key)
    return plan_row_public(after) if after else None


def apply_plan_template(body: dict[str, Any]) -> dict[str, Any]:
    plan_key_raw = body.get("planTemplate") or body.get("planKey")
    if not str(plan_key_raw or "").strip():
        return body
    plan_key = normalize_plan_key(plan_key_raw)
    row = get_plan_row(plan_key)
    if not row or bool(row["disabled"]):
        raise ActivationError("套餐模板不存在或已停用", 404)

    merged = dict(body)

    def blank(name: str) -> bool:
        value = merged.get(name)
        return value is None or str(value).strip() == ""

    if blank("features"):
        merged["features"] = ",".join(load_json_value(row["features_json"], DEFAULT_FEATURES))
    if blank("expires"):
        expires = datetime.now(timezone.utc).date() + timedelta(days=int(row["duration_days"] or 31))
        merged["expires"] = expires.isoformat()
    if blank("plan"):
        merged["plan"] = row["plan_key"]
    if blank("gatewayBaseUrl"):
        merged["gatewayBaseUrl"] = row["gateway_base_url"]
    if blank("gatewayImageBaseUrl"):
        merged["gatewayImageBaseUrl"] = row["gateway_image_base_url"]
    if blank("gatewayVideoBaseUrl"):
        merged["gatewayVideoBaseUrl"] = row["gateway_video_base_url"]
    if blank("gatewayToken"):
        merged["gatewayToken"] = row["gateway_token"]
    if blank("gatewayImageToken"):
        merged["gatewayImageToken"] = row["gateway_image_token"]
    if blank("gatewayVideoToken"):
        merged["gatewayVideoToken"] = row["gateway_video_token"]
    if blank("gatewayDefaultModel"):
        merged["gatewayDefaultModel"] = row["gateway_default_model"]
    if blank("gatewayImageModel"):
        merged["gatewayImageModel"] = row["gateway_image_model"]
    if blank("gatewayVideoModel"):
        merged["gatewayVideoModel"] = row["gateway_video_model"]
    if blank("gatewayModels"):
        merged["gatewayModels"] = ",".join(load_json_value(row["gateway_models_json"], []))
    if blank("quotas"):
        merged["quotas"] = row["quotas_json"] or "{}"
    merged["memberMode"] = True
    return merged


def make_db_backup(label: str) -> str:
    if not os.path.exists(DB_PATH):
        return ""
    safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in label.strip())[:48] or "change"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_path = os.path.join(BACKUP_DIR, f"license-{timestamp}-{safe_label}.db")
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def audit_json(value: Any) -> str:
    return json.dumps({} if value is None else value, ensure_ascii=False, sort_keys=True)


def masked_code_label(value: Any) -> str:
    text = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    return f"••••-{text[-8:]}" if text else "[REDACTED]"


def audit_public_value(value: Any, *, key: str = "") -> Any:
    normalized_key = "".join(ch for ch in key.lower() if ch.isalnum())
    if normalized_key in AUDIT_SECRET_KEYS:
        return masked_code_label(value) if normalized_key in {"fullcode", "code"} else "[REDACTED]"
    if normalized_key == "codes" and isinstance(value, list):
        return [masked_code_label(item) for item in value]
    if isinstance(value, dict):
        return {str(k): audit_public_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [audit_public_value(item, key=key) for item in value]
    return value


def add_audit_log(
    *,
    action: str,
    target_type: str = "",
    target_id: str = "",
    before: Any = None,
    after: Any = None,
    actor: str = "",
    request_ip: str = "",
    backup_path: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            insert into audit_logs (
                actor, action, target_type, target_id, before_json, after_json,
                request_ip, backup_path, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor[:128],
                action[:80],
                target_type[:80],
                target_id[:256],
                audit_json(before),
                audit_json(after),
                request_ip[:80],
                backup_path,
                utc_now(),
            ),
        )
        conn.commit()


def masked_secret(value: Any) -> str:
    return "已配置" if str(value or "").strip() else ""


def code_row_snapshot(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    row_keys = set(row.keys())
    return {
        "codeHash": row["code_hash"],
        "codeLabel": row["code_label"],
        "licensee": row["licensee"],
        "edition": row["edition"],
        "features": load_json_value(row["features_json"], DEFAULT_FEATURES),
        "expires": row["expires"],
        "maxActivations": row["max_activations"],
        "disabled": bool(row["disabled"]),
        "memberMode": bool(row["member_mode"]),
        "plan": row["plan"],
        "gatewayBaseUrl": row["gateway_base_url"],
        "gatewayImageBaseUrl": row["gateway_image_base_url"],
        "gatewayVideoBaseUrl": row["gateway_video_base_url"],
        "gatewayToken": masked_secret(row["gateway_token"]),
        "gatewayImageToken": masked_secret(row["gateway_image_token"]),
        "gatewayVideoToken": masked_secret(row["gateway_video_token"]),
        "gatewayDefaultModel": row["gateway_default_model"],
        "gatewayImageModel": row["gateway_image_model"],
        "gatewayVideoModel": row["gateway_video_model"],
        "gatewayModels": load_json_value(row["gateway_models_json"], []),
        "quotas": load_json_value(row["quotas_json"], {}),
        "ownerAccountId": int(row["owner_account_id"]) if "owner_account_id" in row_keys and row["owner_account_id"] is not None else 0,
        "ownerUsername": row["owner_username"] if "owner_username" in row_keys else "",
        "ownerDisplayName": row["owner_display_name"] if "owner_display_name" in row_keys else "",
        "ownerRole": row["owner_role"] if "owner_role" in row_keys else "",
        "activations": int(row["activations"]) if "activations" in row_keys else None,
        "createdAt": row["created_at"],
    }


def get_code_snapshot(code_hash_value: str, current_account: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not code_hash_value:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            select c.*, count(a.id) as activations,
                   coalesce(acc.username, '') as owner_username,
                   coalesce(acc.display_name, '') as owner_display_name,
                   coalesce(acc.role, '') as owner_role
            from codes c
            left join activations a on a.code_hash = c.code_hash
            left join accounts acc on acc.id = c.owner_account_id
            where c.code_hash = ?
            group by c.code_hash
            """,
            (code_hash_value,),
        ).fetchone()
    if row and current_account and not code_row_owned_by_context(row, current_account):
        return None
    return code_row_snapshot(row)


def get_code_snapshots(code_hashes: list[Any], current_account: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    clean_hashes = [str(item).strip() for item in code_hashes if str(item).strip()]
    if not clean_hashes:
        return []
    placeholders = ",".join(["?"] * len(clean_hashes))
    with connect() as conn:
        rows = conn.execute(
            f"""
            select c.*, count(a.id) as activations,
                   coalesce(acc.username, '') as owner_username,
                   coalesce(acc.display_name, '') as owner_display_name,
                   coalesce(acc.role, '') as owner_role
            from codes c
            left join activations a on a.code_hash = c.code_hash
            left join accounts acc on acc.id = c.owner_account_id
            where c.code_hash in ({placeholders})
            group by c.code_hash
            order by c.created_at desc
            """,
            tuple(clean_hashes),
        ).fetchall()
    snapshots = [snapshot for row in rows if (snapshot := code_row_snapshot(row))]
    if current_account and not is_super_admin_context(current_account):
        snapshots = [row for row in snapshots if row.get("ownerAccountId", 0) == context_account_id(current_account)]
    return snapshots


def get_inventory_snapshot() -> dict[str, Any]:
    with connect() as conn:
        code_count = conn.execute("select count(*) from codes").fetchone()[0]
        activation_count = conn.execute("select count(*) from activations").fetchone()[0]
        sample = conn.execute(
            """
            select code_hash, code_label, licensee, edition, expires
            from codes
            order by created_at desc
            limit 20
            """
        ).fetchall()
    return {
        "codeCount": code_count,
        "activationCount": activation_count,
        "sample": [dict(row) for row in sample],
    }


def get_audit_rows(limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with connect() as conn:
        rows = conn.execute(
            """
            select id, actor, action, target_type, target_id, before_json, after_json,
                   request_ip, backup_path, created_at
            from audit_logs
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "actor": row["actor"],
            "action": row["action"],
            "targetType": row["target_type"],
            "targetId": row["target_id"],
            "before": audit_public_value(load_json_value(row["before_json"], {})),
            "after": audit_public_value(load_json_value(row["after_json"], {})),
            "requestIp": row["request_ip"],
            "backupPath": row["backup_path"],
            "backupFile": os.path.basename(row["backup_path"]) if row["backup_path"] else "",
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def create_codes(args: argparse.Namespace) -> None:
    features = args.features.split(",") if args.features else DEFAULT_FEATURES
    for code in create_code_records(
        count=args.count,
        licensee=args.licensee,
        edition=args.edition,
        features=features,
        expires=args.expires,
        max_activations=args.max_activations,
        member_mode=args.member_mode,
        plan=args.plan,
        gateway_base_url=args.gateway_base_url,
        gateway_image_base_url=args.gateway_image_base_url,
        gateway_video_base_url=args.gateway_video_base_url,
        gateway_token=args.gateway_token,
        gateway_image_token=args.gateway_image_token,
        gateway_video_token=args.gateway_video_token,
        gateway_default_model=args.gateway_default_model,
        gateway_image_model=args.gateway_image_model,
        gateway_video_model=args.gateway_video_model,
        gateway_models=parse_models(args.gateway_models),
        quotas=parse_json_object(args.quotas),
    ):
        print(code)


def get_code_rows(current_account: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    where_clause = ""
    params: tuple[Any, ...] = ()
    if current_account and not is_super_admin_context(current_account):
        where_clause = "where c.owner_account_id = ?"
        params = (context_account_id(current_account),)
    with connect() as conn:
        rows = conn.execute(
            f"""
            select c.code_hash, c.code_label, c.licensee, c.edition, c.features_json, c.expires, c.max_activations,
                   c.disabled, c.member_mode, c.plan, c.gateway_base_url,
                   c.gateway_image_base_url, c.gateway_video_base_url, c.gateway_token,
                   c.gateway_image_token, c.gateway_video_token, c.gateway_default_model,
                   c.gateway_image_model, c.gateway_video_model, c.gateway_models_json,
                   c.quotas_json, c.owner_account_id,
                   coalesce(acc.username, '') as owner_username,
                   coalesce(acc.display_name, '') as owner_display_name,
                   coalesce(acc.role, '') as owner_role,
                   c.created_at, count(a.id) as activations
            from codes c
            left join activations a on a.code_hash = c.code_hash
            left join accounts acc on acc.id = c.owner_account_id
            {where_clause}
            group by c.code_hash
            order by c.created_at desc
            """,
            params,
        ).fetchall()
    return [
        {
            "codeHash": row["code_hash"],
            "codeLabel": row["code_label"],
            "licensee": row["licensee"],
            "edition": row["edition"],
            "features": json.loads(row["features_json"]),
            "expires": row["expires"],
            "maxActivations": row["max_activations"],
            "activations": row["activations"],
            "disabled": bool(row["disabled"]),
            "memberMode": bool(row["member_mode"]),
            "plan": row["plan"],
            "gatewayBaseUrl": row["gateway_base_url"],
            "gatewayImageBaseUrl": row["gateway_image_base_url"],
            "gatewayVideoBaseUrl": row["gateway_video_base_url"],
            "gatewayToken": masked_secret(row["gateway_token"]),
            "gatewayImageToken": masked_secret(row["gateway_image_token"]),
            "gatewayVideoToken": masked_secret(row["gateway_video_token"]),
            "gatewayDefaultModel": row["gateway_default_model"],
            "gatewayImageModel": row["gateway_image_model"],
            "gatewayVideoModel": row["gateway_video_model"],
            "gatewayModels": json.loads(row["gateway_models_json"] or "[]"),
            "quotas": json.loads(row["quotas_json"] or "{}"),
            "ownerAccountId": int(row["owner_account_id"] or 0),
            "ownerUsername": row["owner_username"],
            "ownerDisplayName": row["owner_display_name"],
            "ownerRole": row["owner_role"],
            "gatewayConfigured": bool(row["gateway_base_url"] and row["gateway_token"]),
            "gatewayImageConfigured": bool((row["gateway_image_base_url"] or row["gateway_base_url"]) and (row["gateway_image_token"] or row["gateway_token"])),
            "gatewayVideoConfigured": bool((row["gateway_video_base_url"] or row["gateway_base_url"]) and (row["gateway_video_token"] or row["gateway_token"])),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


def get_code_secret_rows(
    code_hashes: list[Any],
    current_account: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized = normalize_code_hashes(code_hashes)
    if not normalized:
        raise ActivationError("请选择授权码", 400)
    if len(normalized) > MAX_CODE_SECRET_EXPORT:
        raise ActivationError(f"单次最多导出 {MAX_CODE_SECRET_EXPORT} 个授权码", 400)
    placeholders = ",".join(["?"] * len(normalized))
    with connect() as conn:
        rows = conn.execute(
            f"""
            select code_hash, code_label, full_code, licensee, edition, plan, expires,
                   max_activations, owner_account_id, disabled
            from codes
            where code_hash in ({placeholders})
            """,
            tuple(normalized),
        ).fetchall()
    by_hash = {str(row["code_hash"]): row for row in rows}
    ordered: list[dict[str, Any]] = []
    for code_hash_value in normalized:
        row = by_hash.get(code_hash_value)
        if not row or not code_row_owned_by_context(row, current_account):
            raise ActivationError("授权码不存在或无权访问", 404)
        ordered.append(
            {
                "codeHash": row["code_hash"],
                "codeLabel": row["code_label"],
                "code": row["full_code"] or ("OC-" + str(row["edition"]).upper() + "-" + row["code_label"]),
                "licensee": row["licensee"],
                "plan": row["plan"],
                "expires": row["expires"],
                "maxActivations": int(row["max_activations"] or 1),
                "disabled": bool(row["disabled"]),
            }
        )
    return ordered


def activation_row_public(row: sqlite3.Row) -> dict[str, Any]:
    try:
        license_data = json.loads(row["license_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        license_data = {}
    return {
        "id": row["id"],
        "codeHash": row["code_hash"],
        "installId": row["install_id"],
        "deviceId": row["device_id"],
        "licenseId": license_data.get("licenseId", ""),
        "memberId": license_data.get("memberId", ""),
        "plan": license_data.get("plan") or license_data.get("edition", ""),
        "activatedAt": row["activated_at"],
    }


def get_activation_rows(code_hash_value: str, current_account: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    owner_clause = ""
    params: tuple[Any, ...] = (code_hash_value,)
    if current_account and not is_super_admin_context(current_account):
        owner_clause = "and c.owner_account_id = ?"
        params += (context_account_id(current_account),)
    with connect() as conn:
        code_row = conn.execute(
            f"select c.owner_account_id from codes c where c.code_hash = ? {owner_clause}",
            params,
        ).fetchone()
        if not code_row:
            raise ActivationError("授权码不存在或无权访问", 404)
        rows = conn.execute(
            f"""
            select a.id, a.code_hash, a.install_id, a.device_id, a.license_json, a.activated_at
            from activations a
            join codes c on c.code_hash = a.code_hash
            where a.code_hash = ? {owner_clause}
            order by a.activated_at desc
            """,
            params,
        ).fetchall()
    return [activation_row_public(row) for row in rows]


def get_all_activation_rows(
    current_account: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    where_clause = ""
    params: tuple[Any, ...] = ()
    if current_account and not is_super_admin_context(current_account):
        where_clause = "where c.owner_account_id = ?"
        params = (context_account_id(current_account),)
    with connect() as conn:
        rows = conn.execute(
            f"""
            select a.id, a.code_hash, a.install_id, a.device_id, a.activated_at,
                   c.code_label, c.plan, c.owner_account_id,
                   coalesce(acc.display_name, '') as owner_display_name
            from activations a
            join codes c on c.code_hash = a.code_hash
            left join accounts acc on acc.id = c.owner_account_id
            {where_clause}
            order by a.activated_at desc, a.id desc
            """,
            params,
        ).fetchall()
    return [
        {
            "activationId": int(row["id"]),
            "codeHash": row["code_hash"],
            "codeLabel": row["code_label"],
            "installId": row["install_id"],
            "deviceId": row["device_id"],
            "plan": row["plan"],
            "ownerDisplayName": row["owner_display_name"],
            "activatedAt": row["activated_at"],
        }
        for row in rows
    ]


def get_activation_snapshot(
    activation_id: int,
    current_account: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    owner_clause = ""
    params: tuple[Any, ...] = (activation_id,)
    if current_account and not is_super_admin_context(current_account):
        owner_clause = "and c.owner_account_id = ?"
        params += (context_account_id(current_account),)
    with connect() as conn:
        row = conn.execute(
            f"""
            select a.id, a.code_hash, a.install_id, a.device_id, a.license_json, a.activated_at
            from activations a
            left join codes c on c.code_hash = a.code_hash
            where a.id = ? {owner_clause}
            """,
            params,
        ).fetchone()
    return activation_row_public(row) if row else None


def list_codes(_args: argparse.Namespace) -> None:
    with connect() as conn:
        rows = conn.execute(
            """
            select c.code_label, c.licensee, c.edition, c.expires, c.max_activations,
                   count(a.id) as activations, c.disabled
            from codes c
            left join activations a on a.code_hash = c.code_hash
            group by c.code_hash
            order by c.created_at desc
            """
        ).fetchall()
    for row in rows:
        status = "disabled" if row["disabled"] else "active"
        print(f"{row['code_label']} | {row['licensee']} | {row['edition']} | {row['expires']} | {row['activations']}/{row['max_activations']} | {status}")


def load_json_value(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def apply_member_fields(payload: dict[str, Any], code_row: sqlite3.Row) -> dict[str, Any]:
    if not bool(code_row["member_mode"]):
        return payload

    allow_global_gateway_fallback = int(code_row["owner_account_id"] or 0) <= 0
    default_gateway_base_url = DEFAULT_GATEWAY_BASE_URL if allow_global_gateway_fallback else ""
    default_gateway_image_base_url = DEFAULT_GATEWAY_IMAGE_BASE_URL if allow_global_gateway_fallback else ""
    default_gateway_video_base_url = DEFAULT_GATEWAY_VIDEO_BASE_URL if allow_global_gateway_fallback else ""
    default_gateway_token = DEFAULT_GATEWAY_TOKEN if allow_global_gateway_fallback else ""
    default_gateway_image_token = DEFAULT_GATEWAY_IMAGE_TOKEN if allow_global_gateway_fallback else ""
    default_gateway_video_token = DEFAULT_GATEWAY_VIDEO_TOKEN if allow_global_gateway_fallback else ""

    gateway_base_url = str(code_row["gateway_base_url"] or default_gateway_base_url).strip().rstrip("/")
    gateway_image_base_url = str(code_row["gateway_image_base_url"] or default_gateway_image_base_url or gateway_base_url).strip().rstrip("/")
    gateway_video_base_url = str(code_row["gateway_video_base_url"] or default_gateway_video_base_url or gateway_base_url).strip().rstrip("/")
    gateway_token = str(code_row["gateway_token"] or default_gateway_token).strip()
    if not gateway_base_url or not gateway_token:
        raise ActivationError("会员网关未配置，缺少 Base URL 或 Token", 500)

    gateway_models = load_json_value(code_row["gateway_models_json"], [])
    if not isinstance(gateway_models, list):
        gateway_models = []
    gateway_models = [str(item).strip() for item in gateway_models if str(item).strip()] or list(DEFAULT_GATEWAY_MODELS)

    default_model = str(code_row["gateway_default_model"] or DEFAULT_GATEWAY_DEFAULT_MODEL or "").strip()
    if not default_model and gateway_models:
        default_model = gateway_models[0]

    image_model = str(code_row["gateway_image_model"] or DEFAULT_GATEWAY_IMAGE_MODEL or "").strip()
    video_model = str(code_row["gateway_video_model"] or DEFAULT_GATEWAY_VIDEO_MODEL or "").strip()
    image_token = str(code_row["gateway_image_token"] or default_gateway_image_token or gateway_token).strip() or gateway_token
    video_token = str(code_row["gateway_video_token"] or default_gateway_video_token or gateway_token).strip() or gateway_token

    quotas = load_json_value(code_row["quotas_json"], {})
    if not isinstance(quotas, dict):
        quotas = {}

    member_id = f"member_{code_row['code_label']}"
    payload.update(
        {
            "memberMode": True,
            "memberId": member_id,
            "plan": str(code_row["plan"] or code_row["edition"] or "monthly").strip(),
            "leaseExpiresAt": payload.get("expires"),
            "gatewayBaseUrl": gateway_base_url,
            "gatewayImageBaseUrl": gateway_image_base_url,
            "gatewayVideoBaseUrl": gateway_video_base_url,
            "gatewayAccessToken": gateway_token,
            "gatewayToken": gateway_token,
            "gatewayImageAccessToken": image_token,
            "gatewayVideoAccessToken": video_token,
            "gatewayImageToken": image_token,
            "gatewayVideoToken": video_token,
            "gatewayDefaultModel": default_model,
            "gatewayImageModel": image_model,
            "gatewayVideoModel": video_model,
            "gatewayModels": gateway_models,
            "quotas": quotas,
            "usage": {},
        }
    )
    return payload


def build_signed_license(
    code_row: sqlite3.Row,
    install_id: str,
    device_id: str,
    *,
    license_id: str | None = None,
    activated_at: str | None = None,
) -> dict[str, Any]:
    full_code = str(code_row["full_code"] or "").strip()
    code_label = str(code_row["code_label"] or "").strip()
    code_last8 = "".join(ch for ch in (full_code or code_label).upper() if ch.isalnum())[-8:]
    payload = {
        "licenseId": license_id or secrets.token_hex(12),
        "licensee": code_row["licensee"],
        "edition": code_row["edition"],
        "plan": str(code_row["plan"] or code_row["edition"] or "monthly").strip(),
        "features": json.loads(code_row["features_json"]),
        "expires": code_row["expires"],
        "expiresAt": code_row["expires"],
        "installId": install_id,
        "deviceId": device_id,
        "deviceLimit": int(code_row["max_activations"] or 1),
        "activatedAt": activated_at or utc_now(),
        "activationCodeLabel": code_label,
        "activationCodeLast8": code_last8,
    }
    payload = apply_member_fields(payload, code_row)
    return sign_license(payload)


def member_response(license_data: dict[str, Any]) -> dict[str, Any]:
    gateway = {
        "baseUrl": license_data.get("gatewayBaseUrl"),
        "imageBaseUrl": license_data.get("gatewayImageBaseUrl") or license_data.get("gatewayBaseUrl"),
        "videoBaseUrl": license_data.get("gatewayVideoBaseUrl") or license_data.get("gatewayBaseUrl"),
        "accessToken": license_data.get("gatewayAccessToken"),
        "token": license_data.get("gatewayAccessToken"),
        "imageAccessToken": license_data.get("gatewayImageAccessToken") or license_data.get("gatewayImageToken") or license_data.get("gatewayAccessToken"),
        "videoAccessToken": license_data.get("gatewayVideoAccessToken") or license_data.get("gatewayVideoToken") or license_data.get("gatewayAccessToken"),
        "imageToken": license_data.get("gatewayImageAccessToken") or license_data.get("gatewayImageToken") or license_data.get("gatewayAccessToken"),
        "videoToken": license_data.get("gatewayVideoAccessToken") or license_data.get("gatewayVideoToken") or license_data.get("gatewayAccessToken"),
        "defaultModel": license_data.get("gatewayDefaultModel"),
        "imageModel": license_data.get("gatewayImageModel"),
        "videoModel": license_data.get("gatewayVideoModel"),
        "models": license_data.get("gatewayModels") or [],
    }
    member = {
        "memberId": license_data.get("memberId"),
        "memberName": license_data.get("licensee"),
        "plan": license_data.get("plan") or license_data.get("edition"),
        "status": "active",
        "expiresAt": license_data.get("expires"),
        "leaseExpiresAt": license_data.get("leaseExpiresAt") or license_data.get("expires"),
        "gatewayBaseUrl": license_data.get("gatewayBaseUrl"),
        "gatewayImageBaseUrl": license_data.get("gatewayImageBaseUrl") or license_data.get("gatewayBaseUrl"),
        "gatewayVideoBaseUrl": license_data.get("gatewayVideoBaseUrl") or license_data.get("gatewayBaseUrl"),
        "gatewayAccessToken": license_data.get("gatewayAccessToken"),
        "gatewayToken": license_data.get("gatewayAccessToken"),
        "gatewayImageAccessToken": license_data.get("gatewayImageAccessToken") or license_data.get("gatewayImageToken") or license_data.get("gatewayAccessToken"),
        "gatewayVideoAccessToken": license_data.get("gatewayVideoAccessToken") or license_data.get("gatewayVideoToken") or license_data.get("gatewayAccessToken"),
        "gatewayImageToken": license_data.get("gatewayImageAccessToken") or license_data.get("gatewayImageToken") or license_data.get("gatewayAccessToken"),
        "gatewayVideoToken": license_data.get("gatewayVideoAccessToken") or license_data.get("gatewayVideoToken") or license_data.get("gatewayAccessToken"),
        "gatewayDefaultModel": license_data.get("gatewayDefaultModel"),
        "gatewayImageModel": license_data.get("gatewayImageModel"),
        "gatewayVideoModel": license_data.get("gatewayVideoModel"),
        "gatewayModels": license_data.get("gatewayModels") or [],
        "features": license_data.get("features") or [],
        "quotas": license_data.get("quotas") or {},
        "usage": license_data.get("usage") or {},
        "gateway": gateway,
        "lease": {
            "memberId": license_data.get("memberId"),
            "plan": license_data.get("plan") or license_data.get("edition"),
            "expiresAt": license_data.get("expires"),
            "leaseExpiresAt": license_data.get("leaseExpiresAt") or license_data.get("expires"),
            "features": license_data.get("features") or [],
            "gatewayDefaultModel": license_data.get("gatewayDefaultModel"),
            "gatewayImageBaseUrl": license_data.get("gatewayImageBaseUrl") or license_data.get("gatewayBaseUrl"),
            "gatewayVideoBaseUrl": license_data.get("gatewayVideoBaseUrl") or license_data.get("gatewayBaseUrl"),
            "gatewayImageModel": license_data.get("gatewayImageModel"),
            "gatewayVideoModel": license_data.get("gatewayVideoModel"),
            "gatewayImageAccessToken": license_data.get("gatewayImageAccessToken") or license_data.get("gatewayImageToken") or license_data.get("gatewayAccessToken"),
            "gatewayVideoAccessToken": license_data.get("gatewayVideoAccessToken") or license_data.get("gatewayVideoToken") or license_data.get("gatewayAccessToken"),
        },
    }
    return {
        "license": license_data,
        "member": member,
        "lease": member["lease"],
        "gateway": gateway,
        "usage": member["usage"],
    }


def find_member_license(body: dict[str, Any]) -> dict[str, Any] | None:
    member_id = str(body.get("memberId") or "").strip()
    token = str(
        body.get("memberToken")
        or body.get("leaseToken")
        or body.get("gatewayAccessToken")
        or body.get("gatewayImageAccessToken")
        or body.get("gatewayVideoAccessToken")
        or body.get("gatewayToken")
        or body.get("gatewayImageToken")
        or body.get("gatewayVideoToken")
        or ""
    ).strip()
    install_id = str(body.get("installId") or "").strip()
    device_id = str(body.get("deviceId") or "").strip()
    if not token or not install_id:
        return None
    with connect() as conn:
        rows = conn.execute(
            """
            select id, code_hash, install_id, device_id, license_json, activated_at
            from activations
            order by activated_at desc
            """
        ).fetchall()
        for row in rows:
            try:
                old_license = json.loads(row["license_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if install_id and row["install_id"] != install_id:
                continue
            if device_id and row["device_id"] != device_id:
                continue
            if member_id and str(old_license.get("memberId") or "") != member_id:
                continue
            token_candidates = [
                old_license.get("gatewayAccessToken"),
                old_license.get("gatewayToken"),
                old_license.get("gatewayImageAccessToken"),
                old_license.get("gatewayVideoAccessToken"),
                old_license.get("gatewayImageToken"),
                old_license.get("gatewayVideoToken"),
            ]
            if token and token not in {str(item or "").strip() for item in token_candidates if str(item or "").strip()}:
                continue

            code_row = conn.execute("select * from codes where code_hash = ?", (row["code_hash"],)).fetchone()
            if not code_row or code_row["disabled"] or not bool(code_row["member_mode"]):
                continue

            license_data = build_signed_license(
                code_row,
                str(row["install_id"] or ""),
                str(row["device_id"] or ""),
                license_id=str(old_license.get("licenseId") or "") or None,
                activated_at=str(old_license.get("activatedAt") or row["activated_at"] or "") or None,
            )
            conn.execute(
                "update activations set license_json = ? where id = ?",
                (json.dumps(license_data, ensure_ascii=False), row["id"]),
            )
            conn.commit()
            return license_data
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenClawLicense/1.0"

    def admin_context(self, *, allow_legacy: bool = True) -> dict[str, Any] | None:
        context = getattr(self, "_admin_context", None)
        if context is not None:
            return context
        token = request_admin_token(self.headers)
        context = load_admin_context_from_session(token)
        if context is None and allow_legacy:
            context = load_legacy_admin_context(token)
        self._admin_context = context
        return context

    def admin_actor(self) -> str:
        context = self.admin_context()
        if not context:
            return "admin"
        return str(context.get("actor") or "admin")

    def admin_role(self) -> str:
        context = self.admin_context()
        return str(context.get("role") or "") if context else ""

    def admin_account_id(self) -> int:
        context = self.admin_context()
        return context_account_id(context)

    def request_ip(self) -> str:
        # Behind the nginx TLS proxy the socket peer is always 127.0.0.1, so the
        # real visitor IP arrives in proxy headers. The site sits behind
        # Cloudflare, which puts the true client in CF-Connecting-IP (a single
        # value it sets itself); prefer it. Otherwise X-Real-IP (nginx
        # $remote_addr = the CF edge), then the last X-Forwarded-For entry, then
        # the socket peer.
        cf_ip = self.headers.get("CF-Connecting-IP", "").strip()
        if cf_ip:
            return cf_ip
        real_ip = self.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            parts = [p.strip() for p in forwarded.split(",") if p.strip()]
            if parts:
                return parts[-1]
        return self.client_address[0] if self.client_address else ""

    def require_admin(self, role: str | None = None, *, allow_legacy: bool = True) -> bool:
        context = self.admin_context(allow_legacy=allow_legacy)
        if not context:
            self.send_json(401, {"error": "请先登录"})
            return False
        if role and role_rank(str(context.get("role") or "")) < role_rank(role):
            self.send_json(403, {"error": "权限不足"})
            return False
        return True

    def audit_admin_change(
        self,
        action: str,
        *,
        target_type: str = "",
        target_id: str = "",
        before: Any = None,
        after: Any = None,
        backup_path: str = "",
    ) -> None:
        add_audit_log(
            action=action,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            actor=self.admin_actor(),
            request_ip=self.request_ip(),
            backup_path=backup_path,
        )

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def require_publish_relay_auth(self) -> bool:
        if not publish_relay_configured():
            self.send_json(503, {"ok": False, "error": "Relay token is not configured"})
            return False
        if publish_relay_token_valid(self.headers):
            return True
        self.send_json(
            401,
            {"ok": False, "error": "Relay auth required"},
            headers={"WWW-Authenticate": 'Bearer realm="openclaw-publish-relay"'},
        )
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self.send_json(200, {"ok": True, "time": utc_now()})
            return
        if path == "/api/beta/status":
            self.send_json(200, {"ok": True, "data": beta_status_snapshot()})
            return
        if path == "/admin/api/beta/config":
            if not self.require_admin():
                return
            self.send_json(200, {"ok": True, "data": get_beta_config()})
            return
        if path == "/api/templates":
            kind = str(parse_qs(parsed.query).get("kind", [""])[0]).strip().lower()
            self.send_json(200, {"ok": True, "data": list_templates(kind, only_enabled=True)})
            return
        if path == "/admin/api/templates":
            if not self.require_admin():
                return
            kind = str(parse_qs(parsed.query).get("kind", [""])[0]).strip().lower()
            self.send_json(200, {"ok": True, "data": list_templates(kind)})
            return
        if path in {"/api/lumi/relay/health", "/api/lumi/publish/health"}:
            authorized = publish_relay_token_valid(self.headers)
            self.send_json(
                200,
                {
                    "ok": True,
                    "data": {
                        "authRequired": publish_relay_auth_required(),
                        "configured": publish_relay_configured(),
                        "authenticated": authorized,
                        "queue": publish_relay_stats() if authorized else None,
                        "timestamp": utc_now(),
                    },
                },
            )
            return
        if path in {"/api/lumi/relay/poll", "/api/lumi/publish/poll"}:
            if not self.require_publish_relay_auth():
                return
            query = parse_qs(parsed.query)
            channel_id = normalize_string((query.get("channelId") or query.get("channel_id") or [""])[0])
            client_id = normalize_string((query.get("clientId") or query.get("client_id") or ["default-client"])[0]) or "default-client"
            lease_ms = clamp_int((query.get("leaseMs") or query.get("lease_ms") or [PUBLISH_RELAY_DEFAULT_LEASE_MS])[0], 1_000, 15 * 60_000, PUBLISH_RELAY_DEFAULT_LEASE_MS)
            wait_ms = clamp_int((query.get("waitMs") or query.get("wait_ms") or [PUBLISH_RELAY_DEFAULT_WAIT_MS])[0], 0, 15 * 60_000, PUBLISH_RELAY_DEFAULT_WAIT_MS)
            try:
                record = publish_relay_wait_for_packet(channel_id, client_id, lease_ms, wait_ms)
                if not record:
                    self.send_json(
                        200,
                        {
                            "ok": True,
                            "data": {
                                "packet": None,
                                "channelId": channel_id,
                                "clientId": client_id,
                                "waitMs": wait_ms,
                                "leaseMs": lease_ms,
                            },
                        },
                    )
                    return
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "data": {
                            "packetId": record["id"],
                            "leaseId": record["leaseId"],
                            "channelId": record["channelId"],
                            "leaseUntil": record["leaseUntil"],
                            "attempts": record["attempts"],
                            "packet": record["packet"],
                        },
                    },
                )
            except ActivationError as error:
                self.send_json(error.status, {"ok": False, "error": str(error)})
            except Exception as error:
                self.send_json(500, {"ok": False, "error": f"server error: {error}"})
            return
        if path in {"/api/lumi/relay/status", "/api/lumi/publish/status"}:
            if not self.require_publish_relay_auth():
                return
            query = parse_qs(parsed.query)
            packet_id = normalize_string((query.get("id") or query.get("packetId") or query.get("packet_id") or [""])[0])
            channel_id = normalize_string((query.get("channelId") or query.get("channel_id") or [""])[0])
            try:
                if packet_id:
                    self.send_json(200, {"ok": True, "data": publish_relay_status(packet_id, include_packet=True)})
                else:
                    self.send_json(200, {"ok": True, "data": {"queue": publish_relay_stats(channel_id)}})
            except ActivationError as error:
                self.send_json(error.status, {"ok": False, "error": str(error)})
            except Exception as error:
                self.send_json(500, {"ok": False, "error": f"server error: {error}"})
            return
        if path == "/public-key":
            self.send_json(200, {"publicKey": public_key_b64()})
            return
        if path in {"/admin", "/admin/"}:
            self.send_html(200, ADMIN_HTML)
            return
        if path in {"/logo.ico", "/admin/logo.ico"}:
            self.send_file(200, LOGO_FILE, "image/x-icon")
            return
        if path in {"/api/client/config", "/api/public/config", "/client/config"}:
            self.send_json(200, client_public_config())
            return
        if path == "/admin/api/auth/status":
            self.send_json(200, auth_status_snapshot())
            return
        if path == "/admin/api/me":
            if not self.require_admin():
                return
            context = self.admin_context()
            account = account_summary_row(context_account_id(context)) if context and context_account_id(context) else None
            payload = {
                "account": account or (context or {}),
                "session": {
                    "authType": context.get("authType") if context else "",
                    "role": context.get("role") if context else "",
                },
                "authStatus": auth_status_snapshot(),
            }
            self.send_json(200, payload)
            return
        if path == "/admin/api/accounts":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            self.send_json(200, {"accounts": list_account_rows()})
            return
        if path == "/admin/api/invites":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            self.send_json(200, {"invites": list_invite_rows()})
            return
        if path == "/admin/api/codes":
            if not self.require_admin():
                return
            self.send_json(200, {"codes": get_code_rows(self.admin_context())})
            return
        if path == "/admin/api/activations":
            if not self.require_admin():
                return
            self.send_json(200, {"activations": get_all_activation_rows(self.admin_context())})
            return
        if path == "/admin/api/plans":
            if not self.require_admin():
                return
            self.send_json(200, {"plans": get_plan_rows(include_disabled=True)})
            return
        if path == "/admin/api/account-gateway":
            if not self.require_admin():
                return
            account_id = context_account_id(self.admin_context())
            self.send_json(200, {"settings": get_account_gateway_settings(account_id, include_secrets=False)})
            return
        if path == "/admin/api/codes/activations":
            if not self.require_admin():
                return
            query = parse_qs(parsed.query)
            code_hash_value = str((query.get("codeHash") or [""])[0]).strip()
            try:
                self.send_json(200, {"activations": get_activation_rows(code_hash_value, self.admin_context())})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            return
        if path == "/admin/api/audit-logs":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            query = parse_qs(parsed.query)
            limit = int((query.get("limit") or ["100"])[0] or "100")
            self.send_json(200, {"logs": get_audit_rows(limit)})
            return
        if path == "/admin/api/public-settings":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            self.send_json(200, {"settings": public_settings(), "clientConfig": client_public_config()})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/beta/claim":
            try:
                ip = self.request_ip()
                rate_limit_consume("beta-claim", ip, limit=20, window_seconds=3600, lockout_seconds=600)
                self.send_json(200, {"ok": True, "data": beta_claim_code(ip)})
            except ActivationError as error:
                self.send_json(error.status, {"ok": False, "error": str(error)})
            except Exception as error:
                self.send_json(500, {"ok": False, "error": f"server error: {error}"})
            return
        if path == "/admin/api/beta/config":
            if not self.require_admin():
                return
            try:
                cfg = set_beta_config(self.read_json())
                self.send_json(200, {"ok": True, "data": cfg})
            except Exception as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return
        if path == "/admin/api/templates":
            if not self.require_admin():
                return
            try:
                tpl = save_template(self.read_json())
                self.send_json(200, {"ok": True, "data": tpl})
            except ActivationError as error:
                self.send_json(error.status, {"ok": False, "error": str(error)})
            except Exception as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return
        if path == "/admin/api/templates/delete":
            if not self.require_admin():
                return
            try:
                delete_template(int(self.read_json().get("id", 0) or 0))
                self.send_json(200, {"ok": True})
            except Exception as error:
                self.send_json(400, {"ok": False, "error": str(error)})
            return
        if path == "/admin/api/auth/status":
            self.send_json(405, {"error": "method not allowed"})
            return
        if path == "/admin/api/auth/login":
            try:
                body = self.read_json()
                username = normalize_username(body.get("username"))
                password = str(body.get("password") or "").strip()
                login_rate_key = f"{self.request_ip()}:{username or '-'}"
                rate_limit_check("admin-login", login_rate_key)
                account = get_account_by_username(username)
                if not account or account["status"] != ACCOUNT_STATUS_ACTIVE or not verify_password(password, account["password_hash"]):
                    rate_limit_record_failure(
                        "admin-login",
                        login_rate_key,
                        limit=LOGIN_RATE_LIMIT_ATTEMPTS,
                        window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
                        lockout_seconds=LOGIN_RATE_LIMIT_LOCKOUT_SECONDS,
                    )
                    self.send_json(401, {"error": "用户名或密码错误"})
                    return
                rate_limit_clear("admin-login", login_rate_key)
                session_token, expires_at = create_admin_session(
                    int(account["id"]),
                    request_ip=self.request_ip(),
                    user_agent=str(self.headers.get("User-Agent", "") or ""),
                )
                with connect() as conn:
                    conn.execute(
                        "update accounts set last_login_at = ?, last_login_ip = ?, updated_at = ? where id = ?",
                        (utc_now(), self.request_ip(), utc_now(), int(account["id"])),
                    )
                    conn.commit()
                account = get_account_by_id(int(account["id"]))
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "sessionToken": session_token,
                        "expiresAt": expires_at,
                        "account": account_row_public(account),
                        "authStatus": auth_status_snapshot(),
                    },
                )
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/auth/register":
            try:
                rate_limit_consume(
                    "admin-register",
                    self.request_ip(),
                    limit=REGISTER_RATE_LIMIT_ATTEMPTS,
                    window_seconds=REGISTER_RATE_LIMIT_WINDOW_SECONDS,
                    lockout_seconds=REGISTER_RATE_LIMIT_LOCKOUT_SECONDS,
                )
                body = self.read_json()
                account, invite_code, _ = register_account_with_invite(
                    invite_code=str(body.get("inviteCode") or body.get("invite_code") or ""),
                    username=str(body.get("username") or ""),
                    display_name=str(body.get("displayName") or body.get("display_name") or ""),
                    password=str(body.get("password") or ""),
                    request_ip=self.request_ip(),
                    user_agent=str(self.headers.get("User-Agent", "") or ""),
                )
                account_id = int(account.get("accountId") or 0)
                session_token, expires_at = create_admin_session(
                    account_id,
                    request_ip=self.request_ip(),
                    user_agent=str(self.headers.get("User-Agent", "") or ""),
                )
                with connect() as conn:
                    conn.execute(
                        "update accounts set last_login_at = ?, last_login_ip = ?, updated_at = ? where id = ?",
                        (utc_now(), self.request_ip(), utc_now(), account_id),
                    )
                    conn.commit()
                account = get_account_by_id(account_id)
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "inviteCode": invite_code,
                        "sessionToken": session_token,
                        "expiresAt": expires_at,
                        "account": account_row_public(account),
                        "authStatus": auth_status_snapshot(),
                    },
                )
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/auth/bootstrap":
            try:
                if count_accounts() > 0:
                    self.send_json(409, {"error": "系统已经初始化"})
                    return
                provided = str(
                    self.headers.get("X-Admin-Token")
                    or self.headers.get("Authorization", "")
                    or ""
                ).strip()
                if provided.lower().startswith("bearer "):
                    provided = provided.split(" ", 1)[1].strip()
                expected = load_admin_token()
                if not expected or not provided or not secrets.compare_digest(provided, expected):
                    self.send_json(401, {"error": "初始化口令错误"})
                    return
                body = self.read_json()
                bootstrap_password = str(body.get("password") or "").strip()
                if not bootstrap_password:
                    raise ActivationError("首次初始化必须设置密码", 400)
                account, _ = create_account_record(
                    username=str(body.get("username") or "admin").strip(),
                    display_name=str(body.get("displayName") or body.get("display_name") or "超级管理员").strip(),
                    password=bootstrap_password,
                    role=ACCOUNT_ROLE_SUPER_ADMIN,
                    status=ACCOUNT_STATUS_ACTIVE,
                    note=str(body.get("note") or "").strip(),
                    created_by=0,
                )
                session_token, expires_at = create_admin_session(
                    int(account.get("accountId") or 0),
                    request_ip=self.request_ip(),
                    user_agent=str(self.headers.get("User-Agent", "") or ""),
                )
                self.send_json(
                    200,
                    {
                        "ok": True,
                        "account": account,
                        "sessionToken": session_token,
                        "expiresAt": expires_at,
                        "authStatus": auth_status_snapshot(),
                    },
                )
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/auth/logout":
            if not self.require_admin():
                return
            token = request_admin_token(self.headers)
            revoked = revoke_admin_session(token)
            self.send_json(200, {"ok": True, "revoked": revoked})
            return
        if path == "/admin/api/accounts":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                body = self.read_json()
                account_id = int(body.get("accountId") or 0)
                current = self.admin_context()
                if account_id:
                    before_row = get_account_by_id(account_id)
                    if not before_row:
                        self.send_json(404, {"error": "账号不存在"})
                        return
                    next_role = normalize_account_role(body.get("role")) if body.get("role") is not None else str(before_row["role"])
                    next_status = normalize_account_status(body.get("status")) if body.get("status") is not None else str(before_row["status"])
                    removing_active_super = (
                        before_row["role"] == ACCOUNT_ROLE_SUPER_ADMIN
                        and before_row["status"] == ACCOUNT_STATUS_ACTIVE
                        and (next_role != ACCOUNT_ROLE_SUPER_ADMIN or next_status != ACCOUNT_STATUS_ACTIVE)
                    )
                    if removing_active_super and count_active_super_admins() <= 1:
                        self.send_json(409, {"error": "至少需要保留一个启用中的超级管理员账号"})
                        return
                    before = account_row_public(before_row)
                    backup_path = make_db_backup("accounts-update")
                    after = update_account_record(
                        account_id=account_id,
                        display_name=body.get("displayName"),
                        role=body.get("role"),
                        status=body.get("status"),
                        password=body.get("password"),
                        note=body.get("note"),
                    )
                    self.audit_admin_change(
                        "accounts.update",
                        target_type="account",
                        target_id=str(account_id),
                        before=before,
                        after=after,
                        backup_path=backup_path,
                    )
                    self.send_json(200, {"ok": True, "account": after})
                else:
                    account_password = str(body.get("password") or "").strip()
                    if not account_password:
                        raise ActivationError("新建账号必须设置密码", 400)
                    backup_path = make_db_backup("accounts-create")
                    account, _ = create_account_record(
                        username=str(body.get("username") or "").strip(),
                        display_name=str(body.get("displayName") or body.get("display_name") or "").strip(),
                        password=account_password,
                        role=body.get("role") or ACCOUNT_ROLE_MERCHANT,
                        status=body.get("status") or ACCOUNT_STATUS_ACTIVE,
                        note=str(body.get("note") or "").strip(),
                        created_by=int(current.get("accountId") or 0) if current else 0,
                    )
                    self.audit_admin_change(
                        "accounts.create",
                        target_type="account",
                        target_id=str(account.get("accountId") or ""),
                        before={},
                        after=account,
                        backup_path=backup_path,
                    )
                    self.send_json(200, {"ok": True, "account": account})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/accounts/toggle":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                body = self.read_json()
                account_id = int(body.get("accountId") or 0)
                if account_id <= 0:
                    self.send_json(400, {"error": "缺少账号 ID"})
                    return
                before_row = get_account_by_id(account_id)
                if not before_row:
                    self.send_json(404, {"error": "账号不存在"})
                    return
                before = account_row_public(before_row)
                next_status = ACCOUNT_STATUS_DISABLED if before_row["status"] == ACCOUNT_STATUS_ACTIVE else ACCOUNT_STATUS_ACTIVE
                if (
                    before_row["role"] == ACCOUNT_ROLE_SUPER_ADMIN
                    and before_row["status"] == ACCOUNT_STATUS_ACTIVE
                    and next_status == ACCOUNT_STATUS_DISABLED
                    and count_active_super_admins() <= 1
                ):
                    self.send_json(409, {"error": "至少需要保留一个启用中的超级管理员账号"})
                    return
                backup_path = make_db_backup("accounts-toggle")
                after = update_account_record(account_id=account_id, status=next_status)
                self.audit_admin_change(
                    "accounts.toggle",
                    target_type="account",
                    target_id=str(account_id),
                    before=before,
                    after=after,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "account": after})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/invites":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                body = self.read_json()
                current = self.admin_context()
                backup_path = make_db_backup("invites-create")
                invite, raw_code = create_invite_record(
                    note=str(body.get("note") or "").strip(),
                    max_uses=int(body.get("maxUses") or body.get("max_uses") or 1),
                    expires_at=str(body.get("expiresAt") or body.get("expires_at") or "").strip(),
                    created_by=int(current.get("accountId") or 0) if current else 0,
                )
                self.audit_admin_change(
                    "invites.create",
                    target_type="invite",
                    target_id=str(invite.get("inviteId") or invite.get("inviteCode") or ""),
                    before={},
                    after={**invite, "rawInviteCode": raw_code},
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "invite": invite, "inviteCode": raw_code})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/invites/toggle":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                body = self.read_json()
                invite_id = int(body.get("inviteId") or body.get("invite_id") or 0)
                if invite_id <= 0:
                    self.send_json(400, {"error": "缺少邀请码 ID"})
                    return
                with connect() as conn:
                    before_row = conn.execute("select * from invite_codes where id = ?", (invite_id,)).fetchone()
                if not before_row:
                    self.send_json(404, {"error": "邀请码不存在"})
                    return
                backup_path = make_db_backup("invites-toggle")
                after = toggle_invite_record(invite_id)
                self.audit_admin_change(
                    "invites.toggle",
                    target_type="invite",
                    target_id=str(invite_id),
                    before=invite_row_public(before_row),
                    after=after,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "invite": after})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/account-gateway":
            if not self.require_admin():
                return
            try:
                account_id = context_account_id(self.admin_context())
                if account_id <= 0:
                    raise ActivationError("请先使用账号登录", 401)
                before = get_account_gateway_settings(account_id, include_secrets=False)
                backup_path = make_db_backup("account-gateway-update")
                settings = upsert_account_gateway_settings(account_id, self.read_json())
                self.audit_admin_change(
                    "account_gateway.update",
                    target_type="account_gateway",
                    target_id=str(account_id),
                    before=before,
                    after=settings,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "settings": settings})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path in {"/api/lumi/relay/packet", "/api/lumi/publish/packet"}:
            if not self.require_publish_relay_auth():
                return
            try:
                record = publish_relay_enqueue(self.read_json())
                self.send_json(
                    202,
                    {
                        "ok": True,
                        "data": {
                            "packetId": record["id"],
                            "channelId": record["channelId"],
                            "status": record["status"],
                            "attempts": record["attempts"],
                            "createdAt": record["createdAt"],
                            "updatedAt": record["updatedAt"],
                            "statusUrl": f"/api/lumi/relay/status?id={record['id']}",
                        },
                    },
                )
            except ActivationError as error:
                self.send_json(error.status, {"ok": False, "error": str(error)})
            except Exception as error:
                self.send_json(500, {"ok": False, "error": f"server error: {error}"})
            return
        if path in {"/api/lumi/relay/complete", "/api/lumi/publish/complete"}:
            if not self.require_publish_relay_auth():
                return
            try:
                record = publish_relay_complete(self.read_json())
                self.send_json(200, {"ok": True, "data": record})
            except ActivationError as error:
                self.send_json(error.status, {"ok": False, "error": str(error)})
            except Exception as error:
                self.send_json(500, {"ok": False, "error": f"server error: {error}"})
            return
        if path == "/admin/api/codes/reveal":
            if not self.require_admin():
                return
            try:
                body = self.read_json()
                if str(body.get("confirmation") or "") != "REVEAL":
                    raise ActivationError("请确认查看完整授权码", 400)
                rows = get_code_secret_rows([body.get("codeHash")], self.admin_context())
                row = rows[0]
                self.audit_admin_change(
                    "codes.reveal",
                    target_type="code",
                    target_id=row["codeHash"],
                    after={"codeLabel": row["codeLabel"]},
                )
                self.send_json(200, {"code": row["code"], "codeLabel": row["codeLabel"]})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception:
                self.send_json(500, {"error": "查看授权码失败"})
            return
        if path == "/admin/api/codes/export":
            if not self.require_admin():
                return
            try:
                body = self.read_json()
                if str(body.get("confirmation") or "") != "EXPORT":
                    raise ActivationError("请确认导出完整授权码", 400)
                rows = get_code_secret_rows(body.get("codeHashes"), self.admin_context())
                self.audit_admin_change(
                    "codes.export",
                    target_type="codes",
                    target_id=f"count:{len(rows)}",
                    after={
                        "count": len(rows),
                        "codeLabels": [row["codeLabel"] for row in rows],
                    },
                )
                self.send_json(200, {"codes": rows})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception:
                self.send_json(500, {"error": "导出授权码失败"})
            return
        if path == "/admin/api/codes":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                raw_body = self.read_json()
                body = apply_plan_template(raw_body) if is_super_admin_context(current) else raw_body
                owner_account_id = context_account_id(current)
                if current and is_super_admin_context(current):
                    owner_account_id = int(body.get("ownerAccountId") or body.get("owner_account_id") or owner_account_id or 0)
                body = apply_account_gateway_defaults(body, owner_account_id, explicit_body=raw_body)
                features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
                backup_path = make_db_backup("codes-create")
                if owner_account_id:
                    owner = get_account_by_id(owner_account_id)
                    if not owner or owner["status"] != ACCOUNT_STATUS_ACTIVE:
                        raise ActivationError("归属账号不存在或已停用")
                codes = create_code_records(
                    count=int(body.get("count", 1)),
                    licensee=str(body.get("licensee", "客户")).strip() or "客户",
                    edition=str(body.get("edition", "pro")).strip() or "pro",
                    features=features,
                    expires=str(body.get("expires", "2027-05-01")).strip() or "2027-05-01",
                    max_activations=int(body.get("maxActivations", 1)),
                    member_mode=bool(body.get("memberMode")),
                    plan=str(body.get("plan", "")).strip(),
                    gateway_base_url=str(body.get("gatewayBaseUrl", "")).strip(),
                    gateway_image_base_url=str(body.get("gatewayImageBaseUrl") or body.get("gateway_image_base_url") or "").strip(),
                    gateway_video_base_url=str(body.get("gatewayVideoBaseUrl") or body.get("gateway_video_base_url") or "").strip(),
                    gateway_token=str(body.get("gatewayToken", "")).strip(),
                    gateway_image_token=str(body.get("gatewayImageToken") or body.get("gateway_image_token") or "").strip(),
                    gateway_video_token=str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or "").strip(),
                    gateway_default_model=str(body.get("gatewayDefaultModel", "")).strip(),
                    gateway_image_model=str(body.get("gatewayImageModel") or body.get("gateway_image_model") or "").strip(),
                    gateway_video_model=str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or "").strip(),
                    gateway_models=parse_models(body.get("gatewayModels", "")),
                    quotas=parse_json_object(body.get("quotas", "")),
                    owner_account_id=owner_account_id,
                )
                self.audit_admin_change(
                    "codes.create",
                    target_type="codes",
                    target_id=f"count:{len(codes)}",
                    before={},
                    after={
                        "count": len(codes),
                        "codeLabels": [code[-9:] for code in codes],
                        "licensee": str(body.get("licensee", "客户")).strip() or "客户",
                        "memberMode": bool(body.get("memberMode")),
                        "plan": str(body.get("plan", "")).strip(),
                        "ownerAccountId": owner_account_id,
                    },
                    backup_path=backup_path,
                )
                self.send_json(200, {"codes": codes})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/codes/update":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                raw_body = self.read_json()
                body = apply_plan_template(raw_body) if is_super_admin_context(current) else raw_body
                code_hash_value = str(body.get("codeHash", "")).strip()
                before = get_code_snapshot(code_hash_value, current)
                backup_path = make_db_backup("codes-update")
                update_code_record(body, current_account=current)
                after = get_code_snapshot(code_hash_value, current)
                self.audit_admin_change(
                    "codes.update",
                    target_type="code",
                    target_id=code_hash_value,
                    before=before,
                    after=after,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/codes/bulk-update":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                raw_body = self.read_json()
                body = apply_plan_template(raw_body) if is_super_admin_context(current) else dict(raw_body)
                code_hashes = normalize_code_hashes(body.get("codeHashes"))
                body["codeHashes"] = code_hashes
                before = get_code_snapshots(code_hashes, current)
                backup_path = make_db_backup("codes-bulk-update")
                updated = bulk_update_code_records(body, current_account=current)
                after = get_code_snapshots(code_hashes, current)
                self.audit_admin_change(
                    "codes.bulk_update",
                    target_type="codes",
                    target_id=f"count:{updated}",
                    before=before,
                    after=after,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "updated": updated})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/plans/update":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                body = self.read_json()
                plan_key_value = str(body.get("planKey") or body.get("plan") or body.get("key") or "").strip()
                before_row = get_plan_row(normalize_plan_key(plan_key_value)) if plan_key_value else None
                before = plan_row_public(before_row) if before_row else None
                backup_path = make_db_backup("plans-update")
                plan = upsert_plan_record(body)
                self.audit_admin_change(
                    "plans.update",
                    target_type="plan",
                    target_id=plan["planKey"],
                    before=before,
                    after=plan,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "plan": plan})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/plans/delete":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                body = self.read_json()
                plan_key_value = normalize_plan_key(body.get("planKey"))
                before_row = get_plan_row(plan_key_value)
                before = plan_row_public(before_row) if before_row else None
                if before is None:
                    self.send_json(404, {"error": "套餐模板不存在"})
                    return
                backup_path = make_db_backup("plans-delete")
                after = disable_plan_record(plan_key_value)
                self.audit_admin_change(
                    "plans.delete",
                    target_type="plan",
                    target_id=plan_key_value,
                    before=before,
                    after=after,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "plan": after})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/codes/toggle":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                body = self.read_json()
                code_hash_value = str(body.get("codeHash", ""))
                disabled = 1 if body.get("disabled") else 0
                before = get_code_snapshot(code_hash_value, current)
                backup_path = make_db_backup("codes-toggle")
                with connect() as conn:
                    if current and not is_super_admin_context(current):
                        result = conn.execute(
                            "update codes set disabled = ? where code_hash = ? and owner_account_id = ?",
                            (disabled, code_hash_value, context_account_id(current)),
                        )
                    else:
                        result = conn.execute("update codes set disabled = ? where code_hash = ?", (disabled, code_hash_value))
                    conn.commit()
                if result.rowcount == 0:
                    self.send_json(404, {"error": "授权码不存在"})
                else:
                    after = get_code_snapshot(code_hash_value, current)
                    self.audit_admin_change(
                        "codes.toggle",
                        target_type="code",
                        target_id=code_hash_value,
                        before=before,
                        after=after,
                        backup_path=backup_path,
                    )
                    self.send_json(200, {"ok": True})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/codes/clear":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                before = get_inventory_snapshot()
                backup_path = make_db_backup("codes-clear")
                with connect() as conn:
                    conn.execute("delete from activations")
                    conn.execute("delete from codes")
                    conn.commit()
                self.audit_admin_change(
                    "codes.clear",
                    target_type="codes",
                    target_id="all",
                    before=before,
                    after=get_inventory_snapshot(),
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/codes/hash":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                body = self.read_json()
                code = str(body.get("code", "")).strip().upper()
                h = code_hash(code)
                self.send_json(200, {"codeHash": h})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/codes/delete":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                body = self.read_json()
                code_hash_value = str(body.get("codeHash", ""))
                before = get_code_snapshot(code_hash_value, current)
                if not before:
                    self.send_json(404, {"error": "授权码不存在或无权访问"})
                    return
                backup_path = make_db_backup("codes-delete")
                with connect() as conn:
                    if current and not is_super_admin_context(current):
                        conn.execute("delete from activations where code_hash = ?", (code_hash_value,))
                        conn.execute("delete from codes where code_hash = ? and owner_account_id = ?", (code_hash_value, context_account_id(current)))
                    else:
                        conn.execute("delete from activations where code_hash = ?", (code_hash_value,))
                        conn.execute("delete from codes where code_hash = ?", (code_hash_value,))
                    conn.commit()
                self.audit_admin_change(
                    "codes.delete",
                    target_type="code",
                    target_id=code_hash_value,
                    before=before,
                    after={},
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/activations/delete":
            if not self.require_admin():
                return
            try:
                current = self.admin_context()
                body = self.read_json()
                activation_id = int(body.get("id") or 0)
                before = get_activation_snapshot(activation_id, current)
                if before is None:
                    self.send_json(404, {"error": "激活记录不存在或无权访问"})
                    return
                backup_path = make_db_backup("activations-delete")
                with connect() as conn:
                    if current and not is_super_admin_context(current):
                        deleted = conn.execute(
                            """
                            delete from activations
                            where id = ?
                              and code_hash in (
                                  select code_hash from codes where owner_account_id = ?
                              )
                            """,
                            (activation_id, context_account_id(current)),
                        )
                    else:
                        deleted = conn.execute("delete from activations where id = ?", (activation_id,))
                    if deleted.rowcount != 1:
                        conn.rollback()
                        self.send_json(404, {"error": "激活记录不存在或无权访问"})
                        return
                    conn.commit()
                self.audit_admin_change(
                    "activations.delete",
                    target_type="activation",
                    target_id=str(activation_id),
                    before=before,
                    after={},
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path == "/admin/api/public-settings":
            if not self.require_admin(ACCOUNT_ROLE_SUPER_ADMIN):
                return
            try:
                before = public_settings()
                backup_path = make_db_backup("public-settings-update")
                settings = update_public_settings(self.read_json())
                self.audit_admin_change(
                    "settings.update",
                    target_type="settings",
                    target_id="public",
                    before=before,
                    after=settings,
                    backup_path=backup_path,
                )
                self.send_json(200, {"ok": True, "settings": settings, "clientConfig": client_public_config()})
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error)})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
            return
        if path in {"/api/member/current", "/member/current", "/api/v1/member/current", "/api/member/refresh", "/member/refresh", "/api/v1/member/refresh"}:
            try:
                body = self.read_json()
                license_data = find_member_license(body)
                if not license_data:
                    self.send_json(404, {"error": "会员会话不存在或已失效"})
                    return
                self.send_json(200, member_response(license_data))
            except Exception as error:
                self.send_json(500, {"error": f"server error: {error}"})
            return
        if path in {"/api/member/usage", "/member/usage", "/api/v1/member/usage"}:
            try:
                body = self.read_json()
                license_data = find_member_license(body)
                if not license_data:
                    self.send_json(404, {"error": "会员会话不存在或已失效"})
                    return
                self.send_json(200, {"usage": license_data.get("usage") or {}, "quotas": license_data.get("quotas") or {}})
            except Exception as error:
                self.send_json(500, {"error": f"server error: {error}"})
            return
        if path in {"/api/member/activate", "/member/activate", "/api/v1/member/activate"}:
            try:
                body = self.read_json()
                license_data = activate_code(body)
                self.send_json(200, member_response(license_data))
            except ActivationError as error:
                self.send_json(error.status, {"error": str(error), "code": error.code})
            except Exception as error:
                self.send_json(500, {"error": f"server error: {error}"})
            return
        if path != "/activate":
            self.send_json(404, {"error": "not found"})
            return
        try:
            body = self.read_json()
            license_data = activate_code(body)
            self.send_json(200, {"license": license_data})
        except ActivationError as error:
            self.send_json(error.status, {"error": str(error), "code": error.code})
        except Exception as error:
            self.send_json(500, {"error": f"server error: {error}"})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        return json.loads(data.decode("utf-8-sig"))

    def send_cors_headers(self) -> None:
        origin = str(self.headers.get("Origin") or "").strip()
        if is_admin_request_path(self.path):
            if origin and admin_cors_origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-OpenClaw-Relay-Token, X-Admin-Token, X-Admin-Session")

    def send_json(self, status: int, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_cors_headers()
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, status: int, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, status: int, path: str, content_type: str) -> None:
        try:
            with open(path, "rb") as file:
                data = file.read()
        except OSError:
            self.send_json(404, {"error": "file not found"})
            return
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{utc_now()}] {self.address_string()} {fmt % args}")


class ActivationError(RuntimeError):
    def __init__(self, message: str, status: int = 400, code: str = "REQUEST_INVALID"):
        super().__init__(message)
        self.status = status
        self.code = code


def activate_code(body: dict[str, Any]) -> dict[str, Any]:
    code = str(body.get("code", "")).strip().upper()
    install_id = str(body.get("installId", "")).strip()
    device_id = str(body.get("deviceId", "")).strip()
    if not code or not install_id:
        raise ActivationError("缺少授权码或安装 ID", 400, "LICENSE_INVALID_REQUEST")

    hashed = code_hash(code)
    with connect() as conn:
        code_row = conn.execute("select * from codes where code_hash = ?", (hashed,)).fetchone()
        if not code_row:
            raise ActivationError("授权码不存在", 404, "LICENSE_INVALID")
        if code_row["disabled"]:
            raise ActivationError("授权码已停用", 403, "LICENSE_DISABLED")
        try:
            if date.fromisoformat(str(code_row["expires"])) < date.today():
                raise ActivationError("授权码已过期", 403, "LICENSE_EXPIRED")
        except ValueError as error:
            raise ActivationError("授权码到期日期无效", 500, "LICENSE_DATA_INVALID") from error
        existing = conn.execute("select * from activations where code_hash = ? and install_id = ?", (hashed, install_id)).fetchone()
        if existing:
            existing_device = str(existing["device_id"] or "").strip()
            if existing_device and device_id and existing_device != device_id:
                raise ActivationError("授权码绑定设备与当前设备不匹配", 403, "DEVICE_MISMATCH")
            conn.execute("delete from activations where code_hash = ? and install_id = ?", (hashed, install_id))
        used_count = conn.execute("select count(*) as count from activations where code_hash = ?", (hashed,)).fetchone()["count"]
        if used_count >= code_row["max_activations"]:
            raise ActivationError("授权码已被其他设备激活", 403, "DEVICE_MISMATCH")
        license_data = build_signed_license(code_row, install_id, device_id)
        conn.execute(
            """
            insert into activations (code_hash, install_id, device_id, license_json, activated_at)
            values (?, ?, ?, ?, ?)
            """,
            (hashed, install_id, device_id, json.dumps(license_data, ensure_ascii=False), utc_now()),
        )
        conn.commit()
        return license_data


def serve(_args: argparse.Namespace) -> None:
    seed_default_templates()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"OpenClaw license server listening on {HOST}:{PORT}")
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenClaw license server")
    sub = parser.add_subparsers(required=True)

    serve_parser = sub.add_parser("serve")
    serve_parser.set_defaults(func=serve)

    create_parser = sub.add_parser("create-code")
    create_parser.add_argument("--count", type=int, default=1)
    create_parser.add_argument("--licensee", default="客户")
    create_parser.add_argument("--edition", default="pro")
    create_parser.add_argument("--features", default=",".join(DEFAULT_FEATURES))
    create_parser.add_argument("--expires", default="2027-05-01")
    create_parser.add_argument("--max-activations", type=int, default=1)
    create_parser.add_argument("--member-mode", action="store_true")
    create_parser.add_argument("--plan", default="monthly")
    create_parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    create_parser.add_argument("--gateway-image-base-url", default=DEFAULT_GATEWAY_IMAGE_BASE_URL)
    create_parser.add_argument("--gateway-video-base-url", default=DEFAULT_GATEWAY_VIDEO_BASE_URL)
    create_parser.add_argument("--gateway-token", default=DEFAULT_GATEWAY_TOKEN)
    create_parser.add_argument("--gateway-image-token", default=DEFAULT_GATEWAY_IMAGE_TOKEN)
    create_parser.add_argument("--gateway-video-token", default=DEFAULT_GATEWAY_VIDEO_TOKEN)
    create_parser.add_argument("--gateway-default-model", default=DEFAULT_GATEWAY_DEFAULT_MODEL)
    create_parser.add_argument("--gateway-image-model", default=DEFAULT_GATEWAY_IMAGE_MODEL)
    create_parser.add_argument("--gateway-video-model", default=DEFAULT_GATEWAY_VIDEO_MODEL)
    create_parser.add_argument("--gateway-models", default=",".join(DEFAULT_GATEWAY_MODELS))
    create_parser.add_argument("--quotas", default="{}")
    create_parser.set_defaults(func=create_codes)

    list_parser = sub.add_parser("list-codes")
    list_parser.set_defaults(func=list_codes)

    key_parser = sub.add_parser("public-key")
    key_parser.set_defaults(func=lambda _args: print(public_key_b64()))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
