"""HTTP API bridge - bridges Tauri frontend to Python backend modules."""

from __future__ import annotations

import base64
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
import zipfile
from collections.abc import Callable
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Ensure the python package root is on sys.path
_python_dir = os.path.dirname(os.path.abspath(__file__))
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

# Add python dir so openclaw_launcher.* imports can resolve
# (the copied services use `from openclaw_launcher.constants import ...`)
if _python_dir not in sys.path:
    sys.path.insert(0, _python_dir)

# Now set up a fake `openclaw_launcher` package pointing to our core/services
import importlib
import importlib.util
import types

def _install_subpackage(name: str, path: str) -> None:
    """Create a synthetic subpackage so `openclaw_launcher.xxx` resolves here."""
    pkg = types.ModuleType(f"openclaw_launcher.{name}")
    pkg.__path__ = [path]
    setattr(sys.modules["openclaw_launcher"], name, pkg)
    sys.modules[f"openclaw_launcher.{name}"] = pkg

def _install_module(name: str, path: str) -> None:
    spec = importlib.util.spec_from_file_location(f"openclaw_launcher.{name}", path)
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec_module so dataclass introspection works
    sys.modules[f"openclaw_launcher.{name}"] = mod
    spec.loader.exec_module(mod)
    setattr(sys.modules["openclaw_launcher"], name, mod)

_oc = types.ModuleType("openclaw_launcher")
_oc.__path__ = [_python_dir]
sys.modules["openclaw_launcher"] = _oc
_install_subpackage("core", os.path.join(_python_dir, "core"))
_install_subpackage("services", os.path.join(_python_dir, "services"))
_install_module("constants", os.path.join(_python_dir, "core", "constants.py"))
_install_module("paths", os.path.join(_python_dir, "core", "paths.py"))
_install_module("storage", os.path.join(_python_dir, "core", "storage.py"))
_install_module("license_manager", os.path.join(_python_dir, "core", "license_manager.py"))
_install_module("theme_manager", os.path.join(_python_dir, "core", "theme_manager.py"))

