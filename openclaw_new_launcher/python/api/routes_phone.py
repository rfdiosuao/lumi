"""Phone demo configuration routes.

These endpoints only manage the launcher-side APKClaw connection store. They
never return phone tokens to the frontend.
"""

from __future__ import annotations

import os
import re
import json
import subprocess
from urllib.parse import urlparse

from fastapi import Request


_DEVICE_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
_PHONE_SCRIPT_TIMEOUT_SEC = 240
_SYNC_SECRET_KEYS = {
    "apiKey",
    "api_key",
    "accessToken",
    "access_token",
    "memberToken",
    "sessionCookie",
    "launcherToken",
    "password",
    "secret",
    "token",
}


def _phone_store_path(ctx) -> str:
    return os.path.join(ctx.paths.launcher_dir, "phone-agents.json")


def _clip(value: object, limit: int = 256) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _normalize_url(value: object) -> str:
    text = _clip(value, 512).rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("手机地址必须是 http:// 或 https:// 开头的完整地址")
    return text


def _normalize_device_id(value: object, fallback: str = "phone-1") -> str:
    text = _clip(value, 80)
    text = _DEVICE_ID_RE.sub("-", text).strip(".-_")
    return text or fallback


def _public_device(device: dict) -> dict:
    token = str(device.get("token") or "").strip()
    launcher_id = str(device.get("launcherId") or "").strip()
    launcher_secret = str(device.get("launcherSecret") or "").strip()
    return {
        "id": str(device.get("id") or "").strip(),
        "name": str(device.get("name") or "").strip(),
        "baseUrl": str(device.get("baseUrl") or "").strip().rstrip("/"),
        "tokenAvailable": bool(token),
        "paired": bool(launcher_id and launcher_secret),
        "album": str(device.get("album") or "").strip(),
        "lastSeenAt": str(device.get("lastSeenAt") or "").strip(),
    }


def _public_store(store: dict) -> dict:
    devices = [item for item in store.get("devices", []) if isinstance(item, dict)]
    selected = str(store.get("selectedDeviceId") or "").strip()
    if not any(str(item.get("id") or "").strip() == selected for item in devices):
        selected = str(devices[0].get("id") or "").strip() if devices else ""
    return {
        "selectedDeviceId": selected,
        "devices": [_public_device(item) for item in devices],
        "configured": any(str(item.get("baseUrl") or "").strip() and str(item.get("token") or "").strip() for item in devices),
    }


def _script_path(ctx, script_name: str) -> str:
    return os.path.join(ctx.paths.base_path, "scripts", script_name)


def _safe_prompt(value: object) -> str:
    text = str(value or "").strip()
    if "\x00" in text:
        raise ValueError("任务内容包含非法字符")
    return text[:2000]


def _sanitize(ctx, text: str) -> str:
    sanitizer = getattr(ctx, "sanitize_text", None)
    if callable(sanitizer):
        return sanitizer(text)
    return text


def _sanitize_cli_output(ctx, text: str, *, kind: str) -> str:
    cleaned = _drop_embedded_images(text, kind=kind)
    return _sanitize(ctx, cleaned)


def _drop_embedded_images(text: object, *, kind: str) -> str:
    raw = str(text or "")
    if not raw.strip():
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _redact_inline_image_payloads(raw)
    safe = _safe_cli_payload(payload, screenshot_only=(kind == "phone.screenshot"))
    return json.dumps(safe, ensure_ascii=False)


def _safe_cli_payload(value, *, screenshot_only: bool = False):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            key_text = str(key)
            lower = key_text.lower()
            if lower in {"base64", "dataurl", "data_url", "imagedata", "image_data"}:
                safe[key_text] = "[image omitted]"
                continue
            if lower in {"image", "screenshot"} and isinstance(item, (dict, str)):
                safe[key_text] = _image_summary(item)
                continue
            if screenshot_only and lower == "frame" and isinstance(item, dict):
                frame = _safe_cli_payload(item, screenshot_only=True)
                if isinstance(frame, dict):
                    frame.pop("image", None)
                    frame["imageOmitted"] = True
                safe[key_text] = frame
                continue
            safe[key_text] = _safe_cli_payload(item, screenshot_only=screenshot_only)
        return safe
    if isinstance(value, list):
        return [_safe_cli_payload(item, screenshot_only=screenshot_only) for item in value]
    if isinstance(value, str):
        return _redact_inline_image_payloads(value)
    return value


def _image_summary(value) -> dict:
    if isinstance(value, dict):
        return {
            "omitted": True,
            "mime": str(value.get("mime") or value.get("type") or "").strip(),
            "width": value.get("width"),
            "height": value.get("height"),
        }
    return {"omitted": True}


