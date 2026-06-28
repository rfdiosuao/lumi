"""UI-facing component catalog derived from the release manifest and local state."""

from __future__ import annotations

import os
from typing import Any

from collections.abc import Iterable

from core.component_state import ComponentState, ComponentStateStore
from core.release_manifest import (
    ReleaseComponent,
    ReleaseManifest,
    default_release_manifest_public_key,
    load_release_manifest_file,
)
from core.release_manifest_client import ReleaseManifestClient, default_release_manifest_sources


INSTALLED_STATUSES = {"ready", "started", "starting", "start_failed", "upgrade_available"}


class ComponentCatalog:
    def __init__(
        self,
        *,
        manifest_path: str,
        state_store: ComponentStateStore,
        fallback_components: Iterable[ReleaseComponent] = (),
    ):
        self.manifest_path = manifest_path
        self.state_store = state_store
        self.fallback_components = tuple(fallback_components)

    def status(self, *, state_overrides: Iterable[ComponentState] = ()) -> dict[str, Any]:
        overrides = {state.component_id: state for state in state_overrides}
        try:
            manifest, manifest_warning = load_installable_manifest(self.manifest_path)
        except Exception as exc:
            states = self.state_store.load()
            states.update(overrides)
            return {
                "manifest": None,
                "components": [
                    _component_payload(component, states.get(component.component_id) or _default_state(component))
                    for component in self.fallback_components
                ],
                "warning": f"正式组件清单未就绪。请提供已签名的 release-manifest.json 和 release-public-key.txt，或确认 release-channel 可访问；当前仅支持本机检测。{exc}",
                "manifestErrorCode": "manifest_unavailable",
            }

        states = {state.component_id: state for state in self.state_store.snapshot_for_manifest(manifest)}
        states.update(overrides)
        return {
            "manifest": _manifest_payload(manifest),
            "components": [_component_payload(component, states[component.component_id]) for component in manifest.components],
            "warning": manifest_warning,
            "manifestErrorCode": None,
        }


def default_manifest_path(base_path: str) -> str:
    parent_path = os.path.dirname(os.path.abspath(base_path))
    candidates = [
        os.path.join(base_path, "release-manifest.json"),
        os.path.join(base_path, "_up_", "release-manifest.json"),
        os.path.join(parent_path, "release-manifest.json"),
        os.path.join(parent_path, "_up_", "release-manifest.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def default_component_state_path(base_path: str) -> str:
    return os.path.join(base_path, "data", ".installer", "components-state.json")


def load_installable_manifest(manifest_path: str) -> tuple[ReleaseManifest, str | None]:
    public_key = default_release_manifest_public_key(manifest_path)
    local_error: Exception | None = None
    if os.path.exists(manifest_path):
        try:
            return (
                load_release_manifest_file(
                    manifest_path,
                    public_key=public_key,
                    require_signature_verification=True,
                ),
                None,
            )
        except Exception as exc:
            local_error = exc

    client = ReleaseManifestClient(cache_path=manifest_path, public_key=public_key, timeout=5.0)
    result = client.fetch(default_release_manifest_sources())
    warning_parts = list(result.warnings)
    if local_error is not None:
        warning_parts.insert(0, f"local manifest failed: {local_error}")
    if result.from_cache:
        warning_parts.append("使用本机缓存的 release manifest")
    elif result.source_url:
        warning_parts.append(f"release manifest 来自 {result.source_url}")
    return result.manifest, "；".join(warning_parts) if warning_parts else None


def _manifest_payload(manifest: ReleaseManifest) -> dict[str, Any]:
    return {
        "schemaVersion": manifest.schema_version,
        "product": manifest.product,
        "channel": manifest.channel,
        "version": manifest.version,
        "publishedAt": manifest.published_at,
        "minLauncherVersion": manifest.min_launcher_version,
    }


def _default_state(component: ReleaseComponent) -> ComponentState:
    return ComponentState(
        component_id=component.component_id,
        status="not_installed",
        version=component.version,
        updated_at=None,
    )


def _component_payload(component: ReleaseComponent, state) -> dict[str, Any]:
    return {
        "id": component.component_id,
        "name": component.name,
        "version": component.version,
        "installedVersion": state.version if state.status in INSTALLED_STATUSES else None,
        "previousVersion": state.previous_version,
        "status": state.status,
        "jobId": state.job_id,
        "platform": component.platform,
        "arch": component.arch,
        "type": component.archive_type,
        "size": component.size,
        "entry": component.entry,
        "installPath": component.install_path,
        "installCommand": list(component.install_command),
        "uninstallCommand": list(component.uninstall_command),
        "commandTimeoutMs": component.command_timeout_ms,
        "category": component.category or "component",
        "officialUrl": component.official_url,
        "description": component.description,
        "urls": list(component.urls),
        "updatedAt": state.updated_at,
        "errorCode": state.error_code,
        "errorMessage": state.error_message,
    }
