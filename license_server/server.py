#!/usr/bin/env python3
"""Small online activation server for OpenClaw Launcher."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

BASE_DIR = "/opt/openclaw-license"
DB_PATH = os.environ.get("LICENSE_DB", os.path.join(BASE_DIR, "license.db"))
BACKUP_DIR = os.environ.get("LICENSE_BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
PRIVATE_KEY_FILE = os.environ.get("LICENSE_PRIVATE_KEY_FILE", os.path.join(BASE_DIR, "private_key.b64"))
ADMIN_TOKEN_FILE = os.environ.get("LICENSE_ADMIN_TOKEN_FILE", os.path.join(BASE_DIR, "admin_token.txt"))
LOGO_FILE = os.environ.get("LICENSE_LOGO_FILE", os.path.join(BASE_DIR, "logo.ico"))
HOST = os.environ.get("LICENSE_HOST", "0.0.0.0")
PORT = int(os.environ.get("LICENSE_PORT", "18791"))
DEFAULT_FEATURES = ["openclaw", "image", "video", "storyboard"]
DEFAULT_GATEWAY_BASE_URL = os.environ.get("MEMBER_GATEWAY_BASE_URL", "").strip().rstrip("/")
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
    except OSError:
        return None


def public_key_b64() -> str:
    public = load_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public).decode("ascii")


def sign_license(payload: dict[str, Any]) -> dict[str, Any]:
    private_key = load_private_key()
    signature = private_key.sign(canonical(payload))
    license_data = dict(payload)
    license_data["signature"] = base64.b64encode(signature).decode("ascii")
    return license_data


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
    ensure_column(conn, "codes", "full_code", "text not null default ''")
    ensure_column(conn, "codes", "member_mode", "integer not null default 0")
    ensure_column(conn, "codes", "plan", "text not null default ''")
    ensure_column(conn, "codes", "gateway_base_url", "text not null default ''")
    ensure_column(conn, "codes", "gateway_token", "text not null default ''")
    ensure_column(conn, "codes", "gateway_image_token", "text not null default ''")
    ensure_column(conn, "codes", "gateway_video_token", "text not null default ''")
    ensure_column(conn, "codes", "gateway_default_model", "text not null default ''")
    ensure_column(conn, "codes", "gateway_image_model", "text not null default ''")
    ensure_column(conn, "codes", "gateway_video_model", "text not null default ''")
    ensure_column(conn, "codes", "gateway_models_json", "text not null default '[]'")
    ensure_column(conn, "codes", "quotas_json", "text not null default '{}'")
    ensure_column(conn, "plans", "gateway_base_url", "text not null default ''")
    ensure_column(conn, "plans", "gateway_token", "text not null default ''")
    ensure_column(conn, "plans", "gateway_image_token", "text not null default ''")
    ensure_column(conn, "plans", "gateway_video_token", "text not null default ''")
    ensure_column(conn, "plans", "gateway_default_model", "text not null default ''")
    ensure_column(conn, "plans", "gateway_image_model", "text not null default ''")
    ensure_column(conn, "plans", "gateway_video_model", "text not null default ''")
    ensure_column(conn, "plans", "gateway_models_json", "text not null default '[]'")
    ensure_column(conn, "plans", "quotas_json", "text not null default '{}'")
    seed_default_plans(conn)
    conn.commit()


def seed_default_plans(conn: sqlite3.Connection) -> None:
    existing = conn.execute("select count(*) from plans").fetchone()[0]
    if existing:
        return
    now = utc_now()
    defaults = [
        ("monthly", "月卡", 31, DEFAULT_FEATURES, {"image": 100, "video": 20}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
        ("quarterly", "季卡", 93, DEFAULT_FEATURES, {"image": 300, "video": 60}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
        ("yearly", "年卡", 366, DEFAULT_FEATURES, {"image": 1200, "video": 240}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
        ("vip_monthly", "VIP 月卡", 31, ["openclaw", "image", "video", "storyboard", "phoneAgent", "desktopAgent"], {"image": 300, "video": 80, "phoneAgent": True, "desktopAgent": True}, DEFAULT_GATEWAY_IMAGE_MODEL, DEFAULT_GATEWAY_VIDEO_MODEL),
    ]
    for plan_key, display_name, duration_days, features, quotas, gateway_image_model, gateway_video_model in defaults:
        conn.execute(
            """
            insert into plans (
                plan_key, display_name, duration_days, features_json, gateway_base_url,
                gateway_token, gateway_image_token, gateway_video_token,
                gateway_default_model, gateway_image_model, gateway_video_model,
                gateway_models_json, quotas_json,
                disabled, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                plan_key,
                display_name,
                duration_days,
                json.dumps(features, ensure_ascii=False),
                DEFAULT_GATEWAY_BASE_URL,
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
    gateway_token: str = "",
    gateway_image_token: str = "",
    gateway_video_token: str = "",
    gateway_default_model: str = "",
    gateway_image_model: str = "",
    gateway_video_model: str = "",
    gateway_models: list[str] | None = None,
    quotas: dict[str, Any] | None = None,
) -> list[str]:
    count = max(1, min(int(count), 100))
    max_activations = max(1, min(int(max_activations), 20))
    codes: list[str] = []
    with connect() as conn:
        for _ in range(count):
            code = make_code(edition)
            conn.execute(
                """
                insert into codes (
                    code_hash, code_label, full_code, licensee, edition, features_json, expires,
                    max_activations, disabled, member_mode, plan, gateway_base_url, gateway_token,
                    gateway_image_token, gateway_video_token,
                    gateway_default_model, gateway_image_model, gateway_video_model,
                    gateway_models_json, quotas_json, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    gateway_image_token.strip(),
                    gateway_video_token.strip(),
                    gateway_default_model.strip(),
                    gateway_image_model.strip(),
                    gateway_video_model.strip(),
                    json.dumps(gateway_models or [], ensure_ascii=False),
                    json.dumps(quotas or {}, ensure_ascii=False),
                    utc_now(),
                ),
            )
            codes.append(code)
        conn.commit()
    return codes


def update_code_record(body: dict[str, Any]) -> None:
    code_hash_value = str(body.get("codeHash", "")).strip()
    if not code_hash_value:
        raise ActivationError("缺少授权码标识")

    licensee = str(body.get("licensee", "OpenClaw Customer")).strip() or "OpenClaw Customer"
    edition = str(body.get("edition", "pro")).strip() or "pro"
    expires = str(body.get("expires", "")).strip()
    if not expires:
        raise ActivationError("请填写到期时间")

    max_activations = max(1, min(int(body.get("maxActivations", 1)), 999))
    features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
    member_mode = bool(body.get("memberMode"))
    plan = str(body.get("plan", "")).strip()
    gateway_base_url = str(body.get("gatewayBaseUrl", "")).strip().rstrip("/")
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
            select gateway_token, gateway_image_token, gateway_video_token,
                   gateway_image_model, gateway_video_model
            from codes
            where code_hash = ?
            """,
            (code_hash_value,),
        ).fetchone()
        if not existing:
            raise ActivationError("授权码不存在", 404)
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


