"""HTTP API bridge - bridges Tauri frontend to Python backend modules."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import sys
import tempfile
import threading
from collections.abc import Callable
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Ensure the python package root is on sys.path
_python_dir = os.path.dirname(os.path.abspath(__file__))
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

from core.paths import AppPaths
from core.storage import read_json, write_json, update_json
from core.license_manager import LicenseManager
from core.theme_manager import ThemeManager
from services.process import OpenClawProcessService
from services.image_api import ImageApiClient
from services.video_api import DashScopeVideoClient
from services.updater import OpenClawUpdater
from services.skills import SkillService

paths = AppPaths.discover()
log_buffer: list[str] = []
log_lock = threading.Lock()

def append_log(text: str) -> None:
    with log_lock:
        log_buffer.append(text)
        if len(log_buffer) > 500:
            log_buffer[:] = log_buffer[-500:]

def append_log_ui(text: str) -> None:
    append_log(text)

def ui_call(func, *args) -> None:
    func(*args)

# Create service instances
_license_mgr: LicenseManager | None = None
_process_svc: OpenClawProcessService | None = None
_updater: OpenClawUpdater | None = None
_image_client: ImageApiClient | None = None
_video_client: DashScopeVideoClient | None = None
_theme_mgr: ThemeManager | None = None
_skill_svc: SkillService | None = None

PROTECTED_PATHS = {"/api/process/start", "/api/image/generate", "/api/video/generate"}

def _get_license_mgr() -> LicenseManager:
    global _license_mgr
    if _license_mgr is None:
        _license_mgr = LicenseManager(paths)
    return _license_mgr

def _get_process_svc() -> OpenClawProcessService:
    global _process_svc
    if _process_svc is None:
        _process_svc = OpenClawProcessService(paths, append_log_ui, ui_call)
    return _process_svc

def _get_updater() -> OpenClawUpdater:
    global _updater
    if _updater is None:
        _updater = OpenClawUpdater(paths)
    return _updater

def _get_image_client() -> ImageApiClient:
    global _image_client
    if _image_client is None:
        _image_client = ImageApiClient()
    return _image_client

def _get_video_client() -> DashScopeVideoClient:
    global _video_client
    if _video_client is None:
        _video_client = DashScopeVideoClient()
    return _video_client

def _get_theme_mgr() -> ThemeManager:
    global _theme_mgr
    if _theme_mgr is None:
        _theme_mgr = ThemeManager(paths)
    return _theme_mgr

def _get_skill_svc() -> SkillService:
    global _skill_svc
    if _skill_svc is None:
        _skill_svc = SkillService(paths)
    return _skill_svc


def _provider_id_from_base_url(base_url: str, fallback: str) -> str:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    host = parsed.netloc or parsed.path or fallback
    host = host.split("@")[-1].split(":")[0].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-") or fallback
    return f"custom-{slug}"


def _model_definition(model_id: str) -> dict:
    is_reasoning = model_id.startswith(("claude", "qwen3", "o1", "o3", "o4"))
    context_window = 200000 if model_id.startswith("claude") else 128000
    max_tokens = 32000
    if model_id.startswith("qwen3"):
        context_window = 16000000
        max_tokens = 4096000
    return {
        "id": model_id,
        "name": f"{model_id} (Custom Provider)",
        "reasoning": is_reasoning,
        "input": ["text"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": context_window,
        "maxTokens": max_tokens,
        "api": "openai-completions",
    }


def _sync_openclaw_models_from_api_profiles() -> None:
    """Keep launcher API settings compatible with OpenClaw 2026.5+ model config."""
    profiles = read_json(paths.auth_profiles, {"models": {"providers": {}}})
    profile_models = profiles.get("models") if isinstance(profiles, dict) else {}
    providers = profile_models.get("providers") if isinstance(profile_models, dict) else {}
    if not isinstance(providers, dict) or not providers:
        return

    primary_key = profile_models.get("primary") if isinstance(profile_models, dict) else None
    provider = providers.get(primary_key) if primary_key else None
    if not isinstance(provider, dict):
        provider = next((p for p in providers.values() if isinstance(p, dict)), None)
    if not provider:
        return

    api_key = (provider.get("apiKey") or "").strip()
    base_url = (provider.get("baseUrl") or provider.get("url") or "").strip().rstrip("/")
    if not api_key or not base_url:
        return

    raw_models = provider.get("models") if isinstance(provider.get("models"), list) else []
    model_ids: list[str] = []
    for item in raw_models:
        model_id = item.get("id") if isinstance(item, dict) else item
        if isinstance(model_id, str) and model_id.strip() and model_id.strip() not in model_ids:
            model_ids.append(model_id.strip())
    for default_model in ("qwen3.6-plus", "claude-opus-4-7-medium", "kimi-k2.5", "gpt-4o"):
        if default_model not in model_ids:
            model_ids.append(default_model)
    if not model_ids:
        return

    provider_id = _provider_id_from_base_url(base_url, primary_key or "api")
    model_ref = f"{provider_id}/{model_ids[0]}"
    provider_config = {
        "baseUrl": base_url,
        "apiKey": api_key,
        "api": "openai-completions",
        "models": [_model_definition(model_id) for model_id in model_ids],
    }

    agent_dir = os.path.dirname(paths.auth_profiles)
    models_path = os.path.join(agent_dir, "models.json")
    models_json = read_json(models_path, {"providers": {}})
    if not isinstance(models_json, dict):
        models_json = {"providers": {}}
    models_json.setdefault("providers", {})
    models_json["providers"][provider_id] = provider_config
    write_json(models_path, models_json)

    oc = read_json(paths.openclaw_config, {})
    if not isinstance(oc, dict):
        oc = {}
    oc.setdefault("models", {})
    oc["models"]["mode"] = "merge"
    oc["models"].setdefault("providers", {})
    oc["models"]["providers"][provider_id] = provider_config

    oc.setdefault("agents", {})
    oc["agents"].setdefault("defaults", {})
    defaults = oc["agents"]["defaults"]
    defaults.setdefault("model", {})
    defaults["model"]["primary"] = model_ref
    defaults.setdefault("models", {})
    defaults["models"][model_ref] = {"alias": model_ids[0]}
    write_json(paths.openclaw_config, oc)


def _has_configured_api_profile() -> bool:
    profiles = read_json(paths.auth_profiles, {"models": {"providers": {}}})
    models = profiles.get("models") if isinstance(profiles, dict) else {}
    providers = models.get("providers") if isinstance(models, dict) else {}
    if not isinstance(providers, dict):
        return False
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        api_key = str(provider.get("apiKey") or "").strip()
        base_url = str(provider.get("baseUrl") or provider.get("url") or "").strip()
        if api_key and base_url:
            return True
    return False


def _diagnostic_summary(checks: list[dict]) -> dict:
    failed = sum(1 for item in checks if item.get("status") == "fail")
    warnings = sum(1 for item in checks if item.get("status") == "warn")
    ok = sum(1 for item in checks if item.get("status") == "ok")
    status = "fail" if failed else ("warn" if warnings else "ok")
    return {"status": status, "ok": ok, "warnings": warnings, "failed": failed, "total": len(checks)}


SENSITIVE_KEYS = {
    "apiKey",
    "api_key",
    "apikey",
    "key",
    "token",
    "accessToken",
    "access_token",
    "password",
    "secret",
    "signature",
    "dashKey",
    "appSecret",
}


def _mask_secret(value: object) -> str:
    text = str(value)
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}***{text[-4:]}"


def _sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in SENSITIVE_KEYS or key_text.lower().endswith(("key", "token", "secret", "password", "signature")):
                result[key_text] = _mask_secret(item) if item else ""
            else:
                result[key_text] = _sanitize_payload(item)
        return result
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    return value


def _sanitize_text(value: str) -> str:
    value = re.sub(r"\bsk-[A-Za-z0-9_\-]{12,}\b", "sk-***", value)
    value = re.sub(r"(?i)(api[_-]?key|token|secret|password)(\s*[:=]\s*)([^\s,;]+)", r"\1\2***", value)
    return value


def _append_runtime_checks(payload: dict) -> dict:
    checks = list(payload.get("checks", []))

    license_data = _get_license_mgr().current_license()
    checks.append({
        "id": "license",
        "label": "授权状态",
        "status": "ok" if license_data else "fail",
        "message": f"已授权：{license_data.get('licensee', 'OpenClaw Customer')}" if isinstance(license_data, dict) else "未授权，启动服务前需要先激活",
        "detail": paths.license_file,
        "repairable": False,
    })

    api_configured = _has_configured_api_profile()
    checks.append({
        "id": "api_config",
        "label": "API 配置",
        "status": "ok" if api_configured else "warn",
        "message": "已配置模型 API" if api_configured else "未配置 API，AI 生图/视频会不可用",
        "detail": paths.auth_profiles,
        "repairable": False,
    })

    payload["checks"] = checks
    payload["summary"] = _diagnostic_summary(checks)
    payload["repairAvailable"] = any(item.get("repairable") for item in checks)
    return payload


def _build_diagnostics_payload() -> dict:
    return _append_runtime_checks(_get_process_svc().diagnose_environment())


def _read_sanitized_json(path: str, default: object = None) -> object:
    default = {} if default is None else default
    return _sanitize_payload(read_json(path, default))


def _reset_transient_video_config() -> None:
    if os.path.exists(paths.video_config):
        write_json(paths.video_config, {})


_reset_transient_video_config()


class Handler(BaseHTTPRequestHandler):
    """Compatibility service used only when FastAPI is unavailable."""

    bridge_token: str | None = None

    def do_GET(self) -> None:
        self._unavailable()

    def do_POST(self) -> None:
        self._unavailable()

    def do_PUT(self) -> None:
        self._unavailable()

    def _unavailable(self) -> None:
        if Handler.bridge_token:
            req_token = self.headers.get("X-Bridge-Token")
            if req_token != Handler.bridge_token:
                self._send_json(401, {"error": "未授权的请求"})
                return
        self._send_json(
            503,
            {"error": "FastAPI bridge dependencies are required. Run pip install -r python/requirements.txt."},
        )

    def _send_json(self, code: int, data: dict) -> None:
        payload = _bridge_response_payload(data, code)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "http://tauri.localhost")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        pass  # Suppress default HTTP logging


def find_port(start: int = 18791, end: int = 18950) -> int:
    """Find an available port in the given range."""
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            pass
    return 0


def _legacy_headers() -> dict[str, str]:
    return {"Access-Control-Allow-Origin": "http://tauri.localhost"}


def _bridge_response_payload(data: dict, status_code: int) -> dict:
    """Add a stable response metadata block without changing legacy fields."""
    payload = dict(data) if isinstance(data, dict) else {"data": data}
    is_ok = 200 <= status_code < 400 and "error" not in payload
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    meta = {
        **meta,
        "ok": is_ok,
        "status": status_code,
    }
    if not is_ok:
        message = str(payload.get("error") or "")
        meta["error"] = {
            "code": status_code,
            "message": message,
        }
    else:
        meta.pop("error", None)
    payload["_meta"] = meta
    return payload


def _safe_config_path(file_path: str) -> str | None:
    """Validate that the resolved path stays within allowed directories."""
    if not file_path:
        return None
    if not os.path.isabs(file_path):
        file_path = os.path.join(paths.base_path, file_path)
    real_path = os.path.realpath(file_path)
    allowed_prefixes = (os.path.realpath(paths.base_path), os.path.realpath(paths.data_dir))
    if real_path.startswith(allowed_prefixes):
        return real_path
    return None


def _fastapi_json(data: dict, status_code: int = 200):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=status_code,
        content=_bridge_response_payload(data, status_code),
        headers=_legacy_headers(),
    )


def _fastapi_auth_error(request):
    if Handler.bridge_token:
        req_token = request.headers.get("X-Bridge-Token")
        if req_token != Handler.bridge_token:
            return _fastapi_json({"error": "未授权的请求"}, 401)
    return None


def _fastapi_protected_error(path: str):
    if path in PROTECTED_PATHS and not _get_license_mgr().is_authorized():
        return _fastapi_json({"error": "需要有效的许可证才能使用此功能"}, 403)
    return None


async def _fastapi_body(request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _data_url_to_temp_file(data_url: str) -> tuple[str, str]:
    try:
        header, b64_data = data_url.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        image_bytes = base64.b64decode(b64_data)
        ext = mime_type.split("/")[-1].split("+")[0]
        if ext not in ("png", "jpeg", "jpg", "webp"):
            ext = "png"
        fd, temp_file = tempfile.mkstemp(suffix=f".{ext}")
        with os.fdopen(fd, "wb") as file:
            file.write(image_bytes)
        return temp_file, temp_file
    except Exception as exc:
        raise ValueError(f"图片数据解码失败: {exc}") from exc


def _build_fastapi_context():
    from types import SimpleNamespace

    return SimpleNamespace(
        append_log=append_log,
        append_runtime_checks=_append_runtime_checks,
        auth_error=_fastapi_auth_error,
        body=_fastapi_body,
        build_diagnostics_payload=_build_diagnostics_payload,
        data_url_to_temp_file=_data_url_to_temp_file,
        fastapi_json=_fastapi_json,
        get_image_client=_get_image_client,
        get_license_mgr=_get_license_mgr,
        get_process_svc=_get_process_svc,
        get_skill_svc=_get_skill_svc,
        get_theme_mgr=_get_theme_mgr,
        get_updater=_get_updater,
        get_video_client=_get_video_client,
        log_buffer=log_buffer,
        log_lock=log_lock,
        paths=paths,
        protected_error=_fastapi_protected_error,
        read_json=read_json,
        read_sanitized_json=_read_sanitized_json,
        safe_config_path=_safe_config_path,
        sanitize_text=_sanitize_text,
        sync_openclaw_models_from_api_profiles=_sync_openclaw_models_from_api_profiles,
        write_json=write_json,
    )


def _serve_fastapi(port: int, token: str) -> None:
    from fastapi import FastAPI
    import uvicorn

    from api.fastapi_routes import register_fastapi_routes

    app = FastAPI(
        title="OpenClaw Bridge",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    register_fastapi_routes(app, _build_fastapi_context())

    print(f"BRIDGE_PORT={port}", flush=True)
    print(f"BRIDGE_TOKEN={token}", flush=True)
    print("BRIDGE_IMPL=fastapi", flush=True)
    append_log(f"[Bridge] Started on port {port} (fastapi)\n")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()

def _serve_dependency_error(port: int, token: str) -> None:
    Handler.bridge_token = token
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    actual_port = int(server.server_address[1])
    print(f"BRIDGE_PORT={actual_port}", flush=True)
    print(f"BRIDGE_TOKEN={token}", flush=True)
    print("BRIDGE_IMPL=dependency-error", flush=True)
    append_log(f"[Bridge] Started dependency error service on port {actual_port}\n")
    server.serve_forever()


def main() -> None:
    port = find_port()
    token = secrets.token_hex(32)
    Handler.bridge_token = token

    require_fastapi = os.environ.get("OPENCLAW_BRIDGE_REQUIRE_FASTAPI") == "1"

    try:
        _serve_fastapi(port, token)
        return
    except ModuleNotFoundError as error:
        if require_fastapi:
            raise
        append_log(f"[Bridge] FastAPI unavailable: {error}\n")

    _serve_dependency_error(port, token)


if __name__ == "__main__":
    main()
