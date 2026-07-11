"""Runtime wire contract for account-to-local configuration sync."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any

from core.openclaw_model_sync import sync_openclaw_models_from_gateway_profile
from core.paths import AppPaths
from core.secret_store import protect_secret, unprotect_secret
from core.storage import read_json, write_json


WIRE_MANAGED_BY = "heang_account"
WIRE_PROVIDER = "heang"
WIRE_CUSTOM_MANAGED_BY = "custom_provider"
DEFAULT_TEXT_MODEL = "glm-5.2-coding"
DEFAULT_PHONE_MODEL = "qwen3.7-plus"
TEXT_MODEL_PRIORITY = (
    "glm-5.2-coding",
    "qwen3.7-plus",
    "qwen3.6-plus",
    "qwen3.5-plus",
    "glm-4-flash",
    "kimi-k2.5",
    "MiniMax-M2.5",
)
PHONE_MODEL_IDS = {"agnes-2.0-flash"}
IMAGE_MODEL_MARKERS = (
    "image",
    "dall-e",
    "gpt-image",
    "flux",
    "midjourney",
    "sd-",
    "imagen",
    "seedream",
)
VIDEO_MODEL_MARKERS = (
    "video",
    "veo",
    "sora",
    "seedance",
    "kling",
    "wan",
    "hailuo",
    "runway",
    "pika",
    "luma",
)
MANAGED_ACCOUNT_SOURCES = {"newapi_account", WIRE_MANAGED_BY, WIRE_CUSTOM_MANAGED_BY}
AGENT_ENV_KEYS = ("LOOM_OPENCODE_API_KEY", "LOOM_CODEX_API_KEY", "LOOM_CLAUDE_API_KEY")
AGENT_STALE_MODEL_ENV_KEYS = ("OPENAI_MODEL", "ANTHROPIC_MODEL", "CLAUDE_CODE_MODEL", "OPENCODE_MODEL", "OPENCODE_PROVIDER")
AGENT_MODEL_CONFIGS = {
    "codex-desktop": {
        "target": "codex",
        "name": "Codex",
        "configDir": ".codex",
        "configFile": "config.toml",
    },
    "claude-code": {
        "target": "claude",
        "name": "Claude Code",
        "configDir": ".claude",
        "configFile": "settings.json",
    },
    "openclaw-companion": {
        "target": "openclaw",
        "name": "OpenClaw",
        "configDir": ".openclaw",
        "configFile": "openclaw.json",
    },
}

SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|session[_-]?cookie|password|secret|token)(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)\b(bearer\s+)([a-z0-9._~+/=-]{8,})"),
    re.compile(r"\b(sk-[A-Za-z0-9._-]+|sess-[A-Za-z0-9._-]+|eyJ[A-Za-z0-9._=-]+)"),
)


class WireConfigError(RuntimeError):
    """Raised when runtime wire sync cannot be completed safely."""


class WireService:
    def __init__(self, paths: AppPaths, append_log=None):
        self.paths = paths
        self.append_log = append_log or (lambda _text: None)

    def current(self) -> dict[str, Any] | None:
        wire = _read_json_if_exists(self.paths.wire_current)
        if not isinstance(wire, dict):
            return None
        return _unprotect_wire(wire)

    def current_public(self) -> dict[str, Any]:
        return _public_wire(self.current())

    def sync_from_session(
        self,
        session: dict[str, Any],
        *,
        targets: tuple[str, ...] = ("openclaw", "opencode", "codex", "claude", "image", "desktop", "phone"),
    ) -> dict[str, Any]:
        wire = build_wire_from_session(session)
        current = _read_json_if_exists(self.paths.wire_current)
        if isinstance(current, dict):
            write_json(self.paths.wire_last_good, current)

        write_json(self.paths.wire_current, _protected_wire(wire))
        results = self.apply_wire(wire, targets=targets)
        return {
            "wire": _public_wire(wire),
            "syncResults": results,
        }

    def sync_custom_provider(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        text_model: str,
        image_model: str = "",
        phone_model: str = "",
        video_model: str = "",
        targets: tuple[str, ...] = ("openclaw", "opencode", "codex", "claude", "image", "desktop", "phone"),
    ) -> dict[str, Any]:
        provider = _pick_text(provider, "自定义 Provider")
        base_url = _normalize_base_url(base_url)
        api_key = _pick_text(api_key)
        text_model = _pick_text(text_model)
        image_model = _pick_text(image_model)
        phone_model = _pick_text(phone_model, DEFAULT_PHONE_MODEL)
        video_model = _pick_text(video_model)
        if not base_url:
            raise WireConfigError("请输入第三方 Provider URL")
        if not api_key:
            raise WireConfigError("请输入第三方 API Key")
        if not text_model:
            raise WireConfigError("请输入默认文本模型")
        if _looks_like_non_text_model(text_model):
            raise WireConfigError("默认文本模型不能使用手机/图像/视频模型")

        wire = {
            "schemaVersion": 1,
            "managedBy": WIRE_CUSTOM_MANAGED_BY,
            "accountId": "",
            "account": "第三方 Provider",
            "provider": provider,
            "baseUrl": base_url,
            "apiKey": api_key,
            "tokenMasked": _mask_secret(api_key),
            "models": {
                "text": text_model,
                "phone": phone_model,
                "image": image_model,
                "video": video_model,
            },
            "modelLists": {
                "text": [text_model],
                "image": [image_model] if image_model else [],
                "video": [video_model] if video_model else [],
            },
            "targets": {
                "openclaw": True,
                "phone": True,
                "desktopRpa": True,
                "imageGateway": bool(image_model),
                "videoGateway": False,
                "opencode": True,
                "codex": True,
                "claude": True,
            },
            "updatedAt": _iso_now(),
        }
        current = _read_json_if_exists(self.paths.wire_current)
        if isinstance(current, dict):
            write_json(self.paths.wire_last_good, current)
        write_json(self.paths.wire_current, _protected_wire(wire))
        results = self.apply_wire(wire, targets=targets)
        return {
            "wire": _public_wire(wire),
            "syncResults": results,
        }

    def apply_wire(self, wire: dict[str, Any], *, targets: tuple[str, ...]) -> list[dict[str, Any]]:
        actions = {
            "openclaw": self._sync_openclaw,
            "opencode": self._sync_opencode,
            "codex": self._sync_codex,
            "claude": self._sync_claude,
            "image": self._sync_image,
            "desktop": self._sync_desktop,
            "phone": self._sync_phone,
            "video": self._clear_video,
        }
        results: list[dict[str, Any]] = []
        for target in targets:
            action = actions.get(target)
            if action is None:
                results.append({"target": target, "ok": False, "error": "unknown_target"})
                continue
            try:
                action(wire)
                results.append({"target": target, "ok": True})
            except Exception as exc:
                safe_error = _redact_secret_text(str(exc))
                self.append_log(f"[Wire] sync target {target} failed: {safe_error}\n")
                results.append({"target": target, "ok": False, "error": safe_error})
        return results

    def verify(self) -> dict[str, Any]:
        wire = self.current()
        if not wire:
            return {
                "ok": False,
                "error": "wire_not_configured",
                "targets": {},
            }
        targets = {
            "token": {"ok": bool(_pick_text(wire.get("apiKey")))},
            "openclaw": {"ok": bool(read_json(self.paths.openclaw_config, {}))},
            "opencode": {"ok": bool(read_json(os.path.join(self.paths.data_dir, ".opencode", "opencode.json"), {}))},
            "codex": {"ok": self.agent_model_config_status("codex-desktop")["configured"]},
            "claude": {"ok": self.agent_model_config_status("claude-code")["configured"]},
            "phone": {"ok": bool(read_json(os.path.join(self.paths.launcher_dir, "phone-agent.json"), {}))},
            "desktop": {"ok": bool(read_json(os.path.join(self.paths.launcher_dir, "desktop-agent.json"), {}))},
            "image": {"ok": bool(read_json(self.paths.image_config, {}))},
            "video": {"ok": not bool(read_json(self.paths.video_config, {})) and not bool(read_json(self.paths.videoapi_config, {}))},
        }
        ok = all(bool(item.get("ok")) for item in targets.values())
        return {
            "ok": ok,
            "wire": _public_wire(wire),
            "targets": targets,
        }

    def rollback(self) -> dict[str, Any]:
        previous = _read_json_if_exists(self.paths.wire_last_good)
        if not isinstance(previous, dict):
            raise WireConfigError("没有可回滚的模型同步快照")
        write_json(self.paths.wire_current, previous)
        wire = _unprotect_wire(previous)
        results = self.apply_wire(wire, targets=("openclaw", "opencode", "codex", "claude", "image", "desktop", "phone"))
        return {
            "wire": _public_wire(wire),
            "syncResults": results,
        }

    def agent_model_config_status(self, component_id: str) -> dict[str, Any]:
        component_id = str(component_id or "").strip()
        target = AGENT_MODEL_CONFIGS.get(component_id)
        if not target:
            return {
                "componentId": component_id,
                "supported": False,
                "configured": False,
                "status": "unsupported",
                "message": "该组件暂不支持模型配置",
                "availableModels": [],
            }

        wire = self.current()
        config_path = self._agent_config_path(component_id)
        metadata = self._agent_config_metadata(component_id)
        model_lists = wire.get("modelLists") if isinstance(wire, dict) and isinstance(wire.get("modelLists"), dict) else {}
        text_models = _desktop_text_models(_list_values(model_lists.get("text")))
        current_model = _desktop_text_model(_model_value(wire, "text", "")) if isinstance(wire, dict) else ""
        if current_model and not text_models:
            text_models = [current_model, *text_models]
        metadata_model = _desktop_text_model(metadata.get("model"))
        expected_model = metadata_model or current_model
        actual_raw_model = _agent_config_model(component_id, config_path)
        actual_model = _desktop_text_model(actual_raw_model)
        user_config_path = _user_codex_config_path(self.paths) if component_id == "codex-desktop" else ""
        user_actual_raw_model = _agent_config_model(component_id, user_config_path) if user_config_path else ""
        user_actual_model = _desktop_text_model(user_actual_raw_model)
        invalid_actual_model = bool(actual_raw_model and not actual_model)
        invalid_user_model = bool(user_actual_raw_model and not user_actual_model)
        invalid_model = actual_raw_model if invalid_actual_model else ""
        config_matches = not invalid_actual_model and (not actual_model or not expected_model or actual_model == expected_model)
        user_config_matches = not invalid_user_model and (not user_actual_model or not expected_model or user_actual_model == expected_model)
        user_config_warning = _pick_text(metadata.get("userConfigWarning"))
        if component_id == "codex-desktop" and not user_config_warning:
            if invalid_user_model:
                user_config_warning = "用户 Codex 配置包含非文本模型；LOOM 专用配置仍可正常使用"
            elif user_actual_model and expected_model and user_actual_model != expected_model:
                user_config_warning = "用户 Codex 配置与 LOOM 专用配置不一致；LOOM 启动不受影响"
            elif user_config_path and not os.path.isfile(user_config_path):
                user_config_warning = "用户 Codex 配置未同步；LOOM 专用配置仍可正常使用"
        user_config_synchronized = component_id != "codex-desktop" or (not user_config_warning and user_config_matches)
        environment_warning = _pick_text(metadata.get("environmentWarning"))
        environment_synchronized = component_id != "codex-desktop" or not environment_warning
        optional_warnings = [warning for warning in (user_config_warning, environment_warning) if warning]
        optional_warning_message = "；".join(optional_warnings)
        configured = bool(
            os.path.isfile(config_path)
            and metadata.get("configured")
            and expected_model
            and config_matches
        )
        if not wire:
            status = "no_wire"
            message = "请先登录中转站或应用第三方模型配置"
        elif invalid_model:
            status = "unconfigured"
            message = "检测到手机/图像/视频模型被写入桌面 Agent，请重新写入文本模型配置"
        elif configured and component_id == "codex-desktop" and (not user_config_synchronized or not environment_synchronized):
            status = "configured_with_warning"
            message = optional_warning_message
        elif configured:
            status = "configured"
            message = "模型配置已写入"
        else:
            status = "unconfigured"
            message = "可写入 LOOM 管理配置"
        return {
            "componentId": component_id,
            "supported": True,
            "configured": configured,
            "status": status,
            "message": message,
            "model": actual_raw_model or metadata_model or current_model,
            "expectedModel": expected_model,
            "actualModel": actual_raw_model,
            "userActualModel": user_actual_raw_model,
            "invalidModel": invalid_model,
            "userInvalidModel": user_actual_raw_model if invalid_user_model else "",
            "userConfigSynchronized": user_config_synchronized,
            "userConfigWarning": user_config_warning,
            "environmentSynchronized": environment_synchronized,
            "environmentWarning": environment_warning,
            "provider": _pick_text(wire.get("provider")) if isinstance(wire, dict) else "",
            "baseUrl": _pick_text(wire.get("baseUrl")) if isinstance(wire, dict) else "",
            "managedBy": _wire_managed_by(wire) if isinstance(wire, dict) else "",
            "availableModels": text_models,
            "configPath": config_path,
            "userConfigPath": user_config_path,
            "backupAvailable": bool(metadata.get("backupPath") and os.path.exists(str(metadata.get("backupPath")))),
            "updatedAt": metadata.get("updatedAt") or "",
        }

    def sync_agent_model_config(self, component_id: str, *, model: str = "", wire: dict[str, Any] | None = None) -> dict[str, Any]:
        component_id = str(component_id or "").strip()
        if component_id not in AGENT_MODEL_CONFIGS:
            raise WireConfigError("该组件暂不支持模型配置")
        wire = wire or self.current()
        if not wire:
            raise WireConfigError("请先登录中转站或应用第三方模型配置")
        base_url = _pick_text(wire.get("baseUrl")).rstrip("/")
        api_key = _pick_text(wire.get("apiKey"))
        if _looks_like_non_text_model(model):
            raise WireConfigError("手机/图像/视频模型不能写入 Codex / Claude Code，请选择文本模型。")
        selected_model = _pick_agent_model(wire, model)
        if not selected_model:
            raise WireConfigError("没有可用文本模型，请同步/购买/换模型")
        if not base_url or not api_key:
            raise WireConfigError("中转站模型配置不完整，请先同步模型")
        _clear_stale_agent_model_env_keys(self.paths)

        if component_id == "openclaw-companion":
            return self._sync_openclaw_agent_model_config(component_id, wire, selected_model)

        config_path = self._agent_config_path(component_id)
        config_text = self._agent_config_text(component_id, wire, selected_model)
        backup_path = _write_text_with_backup(config_path, config_text)
        user_config_path = ""
        user_backup_path = ""
        user_config_warning = ""
        environment_warning = ""
        if component_id == "codex-desktop":
            user_config_path = _user_codex_config_path(self.paths)
            existing_user_config = _read_text(user_config_path) if os.path.isfile(user_config_path) else ""
            user_config_text = _codex_user_config_text(
                existing_user_config,
                base_url,
                _pick_text(wire.get("provider"), "LOOM"),
                selected_model,
                _wire_managed_by(wire),
            )
            try:
                user_backup_path = _write_text_with_backup(user_config_path, user_config_text)
            except Exception as exc:
                user_config_warning = _redact_secret_text(str(exc)) or "用户 Codex 配置写入失败"
                self.append_log(f"[Wire] optional Codex user config sync failed: {user_config_warning}\n")
        if component_id == "codex-desktop":
            try:
                _persist_agent_env_key(self.paths, "LOOM_CODEX_API_KEY", api_key)
            except Exception as exc:
                environment_warning = _redact_secret_text(str(exc)) or "Codex 用户环境变量写入失败"
                self.append_log(f"[Wire] optional Codex user environment sync failed: {environment_warning}\n")
        elif component_id == "claude-code":
            _persist_agent_env_key(self.paths, "LOOM_CLAUDE_API_KEY", api_key)

        metadata = {
            "componentId": component_id,
            "configured": True,
            "managedBy": _wire_managed_by(wire),
            "provider": _pick_text(wire.get("provider")),
            "baseUrl": base_url,
            "model": selected_model,
            "configPath": config_path,
            "userConfigPath": user_config_path,
            "backupPath": backup_path or self._agent_config_metadata(component_id).get("backupPath") or "",
            "userBackupPath": user_backup_path or self._agent_config_metadata(component_id).get("userBackupPath") or "",
            "userConfigSynchronized": not bool(user_config_warning),
            "userConfigWarning": user_config_warning,
            "environmentSynchronized": not bool(environment_warning),
            "environmentWarning": environment_warning,
            "updatedAt": _iso_now(),
        }
        write_json(self._agent_config_metadata_path(component_id), metadata)
        return self.agent_model_config_status(component_id)

    def rollback_agent_model_config(self, component_id: str) -> dict[str, Any]:
        component_id = str(component_id or "").strip()
        if component_id not in AGENT_MODEL_CONFIGS:
            raise WireConfigError("该组件暂不支持模型配置回滚")
        metadata = self._agent_config_metadata(component_id)
        backup_path = str(metadata.get("backupPath") or "")
        config_path = self._agent_config_path(component_id)
        if not backup_path or not os.path.isfile(backup_path):
            raise WireConfigError("没有可回滚的模型配置备份")
        _atomic_write_text(config_path, _read_text(backup_path))
        metadata["configured"] = True
        metadata["updatedAt"] = _iso_now()
        write_json(self._agent_config_metadata_path(component_id), metadata)
        return self.agent_model_config_status(component_id)

    def _sync_openclaw_agent_model_config(self, component_id: str, wire: dict[str, Any], selected_model: str) -> dict[str, Any]:
        config_path = self._agent_config_path(component_id)
        backup_path = _backup_text_file(config_path)
        models = wire.get("modelLists") if isinstance(wire.get("modelLists"), dict) else {}
        text_models = _desktop_text_models(_list_values(models.get("text")))
        if selected_model and selected_model not in text_models:
            text_models = [selected_model, *text_models]
        managed_by = _wire_managed_by(wire)
        try:
            ok = sync_openclaw_models_from_gateway_profile(
                self.paths,
                {
                    "source": managed_by,
                    "managedBy": managed_by,
                    "profileKey": "custom_provider" if managed_by == WIRE_CUSTOM_MANAGED_BY else "member_gateway",
                    "name": _pick_text(wire.get("provider"), "LOOM"),
                    "authMode": "custom" if managed_by == WIRE_CUSTOM_MANAGED_BY else "member",
                    "baseUrl": _pick_text(wire.get("baseUrl")),
                    "apiKey": _pick_text(wire.get("apiKey")),
                    "defaultModel": selected_model,
                    "imageModel": _model_value(wire, "image", ""),
                    "models": text_models or [selected_model],
                },
            )
            if not ok:
                raise WireConfigError("OpenClaw 模型配置写入失败，请先同步中转站模型")
        except Exception as exc:
            if backup_path and os.path.isfile(backup_path):
                _restore_text(config_path, _read_text(backup_path))
            if isinstance(exc, WireConfigError):
                raise
            raise WireConfigError(f"OpenClaw 模型配置写入失败：{exc}") from exc

        metadata = {
            "componentId": component_id,
            "configured": True,
            "managedBy": managed_by,
            "provider": _pick_text(wire.get("provider")),
            "baseUrl": _pick_text(wire.get("baseUrl")).rstrip("/"),
            "model": selected_model,
            "configPath": config_path,
            "backupPath": backup_path or self._agent_config_metadata(component_id).get("backupPath") or "",
            "updatedAt": _iso_now(),
        }
        write_json(self._agent_config_metadata_path(component_id), metadata)
        return self.agent_model_config_status(component_id)

    def _sync_openclaw(self, wire: dict[str, Any]) -> None:
        models = wire.get("modelLists") if isinstance(wire.get("modelLists"), dict) else {}
        text_models = _desktop_text_models(models.get("text") if isinstance(models.get("text"), list) else [])
        default_model = _desktop_text_model(_model_value(wire, "text", ""))
        if not default_model and text_models:
            default_model = text_models[0]
        managed_by = _wire_managed_by(wire)
        if not default_model:
            raise WireConfigError("没有可用文本模型，请同步/购买/换模型")
        ok = sync_openclaw_models_from_gateway_profile(
            self.paths,
            {
                "source": managed_by,
                "managedBy": managed_by,
                "profileKey": "custom_provider" if managed_by == WIRE_CUSTOM_MANAGED_BY else "member_gateway",
                "name": _pick_text(wire.get("provider"), "Member Gateway"),
                "authMode": "custom" if managed_by == WIRE_CUSTOM_MANAGED_BY else "member",
                "baseUrl": _pick_text(wire.get("baseUrl")),
                "apiKey": _pick_text(wire.get("apiKey")),
                "defaultModel": default_model,
                "imageModel": _model_value(wire, "image", ""),
                "models": text_models or [default_model],
            },
        )
        if not ok:
            raise WireConfigError("OpenClaw 模型配置写入失败，请先同步中转站模型")

    def _sync_opencode(self, wire: dict[str, Any]) -> None:
        base_url = _pick_text(wire.get("baseUrl")).rstrip("/")
        api_key = _pick_text(wire.get("apiKey"))
        default_model = _desktop_text_model(_model_value(wire, "text", ""))
        model_lists = wire.get("modelLists") if isinstance(wire.get("modelLists"), dict) else {}
        text_models = _desktop_text_models(_list_values(model_lists.get("text")))
        if default_model and default_model not in text_models:
            text_models = [default_model, *text_models]
        text_models = [model for model in text_models if model]
        if not default_model and text_models:
            default_model = text_models[0]
        if not text_models and default_model:
            text_models = [default_model]
        if not default_model:
            raise WireConfigError("没有可用文本模型，请同步/购买/换模型")
        if not base_url or not api_key:
            raise WireConfigError("opencode 缺少中转站模型配置")

        _clear_stale_agent_model_env_keys(self.paths)
        provider_id = "loom"
        config_dir = os.path.join(self.paths.data_dir, ".opencode")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "opencode.json")
        config = read_json(config_path, {})
        if not isinstance(config, dict):
            config = {}
        config["$schema"] = "https://opencode.ai/config.json"
        config["model"] = f"{provider_id}/{default_model}"
        provider = config.get("provider") if isinstance(config.get("provider"), dict) else {}
        provider[provider_id] = {
            "name": "LOOM 中转站",
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": base_url,
                "apiKey": "{env:LOOM_OPENCODE_API_KEY}",
            },
            "models": {model: {"name": model} for model in text_models},
        }
        config["provider"] = provider
        write_json(config_path, config)
        _persist_agent_env_key(self.paths, "LOOM_OPENCODE_API_KEY", api_key)

    def _sync_codex(self, wire: dict[str, Any]) -> None:
        self.sync_agent_model_config("codex-desktop", wire=wire)

    def _sync_claude(self, wire: dict[str, Any]) -> None:
        self.sync_agent_model_config("claude-code", wire=wire)

    def _sync_image(self, wire: dict[str, Any]) -> None:
        image_model = _model_value(wire, "image", "")
        if not image_model:
            return
        current = read_json(self.paths.image_config, {})
        if not isinstance(current, dict):
            current = {}
        if current.get("lockedByUser") is True:
            return
        managed_by = _wire_managed_by(wire)
        current.update({
            "gatewayMode": "member",
            "managedBy": managed_by,
            "baseUrl": _pick_text(wire.get("baseUrl")),
            "apiKey": _pick_text(wire.get("apiKey")),
            "model": image_model,
        })
        write_json(self.paths.image_config, current)

    def _sync_desktop(self, wire: dict[str, Any]) -> None:
        model = _desktop_text_model(_model_value(wire, "text", ""))
        if not model:
            model_lists = wire.get("modelLists") if isinstance(wire.get("modelLists"), dict) else {}
            text_models = _desktop_text_models(_list_values(model_lists.get("text")))
            model = text_models[0] if text_models else ""
        if not model:
            raise WireConfigError("没有可用文本模型，请同步/购买/换模型")
        managed_by = _wire_managed_by(wire)
        provider = {
            "managedBy": managed_by,
            "apiKey": _pick_text(wire.get("apiKey")),
            "baseUrl": _pick_text(wire.get("baseUrl")),
            "baseURL": _pick_text(wire.get("baseUrl")),
            "model": model,
        }
        path = os.path.join(self.paths.launcher_dir, "desktop-agent.json")
        current = read_json(path, {})
        if not isinstance(current, dict):
            current = {}
        current.setdefault("provider", {})
        current.setdefault("llm", {})
        current.setdefault("chatProvider", {})
        current["chatProvider"].setdefault("config", {})
        current["provider"].update(provider)
        current["llm"].update(provider)
        current["chatProvider"]["config"].update(provider)
        write_json(path, current)

    def _sync_phone(self, wire: dict[str, Any]) -> None:
        path = os.path.join(self.paths.launcher_dir, "phone-agent.json")
        current = read_json(path, {})
        if not isinstance(current, dict):
            current = {}
        current.setdefault("llm", {})
        managed_by = _wire_managed_by(wire)
        current["llm"].update({
            "managedBy": managed_by,
            "baseUrl": _pick_text(wire.get("baseUrl")),
            "apiKey": _pick_text(wire.get("apiKey")),
            "model": _model_value(wire, "phone", DEFAULT_PHONE_MODEL),
        })
        write_json(path, current)

    def _clear_video(self, _wire: dict[str, Any]) -> None:
        for path in (self.paths.video_config, self.paths.videoapi_config):
            current = read_json(path, {})
            if not isinstance(current, dict) or current.get("lockedByUser") is True:
                continue
            if current.get("managedBy") in MANAGED_ACCOUNT_SOURCES or current.get("gatewayMode") == "member":
                write_json(path, {})

    def _agent_config_path(self, component_id: str) -> str:
        target = AGENT_MODEL_CONFIGS[component_id]
        return os.path.join(self.paths.data_dir, str(target["configDir"]), str(target["configFile"]))

    def _agent_config_metadata_path(self, component_id: str) -> str:
        return os.path.join(self.paths.launcher_dir, "agent-model-configs", f"{component_id}.json")

    def _agent_config_metadata(self, component_id: str) -> dict[str, Any]:
        metadata = read_json(self._agent_config_metadata_path(component_id), {})
        return metadata if isinstance(metadata, dict) else {}

    def _agent_config_text(self, component_id: str, wire: dict[str, Any], model: str) -> str:
        base_url = _pick_text(wire.get("baseUrl")).rstrip("/")
        provider = _pick_text(wire.get("provider"), "LOOM")
        if component_id == "codex-desktop":
            return _codex_config_text(base_url, provider, model, _wire_managed_by(wire))
        if component_id == "claude-code":
            return _claude_settings_text(base_url, provider, model)
        raise WireConfigError("该组件暂不支持模型配置")


def build_wire_from_session(session: dict[str, Any]) -> dict[str, Any]:
    gateway = session.get("gateway") if isinstance(session.get("gateway"), dict) else {}
    newapi = session.get("newApi") if isinstance(session.get("newApi"), dict) else {}
    phone_agent = session.get("phoneAgent") if isinstance(session.get("phoneAgent"), dict) else {}
    classes = gateway.get("classifiedModels") if isinstance(gateway.get("classifiedModels"), dict) else newapi.get("modelClasses")
    if not isinstance(classes, dict):
        classes = _classify_models(session.get("gatewayModels") if isinstance(session.get("gatewayModels"), list) else [])

    text_model = _pick_text_model(
        _pick_text(session.get("gatewayDefaultModel"), gateway.get("defaultModel")),
        classes.get("text"),
        "",
    )
    image_model = _pick_model(_pick_text(session.get("gatewayImageModel"), gateway.get("imageModel")), classes.get("image"), "")
    video_model = _pick_model(
        _pick_text(session.get("gatewayVideoDraftModel"), gateway.get("videoDraftModel"), session.get("gatewayVideoModel")),
        classes.get("video"),
        "",
    )
    phone_model = _pick_text(phone_agent.get("model"), DEFAULT_PHONE_MODEL)
    api_key = _pick_text(phone_agent.get("apiKey"), session.get("memberToken"), gateway.get("accessToken"))
    base_url = _pick_text(phone_agent.get("baseUrl"), session.get("gatewayBaseUrl"), gateway.get("baseUrl"), "https://api.heang.top/v1")
    text_model_list = _desktop_text_models(_list_values(classes.get("text")))
    if text_model and text_model not in text_model_list:
        text_model_list = [text_model, *text_model_list]
    model_lists = {
        "text": text_model_list,
        "image": _list_values(classes.get("image")),
        "video": _list_values(classes.get("video")),
    }
    return {
        "schemaVersion": 1,
        "managedBy": WIRE_MANAGED_BY,
        "accountId": _pick_text(session.get("memberId"), newapi.get("userId")),
        "account": _pick_text(session.get("memberName"), newapi.get("account")),
        "provider": WIRE_PROVIDER,
        "baseUrl": base_url.rstrip("/"),
        "apiKey": api_key,
        "tokenMasked": _mask_secret(api_key),
        "models": {
            "text": text_model,
            "phone": phone_model,
            "image": image_model,
            "video": video_model,
        },
        "modelLists": model_lists,
            "targets": {
                "openclaw": True,
                "phone": True,
                "desktopRpa": True,
                "imageGateway": bool(image_model),
                "videoGateway": False,
                "opencode": True,
                "codex": True,
                "claude": True,
            },
        "updatedAt": _iso_now(),
    }


def _protected_wire(wire: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(wire)
    if payload.get("apiKey"):
        payload["apiKey"] = protect_secret(payload.get("apiKey"))
    return payload


def _read_json_if_exists(path: str) -> Any | None:
    if not os.path.exists(path):
        return None
    return read_json(path, None)


def _unprotect_wire(wire: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(wire)
    if "apiKey" in payload:
        payload["apiKey"] = unprotect_secret(payload.get("apiKey"))
    return payload


def _public_wire(wire: dict[str, Any] | None) -> dict[str, Any]:
    if not wire:
        return {
            "ok": False,
            "managedBy": "",
            "provider": "",
            "models": {"text": "", "phone": "", "image": "", "video": ""},
            "targets": {},
        }
    payload = copy.deepcopy(wire)
    payload.pop("apiKey", None)
    payload["ok"] = True
    payload["tokenMasked"] = _mask_secret(wire.get("apiKey") or wire.get("tokenMasked") or "")
    return payload


def _classify_models(models: list[Any]) -> dict[str, list[str]]:
    classified = {"text": [], "image": [], "video": []}
    for raw in models:
        model = _pick_text(raw.get("id") if isinstance(raw, dict) else raw)
        if not model:
            continue
        if _looks_like_video_model(model):
            classified["video"].append(model)
        elif _looks_like_image_model(model):
            classified["image"].append(model)
        elif _looks_like_phone_model(model):
            continue
        else:
            classified["text"].append(model)
    return classified


def _list_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = _pick_text(value.get("id") if isinstance(value, dict) else value)
        if text and text not in result:
            result.append(text)
    return result


def _model_value(wire: dict[str, Any], key: str, fallback: str) -> str:
    models = wire.get("models") if isinstance(wire.get("models"), dict) else {}
    return _pick_text(models.get(key), fallback)


def _pick_agent_model(wire: dict[str, Any], preferred: str = "") -> str:
    model_lists = wire.get("modelLists") if isinstance(wire.get("modelLists"), dict) else {}
    text_models = _desktop_text_models(_list_values(model_lists.get("text")))
    preferred = _pick_text(preferred)
    if preferred:
        return _desktop_text_model(preferred)
    current = _desktop_text_model(_model_value(wire, "text", ""))
    if current and (not text_models or current in text_models):
        return current
    return text_models[0] if text_models else ""


def _pick_model(preferred: str, candidates: Any, fallback: str) -> str:
    values = _list_values(candidates)
    if preferred and (not values or preferred in values):
        return preferred
    return values[0] if values else fallback


def _pick_text_model(preferred: str, candidates: Any, fallback: str) -> str:
    values = _desktop_text_models(_list_values(candidates))
    preferred = _desktop_text_model(preferred)
    fallback = _desktop_text_model(fallback)
    if preferred and (not values or preferred in values):
        return preferred
    for model in TEXT_MODEL_PRIORITY:
        if model in values:
            return model
    return values[0] if values else fallback


def _looks_like_phone_model(model_id: Any) -> bool:
    text = _pick_text(model_id).lower()
    return bool(text) and text in PHONE_MODEL_IDS


def _looks_like_image_model(model_id: Any) -> bool:
    text = _pick_text(model_id).lower()
    return bool(text) and any(marker in text for marker in IMAGE_MODEL_MARKERS)


def _looks_like_video_model(model_id: Any) -> bool:
    text = _pick_text(model_id).lower()
    return bool(text) and any(marker in text for marker in VIDEO_MODEL_MARKERS)


def _looks_like_non_text_model(model_id: Any) -> bool:
    return _looks_like_phone_model(model_id) or _looks_like_image_model(model_id) or _looks_like_video_model(model_id)


def _desktop_text_model(model_id: Any) -> str:
    text = _pick_text(model_id)
    return "" if _looks_like_non_text_model(text) else text


def _desktop_text_models(models: list[str]) -> list[str]:
    result: list[str] = []
    for model in models:
        text = _desktop_text_model(model)
        if text and text not in result:
            result.append(text)
    return result


def _wire_managed_by(wire: dict[str, Any]) -> str:
    value = _pick_text(wire.get("managedBy"), WIRE_MANAGED_BY)
    return value if value in MANAGED_ACCOUNT_SOURCES else WIRE_MANAGED_BY


def _normalize_base_url(value: Any) -> str:
    text = _pick_text(value).rstrip("/")
    if not text:
        return ""
    if not text.startswith(("http://", "https://")):
        text = f"https://{text}"
    return text.rstrip("/")


def _pick_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return ""


def _agent_config_model(component_id: str, path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        if component_id == "codex-desktop":
            for line in _read_text(path).splitlines():
                stripped = line.strip()
                if stripped.startswith("model = "):
                    return _pick_text(stripped.split("=", 1)[1].strip().strip('"'))
        if component_id == "claude-code":
            payload = json.loads(_read_text(path))
            env = payload.get("env") if isinstance(payload, dict) else {}
            return _pick_text(env.get("ANTHROPIC_MODEL")) if isinstance(env, dict) else ""
    except Exception:
        return ""
    return ""


def _mask_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"


def _codex_provider_id(provider: str, managed_by: str = "") -> str:
    if managed_by == WIRE_MANAGED_BY and _pick_text(provider).lower() in {"", "loom", "luming", "麓鸣"}:
        provider = WIRE_PROVIDER
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", _pick_text(provider, WIRE_PROVIDER).lower()).strip("-_")
    if not slug or slug in {"openai", "ollama", "lmstudio"}:
        slug = "loom"
    return slug


def _codex_provider_block(base_url: str, provider: str, provider_id: str) -> list[str]:
    return [
        f"[model_providers.{provider_id}]",
        f'name = "{_toml_string(provider or "LOOM")}"',
        f'base_url = "{_toml_string(base_url)}"',
        'env_key = "LOOM_CODEX_API_KEY"',
        'wire_api = "responses"',
    ]


def _codex_config_text(base_url: str, provider: str, model: str, managed_by: str = "") -> str:
    provider_id = _codex_provider_id(provider, managed_by)
    return "\n".join([
        "# Managed by LOOM. The real token is injected at launch time.",
        "# Only model/provider fields are managed; personal Codex plugins and MCP stay in user config.",
        f'model = "{_toml_string(model)}"',
        f'model_provider = "{provider_id}"',
        "",
        *_codex_provider_block(base_url, provider, provider_id),
        "",
    ])


def _codex_user_config_text(existing_text: str, base_url: str, provider: str, model: str, managed_by: str = "") -> str:
    if not _pick_text(existing_text):
        return _codex_config_text(base_url, provider, model, managed_by)
    provider_id = _codex_provider_id(provider, managed_by)
    lines = existing_text.splitlines()
    lines = _upsert_top_level_toml_value(lines, "model", model)
    lines = _upsert_top_level_toml_value(lines, "model_provider", provider_id)
    lines = _remove_toml_table(lines, f"[model_providers.{provider_id}]")
    while lines and not lines[-1].strip():
        lines.pop()
    lines.extend(["", *_codex_provider_block(base_url, provider, provider_id), ""])
    return "\n".join(lines)


def _upsert_top_level_toml_value(lines: list[str], key: str, value: str) -> list[str]:
    result: list[str] = []
    replaced = False
    in_top_level = True
    assignment = f'{key} = "{_toml_string(value)}"'
    key_pattern = re.compile(rf"^{re.escape(key)}\s*=")
    for line in lines:
        stripped = line.strip()
        if in_top_level and stripped.startswith("[") and stripped.endswith("]"):
            if not replaced:
                result.append(assignment)
                replaced = True
            in_top_level = False
        if in_top_level and key_pattern.match(stripped):
            if not replaced:
                result.append(assignment)
                replaced = True
            continue
        result.append(line)
    if in_top_level and not replaced:
        result.append(assignment)
    return result


def _remove_toml_table(lines: list[str], table_header: str) -> list[str]:
    result: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == table_header:
                skipping = True
                continue
            if skipping:
                skipping = False
        if not skipping:
            result.append(line)
    return result


def _user_codex_config_path(paths: AppPaths) -> str:
    override = _pick_text(os.environ.get("LOOM_CODEX_CONFIG_PATH"))
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base_path = os.path.abspath(paths.base_path)
    temp_root = os.path.abspath(tempfile.gettempdir())
    if base_path.startswith(temp_root):
        return os.path.join(paths.data_dir, ".codex-user", "config.toml")
    return os.path.join(os.path.expanduser("~"), ".codex", "config.toml")


def clear_agent_user_env_keys(paths: AppPaths) -> None:
    for name in AGENT_ENV_KEYS:
        os.environ.pop(name, None)
        if _should_persist_user_env(paths):
            _delete_user_env_var(name)


def _clear_stale_agent_model_env_keys(paths: AppPaths) -> None:
    for name in AGENT_STALE_MODEL_ENV_KEYS:
        os.environ.pop(name, None)
        if _should_persist_user_env(paths):
            _delete_user_env_var(name)


def _persist_agent_env_key(paths: AppPaths, name: str, value: str) -> None:
    if name not in AGENT_ENV_KEYS or not value:
        return
    os.environ[name] = value
    if _should_persist_user_env(paths):
        _write_user_env_var(name, value)


def _should_persist_user_env(paths: AppPaths) -> bool:
    if str(os.environ.get("LOOM_DISABLE_USER_ENV_SYNC") or "").strip().lower() in {"1", "true", "yes"}:
        return False
    if str(os.environ.get("LOOM_FORCE_USER_ENV_SYNC") or "").strip().lower() in {"1", "true", "yes"}:
        return True
    try:
        base_path = os.path.abspath(paths.base_path)
        temp_root = os.path.abspath(tempfile.gettempdir())
        return not (base_path == temp_root or base_path.startswith(temp_root + os.sep))
    except Exception:
        return False


def _write_user_env_var(name: str, value: str) -> None:
    if os.name != "nt":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
    _broadcast_user_env_change()


def _delete_user_env_var(name: str) -> None:
    if os.name != "nt":
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return
    _broadcast_user_env_change()


def _broadcast_user_env_change() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None,
        )
    except Exception:
        pass


def _anthropic_base_url(base_url: str) -> str:
    text = _pick_text(base_url).rstrip("/")
    if text.endswith("/v1"):
        return text[:-3].rstrip("/")
    return text


def _claude_settings_text(base_url: str, provider: str, model: str) -> str:
    return json.dumps({
        "managedBy": "LOOM",
        "provider": provider or "LOOM",
        "env": {
            "ANTHROPIC_BASE_URL": _anthropic_base_url(base_url),
            "ANTHROPIC_AUTH_TOKEN": "{env:LOOM_CLAUDE_API_KEY}",
            "ANTHROPIC_API_KEY": "{env:LOOM_CLAUDE_API_KEY}",
            "ANTHROPIC_MODEL": model,
        },
    }, indent=2, ensure_ascii=False) + "\n"


def _write_text_with_backup(path: str, text: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    backup_path = _backup_text_file(path)
    try:
        _atomic_write_text(path, text)
    except Exception as exc:
        if backup_path and os.path.isfile(backup_path):
            _restore_text(path, _read_text(backup_path))
        raise WireConfigError(f"模型配置写入失败：{exc}") from exc
    return backup_path


def _backup_text_file(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    backup_dir = os.path.join(os.path.dirname(path), ".loom-backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(backup_dir, f"{os.path.basename(path)}.{stamp}.bak")
    _restore_text(backup_path, _read_text(path))
    return backup_path


def _atomic_write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".loom-", suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _restore_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _toml_string(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _redact_secret_text(value: Any) -> str:
    text = str(value or "")
    for pattern in SECRET_TEXT_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", text)
        elif pattern.groups == 2:
            text = pattern.sub(lambda match: f"{match.group(1)}[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    return text


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