def bulk_update_code_records(body: dict[str, Any]) -> int:
    code_hashes = body.get("codeHashes")
    if not isinstance(code_hashes, list):
        raise ActivationError("批量更新需要授权码列表")

    updated = 0
    with connect() as conn:
        rows = conn.execute(
            f"select * from codes where code_hash in ({','.join(['?'] * len(code_hashes))})",
            tuple(str(item).strip() for item in code_hashes),
        ).fetchall() if code_hashes else []

    for row in rows:
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
            "gatewayToken": str(body.get("gatewayToken") or "").strip(),
            "gatewayImageToken": str(body.get("gatewayImageToken") or body.get("gateway_image_token") or "").strip(),
            "gatewayVideoToken": str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or "").strip(),
            "gatewayDefaultModel": str(body.get("gatewayDefaultModel") or "").strip() or row["gateway_default_model"],
            "gatewayImageModel": str(body.get("gatewayImageModel") or body.get("gateway_image_model") or "").strip() or row["gateway_image_model"],
            "gatewayVideoModel": str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or "").strip() or row["gateway_video_model"],
            "gatewayModels": str(body.get("gatewayModels") or "").strip() or ",".join(load_json_value(row["gateway_models_json"], [])),
            "quotas": str(body.get("quotas") or "").strip() or row["quotas_json"] or "{}",
        }
        update_code_record(merged)
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
        "gatewayConfigured": bool(row["gateway_base_url"] and row["gateway_token"]),
        "gatewayImageConfigured": bool(row["gateway_base_url"] and (row["gateway_image_token"] or row["gateway_token"])),
        "gatewayVideoConfigured": bool(row["gateway_base_url"] and (row["gateway_video_token"] or row["gateway_token"])),
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


