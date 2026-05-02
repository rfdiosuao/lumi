#!/usr/bin/env python3
"""Small online activation server for OpenClaw Launcher."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

BASE_DIR = "/opt/openclaw-license"
DB_PATH = os.environ.get("LICENSE_DB", os.path.join(BASE_DIR, "license.db"))
PRIVATE_KEY_FILE = os.environ.get("LICENSE_PRIVATE_KEY_FILE", os.path.join(BASE_DIR, "private_key.b64"))
ADMIN_TOKEN_FILE = os.environ.get("LICENSE_ADMIN_TOKEN_FILE", os.path.join(BASE_DIR, "admin_token.txt"))
LOGO_FILE = os.environ.get("LICENSE_LOGO_FILE", os.path.join(BASE_DIR, "logo.ico"))
HOST = os.environ.get("LICENSE_HOST", "0.0.0.0")
PORT = int(os.environ.get("LICENSE_PORT", "18791"))
DEFAULT_FEATURES = ["openclaw", "image", "video", "storyboard"]
ADMIN_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" href="logo.ico" />
  <title>OpenClaw 授权管理</title>
  <style>
    :root {
      --bg: #0d1117;
      --panel: #151b23;
      --panel-2: #1f2630;
      --ink: #f4efe7;
      --muted: #9aa4b2;
      --line: #2c3542;
      --accent: #21b7a8;
      --accent-2: #f1b84b;
      --danger: #ee6a5f;
      --ok: #72d39a;
      --shadow: 0 24px 70px rgba(0,0,0,.34);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px),
        linear-gradient(135deg, #0d1117 0%, #17140f 100%);
      background-size: 44px 44px, 44px 44px, auto;
      color: var(--ink);
      font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    }
    button, input, select { font: inherit; }
    .shell { max-width: 1180px; margin: 0 auto; padding: 32px; }
    header { display: flex; justify-content: space-between; gap: 18px; align-items: center; margin-bottom: 22px; }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-logo { width: 46px; height: 46px; border-radius: 8px; box-shadow: 0 12px 28px rgba(0,0,0,.26); }
    h1 { margin: 0; font-size: 28px; letter-spacing: 0; }
    .sub { margin-top: 6px; color: var(--muted); font-size: 14px; }
    .badge { padding: 9px 13px; border: 1px solid var(--line); background: rgba(255,255,255,.04); color: var(--muted); border-radius: 8px; }
    .grid { display: grid; grid-template-columns: 360px 1fr; gap: 18px; align-items: start; }
    .card { background: rgba(21,27,35,.94); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); overflow: hidden; }
    .card h2 { margin: 0; font-size: 16px; padding: 18px 18px 0; }
    .card-body { padding: 18px; }
    label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 7px; }
    input, select {
      width: 100%;
      border: 1px solid var(--line);
      color: var(--ink);
      background: #0f141b;
      border-radius: 8px;
      padding: 11px 12px;
      outline: none;
    }
    input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(33,183,168,.12); }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .form-line { margin-bottom: 13px; }
    .btn {
      border: 0;
      border-radius: 8px;
      padding: 11px 14px;
      cursor: pointer;
      color: #031412;
      background: var(--accent);
      font-weight: 700;
    }
    .btn.secondary { color: var(--ink); background: var(--panel-2); border: 1px solid var(--line); }
    .btn.danger { color: white; background: var(--danger); }
    .btn:disabled { opacity: .55; cursor: wait; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }
    .stat { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
    .stat strong { display: block; font-size: 22px; margin-bottom: 3px; }
    .stat span { color: var(--muted); font-size: 12px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--line); padding: 11px 8px; text-align: left; font-size: 13px; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; font-weight: 600; background: #111821; position: sticky; top: 0; }
    .table-wrap { max-height: 610px; overflow: auto; }
    .pill { display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 8px; font-size: 12px; border: 1px solid var(--line); color: var(--muted); }
    .pill.ok { color: var(--ok); border-color: rgba(114,211,154,.35); }
    .pill.bad { color: var(--danger); border-color: rgba(238,106,95,.35); }
    .codes { display: none; margin-top: 14px; background: #0f141b; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
    .codes pre { margin: 0; white-space: pre-wrap; word-break: break-all; color: var(--accent-2); }
    .auth {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      margin-bottom: 18px;
      background: rgba(255,255,255,.04);
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .toast { min-height: 22px; color: var(--muted); margin-top: 10px; font-size: 13px; }
    @media (max-width: 900px) {
      .shell { padding: 18px; }
      .grid, .stats { grid-template-columns: 1fr; }
      header { display: block; }
      .badge { display: inline-block; margin-top: 12px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div class="brand">
        <img class="brand-logo" src="logo.ico" alt="OpenClaw" />
        <div>
          <h1>OpenClaw 授权管理</h1>
          <div class="sub">生成、查看、停用授权码。授权码明文只在生成时显示一次。</div>
        </div>
      </div>
      <div class="badge" id="serverState">未连接</div>
    </header>

    <div class="auth">
      <input id="token" type="password" placeholder="管理员 Token" autocomplete="current-password" />
      <button class="btn secondary" id="saveToken">保存 Token</button>
    </div>

    <div class="grid">
      <section class="card">
        <h2>生成授权码</h2>
        <div class="card-body">
          <div class="form-line">
            <label>客户名称</label>
            <input id="licensee" value="OpenClaw Customer" />
          </div>
          <div class="row">
            <div class="form-line">
              <label>版本</label>
              <select id="edition">
                <option value="pro">pro</option>
                <option value="basic">basic</option>
                <option value="enterprise">enterprise</option>
              </select>
            </div>
            <div class="form-line">
              <label>数量</label>
              <input id="count" type="number" min="1" max="100" value="1" />
            </div>
          </div>
          <div class="row">
            <div class="form-line">
              <label>到期日期</label>
              <input id="expires" type="date" value="2027-05-01" />
            </div>
            <div class="form-line">
              <label>每码激活次数</label>
              <input id="maxActivations" type="number" min="1" max="20" value="1" />
            </div>
          </div>
          <div class="form-line">
            <label>功能</label>
            <input id="features" value="openclaw,image,video,storyboard" />
          </div>
          <button class="btn" id="createCode">生成授权码</button>
          <button class="btn secondary" id="refresh" style="margin-left:8px">刷新列表</button>
          <div class="toast" id="toast"></div>
          <div class="codes" id="codesBox"><pre id="codes"></pre></div>
        </div>
      </section>

      <section>
        <div class="stats" id="stats">
          <div class="stat"><strong>0</strong><span>授权码</span></div>
          <div class="stat"><strong>0</strong><span>已激活</span></div>
          <div class="stat"><strong>0</strong><span>可用</span></div>
          <div class="stat"><strong>0</strong><span>停用</span></div>
        </div>
        <section class="card">
          <h2>授权码列表</h2>
          <div class="card-body table-wrap">
            <table>
              <thead><tr><th>尾号</th><th>客户</th><th>版本</th><th>到期</th><th>激活</th><th>功能</th><th>状态</th><th>操作</th></tr></thead>
              <tbody id="rows"><tr><td colspan="8">请输入管理员 Token 后刷新。</td></tr></tbody>
            </table>
          </div>
        </section>
      </section>
    </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const adminBase = window.location.pathname.replace(/\/admin\/?$/, "/admin");
    const tokenInput = $("token");
    tokenInput.value = localStorage.getItem("openclawAdminToken") || "";

    function token() { return tokenInput.value.trim(); }
    function setToast(text, bad=false) {
      $("toast").textContent = text;
      $("toast").style.color = bad ? "var(--danger)" : "var(--muted)";
    }
    async function api(path, options={}) {
      const response = await fetch(`${adminBase}/${path.replace(/^\/+/, "")}`, {
        ...options,
        headers: {
          "Content-Type": "application/json",
          "X-Admin-Token": token(),
          ...(options.headers || {})
        }
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
      return data;
    }
    function renderStats(items) {
      const total = items.length;
      const used = items.filter(x => x.activations > 0).length;
      const disabled = items.filter(x => x.disabled).length;
      const available = items.filter(x => !x.disabled && x.activations < x.maxActivations).length;
      $("stats").innerHTML = [
        [total, "授权码"],
        [used, "已激活"],
        [available, "可用"],
        [disabled, "停用"]
      ].map(([num, label]) => `<div class="stat"><strong>${num}</strong><span>${label}</span></div>`).join("");
    }
    function escapeHtml(text) {
      return String(text ?? "").replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    }
    async function loadCodes() {
      try {
        $("serverState").textContent = "连接中";
        const data = await api("api/codes");
        const items = data.codes || [];
        renderStats(items);
        $("rows").innerHTML = items.length ? items.map(item => `
          <tr>
            <td><code>${escapeHtml(item.codeLabel)}</code></td>
            <td>${escapeHtml(item.licensee)}</td>
            <td>${escapeHtml(item.edition)}</td>
            <td>${escapeHtml(item.expires)}</td>
            <td>${item.activations}/${item.maxActivations}</td>
            <td>${escapeHtml((item.features || []).join(", "))}</td>
            <td><span class="pill ${item.disabled ? "bad" : "ok"}">${item.disabled ? "停用" : "启用"}</span></td>
            <td><button class="btn ${item.disabled ? "secondary" : "danger"}" onclick="toggleCode('${item.codeHash}', ${item.disabled ? "false" : "true"})">${item.disabled ? "启用" : "停用"}</button></td>
          </tr>
        `).join("") : `<tr><td colspan="8">还没有授权码。</td></tr>`;
        $("serverState").textContent = "已连接";
      } catch (error) {
        $("serverState").textContent = "未授权";
        setToast(error.message, true);
      }
    }
    async function createCode() {
      try {
        $("createCode").disabled = true;
        const payload = {
          licensee: $("licensee").value.trim(),
          edition: $("edition").value,
          count: Number($("count").value || 1),
          expires: $("expires").value,
          maxActivations: Number($("maxActivations").value || 1),
          features: $("features").value
        };
        const data = await api("api/codes", { method: "POST", body: JSON.stringify(payload) });
        $("codesBox").style.display = "block";
        $("codes").textContent = data.codes.join("\\n");
        setToast(`已生成 ${data.codes.length} 个授权码。请立刻保存，之后后台不再显示完整授权码。`);
        await loadCodes();
      } catch (error) {
        setToast(error.message, true);
      } finally {
        $("createCode").disabled = false;
      }
    }
    async function toggleCode(codeHash, disabled) {
      try {
        await api("api/codes/toggle", { method: "POST", body: JSON.stringify({ codeHash, disabled }) });
        await loadCodes();
      } catch (error) {
        setToast(error.message, true);
      }
    }
    $("saveToken").onclick = () => {
      localStorage.setItem("openclawAdminToken", token());
      setToast("Token 已保存到本浏览器。");
      loadCodes();
    };
    $("createCode").onclick = createCode;
    $("refresh").onclick = loadCodes;
    if (token()) loadCodes();
  </script>
</body>
</html>
"""


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


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists codes (
            code_hash text primary key,
            code_label text not null,
            licensee text not null,
            edition text not null,
            features_json text not null,
            expires text not null,
            max_activations integer not null default 1,
            disabled integer not null default 0,
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
    conn.commit()


def make_code(edition: str = "PRO") -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    chunks = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4)]
    return f"OC-{edition.upper()}-" + "-".join(chunks)


