"""Feishu/Lark lead-table integration for the acquisition workbench."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Dict

from core.paths import AppPaths


Json = Dict[str, Any]
LEAD_TABLE_FIELDS = [
    "来源平台",
    "来源任务",
    "客户昵称/账号",
    "主页或内容链接",
    "原始线索内容",
    "痛点/需求",
    "意向等级",
    "推荐跟进动作",
    "跟进话术草稿",
    "状态",
    "负责人",
    "创建时间",
    "更新时间",
    "任务日志 ID",
]


class FeishuAcquisitionIntegration:
    def __init__(
        self,
        paths: AppPaths,
        *,
        command_resolver: Callable[[str], str | None] | None = None,
        runner: Callable[..., Json] | None = None,
    ):
        self.paths = paths
        self.command_resolver = command_resolver or shutil.which
        self.runner = runner or _run_command

    @property
    def state_path(self) -> str:
        return os.path.join(self.paths.launcher_dir, "feishu-acquisition.json")

    def doctor(self) -> Json:
        cli_path = self._cli_path()
        version = ""
        if cli_path:
            completed = self.runner(["lark-cli", "--version"], timeout=8)
            if _returncode(completed) == 0:
                version = _redact((completed.get("stdout") or "").strip())
        status = self.status()
        return {
            "schema": "loom.feishu_acquisition.doctor.v1",
            "cli": {
                "installed": bool(cli_path),
                "path": _redact_path(cli_path),
                "version": version,
                "installCommand": "npm install -g @larksuite/cli@latest",
                "requiresInstallConfirmation": not bool(cli_path),
            },
            "auth": status["auth"],
            "table": status["table"],
            "connected": status["connected"],
        }

    def install_cli(self, *, confirmed: bool = False) -> Json:
        if self._cli_path():
            return {"installed": True, "executed": False, "message": "lark-cli already available"}
        command = ["npm", "install", "-g", "@larksuite/cli@latest"]
        if not confirmed:
            return {"installed": False, "executed": False, "requiresConfirmation": True, "command": " ".join(command)}
        completed = self.runner(command, timeout=600)
        ok = _returncode(completed) == 0
        return {
            "installed": ok,
            "executed": True,
            "command": " ".join(command),
            "error": "" if ok else _redact(completed.get("stderr") or completed.get("stdout") or "install failed"),
        }

    def status(self) -> Json:
        state = self._load_state()
        auth = self._auth_status()
        table = state.get("table") if isinstance(state.get("table"), dict) else {}
        connected = bool(self._cli_path() and auth.get("loggedIn") and table.get("baseToken") and table.get("tableId"))
        return {
            "schema": "loom.feishu_acquisition.status.v1",
            "cliInstalled": bool(self._cli_path()),
            "auth": auth,
            "table": _redact_json(table),
            "connected": connected,
            "lastSync": _redact_json(state.get("lastSync") if isinstance(state.get("lastSync"), dict) else {}),
            "pendingCount": len(self.pending_syncs()),
        }

    def start_login(self) -> Json:
        self._require_cli()
        completed = self.runner(["lark-cli", "auth", "login", "--recommend", "--no-wait", "--json"], timeout=30)
        if _returncode(completed) != 0:
            return {"ok": False, "error": _redact(completed.get("stderr") or completed.get("stdout") or "login failed")}
        payload = _json_loads(completed.get("stdout") or "{}")
        login_url = str(payload.get("verification_uri_complete") or payload.get("verification_url") or payload.get("verification_uri") or "")
        user_code = str(payload.get("user_code") or "")
        qr_ascii = ""
        if login_url:
            qr = self.runner(["lark-cli", "auth", "qrcode", login_url, "--ascii"], timeout=20)
            if _returncode(qr) == 0:
                qr_ascii = _redact(qr.get("stdout") or "")
        return {
            "ok": bool(login_url),
            "loginUrl": _redact_url(login_url),
            "verificationUrl": _redact_url(str(payload.get("verification_uri") or "")),
            "userCode": user_code,
            "qrAscii": qr_ascii,
            "message": "请用飞书扫码或打开登录链接完成授权。",
        }

    def bind_table(self, raw: Json) -> Json:
        state = self._load_state()
        table = {
            "url": _redact_url(str(raw.get("url") or "")),
            "baseToken": _clip(raw.get("baseToken") or _extract_base_token(raw.get("url")), 120),
            "tableId": _clip(raw.get("tableId") or _extract_table_id(raw.get("url")), 120),
            "name": _clip(raw.get("name") or "麓鸣获客线索表", 120),
            "boundAt": _now_iso(),
            "fields": LEAD_TABLE_FIELDS,
        }
        state["table"] = table
        state["updatedAt"] = _now_iso()
        self._write_state(state)
        return {"table": _redact_json(table), "status": self.status()}

    def create_table(self, *, confirmed: bool = False) -> Json:
        self._require_cli()
        if not confirmed:
            return {"requiresConfirmation": True, "executed": False, "name": "麓鸣获客线索表", "fields": LEAD_TABLE_FIELDS}
        fields = json.dumps([{"name": name, "type": "text"} for name in LEAD_TABLE_FIELDS], ensure_ascii=False)
        completed = self.runner(
            [
                "lark-cli",
                "base",
                "+base-create",
                "--name",
                "麓鸣获客线索表",
                "--table-name",
                "线索池",
                "--fields",
                fields,
                "--as",
                "user",
                "--format",
                "json",
            ],
            timeout=120,
        )
        ok = _returncode(completed) == 0
        payload = _json_loads(completed.get("stdout") or "{}")
        if ok:
            base_token = str(payload.get("app_token") or payload.get("base_token") or payload.get("token") or "")
            table_id = _first_table_id(payload)
            if base_token and table_id:
                self.bind_table({"baseToken": base_token, "tableId": table_id, "url": ""})
        return {"ok": ok, "result": _redact_json(payload), "error": "" if ok else _redact(completed.get("stderr") or "")}

    def test_write(self) -> Json:
        lead = {
            "leadId": f"test_{int(time.time())}",
            "platform": "dry-run",
            "sourceTask": "飞书测试写入",
            "title": "测试客户",
            "summary": "这是一条麓鸣获客线索表测试记录",
            "need": "验证字段和权限",
            "intentLevel": "测试",
            "recommendedAction": "确认表格能写入",
            "draft": "这是一条测试草稿，不会触达真实客户。",
            "status": "test",
            "owner": "麓鸣",
            "logId": "test-write",
        }
        return self.sync_lead(lead)

    def sync_lead(self, lead: Json) -> Json:
        safe_lead = _lead_fields(lead)
        state = self._load_state()
        table = state.get("table") if isinstance(state.get("table"), dict) else {}
        if not self._cli_path() or not table.get("baseToken") or not table.get("tableId"):
            return self._cache_pending(safe_lead, "pending_sync", "飞书未连接或未绑定线索表")
        completed = self.runner(
            [
                "lark-cli",
                "base",
                "+record-upsert",
                "--base-token",
                str(table.get("baseToken")),
                "--table-id",
                str(table.get("tableId")),
                "--json",
                json.dumps(safe_lead["fields"], ensure_ascii=False),
                "--as",
                "user",
                "--format",
                "json",
            ],
            timeout=60,
        )
        ok = _returncode(completed) == 0
        payload = _json_loads(completed.get("stdout") or "{}")
        record_id = str(payload.get("record_id") or payload.get("recordId") or payload.get("id") or "")
        if ok:
            result = {
                "leadId": safe_lead["leadId"],
                "syncStatus": "synced",
                "recordId": record_id,
                "syncedAt": _now_iso(),
            }
            state["lastSync"] = result
            self._write_state(state)
            return _redact_json(result)
        error = _redact(completed.get("stderr") or completed.get("stdout") or "飞书写入失败")
        return self._cache_pending(safe_lead, "sync_failed", error)

    def pending_syncs(self) -> list[Json]:
        state = self._load_state()
        rows = state.get("pendingSync")
        return _redact_json(rows if isinstance(rows, list) else [])

    def retry_pending(self) -> Json:
        rows = self.pending_syncs()
        state = self._load_state()
        state["pendingSync"] = []
        self._write_state(state)
        results = [self.sync_lead(row) for row in rows]
        return {"retried": len(rows), "results": results, "status": self.status()}

    def _cache_pending(self, safe_lead: Json, status: str, error: str) -> Json:
        state = self._load_state()
        pending = state.get("pendingSync")
        if not isinstance(pending, list):
            pending = []
        row = {
            "leadId": safe_lead["leadId"],
            "fields": safe_lead["fields"],
            "syncStatus": status,
            "syncError": _redact(error)[:240],
            "updatedAt": _now_iso(),
        }
        pending = [item for item in pending if not isinstance(item, dict) or item.get("leadId") != row["leadId"]]
        pending.append(row)
        state["pendingSync"] = pending[-500:]
        state["lastSync"] = row
        state["updatedAt"] = _now_iso()
        self._write_state(state)
        return _redact_json({"leadId": row["leadId"], "syncStatus": status, "syncError": row["syncError"]})

    def _auth_status(self) -> Json:
        if not self._cli_path():
            return {"loggedIn": False, "botReady": False, "message": "lark-cli 未安装"}
        try:
            completed = self.runner(["lark-cli", "auth", "status"], timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"loggedIn": False, "botReady": False, "message": _redact(exc)}
        text = (completed.get("stdout") or "").strip()
        data = _json_loads(text)
        user = data.get("identities", {}).get("user", {}) if isinstance(data.get("identities"), dict) else {}
        bot = data.get("identities", {}).get("bot", {}) if isinstance(data.get("identities"), dict) else {}
        return {
            "loggedIn": bool(user.get("available") and user.get("status") == "ready"),
            "botReady": bool(bot.get("available") and bot.get("status") == "ready"),
            "identity": str(data.get("identity") or ""),
            "userName": _clip(user.get("userName") or data.get("userName"), 80),
            "message": _redact(str(user.get("message") or data.get("note") or text[:160])),
        }

    def _require_cli(self) -> None:
        if not self._cli_path():
            raise RuntimeError("lark-cli is not installed")

    def _cli_path(self) -> str:
        return str(self.command_resolver("lark-cli") or "").strip()

    def _load_state(self) -> Json:
        if not os.path.exists(self.state_path):
            return {"schema": "loom.feishu_acquisition.v1", "updatedAt": "", "table": {}, "pendingSync": [], "lastSync": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {"schema": "loom.feishu_acquisition.v1", "updatedAt": "", "table": {}, "pendingSync": [], "lastSync": {}}

    def _write_state(self, state: Json) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        state["schema"] = "loom.feishu_acquisition.v1"
        tmp = f"{self.state_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(_redact_json(state), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, self.state_path)


def _run_command(args: list[str], *, timeout: int = 30) -> Json:
    run_args = list(args)
    if args and args[0] == "lark-cli":
        resolved = shutil.which("lark-cli")
        if resolved:
            run_args[0] = resolved
    completed = subprocess.run(
        run_args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {"returncode": completed.returncode, "stdout": completed.stdout or "", "stderr": completed.stderr or ""}


def _lead_fields(lead: Json) -> Json:
    now = _now_iso()
    lead_id = _clip(lead.get("leadId") or lead.get("id") or f"lead_{int(time.time())}", 80)
    fields = {
        "来源平台": _clip(lead.get("platform") or lead.get("sourcePlatform") or lead.get("source") or "manual", 120),
        "来源任务": _clip(lead.get("sourceTask") or lead.get("campaignId") or lead.get("title") or "", 180),
        "客户昵称/账号": _clip(lead.get("nickname") or lead.get("account") or lead.get("title") or "潜在线索", 160),
        "主页或内容链接": _redact_url(str(lead.get("profileUrl") or lead.get("contentUrl") or lead.get("url") or "")),
        "原始线索内容": _clip(lead.get("rawContent") or lead.get("summary") or lead.get("description") or "", 500),
        "痛点/需求": _clip(lead.get("need") or lead.get("painPoint") or lead.get("summary") or "", 300),
        "意向等级": _clip(lead.get("intentLevel") or "待判断", 80),
        "推荐跟进动作": _clip(lead.get("recommendedAction") or "生成草稿后人工确认", 240),
        "跟进话术草稿": _clip(lead.get("draft") or lead.get("draftBody") or "", 500),
        "状态": _clip(lead.get("status") or "new", 80),
        "负责人": _clip(lead.get("owner") or "", 80),
        "创建时间": _clip(lead.get("createdAt") or now, 80),
        "更新时间": _clip(lead.get("updatedAt") or now, 80),
        "任务日志 ID": _clip(lead.get("logId") or lead.get("taskLogId") or lead_id, 120),
    }
    return {"leadId": lead_id, "fields": _redact_json(fields)}


def _json_loads(text: str) -> Json:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _returncode(completed: Json) -> int:
    value = completed.get("returncode")
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _first_table_id(payload: Json) -> str:
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    for item in tables:
        if isinstance(item, dict) and item.get("table_id"):
            return str(item.get("table_id"))
    table = payload.get("table") if isinstance(payload.get("table"), dict) else {}
    return str(table.get("table_id") or payload.get("table_id") or "")


def _extract_base_token(url: Any) -> str:
    match = re.search(r"/base/([A-Za-z0-9_]+)", str(url or ""))
    return match.group(1) if match else ""


def _extract_table_id(url: Any) -> str:
    match = re.search(r"(?:table=|[?&]table_id=)(tbl[A-Za-z0-9_]+)", str(url or ""))
    return match.group(1) if match else ""


def _clip(value: Any, limit: int) -> str:
    return _redact(str(value or "").strip())[:limit]


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        safe: Json = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if str(key) != "baseToken" and any(mark in lowered for mark in ("token", "secret", "password", "credential", "device_code", "refresh")):
                continue
            safe[key] = _redact_json(item)
        return safe
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    return value


def _redact_path(path: str) -> str:
    return _redact(path)


def _redact_url(value: str) -> str:
    text = _redact(value)
    return re.sub(r"([?&](?:token|secret|key|device_code|refresh_token)=)[^&]+", r"\1***", text, flags=re.I)


def _redact(text: Any) -> str:
    value = str(text or "")
    value = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", value, flags=re.I)
    value = re.sub(r"\b1[3-9]\d{9}\b", "[手机号已隐藏]", value)
    value = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[邮箱已隐藏]", value)
    value = re.sub(r"(secret|token|password|credential)[-_:= ]+[A-Za-z0-9._\-]+", r"\1=***", value, flags=re.I)
    return value


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")