def upsert_plan_record(body: dict[str, Any]) -> dict[str, Any]:
    plan_key = normalize_plan_key(body.get("planKey") or body.get("plan") or body.get("key"))
    display_name = str(body.get("displayName") or body.get("name") or plan_key).strip() or plan_key
    duration_days = max(1, min(int(body.get("durationDays") or 31), 3660))
    features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
    gateway_base_url = str(body.get("gatewayBaseUrl", "")).strip().rstrip("/")
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
            select gateway_token, gateway_image_token, gateway_video_token,
                   gateway_image_model, gateway_video_model, created_at
            from plans
            where plan_key = ?
            """,
            (plan_key,),
        ).fetchone()
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
                gateway_token, gateway_image_token, gateway_video_token,
                gateway_default_model, gateway_image_model, gateway_video_model,
                gateway_models_json, quotas_json,
                disabled, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(plan_key) do update set
                display_name = excluded.display_name,
                duration_days = excluded.duration_days,
                features_json = excluded.features_json,
                gateway_base_url = excluded.gateway_base_url,
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
        "gatewayToken": masked_secret(row["gateway_token"]),
        "gatewayImageToken": masked_secret(row["gateway_image_token"]),
        "gatewayVideoToken": masked_secret(row["gateway_video_token"]),
        "gatewayDefaultModel": row["gateway_default_model"],
        "gatewayImageModel": row["gateway_image_model"],
        "gatewayVideoModel": row["gateway_video_model"],
        "gatewayModels": load_json_value(row["gateway_models_json"], []),
        "quotas": load_json_value(row["quotas_json"], {}),
        "activations": int(row["activations"]) if "activations" in row_keys else None,
        "createdAt": row["created_at"],
    }


def get_code_snapshot(code_hash_value: str) -> dict[str, Any] | None:
    if not code_hash_value:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            select c.*, count(a.id) as activations
            from codes c
            left join activations a on a.code_hash = c.code_hash
            where c.code_hash = ?
            group by c.code_hash
            """,
            (code_hash_value,),
        ).fetchone()
    return code_row_snapshot(row)


def get_code_snapshots(code_hashes: list[Any]) -> list[dict[str, Any]]:
    clean_hashes = [str(item).strip() for item in code_hashes if str(item).strip()]
    if not clean_hashes:
        return []
    placeholders = ",".join(["?"] * len(clean_hashes))
    with connect() as conn:
        rows = conn.execute(
            f"""
            select c.*, count(a.id) as activations
            from codes c
            left join activations a on a.code_hash = c.code_hash
            where c.code_hash in ({placeholders})
            group by c.code_hash
            order by c.created_at desc
            """,
            tuple(clean_hashes),
        ).fetchall()
    return [snapshot for row in rows if (snapshot := code_row_snapshot(row))]


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
            "before": load_json_value(row["before_json"], {}),
            "after": load_json_value(row["after_json"], {}),
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