def parse_features(raw: str) -> list[str]:
    features = [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    return features or DEFAULT_FEATURES


def create_code_records(
    *,
    count: int,
    licensee: str,
    edition: str,
    features: list[str],
    expires: str,
    max_activations: int,
) -> list[str]:
    count = max(1, min(int(count), 100))
    max_activations = max(1, min(int(max_activations), 20))
    codes: list[str] = []
    with connect() as conn:
        for _ in range(count):
            code = make_code(edition)
            conn.execute(
                """
                insert into codes (code_hash, code_label, licensee, edition, features_json, expires, max_activations, disabled, created_at)
                values (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    code_hash(code),
                    code[-9:],
                    licensee,
                    edition,
                    json.dumps(features, ensure_ascii=False),
                    expires,
                    max_activations,
                    utc_now(),
                ),
            )
            codes.append(code)
        conn.commit()
    return codes


def create_codes(args: argparse.Namespace) -> None:
    features = args.features.split(",") if args.features else DEFAULT_FEATURES
    for code in create_code_records(
        count=args.count,
        licensee=args.licensee,
        edition=args.edition,
        features=features,
        expires=args.expires,
        max_activations=args.max_activations,
    ):
        print(code)


def get_code_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            select c.code_hash, c.code_label, c.licensee, c.edition, c.features_json, c.expires, c.max_activations,
                   c.disabled, c.created_at, count(a.id) as activations
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
            "licensee": row["licensee"],
            "edition": row["edition"],
            "features": json.loads(row["features_json"]),
            "expires": row["expires"],
            "maxActivations": row["max_activations"],
            "activations": row["activations"],
            "disabled": bool(row["disabled"]),
            "createdAt": row["created_at"],
        }
        for row in rows
    ]


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


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenClawLicense/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
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
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/admin/api/codes":
            if not self.require_admin():
                return
            try:
                body = self.read_json()
                features = parse_features(str(body.get("features", ",".join(DEFAULT_FEATURES))))
                codes = create_code_records(
                    count=int(body.get("count", 1)),
                    licensee=str(body.get("licensee", "客户")).strip() or "客户",
                    edition=str(body.get("edition", "pro")).strip() or "pro",
                    features=features,
                    expires=str(body.get("expires", "2027-05-01")).strip() or "2027-05-01",
                    max_activations=int(body.get("maxActivations", 1)),
                )
                self.send_json(200, {"codes": codes})
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
                with connect() as conn:
                    result = conn.execute("update codes set disabled = ? where code_hash = ?", (disabled, code_hash_value))
                    conn.commit()
                if result.rowcount == 0:
                    self.send_json(404, {"error": "授权码不存在"})
                else:
                    self.send_json(200, {"ok": True})
            except Exception as error:
                self.send_json(400, {"error": str(error)})
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
        return json.loads(data.decode("utf-8"))

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
            return json.loads(existing["license_json"])
        used_count = conn.execute("select count(*) as count from activations where code_hash = ?", (hashed,)).fetchone()["count"]
        if used_count >= code_row["max_activations"]:
            raise ActivationError("授权码已被其他设备激活", 403)
        payload = {
            "licenseId": secrets.token_hex(12),
            "licensee": code_row["licensee"],
            "edition": code_row["edition"],
            "features": json.loads(code_row["features_json"]),
            "expires": code_row["expires"],
            "installId": install_id,
            "deviceId": device_id,
            "activatedAt": utc_now(),
        }
        license_data = sign_license(payload)
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
    create_parser.set_defaults(func=create_codes)

    list_parser = sub.add_parser("list-codes")
    list_parser.set_defaults(func=list_codes)

    key_parser = sub.add_parser("public-key")
    key_parser.set_defaults(func=lambda _args: print(public_key_b64()))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