# Now import the actual modules
from core.paths import AppPaths
from core.storage import read_json, write_json, update_json
from core.license_manager import LicenseManager
from core.theme_manager import ThemeManager
from services.process import OpenClawProcessService
from services.image_api import ImageApiClient, ImageApiError
from services.video_api import DashScopeVideoClient, VideoApiError
from services.updater import OpenClawUpdater

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
    """HTTP request handler for the API bridge."""

    bridge_token: str | None = None

    def do_GET(self) -> None:
        self._route("GET", None)

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = None
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
        self._route("POST", body)

    def do_PUT(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = None
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
        self._route("PUT", body)

    def _route(self, method: str, body: dict | None) -> None:
        path = self.path.split("?")[0]
        body = body or {}
        try:
            if Handler.bridge_token:
                req_token = self.headers.get("X-Bridge-Token")
                if req_token != Handler.bridge_token:
                    self._error(401, "未授权的请求")
                    return

            # Protected endpoints — require valid license
            if path in PROTECTED_PATHS:
                if not _get_license_mgr().is_authorized():
                    self._error(403, "需要有效的许可证才能使用此功能")
                    return

            if path == "/api/process/start":
                self._process_start(body)
            elif path == "/api/process/stop":
                self._process_stop()
            elif path == "/api/process/status":
                self._process_status()
            elif path == "/api/log/get":
                self._log_get()
            elif path == "/api/log/clear":
                self._log_clear()
            elif path == "/api/license/current":
                self._license_current()
            elif path == "/api/license/activate":
                self._license_activate(body)
            elif path == "/api/license/authorized":
                self._license_authorized(body)
            elif path == "/api/image/generate":
                self._image_generate(body)
            elif path == "/api/video/generate":
                self._video_generate(body)
            elif path == "/api/update/check":
                self._update_check()
            elif path == "/api/update/do":
                self._update_do()
            elif path == "/api/config/read":
                self._config_read(body)
            elif path == "/api/config/write":
                self._config_write(body)
            elif path == "/api/auth/profiles":
                self._auth_profiles(method, body)
            elif path == "/api/system/info":
                self._system_info()
            elif path == "/api/diagnostics/run":
                self._diagnostics_run()
            elif path == "/api/diagnostics/repair":
                self._diagnostics_repair()
            elif path == "/api/diagnostics/export":
                self._diagnostics_export()
            elif path == "/api/theme/current":
                self._theme_current()
            elif path == "/api/theme/by_merchant":
                self._theme_by_merchant(body)
            elif path == "/api/theme/list":
                self._theme_list()
            else:
                self._error(404, f"Not found: {path}")
        except Exception as e:
            append_log(f"[Bridge Error] {path}: {e}\n{traceback.format_exc()}\n")
            self._error(500, str(e))

    # === Process Management ===

    def _process_start(self, body: dict) -> None:
        svc = _get_process_svc()
        if svc.running:
            self._ok({"status": "already_running"})
            return

        def on_exit(code: int | None) -> None:
            append_log(f"\n[OpenClaw] Process ended (exit: {code})\n")

        svc.start(on_exit=on_exit)
        self._ok({"status": "started", "pid": svc.process.pid if svc.process else None})

    def _process_stop(self) -> None:
        svc = _get_process_svc()
        msg = svc.stop()
        self._ok({"status": "stopped", "message": msg})

    def _process_status(self) -> None:
        svc = _get_process_svc()
        self._ok({
            "running": svc.running,
            "pid": svc.process.pid if svc.process and svc.process.poll() is None else None,
        })

    # === Log ===

    def _log_get(self) -> None:
        with log_lock:
            text = "".join(log_buffer)
        self._ok({"log": text})

    def _log_clear(self) -> None:
        with log_lock:
            log_buffer.clear()
        self._ok({"status": "cleared"})

    # === License ===

    def _license_current(self) -> None:
        mgr = _get_license_mgr()
        lic = mgr.current_license()
        self._ok({"license": lic})

    def _license_activate(self, body: dict) -> None:
        from core.license_manager import LicenseError
        mgr = _get_license_mgr()
        code = body.get("code", "")
        if not code:
            self._error(400, "授权码不能为空")
            return
        try:
            result = mgr.activate(code)
            theme = _get_theme_mgr().get_current(mgr.current_license())
            self._ok({"license": result, "theme": theme})
        except LicenseError as e:
            self._error(400, str(e))

    def _license_authorized(self, body: dict) -> None:
        mgr = _get_license_mgr()
        feature = body.get("feature")
        self._ok({"authorized": mgr.is_authorized(feature)})

    # === Image API ===

    def _image_generate(self, body: dict) -> None:
        client = _get_image_client()
        base_url = body.get("baseUrl", "")
        api_key = body.get("apiKey", "")
        prompt = body.get("prompt", "")
        size = body.get("size", "1024x1024")
        edit_path = body.get("editImagePath")
        count = body.get("count", 1)

        if not base_url:
            self._error(400, "中转站地址不能为空")
            return
        if not prompt:
            self._error(400, "提示词不能为空")
            return

        # Handle base64 data URL from frontend: save to temp file
        temp_file: str | None = None
        if edit_path and edit_path.startswith("data:"):
            try:
                header, b64_data = edit_path.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
                image_bytes = base64.b64decode(b64_data)
                ext = mime_type.split("/")[-1].split("+")[0]
                if ext not in ("png", "jpeg", "jpg", "webp"):
                    ext = "png"
                fd, temp_file = tempfile.mkstemp(suffix=f".{ext}")
                with os.fdopen(fd, "wb") as f:
                    f.write(image_bytes)
                edit_path = temp_file
            except Exception as e:
                self._error(400, f"图片数据解码失败: {e}")
                return

        try:
            results = client.generate_many(base_url, api_key, prompt, size, count=count, edit_image_path=edit_path)
            images_b64 = [base64.b64encode(r).decode() for r in results]
            self._ok({"images": images_b64, "count": len(images_b64)})
        except ImageApiError as e:
            self._error(500, str(e))
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    # === Video API ===

    def _video_generate(self, body: dict) -> None:
        client = _get_video_client()
        dash_key = body.get("dashKey", "")
        prompt = body.get("prompt", "")
        mode = body.get("mode", "t2v")
        resolution = body.get("resolution", "720P")
        duration = body.get("duration", 5)
        ratio = body.get("ratio", "16:9")
        image_path = body.get("imagePath")

        if not dash_key:
            self._error(400, "DashScope API Key 不能为空")
            return
        if not prompt:
            self._error(400, "提示词不能为空")
            return

        # Handle base64 data URL from frontend: save to temp file
        temp_file: str | None = None
        if image_path and image_path.startswith("data:"):
            try:
                header, b64_data = image_path.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
                image_bytes = base64.b64decode(b64_data)
                ext = mime_type.split("/")[-1].split("+")[0]
                if ext not in ("png", "jpeg", "jpg", "webp"):
                    ext = "png"
                fd, temp_file = tempfile.mkstemp(suffix=f".{ext}")
                with os.fdopen(fd, "wb") as f:
                    f.write(image_bytes)
                image_path = temp_file
            except Exception as e:
                self._error(400, f"图片数据解码失败: {e}")
                return

        try:
            video_bytes = client.generate(
                dash_key, prompt, mode, resolution, duration, ratio, image_path
            )
            video_dir = os.path.join(paths.data_dir, "videos")
            os.makedirs(video_dir, exist_ok=True)
            filename = f"lumi-video-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
            save_path = os.path.join(video_dir, filename)
            with open(save_path, "wb") as file:
                file.write(video_bytes)
            self._ok({
                "video": base64.b64encode(video_bytes).decode(),
                "mime": "video/mp4",
                "size": len(video_bytes),
                "path": save_path,
                "directory": video_dir,
                "filename": filename,
            })
        except VideoApiError as e:
            self._error(500, str(e))
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    # === Updater ===

    def _update_check(self) -> None:
        updater = _get_updater()
        current = updater.current_version()
        latest, error = updater.latest_version()
        if error:
            self._error(500, error)
        else:
            self._ok({"current": current, "latest": latest, "hasUpdate": current != latest})

    def _update_do(self) -> None:
        updater = _get_updater()
        results: list[str] = []
        def log(text: str) -> None:
            results.append(text)
            append_log(text)
        def done(success: bool, message: str) -> None:
            pass  # response sent below

        import subprocess
        node_exe = paths.node_exe
        pnpm_cli = paths.pnpm_cli
        try:
            proc = subprocess.Popen(
                [node_exe, pnpm_cli, "add", "openclaw@latest"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding="utf-8", errors="replace",
                cwd=paths.base_path,
            )
            output = []
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        output.append(line)
                        append_log(line)
            exit_code = proc.wait()
            current = updater.current_version()
            self._ok({"success": exit_code == 0, "current_version": current, "log": output})
        except Exception as e:
            self._error(500, str(e))

    # === Config ===

    def _safe_path(self, file_path: str) -> str | None:
        """Validate that the resolved path stays within allowed directories."""
        if not file_path:
            return None
        if not os.path.isabs(file_path):
            file_path = os.path.join(paths.base_path, file_path)
        # Resolve to absolute path (handles relative paths and symlinks)
        real_path = os.path.realpath(file_path)
        # Allow paths within base_path or data_dir
        allowed_prefixes = (os.path.realpath(paths.base_path), os.path.realpath(paths.data_dir))
        if real_path.startswith(allowed_prefixes):
            return real_path
        return None

    def _config_read(self, body: dict) -> None:
        file_path = body.get("path", "")
        default = body.get("default", {})
        safe = self._safe_path(file_path)
        if safe is None:
            self._error(403, "路径不在允许的范围内")
            return
        self._ok({"data": read_json(safe, default)})

    def _config_write(self, body: dict) -> None:
        file_path = body.get("path", "")
        safe = self._safe_path(file_path)
        if safe is None:
            self._error(403, "路径不在允许的范围内")
            return
        write_json(safe, body["data"])
        if file_path.replace("\\", "/").endswith(("auth-profiles.json", "openclaw.json")):
            _sync_openclaw_models_from_api_profiles()
        self._ok({"status": "ok"})

    # === Auth Profiles ===

    def _auth_profiles(self, method: str, body: dict) -> None:
        if method == "PUT":
            # Read existing profiles
            profiles = read_json(paths.auth_profiles, {"models": {"providers": {}}})
            # Merge new data
            profiles.update(body)
            write_json(paths.auth_profiles, profiles)
            _sync_openclaw_models_from_api_profiles()
            self._ok({"status": "ok"})
        else:
            self._ok({"profiles": read_json(paths.auth_profiles, {})})

    # === System ===

    def _system_info(self) -> None:
        updater = _get_updater()
        self._ok({
            "node_path": paths.node_exe,
            "base_path": paths.base_path,
            "openclaw_version": updater.current_version(),
        })

    # === Diagnostics ===

    def _diagnostics_run(self) -> None:
        self._ok(_build_diagnostics_payload())

    def _diagnostics_repair(self) -> None:
        svc = _get_process_svc()
        result = svc.repair_environment()
        result["diagnostics"] = _append_runtime_checks(result.get("diagnostics", {}))
        self._ok(result)

    def _diagnostics_export(self) -> None:
        diagnostics = _build_diagnostics_payload()
        now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        export_dir = os.path.join(paths.data_dir, "diagnostics")
        os.makedirs(export_dir, exist_ok=True)
        filename = f"openclaw-diagnostics-{now}.zip"
        zip_path = os.path.join(export_dir, filename)

        system_info = {
            "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
            "basePath": paths.base_path,
            "nodePath": paths.node_exe,
            "openclawMjs": paths.openclaw_mjs,
            "stateDir": paths.state_dir,
            "diagnosticSummary": diagnostics.get("summary", {}),
        }

        with log_lock:
            service_log = _sanitize_text("".join(log_buffer))

        readme = (
            "OpenClaw diagnostics package\n\n"
            "This package is generated by the launcher for troubleshooting.\n"
            "Secrets such as API keys, tokens, passwords, signatures and app secrets are masked.\n"
        )

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("README.txt", readme)
            archive.writestr("diagnostics.json", json.dumps(diagnostics, ensure_ascii=False, indent=2))
            archive.writestr("system.json", json.dumps(system_info, ensure_ascii=False, indent=2))
            archive.writestr("service.log", service_log)
            archive.writestr("configs/openclaw.json", json.dumps(_read_sanitized_json(paths.openclaw_config, {}), ensure_ascii=False, indent=2))
            archive.writestr("configs/auth-profiles.json", json.dumps(_read_sanitized_json(paths.auth_profiles, {}), ensure_ascii=False, indent=2))
            archive.writestr("configs/imgapi_config.json", json.dumps(_read_sanitized_json(paths.image_config, {}), ensure_ascii=False, indent=2))
            archive.writestr("configs/video_config.json", json.dumps(_read_sanitized_json(paths.video_config, {}), ensure_ascii=False, indent=2))

        self._ok({
            "path": zip_path,
            "directory": export_dir,
            "filename": filename,
            "size": os.path.getsize(zip_path),
        })

    # === Theme ===

    def _theme_current(self) -> None:
        mgr = _get_theme_mgr()
        license_mgr = _get_license_mgr()
        license_data = license_mgr.current_license()
        theme = mgr.get_current(license_data)
        self._ok({"theme": theme})

    def _theme_by_merchant(self, body: dict) -> None:
        mgr = _get_theme_mgr()
        merchant_id = body.get("merchantId", "")
        if not merchant_id:
            self._error(400, "merchantId 不能为空")
            return
        theme = mgr.get_by_merchant(merchant_id)
        if theme is None:
            self._error(404, f"未找到商户 {merchant_id} 的主题")
            return
        self._ok({"theme": theme})

    def _theme_list(self) -> None:
        mgr = _get_theme_mgr()
        themes = mgr.list_themes()
        self._ok({"themes": themes})

    # === Helpers ===

    def _ok(self, data: dict) -> None:
        self._send_json(200, data)

    def _error(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message})

    def _send_json(self, code: int, data: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "http://tauri.localhost")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format: str, *args) -> None:
        pass  # Suppress default HTTP logging


def find_port(start: int = 18791, end: int = 18800) -> int:
    """Find an available port in the given range."""
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    import secrets as _secrets
    port = find_port()
    token = _secrets.token_hex(32)
    print(f"BRIDGE_PORT={port}", flush=True)
    print(f"BRIDGE_TOKEN={token}", flush=True)
    Handler.bridge_token = token
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    append_log(f"[Bridge] Started on port {port}\n")
    server.serve_forever()