def get_code_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select c.code_hash, c.code_label, c.full_code, c.licensee, c.edition, c.features_json, c.expires, c.max_activations,
                   c.disabled, c.member_mode, c.plan, c.gateway_base_url, c.gateway_token,
                   c.gateway_image_token, c.gateway_video_token, c.gateway_default_model,
                   c.gateway_image_model, c.gateway_video_model, c.gateway_models_json,
                   c.quotas_json, c.created_at, count(a.id) as activations
            from codes c
            left join activations a on a.code_hash = c.code_hash
            group by c.code_hash
            order by c.created_at desc
            """
        ).fetchall()
    return [
        {
            "codeHash": row["code_hash"],
            "codeLabel": row["code_label"],
            "fullCode": row["full_code"] or ("OC-" + row["edition"].upper() + "-" + row["code_label"]),
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
            "gatewayToken": masked_secret(row["gateway_token"]),
            "gatewayImageToken": masked_secret(row["gateway_image_token"]),
            "gatewayVideoToken": masked_secret(row["gateway_video_token"]),
            "gatewayDefaultModel": row["gateway_default_model"],
            "gatewayImageModel": row["gateway_image_model"],
            "gatewayVideoModel": row["gateway_video_model"],
            "gatewayModels": json.loads(row["gateway_models_json"] or "[]"),
            "quotas": json.loads(row["quotas_json"] or "{}"),
            "gatewayConfigured": bool(row["gateway_base_url"] and row["gateway_token"]),
            "gatewayImageConfigured": bool(row["gateway_base_url"] and (row["gateway_image_token"] or row["gateway_token"])),
            "gatewayVideoConfigured": bool(row["gateway_base_url"] and (row["gateway_video_token"] or row["gateway_token"])),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


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


def get_activation_rows(code_hash_value: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select id, code_hash, install_id, device_id, license_json, activated_at
            from activations
            where code_hash = ?
            order by activated_at desc
            """,
            (code_hash_value,),
        ).fetchall()
    return [activation_row_public(row) for row in rows]