def _redact_inline_image_payloads(text: str) -> str:
    text = re.sub(r"data:image/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=\r\n]+", "[image omitted]", text, flags=re.I)
    return re.sub(r'"base64"\s*:\s*"[^"]+"', '"base64":"[image omitted]"', text, flags=re.I)


def _submit_phone_job(
    ctx,
    *,
    kind: str,
    label: str,
    script_name: str,
    args: list[str],
    timeout_sec: int = _PHONE_SCRIPT_TIMEOUT_SEC,
):
    script_path = _script_path(ctx, script_name)
    if not os.path.exists(script_path):
        return ctx.fastapi_json({"error": "手机能力脚本缺失"}, 404)
    node_exe = str(getattr(ctx.paths, "node_exe", "") or "")
    if not node_exe or not os.path.exists(node_exe):
        return ctx.fastapi_json({"error": "Node.js 运行时缺失，无法执行手机任务"}, 500)
    timeout_sec = max(5, min(int(timeout_sec or _PHONE_SCRIPT_TIMEOUT_SEC), 1800))

    def target(job_id: str) -> dict:
        ctx.get_job_mgr().progress(job_id, "正在执行手机任务", "neutral", phase=kind, commandId=kind)
        try:
            completed = subprocess.run(
                [node_exe, script_path, *args],
                cwd=ctx.paths.base_path,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _sanitize_cli_output(ctx, exc.stdout if isinstance(exc.stdout, str) else "", kind=kind)
            stderr = _sanitize_cli_output(ctx, exc.stderr if isinstance(exc.stderr, str) else "", kind=kind)
            return {
                "success": False,
                "code": "timeout",
                "error": "手机任务执行超时，请检查手机连接状态",
                "stdout": stdout,
                "stderr": stderr,
            }
        stdout = _sanitize_cli_output(ctx, completed.stdout or "", kind=kind)
        stderr = _sanitize_cli_output(ctx, completed.stderr or "", kind=kind)
        if completed.returncode != 0:
            return {
                "success": False,
                "code": completed.returncode,
                "error": "手机任务执行失败，请检查手机连接和诊断日志",
                "stdout": stdout,
                "stderr": stderr,
            }
        return {
            "success": True,
            "code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    job = ctx.get_job_mgr().submit_progress(kind, label, target)
    return ctx.fastapi_json({"jobId": job["id"], "job": job})


def _secret_safe_payload(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            text_key = str(key)
            lower_key = text_key.lower()
            if text_key in _SYNC_SECRET_KEYS or lower_key.endswith("secret") or lower_key.endswith("token"):
                if text_key == "tokenMasked":
                    safe[text_key] = _clip(item, 80)
                continue
            safe[text_key] = _secret_safe_payload(item)
        return safe
    if isinstance(value, list):
        return [_secret_safe_payload(item) for item in value]
    return value


def _current_account_session(ctx) -> dict | None:
    manager_getter = getattr(ctx, "get_newapi_account_mgr", None)
    if not callable(manager_getter):
        return None
    manager = manager_getter()
    current = getattr(manager, "current", None)
    if not callable(current):
        return None
    session = current()
    return session if isinstance(session, dict) else None


def _sync_failed(sync_result: dict) -> bool:
    results = sync_result.get("syncResults")
    if not isinstance(results, list):
        return False
    return any(isinstance(item, dict) and item.get("ok") is False for item in results)


def _phone_sync_model_result(ctx) -> dict:
    wire_getter = getattr(ctx, "get_wire_svc", None)
    if not callable(wire_getter):
        return {
            "success": False,
            "error": "模型同步服务不可用，请重新启动 LOOM 后再试",
        }

    wire_svc = wire_getter()
    session = _current_account_session(ctx)
    if session:
        result = wire_svc.sync_from_session(session, targets=("phone",))
    else:
        wire = wire_svc.current()
        if not wire:
            return {
                "success": False,
                "error": "尚未登录中转站账号，也没有可同步的模型配置。请先登录中转站，或在模型/账号页配置第三方 Provider。",
            }
        result = {
            "wire": wire_svc.current_public(),
            "syncResults": wire_svc.apply_wire(wire, targets=("phone",)),
        }

    public_result = _secret_safe_payload(result)
    if _sync_failed(public_result):
        return {
            "success": False,
            "error": "手机模型同步失败，请查看诊断日志",
            **public_result,
        }
    return {
        "success": True,
        "message": "手机模型已同步到本机配置",
        **public_result,
    }


def _load_store(ctx) -> dict:
    store = ctx.read_json(_phone_store_path(ctx), {"selectedDeviceId": "", "devices": []})
    if not isinstance(store, dict):
        return {"selectedDeviceId": "", "devices": []}
    devices = store.get("devices")
    if not isinstance(devices, list):
        store["devices"] = []
    return store


def _upsert_device(store: dict, body: dict) -> dict:
    devices = [item for item in store.get("devices", []) if isinstance(item, dict)]
    raw_id = body.get("id") or body.get("deviceId") or body.get("name") or "phone-1"
    device_id = _normalize_device_id(raw_id)
    existing = next((item for item in devices if str(item.get("id") or "").strip() == device_id), {})
    base_url = _normalize_url(body.get("baseUrl") or body.get("phoneUrl") or existing.get("baseUrl") or "")
    token = _clip(body.get("token"), 4096) or str(existing.get("token") or "").strip()
    if not base_url:
        raise ValueError("请输入 APKClaw 手机地址")
    if not token:
        raise ValueError("请输入 APKClaw 连接令牌")
    next_device = {
        **existing,
        "id": device_id,
        "name": _clip(body.get("name") or existing.get("name") or "Android Phone", 80),
        "baseUrl": base_url,
        "token": token,
        "album": _clip(body.get("album") or existing.get("album") or "LOOM", 80),
    }
    replaced = False
    next_devices: list[dict] = []
    for item in devices:
        if str(item.get("id") or "").strip() == device_id:
            next_devices.append(next_device)
            replaced = True
        else:
            next_devices.append(item)
    if not replaced:
        next_devices.append(next_device)
    selected = _normalize_device_id(body.get("selectedDeviceId") or store.get("selectedDeviceId") or device_id, device_id)
    if not any(str(item.get("id") or "").strip() == selected for item in next_devices):
        selected = device_id
    return {
        **store,
        "selectedDeviceId": selected,
        "devices": next_devices,
    }


def register_phone_routes(app, ctx) -> None:
    @app.api_route("/api/phone/config", methods=["GET", "POST"])
    async def phone_config(request: Request):
        if error := ctx.auth_error(request):
            return error
        store = _load_store(ctx)
        return ctx.fastapi_json(_public_store(store))

    @app.post("/api/phone/config/device")
    async def phone_config_device(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        try:
            store = _upsert_device(_load_store(ctx), body)
        except ValueError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)
        ctx.write_json(_phone_store_path(ctx), store)
        return ctx.fastapi_json(_public_store(store))

    @app.post("/api/phone/sync-model")
    async def phone_sync_model(request: Request):
        if error := ctx.auth_error(request):
            return error

        def target(job_id: str) -> dict:
            ctx.get_job_mgr().progress(
                job_id,
                "正在同步手机模型配置",
                "neutral",
                phase="phone.sync_model",
                commandId="phone.sync_model",
            )
            return _phone_sync_model_result(ctx)

        job = ctx.get_job_mgr().submit_progress("phone.sync_model", "手机模型同步", target)
        return ctx.fastapi_json({"jobId": job["id"], "job": job})

    @app.api_route("/api/phone/devices", methods=["GET", "POST"])
    async def phone_devices(request: Request):
        if error := ctx.auth_error(request):
            return error
        return _submit_phone_job(
            ctx,
            kind="phone.devices",
            label="手机设备",
            script_name="openclaw-phone-fleet.mjs",
            args=["list", "--json"],
            timeout_sec=60,
        )

    @app.api_route("/api/phone/status", methods=["GET", "POST"])
    async def phone_status(request: Request):
        if error := ctx.auth_error(request):
            return error
        return _submit_phone_job(
            ctx,
            kind="phone.status",
            label="手机连接",
            script_name="openclaw-phone-fleet.mjs",
            args=["status", "--json"],
            timeout_sec=60,
        )

    @app.post("/api/phone/screenshot")
    async def phone_screenshot(request: Request):
        if error := ctx.auth_error(request):
            return error
        return _submit_phone_job(
            ctx,
            kind="phone.screenshot",
            label="手机截图",
            script_name="openclaw-phone-vision.mjs",
            args=["frame", "--json"],
        )

    @app.post("/api/phone/read")
    async def phone_read(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        try:
            prompt = _safe_prompt(body.get("prompt") or "只读取当前手机屏幕，不要点击、输入或滑动。")
        except ValueError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)
        return _submit_phone_job(
            ctx,
            kind="phone.read",
            label="读取屏幕",
            script_name="openclaw-phone-agent.mjs",
            args=[
                "run",
                "--prompt",
                prompt,
                "--mode",
                "observe",
                "--timeout-sec",
                "90",
                "--max-wait-sec",
                "100",
                "--max-rounds",
                "8",
                "--json",
            ],
        )

    @app.post("/api/phone/history")
    async def phone_history(request: Request):
        if error := ctx.auth_error(request):
            return error
        return _submit_phone_job(
            ctx,
            kind="phone.history",
            label="手机最近任务",
            script_name="openclaw-phone-agent.mjs",
            args=["history", "--limit", "10", "--json"],
            timeout_sec=60,
        )
