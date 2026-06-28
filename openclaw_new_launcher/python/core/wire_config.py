"""Runtime wire contract for account-to-local configuration sync."""

from __future__ import annotations

import copy
import os
import re
from datetime import datetime, timezone
from typing import Any

from core.openclaw_model_sync import sync_openclaw_models_from_gateway_profile
from core.paths import AppPaths
from core.secret_store import protect_secret, unprotect_secret
from core.storage import read_json, write_json


WIRE_MANAGED_BY = "heang_account"
WIRE_PROVIDER = "heang"
WIRE_CUSTOM_MANAGED_BY = "custom_provider"
DEFAULT_TEXT_MODEL = "qwen3.7-plus"
DEFAULT_PHONE_MODEL = "agnes-2.0-flash"
MANAGED_ACCOUNT_SOURCES = {"newapi_account", WIRE_MANAGED_BY, WIRE_CUSTOM_MANAGED_BY}

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
        wire = read_json(self.paths.wire_current, None)
        if not isinstance(wire, dict):
            return None
        return _unprotect_wire(wire)

    def current_public(self) -> dict[str, Any]:
        return _public_wire(self.current())

    def sync_from_session(
        self,
        session: dict[str, Any],
        *,
        targets: tuple[str, ...] = ("openclaw", "image", "desktop", "phone"),
    ) -> dict[str, Any]:
        wire = build_wire_from_session(session)
        current = read_json(self.paths.wire_current, None)
        if isinstance(current, dict):
            write_json(self.paths.wire_last_good, current)
        elif not os.path.exists(self.paths.wire_last_good):
            write_json(self.paths.wire_last_good, _protected_wire(wire))

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
        targets: tuple[str, ...] = ("openclaw", "image", "desktop", "phone"),
    ) -> dict[str, Any]:
        provider = _pick_text(provider, "自定义 Provider")
        base_url = _normalize_base_url(base_url)
        api_key = _pick_text(api_key)
        text_model = _pick_text(text_model)
        image_model = _pick_text(image_model)
        phone_model = _pick_text(phone_model, text_model, DEFAULT_PHONE_MODEL)
        video_model = _pick_text(video_model)
        if not base_url:
            raise WireConfigError("请输入第三方 Provider URL")
        if not api_key:
            raise WireConfigError("请输入第三方 API Key")
        if not text_model:
            raise WireConfigError("请输入默认文本模型")

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
                "codex": False,
            },
            "updatedAt": _iso_now(),
        }
        current = read_json(self.paths.wire_current, None)
        if isinstance(current, dict):
            write_json(self.paths.wire_last_good, current)
        elif not os.path.exists(self.paths.wire_last_good):
            write_json(self.paths.wire_last_good, _protected_wire(wire))
        write_json(self.paths.wire_current, _protected_wire(wire))
        results = self.apply_wire(wire, targets=targets)
        return {
            "wire": _public_wire(wire),
            "syncResults": results,
        }

    def apply_wire(self, wire: dict[str, Any], *, targets: tuple[str, ...]) -> list[dict[str, Any]]:
        actions = {
            "openclaw": self._sync_openclaw,
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
        previous = read_json(self.paths.wire_last_good, None)
        if not isinstance(previous, dict):
            raise WireConfigError("没有可回滚的模型同步快照")
        write_json(self.paths.wire_current, previous)
        wire = _unprotect_wire(previous)
        results = self.apply_wire(wire, targets=("openclaw", "image", "desktop", "phone"))
        return {
            "wire": _public_wire(wire),
            "syncResults": results,
        }

    def _sync_openclaw(self, wire: dict[str, Any]) -> None:
        models = wire.get("modelLists") if isinstance(wire.get("modelLists"), dict) else {}
        text_models = models.get("text") if isinstance(models.get("text"), list) else []
        default_model = _model_value(wire, "text", DEFAULT_TEXT_MODEL)
        managed_by = _wire_managed_by(wire)
        sync_openclaw_models_from_gateway_profile(
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
        model = _model_value(wire, "text", DEFAULT_TEXT_MODEL)
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


def build_wire_from_session(session: dict[str, Any]) -> dict[str, Any]:
    gateway = session.get("gateway") if isinstance(session.get("gateway"), dict) else {}
    newapi = session.get("newApi") if isinstance(session.get("newApi"), dict) else {}
    phone_agent = session.get("phoneAgent") if isinstance(session.get("phoneAgent"), dict) else {}
    classes = gateway.get("classifiedModels") if isinstance(gateway.get("classifiedModels"), dict) else newapi.get("modelClasses")
    if not isinstance(classes, dict):
        classes = _classify_models(session.get("gatewayModels") if isinstance(session.get("gatewayModels"), list) else [])

    text_model = _pick_model(_pick_text(session.get("gatewayDefaultModel"), gateway.get("defaultModel")), classes.get("text"), DEFAULT_TEXT_MODEL)
    image_model = _pick_model(_pick_text(session.get("gatewayImageModel"), gateway.get("imageModel")), classes.get("image"), "")
    video_model = _pick_model(
        _pick_text(session.get("gatewayVideoDraftModel"), gateway.get("videoDraftModel"), session.get("gatewayVideoModel")),
        classes.get("video"),
        "",
    )
    phone_model = _pick_text(phone_agent.get("model"), DEFAULT_PHONE_MODEL)
    api_key = _pick_text(phone_agent.get("apiKey"), session.get("memberToken"), gateway.get("accessToken"))
    base_url = _pick_text(phone_agent.get("baseUrl"), session.get("gatewayBaseUrl"), gateway.get("baseUrl"), "https://api.heang.top/v1")
    model_lists = {
        "text": _list_values(classes.get("text")),
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
            "codex": False,
        },
        "updatedAt": _iso_now(),
    }


def _protected_wire(wire: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(wire)
    if payload.get("apiKey"):
        payload["apiKey"] = protect_secret(payload.get("apiKey"))
    return payload


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
        lower = model.lower()
        if any(marker in lower for marker in ("video", "veo", "sora", "seedance", "kling", "wan", "hailuo", "runway", "pika", "luma")):
            classified["video"].append(model)
        elif any(marker in lower for marker in ("image", "dall-e", "gpt-image", "flux", "midjourney", "sd-", "imagen", "seedream")):
            classified["image"].append(model)
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


def _pick_model(preferred: str, candidates: Any, fallback: str) -> str:
    values = _list_values(candidates)
    if preferred and (not values or preferred in values):
        return preferred
    return values[0] if values else fallback


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


def _mask_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"


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