def get_activation_snapshot(activation_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            select id, code_hash, install_id, device_id, license_json, activated_at
            from activations
            where id = ?
            """,
            (activation_id,),
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

    gateway_base_url = str(code_row["gateway_base_url"] or DEFAULT_GATEWAY_BASE_URL).strip().rstrip("/")
    gateway_token = str(code_row["gateway_token"] or DEFAULT_GATEWAY_TOKEN).strip()
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
    image_token = str(code_row["gateway_image_token"] or DEFAULT_GATEWAY_IMAGE_TOKEN or gateway_token).strip() or gateway_token
    video_token = str(code_row["gateway_video_token"] or DEFAULT_GATEWAY_VIDEO_TOKEN or gateway_token).strip() or gateway_token

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
        "features": json.loads(code_row["features_json"]),
        "expires": code_row["expires"],
        "installId": install_id,
        "deviceId": device_id,
        "activatedAt": activated_at or utc_now(),
        "activationCodeLabel": code_label,
        "activationCodeLast8": code_last8,
    }
    payload = apply_member_fields(payload, code_row)
    return sign_license(payload)


def member_response(license_data: dict[str, Any]) -> dict[str, Any]:
    gateway = {
        "baseUrl": license_data.get("gatewayBaseUrl"),
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

    def admin_actor(self) -> str:
        provided = (self.headers.get("X-Admin-Token") or "").strip()
        if not provided:
            return "admin"
        digest = hashlib.sha256(provided.encode("utf-8")).hexdigest()[:10]
        return f"admin:{digest}"

    def request_ip(self) -> str:
        return self.client_address[0] if self.client_address else ""

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/health":
            self.send_json(200, {"ok": True, "time": utc_now()})
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
        if path == "/admin/api/codes":
            if not self.require_admin():
                return
            self.send_json(200, {"codes": get_code_rows()})
            return
        if path == "/admin/api/plans":
            if not self.require_admin():
                return
            self.send_json(200, {"plans": get_plan_rows(include_disabled=True)})
            return
        if path == "/admin/api/codes/activations":
            if not self.require_admin():
                return
            query = parse_qs(parsed.query)
            code_hash_value = str((query.get("codeHash") or [""])[0]).strip()
            self.send_json(200, {"activations": get_activation_rows(code_hash_value)})
            return
        if path == "/admin/api/audit-logs":
            if not self.require_admin():
                return
            query = parse_qs(parsed.query)
            limit = int((query.get("limit") or ["100"])[0] or "100")
            self.send_json(200, {"logs": get_audit_rows(limit)})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/admin/api/codes":
            if not self.require_admin():
                return
            try:
                body = apply_plan_template(self.read_json())
                features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
                backup_path = make_db_backup("codes-create")
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
                    gateway_token=str(body.get("gatewayToken", "")).strip(),
                    gateway_image_token=str(body.get("gatewayImageToken") or body.get("gateway_image_token") or "").strip(),
                    gateway_video_token=str(body.get("gatewayVideoToken") or body.get("gateway_video_token") or "").strip(),
                    gateway_default_model=str(body.get("gatewayDefaultModel", "")).strip(),
                    gateway_image_model=str(body.get("gatewayImageModel") or body.get("gateway_image_model") or "").strip(),
                    gateway_video_model=str(body.get("gatewayVideoModel") or body.get("gateway_video_model") or "").strip(),
                    gateway_models=parse_models(body.get("gatewayModels", "")),
                    quotas=parse_json_object(body.get("quotas", "")),
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
                body = apply_plan_template(self.read_json())
                code_hash_value = str(body.get("codeHash", "")).strip()
                before = get_code_snapshot(code_hash_value)
                backup_path = make_db_backup("codes-update")
                update_code_record(body)
                after = get_code_snapshot(code_hash_value)
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
                body = apply_plan_template(self.read_json())
                code_hashes = body.get("codeHashes") if isinstance(body.get("codeHashes"), list) else []
                before = get_code_snapshots(code_hashes)
                backup_path = make_db_backup("codes-bulk-update")
                updated = bulk_update_code_records(body)
                after = get_code_snapshots(code_hashes)
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
            if not self.require_admin():
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
            if not self.require_admin():
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
                body = self.read_json()
                code_hash_value = str(body.get("codeHash", ""))
                disabled = 1 if body.get("disabled") else 0
                before = get_code_snapshot(code_hash_value)
                backup_path = make_db_backup("codes-toggle")
                with connect() as conn:
                    result = conn.execute("update codes set disabled = ? where code_hash = ?", (disabled, code_hash_value))
                    conn.commit()
                if result.rowcount == 0:
                    self.send_json(404, {"error": "授权码不存在"})
                else:
                    after = get_code_snapshot(code_hash_value)
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
            if not self.require_admin():
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
                body = self.read_json()
                code_hash_value = str(body.get("codeHash", ""))
                before = get_code_snapshot(code_hash_value)
                backup_path = make_db_backup("codes-delete")
                with connect() as conn:
                    conn.execute("delete from codes where code_hash = ?", (code_hash_value,))
                    conn.execute("delete from activations where code_hash = ?", (code_hash_value,))
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
                body = self.read_json()
                activation_id = int(body.get("id") or 0)
                before = get_activation_snapshot(activation_id)
                if before is None:
                    self.send_json(404, {"error": "激活记录不存在"})
                    return
                backup_path = make_db_backup("activations-delete")
                with connect() as conn:
                    conn.execute("delete from activations where id = ?", (activation_id,))
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
                self.send_json(error.status, {"error": str(error)})
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
            self.send_json(error.status, {"error": str(error)})
        except Exception as error:
            self.send_json(500, {"error": f"server error: {error}"})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        return json.loads(data.decode("utf-8-sig"))

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, status: int, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
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
        self.end_headers()
        self.wfile.write(data)

    def require_admin(self) -> bool:
        expected = load_admin_token()
        if not expected:
            self.send_json(503, {"error": "管理员后台未配置 Token"})
            return False
        provided = self.headers.get("X-Admin-Token", "")
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            provided = auth.split(" ", 1)[1]
        if not secrets.compare_digest(provided, expected):
            self.send_json(401, {"error": "管理员 Token 错误"})
            return False
        return True

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{utc_now()}] {self.address_string()} {fmt % args}")


class ActivationError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def activate_code(body: dict[str, Any]) -> dict[str, Any]:
    code = str(body.get("code", "")).strip().upper()
    install_id = str(body.get("installId", "")).strip()
    device_id = str(body.get("deviceId", "")).strip()
    if not code or not install_id:
        raise ActivationError("缺少授权码或安装 ID")

    hashed = code_hash(code)
    with connect() as conn:
        code_row = conn.execute("select * from codes where code_hash = ?", (hashed,)).fetchone()
        if not code_row:
            raise ActivationError("授权码不存在", 404)
        if code_row["disabled"]:
            raise ActivationError("授权码已停用", 403)
        existing = conn.execute("select * from activations where code_hash = ? and install_id = ?", (hashed, install_id)).fetchone()
        if existing:
            conn.execute("delete from activations where code_hash = ? and install_id = ?", (hashed, install_id))
        used_count = conn.execute("select count(*) as count from activations where code_hash = ?", (hashed,)).fetchone()["count"]
        if used_count >= code_row["max_activations"]:
            raise ActivationError("授权码已被其他设备激活", 403)
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
