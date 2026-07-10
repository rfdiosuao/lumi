"""Component download, verification, extraction, and rollback."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import zipfile
from dataclasses import dataclass
from typing import Callable, List
from urllib.request import Request, urlopen

from core.component_state import ComponentState, ComponentStateStore
from core.release_manifest import ReleaseComponent
from core.secret_store import unprotect_secret


ComponentFetcher = Callable[[str, float], bytes]
ComponentHealthChecker = Callable[[ReleaseComponent, str], None]
ComponentLauncher = Callable[[str, str], dict]
ComponentInstallerRunner = Callable[[List[str], str, int], subprocess.CompletedProcess]
ProgressCallback = Callable[[str, str], None]
RetrySleeper = Callable[[float], None]


class ComponentInstallError(RuntimeError):
    """Raised when a component cannot be installed safely."""


WINDOWS_COMMAND_SUFFIXES = ("", ".cmd", ".exe", ".ps1", ".bat")

KNOWN_COMPONENT_COMMANDS: dict[str, tuple[str, ...]] = {
    "codex-desktop": ("Codex", "codex"),
    "claude-code": ("claude",),
    "opencode": ("opencode",),
    "openclaw-companion": ("openclaw",),
    "hermes": ("hermes",),
}

KNOWN_NPM_PACKAGE_COMMANDS: dict[str, tuple[str, ...]] = {
    "@openai/codex": ("codex",),
    "@anthropic-ai/claude-code": ("claude",),
    "opencode-ai": ("opencode",),
    "opencode-windows-x64": ("opencode",),
    "openclaw": ("openclaw",),
}

RETRY_DELAYS_SECONDS = (0.0, 0.8, 1.6)
EXTERNAL_ENTRY_CACHE_TTL_SECONDS = 30.0
VERSION_DETECT_TIMEOUT_MS = 5000
_EXTERNAL_ENTRY_CACHE: dict[tuple[object, ...], tuple[float, str | None]] = {}
CODEX_DESKTOP_PACKAGE_NAME = "OpenAI.Codex"
CODEX_DESKTOP_APP_ID = "App"
PYTHON_SOURCE_CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")
PHONE_MODEL_IDS = {"agnes-2.0-flash"}
NON_TEXT_MODEL_MARKERS = (
    "image",
    "dall-e",
    "gpt-image",
    "flux",
    "midjourney",
    "sd-",
    "imagen",
    "seedream",
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
MODEL_ENV_SCRUB_COMPONENTS = {"codex-desktop", "claude-code", "opencode", "openclaw-companion"}
AGENT_MODEL_ENV_KEYS = (
    "LOOM_CODEX_API_KEY",
    "LOOM_CLAUDE_API_KEY",
    "LOOM_OPENCODE_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "OPENAI_API_TYPE",
    "OPENAI_API_VERSION",
    "OPENAI_MODEL",
    "OPENAI_ORG_ID",
    "OPENAI_ORGANIZATION",
    "OPENAI_PROJECT",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "CLAUDE_API_KEY",
    "CLAUDE_CODE_API_KEY",
    "CLAUDE_CODE_MODEL",
    "OPENCODE_API_KEY",
    "OPENCODE_BASE_URL",
    "OPENCODE_MODEL",
    "OPENCODE_PROVIDER",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENROUTER_API_KEY",
    "SILICONFLOW_API_KEY",
    "VOLCENGINE_ARK_API_KEY",
    "XAI_API_KEY",
    "ZHIPUAI_API_KEY",
)


@dataclass(frozen=True)
class PreviousInstall:
    path: str
    version: str | None


class ComponentInstaller:
    def __init__(
        self,
        *,
        base_path: str,
        state_store: ComponentStateStore,
        fetcher: ComponentFetcher | None = None,
        health_checker: ComponentHealthChecker | None = None,
        launcher: ComponentLauncher | None = None,
        installer_runner: ComponentInstallerRunner | None = None,
        retry_sleep: RetrySleeper | None = None,
        timeout: float = 30.0,
    ):
        self.base_path = os.path.abspath(base_path)
        self.state_store = state_store
        self.fetcher = fetcher or _default_fetcher
        self.health_checker = health_checker or _default_health_checker
        self.launcher = launcher or self._default_launcher
        self._custom_launcher = launcher is not None
        self.installer_runner = installer_runner or _default_installer_runner
        self.retry_sleep = retry_sleep or time.sleep
        self.timeout = timeout
        self.cache_dir = os.path.join(self.base_path, "data", ".installer", "cache")
        self.staging_dir = os.path.join(self.base_path, "data", ".installer", "staging")
        self.rollback_dir = os.path.join(self.base_path, "data", ".installer", "rollback")

    def install(
        self,
        component: ReleaseComponent,
        *,
        simulate: bool = False,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ComponentState:
        existing_state = self.state_store.load().get(component.component_id)
        existing_version = existing_state.version if existing_state else None
        if simulate:
            return self._simulate_install(component, job_id=job_id, on_progress=on_progress)
        self._mark(component, "downloading", job_id=job_id, on_progress=on_progress, message=f"下载 {component.name}")
        try:
            package = self._download(component, on_progress=on_progress)
        except Exception as exc:
            self.state_store.mark(component.component_id, "download_failed", version=component.version, job_id=job_id, error_message=str(exc))
            if on_progress:
                on_progress(f"下载失败：{exc}", "danger")
            raise ComponentInstallError(f"download failed for {component.component_id}: {exc}") from exc

        self._mark(component, "verifying", job_id=job_id, on_progress=on_progress, message=f"校验 {component.name}")
        digest = hashlib.sha256(package).hexdigest()
        if digest.lower() != component.sha256.lower():
            self.state_store.mark(
                component.component_id,
                "verify_failed",
                version=component.version,
                job_id=job_id,
                error_code="sha256_mismatch",
                error_message=f"sha256 mismatch: expected {component.sha256}, got {digest}",
            )
            if on_progress:
                on_progress("校验失败：sha256 不匹配", "danger")
            raise ComponentInstallError(f"sha256 mismatch for {component.component_id}")

        self._mark(component, "extracting", job_id=job_id, on_progress=on_progress, message=f"安装 {component.name}")
        install_path = self._safe_install_path(component.install_path)
        staging_path = self._component_staging_path(component)
        self._remove_path(staging_path)
        os.makedirs(staging_path, exist_ok=True)

        try:
            self._extract(component, package, staging_path)
            self._assert_entry_exists(component, staging_path)
            previous = self._swap(component, staging_path, install_path, previous_version=existing_version)
        except Exception as exc:
            self._remove_path(staging_path)
            self.state_store.mark(component.component_id, "extract_failed", version=component.version, job_id=job_id, error_message=str(exc))
            if on_progress:
                on_progress(f"安装失败：{exc}", "danger")
            raise ComponentInstallError(f"extract failed for {component.component_id}: {exc}") from exc

        self._mark(component, "configuring", job_id=job_id, on_progress=on_progress, message=f"配置 {component.name}")
        silent_installer_ran = False
        managed_codex_entry = None
        managed_codex_version = None
        if component.component_id == "codex-desktop":
            managed_codex_entry = self._managed_codex_entry(install_path)
            if managed_codex_entry:
                managed_codex_version = self._detect_installed_version(component, install_path, entry_path=managed_codex_entry)
                if not managed_codex_version:
                    self._restore_previous_after_failed_health(install_path, previous)
                    self.state_store.mark(
                        component.component_id,
                        "health_failed",
                        version=component.version,
                        job_id=job_id,
                        previous_version=previous.version if previous else None,
                        error_message="managed Codex version check failed",
                    )
                    if on_progress:
                        on_progress("检测失败：managed Codex version check failed", "danger")
                    raise ComponentInstallError(f"health check failed for {component.component_id}: managed Codex version check failed")
        if component.archive_type == "installer" and getattr(component, "installer_args", ()):
            try:
                if on_progress:
                    on_progress(f"运行 {component.name} 静默安装器", "neutral")
                self._run_silent_installer(component, install_path)
                silent_installer_ran = True
                self._assert_external_install_available(component, force_refresh=True)
            except Exception as exc:
                self.state_store.mark(
                    component.component_id,
                    "config_failed",
                    version=component.version,
                    job_id=job_id,
                    previous_version=previous.version if previous else None,
                    error_message=str(exc),
                )
                if on_progress:
                    on_progress(f"配置失败：{exc}", "danger")
                raise ComponentInstallError(f"installer failed for {component.component_id}: {exc}") from exc
        if getattr(component, "install_command", ()) and not managed_codex_version:
            try:
                if on_progress:
                    on_progress(f"执行 {component.name} 安装命令", "neutral")
                self._run_install_command(component, install_path, on_progress=on_progress)
                self._assert_external_install_available(component, force_refresh=True)
            except Exception as exc:
                self._restore_previous_after_failed_health(install_path, previous)
                self.state_store.mark(
                    component.component_id,
                    "config_failed",
                    version=component.version,
                    job_id=job_id,
                    previous_version=previous.version if previous else None,
                    error_message=str(exc),
                )
                if on_progress:
                    on_progress(f"配置失败：{exc}", "danger")
                raise ComponentInstallError(f"install command failed for {component.component_id}: {exc}") from exc
        if component.health_check is not None:
            self._mark(component, "health_checking", job_id=job_id, on_progress=on_progress, message=f"检测 {component.name}")
            try:
                self.health_checker(component, install_path)
            except Exception as exc:
                self._restore_previous_after_failed_health(install_path, previous)
                self.state_store.mark(
                    component.component_id,
                    "health_failed",
                    version=component.version,
                    job_id=job_id,
                    previous_version=previous.version if previous else None,
                    error_message=str(exc),
                )
                if on_progress:
                    on_progress(f"检测失败：{exc}", "danger")
                raise ComponentInstallError(f"health check failed for {component.component_id}: {exc}") from exc
        elif component.archive_type == "installer" and not silent_installer_ran:
            state = self.state_store.mark(
                component.component_id,
                "manual_install_required",
                version=component.version,
                job_id=job_id,
                previous_version=previous.version if previous else None,
            )
            if on_progress:
                on_progress(f"{component.name} 安装器已保存，等待手动安装和检测", "warning")
            return state

        state = self.state_store.mark(
            component.component_id,
            "ready",
            version=component.version,
            job_id=job_id,
            previous_version=previous.version if previous else None,
        )
        if on_progress:
            on_progress(f"{component.name} 已就绪", "ok")
        return state

    def detect(
        self,
        component: ReleaseComponent,
        *,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
        force_external_probe: bool = False,
    ) -> ComponentState:
        install_path = self._safe_install_path(component.install_path)
        self._mark(component, "health_checking", job_id=job_id, on_progress=on_progress, message=f"检测 {component.name}")
        try:
            entry_path = self._resolve_component_entry(
                component,
                install_path,
                force_external_probe=force_external_probe,
            )
            self._assert_component_available(component, install_path, entry_path)
            if component.health_check is not None:
                self.health_checker(component, install_path)
        except Exception as exc:
            message = str(exc) or "组件检测失败"
            self.state_store.mark(
                component.component_id,
                "health_failed",
                version=component.version,
                job_id=job_id,
                error_code="detect_failed",
                error_message=message,
            )
            if on_progress:
                on_progress(f"检测失败：{message}", "danger")
            raise ComponentInstallError(f"detect failed for {component.component_id}: {message}") from exc

        installed_version = self._detect_installed_version(component, install_path, entry_path=entry_path)
        is_managed_codex = component.component_id == "codex-desktop" and entry_path == self._managed_codex_entry(install_path)
        if is_managed_codex and not installed_version:
            message = "managed Codex version check failed"
            self.state_store.mark(
                component.component_id,
                "health_failed",
                version=component.version,
                job_id=job_id,
                error_code="detect_failed",
                error_message=message,
            )
            if on_progress:
                on_progress(f"检测失败：{message}", "danger")
            raise ComponentInstallError(f"detect failed for {component.component_id}: {message}")
        is_codex_desktop_app = component.component_id == "codex-desktop" and _is_codex_desktop_executable(entry_path)
        if installed_version and not is_codex_desktop_app and not _versions_match(component.version, installed_version):
            state = self.state_store.mark(component.component_id, "upgrade_available", version=installed_version, job_id=job_id)
            if on_progress:
                on_progress(f"{component.name} 已检测到旧版本 {installed_version}，建议升级到 {component.version}", "warning")
            return state

        state = self.state_store.mark(component.component_id, "ready", version=installed_version or component.version, job_id=job_id)
        if on_progress:
            on_progress(f"{component.name} 已就绪", "ok")
        return state

    def launch(self, component: ReleaseComponent, *, job_id: str | None = None) -> dict:
        state = self.state_store.load().get(component.component_id)
        if state is None or state.status not in {"ready", "started"}:
            raise ComponentInstallError("组件尚未就绪，请先检测或安装")
        install_path = self._safe_install_path(component.install_path)
        entry_path = self._component_entry_path(component, install_path)
        self._assert_component_sources_clean(component, install_path, entry_path)
        self.state_store.mark(component.component_id, "starting", version=state.version or component.version, job_id=job_id)
        try:
            cwd = self._component_cwd(install_path)
            if self._custom_launcher:
                result = self.launcher(entry_path, cwd)
            else:
                result = self._default_component_launcher(component, entry_path, cwd)
        except Exception as exc:
            message = str(exc) or "组件启动失败"
            self.state_store.mark(
                component.component_id,
                "start_failed",
                version=state.version or component.version,
                job_id=job_id,
                error_code="start_failed",
                error_message=f"启动失败：{message}",
            )
            raise ComponentInstallError(f"启动失败：{message}") from exc
        self.state_store.mark(component.component_id, "started", version=state.version or component.version, job_id=job_id)
        return {
            "success": True,
            "componentId": component.component_id,
            "status": "started",
            **(result if isinstance(result, dict) else {}),
        }

    def _simulate_install(
        self,
        component: ReleaseComponent,
        *,
        job_id: str | None,
        on_progress: ProgressCallback | None,
    ) -> ComponentState:
        stages = (
            ("resolving_manifest", f"准备 {component.name}"),
            ("downloading", f"下载 {component.name}"),
            ("verifying", f"校验 {component.name}"),
            ("extracting", f"安装 {component.name}"),
            ("configuring", f"配置 {component.name}"),
            ("health_checking", f"检测 {component.name}"),
        )
        for status, message in stages:
            if on_progress:
                on_progress(message, "neutral")
        state = ComponentState(component.component_id, "simulation_ready", version=component.version, job_id=job_id)
        if on_progress:
            on_progress(f"{component.name} 流程预检已完成", "ok")
        return state

    def rollback(self, component_id: str) -> ComponentState:
        states = self.state_store.load()
        state = states.get(component_id)
        previous_version = state.previous_version if state else None
        previous_path = self._rollback_path(component_id)
        if not os.path.isdir(previous_path):
            raise ComponentInstallError(f"rollback is not available for {component_id}")

        install_path = self._find_active_component_path(component_id)
        if install_path and os.path.exists(install_path):
            self._remove_path(install_path)
        elif install_path:
            os.makedirs(os.path.dirname(install_path), exist_ok=True)

        if not install_path:
            install_path = os.path.join(self.base_path, "agents", component_id)
        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        self._replace_path(previous_path, install_path)

        return self.state_store.mark(component_id, "ready", version=previous_version, previous_version=None)

    def uninstall(
        self,
        component: ReleaseComponent,
        *,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> ComponentState:
        existing_state = self.state_store.load().get(component.component_id)
        version = (existing_state.version if existing_state else None) or component.version
        self._mark(component, "uninstalling", job_id=job_id, on_progress=on_progress, message=f"卸载 {component.name}")
        try:
            self._run_uninstall_command(component)
            self._invalidate_external_entry_cache(component)
            install_path = self._safe_install_path(component.install_path)
            self._remove_path(install_path)
            self._remove_path(self._rollback_path(component.component_id))
            self._remove_path(self._component_staging_path(component))
        except Exception as exc:
            self.state_store.mark(
                component.component_id,
                "uninstall_failed",
                version=version,
                job_id=job_id,
                error_code="uninstall_failed",
                error_message=str(exc),
            )
            if on_progress:
                on_progress(f"卸载失败：{exc}", "danger")
            raise ComponentInstallError(f"uninstall failed for {component.component_id}: {exc}") from exc
        state = self.state_store.mark(component.component_id, "not_installed", version=component.version, job_id=job_id)
        if on_progress:
            on_progress(f"{component.name} 已卸载", "ok")
        return state

    def _download(self, component: ReleaseComponent, *, on_progress: ProgressCallback | None = None) -> bytes:
        errors = []
        for url in component.urls:
            for attempt_index, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
                if delay > 0:
                    self.retry_sleep(delay)
                try:
                    return self.fetcher(url, self.timeout)
                except Exception as exc:
                    is_last_attempt = attempt_index >= len(RETRY_DELAYS_SECONDS)
                    if not is_last_attempt:
                        if on_progress:
                            on_progress(f"下载失败，正在重试第 {attempt_index + 1} 次：{_short_error(exc)}", "warning")
                        continue
                    errors.append(f"{url}: {exc}")
        raise ComponentInstallError("; ".join(errors) if errors else "no component urls configured")

    def _mark(
        self,
        component: ReleaseComponent,
        status: str,
        *,
        job_id: str | None,
        on_progress: ProgressCallback | None,
        message: str,
    ) -> ComponentState:
        state = self.state_store.mark(component.component_id, status, version=component.version, job_id=job_id)
        if on_progress:
            on_progress(message, "neutral")
        return state

    def _extract(self, component: ReleaseComponent, package: bytes, staging_path: str) -> None:
        if component.archive_type == "tgz":
            self._extract_tgz(package, staging_path)
            return

        if component.archive_type != "zip":
            os.makedirs(staging_path, exist_ok=True)
            filename = component.entry or f"{component.component_id}.bin"
            target = self._safe_join(staging_path, filename)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as handle:
                handle.write(package)
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp:
            temp.write(package)
            zip_path = temp.name
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                for info in archive.infolist():
                    self._safe_join(staging_path, info.filename)
                archive.extractall(staging_path)
        finally:
            try:
                os.unlink(zip_path)
            except OSError:
                pass

    def _extract_tgz(self, package: bytes, staging_path: str) -> None:
        os.makedirs(staging_path, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(package), mode="r:gz") as archive:
            for member in archive.getmembers():
                target = self._safe_join(staging_path, member.name)
                if member.isdir():
                    os.makedirs(target, exist_ok=True)
                    continue
                if not member.isfile():
                    raise ComponentInstallError("tgz contains an unsupported entry type")
                source = archive.extractfile(member)
                if source is None:
                    raise ComponentInstallError("tgz entry could not be read")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with source, open(target, "wb") as handle:
                    shutil.copyfileobj(source, handle)

    def _assert_entry_exists(self, component: ReleaseComponent, staging_path: str) -> None:
        if not component.entry:
            return
        target = self._safe_join(staging_path, component.entry)
        if not os.path.isfile(target):
            raise ComponentInstallError(f"component entry is missing: {component.entry}")

    def _assert_component_available(self, component: ReleaseComponent, install_path: str, entry_path: str = "") -> None:
        has_internal_install = os.path.exists(install_path)
        if not entry_path:
            entry_path = self._resolve_component_entry(component, install_path)
        if not has_internal_install and not entry_path:
            raise ComponentInstallError("未找到组件目录，请先安装或重新安装")
        self._assert_component_sources_clean(component, install_path, entry_path)

    def _component_entry_path(self, component: ReleaseComponent, install_path: str) -> str:
        return self._resolve_component_entry(component, install_path)

    def _managed_codex_entry(self, install_path: str) -> str | None:
        candidate = os.path.abspath(
            os.path.join(
                install_path,
                "package",
                "vendor",
                "x86_64-pc-windows-msvc",
                "bin",
                "codex.exe",
            )
        )
        return candidate if _is_path_inside(candidate, install_path) and os.path.isfile(candidate) else None

    def _resolve_component_entry(
        self,
        component: ReleaseComponent,
        install_path: str,
        allow_expensive: bool = True,
        force_external_probe: bool = False,
    ) -> str:
        if component.component_id == "codex-desktop":
            managed_entry = self._managed_codex_entry(install_path)
            if managed_entry:
                return managed_entry
        if component.entry:
            target = self._safe_join(install_path, component.entry)
            if os.path.isfile(target):
                return target
        external_entry = (
            self._first_existing_external_entry(component, refresh=force_external_probe)
            if allow_expensive
            else self._cached_existing_external_entry(component)
        )
        if external_entry:
            return external_entry
        if component.entry:
            raise ComponentInstallError("未找到组件文件，请先安装或重新安装")
        raise ComponentInstallError("组件缺少启动入口")

    def _cached_existing_external_entry(self, component: ReleaseComponent) -> str | None:
        cache_key = self._external_entry_cache_key(component)
        cached = _EXTERNAL_ENTRY_CACHE.get(cache_key)
        if cached is None:
            return None
        created_at, entry_path = cached
        if time.monotonic() - created_at > EXTERNAL_ENTRY_CACHE_TTL_SECONDS or (entry_path and not os.path.isfile(entry_path)):
            _EXTERNAL_ENTRY_CACHE.pop(cache_key, None)
            return None
        return entry_path

    def _first_existing_external_entry(self, component: ReleaseComponent, *, refresh: bool = False) -> str | None:
        cache_key = self._external_entry_cache_key(component)
        if not refresh:
            cached_entry = self._cached_existing_external_entry(component)
            if cached_entry is not None or cache_key in _EXTERNAL_ENTRY_CACHE:
                return cached_entry
        for candidate in self._external_entry_candidates(component):
            if os.path.isfile(candidate):
                _EXTERNAL_ENTRY_CACHE[cache_key] = (time.monotonic(), candidate)
                return candidate
        _EXTERNAL_ENTRY_CACHE[cache_key] = (time.monotonic(), None)
        return None

    def _external_entry_cache_key(self, component: ReleaseComponent) -> tuple[object, ...]:
        return (
            os.path.normcase(os.path.abspath(self.base_path)),
            component.component_id,
            component.install_path,
            component.entry or "",
            component.archive_type,
            component.platform,
            component.arch,
            component.version,
            tuple(str(path) for path in getattr(component, "external_paths", ())),
            tuple(str(part) for part in getattr(component, "install_command", ())),
        )

    def _invalidate_external_entry_cache(self, component: ReleaseComponent) -> None:
        _EXTERNAL_ENTRY_CACHE.pop(self._external_entry_cache_key(component), None)

    def _assert_component_sources_clean(self, component: ReleaseComponent, install_path: str, entry_path: str = "") -> None:
        if component.component_id != "hermes":
            return
        for root in _hermes_source_roots(install_path, entry_path):
            conflict = _first_python_conflict_marker(root)
            if conflict:
                raise ComponentInstallError(
                    f"Hermes 运行时包损坏：{conflict} 含有 Git 冲突标记，请重新安装 Hermes。"
                )

    def _external_entry_candidates(self, component: ReleaseComponent) -> list[str]:
        candidates: list[str] = []
        if component.component_id == "codex-desktop":
            for candidate in self._codex_desktop_entry_candidates():
                _append_unique(candidates, candidate)

        for raw_path in getattr(component, "external_paths", ()):
            candidate = self._expand_external_path(raw_path)
            self._append_external_path_variants(candidates, candidate)

        command_names = self._external_command_names(component)
        for candidate in self._default_external_entry_candidates(command_names):
            _append_unique(candidates, candidate)

        for name in command_names:
            found = shutil.which(name)
            if found:
                _append_unique(candidates, found)

        npm_package_names = self._npm_package_names_from_command(component)
        for directory in self._npm_global_bin_dirs() if npm_package_names else ():
            for name in command_names:
                _append_unique(candidates, os.path.join(directory, name))

        for package_name in npm_package_names:
            package_entry = self._npm_package_bin_entry(package_name, command_names)
            if package_entry:
                _append_unique(candidates, package_entry)
        return candidates

    def _codex_desktop_entry_candidates(self) -> tuple[str, ...]:
        candidates: list[str] = []
        for install_location in self._codex_desktop_appx_locations():
            for relative in ("app/Codex.exe", "Codex.exe"):
                _append_unique(candidates, os.path.join(install_location, *relative.split("/")))

        localappdata = os.environ.get("LOCALAPPDATA", "").strip()
        program_files = os.environ.get("ProgramFiles", "").strip()
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "").strip()
        for root, suffixes in (
            (localappdata, ("Programs/Codex/Codex.exe", "Programs/OpenAI Codex/Codex.exe", "OpenAI/Codex/Codex.exe")),
            (program_files, ("Codex/Codex.exe", "OpenAI Codex/Codex.exe")),
            (program_files_x86, ("Codex/Codex.exe", "OpenAI Codex/Codex.exe")),
        ):
            if not root:
                continue
            for suffix in suffixes:
                _append_unique(candidates, os.path.abspath(os.path.join(root, *suffix.split("/"))))
        return tuple(candidates)

    def _codex_desktop_appx_locations(self) -> tuple[str, ...]:
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"Get-AppxPackage -Name {CODEX_DESKTOP_PACKAGE_NAME} | Select-Object -First 1 -ExpandProperty InstallLocation",
        ]
        try:
            result = self.installer_runner(command, self.base_path, 15000)
        except Exception:
            return ()
        if int(getattr(result, "returncode", 0) or 0) != 0:
            return ()
        locations: list[str] = []
        for line in str(getattr(result, "stdout", "") or "").splitlines():
            value = line.strip()
            if value:
                _append_unique(locations, self._expand_external_path(value))
        return tuple(locations)

    def _external_command_names(self, component: ReleaseComponent) -> tuple[str, ...]:
        names: list[str] = []
        for raw_path in getattr(component, "external_paths", ()):
            base_name = os.path.basename(raw_path.replace("\\", "/")).strip()
            if not base_name:
                continue
            self._append_command_name_variants(names, base_name)
        for command_name in KNOWN_COMPONENT_COMMANDS.get(component.component_id, ()):
            self._append_command_name_variants(names, command_name)
        for package_name in self._npm_package_names_from_command(component):
            for command_name in KNOWN_NPM_PACKAGE_COMMANDS.get(package_name, ()):
                self._append_command_name_variants(names, command_name)
        return tuple(names)

    def _append_external_path_variants(self, candidates: list[str], path: str) -> None:
        _append_unique(candidates, path)
        directory = os.path.dirname(path)
        filename = os.path.basename(path)
        stem, _ext = os.path.splitext(filename)
        if not directory or not stem:
            return
        for name in self._command_file_names(stem):
            _append_unique(candidates, os.path.join(directory, name))

    def _append_command_name_variants(self, names: list[str], name: str) -> None:
        for candidate in self._command_file_names(name):
            _append_unique(names, candidate)

    def _command_file_names(self, name: str) -> tuple[str, ...]:
        clean = str(name or "").strip()
        if not clean:
            return ()
        stem, ext = os.path.splitext(clean)
        base = stem or clean
        names: list[str] = []
        _append_unique(names, clean)
        if base and base != clean:
            _append_unique(names, base)
        if base:
            for suffix in WINDOWS_COMMAND_SUFFIXES:
                _append_unique(names, f"{base}{suffix}")
        return tuple(names)

    def _default_external_entry_candidates(self, command_names: tuple[str, ...]) -> tuple[str, ...]:
        stems = self._command_stems(command_names)
        if not stems:
            return ()
        directories = self._common_command_directories()
        candidates: list[str] = []
        for directory in directories:
            for stem in stems:
                for name in self._command_file_names(stem):
                    _append_unique(candidates, os.path.join(directory, name))
        return tuple(candidates)

    def _command_stems(self, command_names: tuple[str, ...]) -> tuple[str, ...]:
        stems: list[str] = []
        for name in command_names:
            base = os.path.basename(str(name or "").replace("\\", "/")).strip()
            if not base:
                continue
            stem, _ext = os.path.splitext(base)
            _append_unique(stems, stem or base)
        return tuple(stems)

    def _common_command_directories(self) -> tuple[str, ...]:
        directories: list[str] = []
        private_prefix = self._npm_private_prefix()
        _append_unique(directories, private_prefix)
        _append_unique(directories, os.path.join(private_prefix, "bin"))
        appdata = os.environ.get("APPDATA", "").strip()
        localappdata = os.environ.get("LOCALAPPDATA", "").strip()
        userprofile = os.environ.get("USERPROFILE", "").strip() or os.path.expanduser("~")
        program_files = os.environ.get("ProgramFiles", "").strip()
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "").strip()

        for root, suffixes in (
            (appdata, ("npm",)),
            (localappdata, ("pnpm", "npm")),
            (userprofile, (".local/bin", "scoop/shims", "AppData/Roaming/npm", "AppData/Local/pnpm")),
            (program_files, ("nodejs",)),
            (program_files_x86, ("nodejs",)),
        ):
            if not root:
                continue
            for suffix in suffixes:
                _append_unique(directories, os.path.abspath(os.path.join(root, *suffix.split("/"))))
        return tuple(directories)

    def _npm_global_bin_dirs(self) -> tuple[str, ...]:
        directories: list[str] = []
        private_prefix = self._npm_private_prefix()
        _append_unique(directories, private_prefix)
        _append_unique(directories, os.path.join(private_prefix, "bin"))
        for command in (("npm", "prefix", "-g"), ("npm", "bin", "-g")):
            try:
                result = self.installer_runner(self._resolve_command(list(command)), self.base_path, 15000)
            except Exception:
                continue
            if int(getattr(result, "returncode", 0) or 0) != 0:
                continue
            for line in str(getattr(result, "stdout", "") or "").splitlines():
                value = line.strip()
                if not value or value.lower().startswith("unknown command"):
                    continue
                _append_unique(directories, self._expand_external_path(value))
                _append_unique(directories, os.path.join(self._expand_external_path(value), "bin"))
        return tuple(directories)

    def _npm_package_names_from_command(self, component: ReleaseComponent) -> tuple[str, ...]:
        command = tuple(getattr(component, "install_command", ()) or ())
        if len(command) < 3:
            return ()
        if os.path.basename(command[0]).lower() not in {"npm", "npm.cmd", "npm.ps1"}:
            return ()

        packages: list[str] = []
        saw_install = False
        skip_next = False
        options_with_value = {"--prefix", "--cache", "--registry", "--userconfig", "--globalconfig", "--tag"}
        for raw_part in command[1:]:
            part = str(raw_part or "").strip()
            if not part:
                continue
            lowered = part.lower()
            if skip_next:
                skip_next = False
                continue
            if not saw_install:
                if lowered in {"install", "i", "add"}:
                    saw_install = True
                continue
            if lowered in options_with_value:
                skip_next = True
                continue
            if lowered.startswith("-"):
                continue
            _append_unique(packages, _strip_npm_package_version(part))
        return tuple(packages)

    def _npm_package_bin_entry(self, package_name: str, command_names: tuple[str, ...]) -> str | None:
        root = self._npm_global_root()
        if not root:
            return None
        package_dir = os.path.join(root, *package_name.split("/"))
        package_json_path = os.path.join(package_dir, "package.json")
        if not os.path.isfile(package_json_path):
            return None
        try:
            import json

            with open(package_json_path, "r", encoding="utf-8-sig") as handle:
                package_json = json.load(handle)
        except Exception:
            return None
        bin_value = package_json.get("bin") if isinstance(package_json, dict) else None
        entries: list[str] = []
        if isinstance(bin_value, str):
            entries.append(bin_value)
        elif isinstance(bin_value, dict):
            preferred_stems = {os.path.splitext(name)[0].lower() for name in command_names}
            for key, value in bin_value.items():
                if not isinstance(value, str):
                    continue
                if not preferred_stems or str(key).lower() in preferred_stems:
                    entries.append(value)
            if not entries:
                entries.extend(value for value in bin_value.values() if isinstance(value, str))
        for relative in entries:
            candidate = os.path.abspath(os.path.join(package_dir, *relative.replace("\\", "/").split("/")))
            if _is_path_inside(candidate, package_dir) and os.path.isfile(candidate):
                return candidate
        return None

    def _npm_global_root(self) -> str:
        private_root = os.path.join(self._npm_private_prefix(), "node_modules")
        if os.path.isdir(private_root):
            return private_root
        try:
            result = self.installer_runner(self._resolve_command(["npm", "root", "-g"]), self.base_path, 15000)
        except Exception:
            return ""
        if int(getattr(result, "returncode", 0) or 0) != 0:
            return ""
        for line in str(getattr(result, "stdout", "") or "").splitlines():
            value = line.strip()
            if value:
                return self._expand_external_path(value)
        return ""

    def _npm_private_prefix(self) -> str:
        return os.path.join(self.base_path, "data", ".installer", "npm-global")

    def _assert_external_install_available(self, component: ReleaseComponent, *, force_refresh: bool = False) -> None:
        if not getattr(component, "external_paths", ()):
            return
        if self._first_existing_external_entry(component, refresh=force_refresh):
            return
        raise ComponentInstallError("静默安装已执行，但未检测到组件入口，请打开诊断或手动重试")

    def _expand_external_path(self, path: str) -> str:
        expanded = os.path.expandvars(os.path.expanduser(path))
        return os.path.abspath(expanded)

    def _default_launcher(self, executable: str, cwd: str) -> dict:
        return _default_launcher(executable, cwd, base_path=self.base_path)

    def _default_component_launcher(self, component: ReleaseComponent, executable: str, cwd: str) -> dict:
        return _default_launcher(executable, cwd, base_path=self.base_path, component_id=component.component_id)

    def _run_silent_installer(self, component: ReleaseComponent, install_path: str) -> None:
        entry_path = self._component_entry_path(component, install_path)
        command = [entry_path, *getattr(component, "installer_args", ())]
        result = self.installer_runner(
            command,
            install_path,
            int(getattr(component, "installer_timeout_ms", 900000) or 900000),
        )
        code = int(getattr(result, "returncode", 0) or 0)
        if code in (0, 3010):
            return
        output = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).strip()
        if len(output) > 240:
            output = output[:240] + "..."
        raise ComponentInstallError(f"安装器返回 {code}：{output or '没有输出'}")

    def _run_uninstall_command(self, component: ReleaseComponent) -> None:
        command = [self._expand_command_part(part) for part in getattr(component, "uninstall_command", ())]
        if not command:
            return
        result = self.installer_runner(
            self._resolve_command(self._with_private_npm_prefix(command)),
            self.base_path,
            int(getattr(component, "command_timeout_ms", 900000) or 900000),
        )
        code = int(getattr(result, "returncode", 0) or 0)
        if code in (0, 3010):
            return
        output = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).strip()
        if len(output) > 240:
            output = output[:240] + "..."
        raise ComponentInstallError(f"卸载命令返回 {code}：{output or '没有输出'}")

    def _run_install_command(
        self,
        component: ReleaseComponent,
        install_path: str,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        command = [self._expand_command_part(part) for part in getattr(component, "install_command", ())]
        if not command:
            return
        timeout_ms = int(getattr(component, "command_timeout_ms", 900000) or 900000)
        resolved = self._resolve_command(self._with_private_npm_prefix(command))
        last_error = ""
        for attempt_index, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
            if delay > 0:
                self.retry_sleep(delay)
            result = self.installer_runner(resolved, install_path, timeout_ms)
            code = int(getattr(result, "returncode", 0) or 0)
            if code in (0, 3010):
                return
            output = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).strip()
            last_error = f"安装命令返回 {code}：{_short_error(output)}"
            is_last_attempt = attempt_index >= len(RETRY_DELAYS_SECONDS)
            if not is_last_attempt and on_progress:
                on_progress(f"安装命令失败，正在重试第 {attempt_index + 1} 次：{_short_error(output)}", "warning")
        raise ComponentInstallError(last_error or "安装命令失败")

    def _with_private_npm_prefix(self, command: list[str]) -> list[str]:
        if not command:
            return command
        executable = os.path.basename(command[0]).lower()
        if executable not in {"npm", "npm.cmd", "npm.ps1"}:
            return command
        lowered = [part.lower() for part in command[1:]]
        if not any(part in {"install", "i", "add", "uninstall", "remove", "rm"} for part in lowered):
            return command
        if "--prefix" in lowered:
            return command
        prefix = self._npm_private_prefix()
        os.makedirs(prefix, exist_ok=True)
        return [command[0], "--prefix", prefix, *command[1:]]

    def _detect_installed_version(
        self,
        component: ReleaseComponent,
        install_path: str,
        entry_path: str | None = None,
    ) -> str | None:
        try:
            entry_path = entry_path or self._resolve_component_entry(component, install_path)
            if component.component_id == "codex-desktop" and _is_codex_desktop_executable(entry_path):
                return _codex_desktop_version_from_path(entry_path)
            cwd = self._component_cwd(install_path)
            command = [*build_launcher_command(entry_path, cwd, base_path=self.base_path), "--version"]
            result = self.installer_runner(command, cwd, VERSION_DETECT_TIMEOUT_MS)
        except Exception:
            return None
        if int(getattr(result, "returncode", 0) or 0) != 0:
            return None
        output = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).strip()
        if not output:
            return None
        match = re.search(r"(?<![A-Za-z0-9])v?(\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?)\b", output, re.IGNORECASE)
        return match.group(1) if match else None

    def _resolve_command(self, command: list[str]) -> list[str]:
        if not command:
            return command
        executable = os.path.basename(command[0]).lower()
        if executable in {"node", "node.exe"}:
            node = self._first_existing_tool(("node.exe", "node"), extra_dirs=("node", "SystemData/.core/node", "_up_/node"))
            if node:
                return [node, *command[1:]]
        if executable in {"npm", "npm.cmd", "npm.ps1"}:
            node = self._first_existing_tool(("node.exe", "node"), extra_dirs=("node", "SystemData/.core/node", "_up_/node"))
            npm_cli = self._first_existing_path(
                (
                    "node/node_modules/npm/bin/npm-cli.js",
                    "node_modules/npm/bin/npm-cli.js",
                    "SystemData/.core/node/node_modules/npm/bin/npm-cli.js",
                    "SystemData/.core/node_modules/npm/bin/npm-cli.js",
                    "_up_/node/node_modules/npm/bin/npm-cli.js",
                )
            )
            if node and npm_cli:
                return [node, npm_cli, *command[1:]]
            npm_shim = self._first_existing_tool(
                ("npm.cmd", "npm.exe", "npm"),
                extra_dirs=("node", "SystemData/.core/node", "_up_/node"),
            )
            if npm_shim:
                return [*build_launcher_command(npm_shim, self.base_path, base_path=self.base_path), *command[1:]]
        if executable in {"python", "python.exe", "py"}:
            python = self._first_existing_tool(("python.exe", "python"), extra_dirs=("python", "runtime/python", "SystemData/.core/python"))
            if python:
                return [python, *command[1:]]
        if executable in {"git", "git.exe"}:
            git = self._first_existing_path(
                (
                    "Git/cmd/git.exe",
                    "git/cmd/git.exe",
                    "SystemData/.core/Git/cmd/git.exe",
                    "SystemData/.core/git/cmd/git.exe",
                )
            )
            if git:
                return [git, *command[1:]]
        return command

    def _first_existing_tool(self, names: tuple[str, ...], *, extra_dirs: tuple[str, ...]) -> str:
        for directory in extra_dirs:
            for name in names:
                path = os.path.join(self.base_path, *directory.replace("\\", "/").split("/"), name)
                if os.path.isfile(path):
                    return path
        for name in names:
            path = shutil.which(name)
            if path:
                return path
        return ""

    def _first_existing_path(self, relatives: tuple[str, ...]) -> str:
        for relative in relatives:
            path = os.path.join(self.base_path, *relative.replace("\\", "/").split("/"))
            if os.path.isfile(path):
                return path
        return ""

    def _expand_command_part(self, value: str) -> str:
        return os.path.expandvars(os.path.expanduser(value))

    def _component_cwd(self, install_path: str) -> str:
        return install_path if os.path.isdir(install_path) else self.base_path

    def _swap(
        self,
        component: ReleaseComponent,
        staging_path: str,
        install_path: str,
        *,
        previous_version: str | None,
    ) -> PreviousInstall | None:
        previous = None
        if os.path.exists(install_path):
            previous = PreviousInstall(path=self._rollback_path(component.component_id), version=previous_version)
            self._remove_path(previous.path)
            os.makedirs(os.path.dirname(previous.path), exist_ok=True)
            self._replace_path(install_path, previous.path)

        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        self._replace_path(staging_path, install_path)
        return previous

    def _replace_path(self, source: str, target: str) -> None:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if not os.path.isdir(source):
                raise
            self._remove_path(target)
            shutil.copytree(source, target)
            self._remove_path(source)

    def _restore_previous_after_failed_health(self, install_path: str, previous: PreviousInstall | None) -> None:
        self._remove_path(install_path)
        if previous is None or not os.path.exists(previous.path):
            return
        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        if os.path.isdir(previous.path):
            shutil.copytree(previous.path, install_path)
            return
        shutil.copy2(previous.path, install_path)

    def _safe_install_path(self, install_path: str) -> str:
        normalized = self._normalize_install_path(install_path)
        target = os.path.abspath(os.path.join(self.base_path, normalized))
        if not _is_path_inside(target, self.base_path):
            raise ComponentInstallError("install path escapes base directory")
        return target

    def _normalize_install_path(self, install_path: str) -> str:
        normalized = install_path.replace("\\", "/")
        parts = [part for part in normalized.split("/") if part]
        payload_root = os.path.basename(self.base_path).lower()
        legacy_root = parts[0].lower() if parts else ""
        if parts and legacy_root == payload_root and legacy_root in ("loomfiles", "openclawfiles"):
            parts = parts[1:]
        return os.path.join(*parts) if parts else ""

    def _component_staging_path(self, component: ReleaseComponent) -> str:
        return os.path.join(self.staging_dir, component.component_id)

    def _rollback_path(self, component_id: str) -> str:
        return os.path.join(self.rollback_dir, component_id)

    def _find_active_component_path(self, component_id: str) -> str | None:
        candidates = [
            os.path.join(self.base_path, "agents", component_id),
            os.path.join(self.base_path, component_id),
            os.path.join(self.base_path, "LOOMFiles", "agents", component_id),
            os.path.join(self.base_path, "LOOMFiles", component_id),
            os.path.join(self.base_path, "OpenClawFiles", "agents", component_id),
            os.path.join(self.base_path, "OpenClawFiles", component_id),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return candidates[0]

    def _safe_join(self, root: str, name: str) -> str:
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or any(part == ".." for part in normalized.split("/")):
            raise ComponentInstallError("archive path traversal is not allowed")
        target = os.path.abspath(os.path.join(root, *[part for part in normalized.split("/") if part]))
        if not _is_path_inside(target, root):
            raise ComponentInstallError("archive path traversal is not allowed")
        return target

    @staticmethod
    def _remove_path(path: str) -> None:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.unlink(path)


def _default_fetcher(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": "LOOM-Launcher/component-installer"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def _default_health_checker(component: ReleaseComponent, _install_path: str) -> None:
    health_check = component.health_check
    if health_check is None:
        return
    if health_check.kind != "http":
        raise ComponentInstallError(f"unsupported health check kind: {health_check.kind}")
    timeout = max(0.1, health_check.timeout_ms / 1000)
    request = Request(health_check.url, headers={"User-Agent": "LOOM-Launcher/component-health"})
    with urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status < 200 or status >= 300:
            raise ComponentInstallError(f"health check returned HTTP {status}")


def _hermes_source_roots(install_path: str, entry_path: str = "") -> tuple[str, ...]:
    roots: list[str] = []
    for candidate in (install_path, entry_path):
        current = os.path.abspath(candidate) if candidate else ""
        if not current:
            continue
        if os.path.isfile(current):
            current = os.path.dirname(current)
        for _ in range(6):
            if not current or current == os.path.dirname(current):
                break
            if os.path.isdir(os.path.join(current, "hermes_cli")) or os.path.isfile(os.path.join(current, "utils.py")):
                _append_unique(roots, current)
            current = os.path.dirname(current)
    return tuple(roots)


def _first_python_conflict_marker(root: str) -> str:
    if not root or not os.path.isdir(root):
        return ""
    ignored_dirs = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "Lib",
        "Scripts",
        "bin",
        "Include",
        "site-packages",
        "node_modules",
    }
    checked = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in ignored_dirs and not name.endswith(".dist-info")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            checked += 1
            if checked > 1000:
                return ""
            path = os.path.join(dirpath, filename)
            try:
                with open(path, "r", encoding="utf-8-sig") as handle:
                    for line in handle:
                        if line.lstrip().startswith(PYTHON_SOURCE_CONFLICT_MARKERS):
                            return path
            except UnicodeDecodeError:
                try:
                    with open(path, "r", encoding="gb18030") as handle:
                        for line in handle:
                            if line.lstrip().startswith(PYTHON_SOURCE_CONFLICT_MARKERS):
                                return path
                except Exception:
                    continue
            except OSError:
                continue
    return ""


def _default_installer_runner(command: list[str], cwd: str, timeout_ms: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=max(1, timeout_ms / 1000),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _is_codex_desktop_executable(executable: str) -> bool:
    path = os.path.abspath(str(executable or ""))
    filename = os.path.basename(path)
    if filename != "Codex.exe":
        return False
    lowered_parts = {part.lower() for part in path.replace("\\", "/").split("/")}
    return not lowered_parts.intersection({"resources", "node_modules", "vendor", "bin", "npm"})


def _codex_desktop_version_from_path(executable: str) -> str | None:
    match = re.search(r"OpenAI\.Codex_(\d+(?:\.\d+){1,3})_", str(executable or ""), re.IGNORECASE)
    return match.group(1) if match else None


def _codex_desktop_app_uri(executable: str) -> str | None:
    match = re.search(
        r"WindowsApps[\\/](OpenAI\.Codex)_[^\\/]+__([0-9a-z]+)[\\/]",
        str(executable or ""),
        re.IGNORECASE,
    )
    if not match:
        return None
    package_family = f"{match.group(1)}_{match.group(2)}"
    return f"shell:AppsFolder\\{package_family}!{CODEX_DESKTOP_APP_ID}"


def build_launcher_command(executable: str, cwd: str, *, base_path: str | None = None) -> list[str]:
    extension = os.path.splitext(executable)[1].lower()
    if extension in {".js", ".mjs", ".cjs"}:
        node_candidates = []
        if base_path:
            node_candidates.extend([
                os.path.join(base_path, "node", "node.exe"),
                os.path.join(base_path, "_up_", "node", "node.exe"),
                os.path.join(base_path, "SystemData", ".core", "node", "node.exe"),
                os.path.join(base_path, "runtime", "node", "node.exe"),
            ])
        node_from_path = shutil.which("node")
        if node_from_path:
            node_candidates.append(node_from_path)
        node = next((candidate for candidate in node_candidates if os.path.isfile(candidate)), "")
        if not node:
            raise ComponentInstallError("未找到 Node.js，无法启动 JavaScript 组件")
        return [node, executable]
    if extension == ".ps1":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", executable]
    if extension in {".cmd", ".bat"}:
        return ["cmd", "/c", executable]
    return [executable]


def build_agent_launcher_command(
    component_id: str | None,
    executable: str,
    cwd: str,
    *,
    base_path: str | None = None,
) -> list[str]:
    if component_id == "codex-desktop" and _is_codex_desktop_executable(executable):
        app_uri = _codex_desktop_app_uri(executable)
        if app_uri and os.name == "nt":
            return ["explorer.exe", app_uri]
        return [executable]

    command = build_launcher_command(executable, cwd, base_path=base_path)
    if component_id == "opencode":
        model = _require_opencode_default_model(base_path)
        return [*command, "--pure", "-m", model]
    if component_id == "openclaw-companion":
        return [*command, "chat", "--local"]
    if component_id == "hermes":
        return [*command, "chat"]
    return command


def build_visible_launcher_command(
    executable: str,
    cwd: str,
    *,
    base_path: str | None = None,
    component_id: str | None = None,
    force_windows: bool | None = None,
) -> list[str]:
    command = build_agent_launcher_command(component_id, executable, cwd, base_path=base_path)
    use_windows_terminal = os.name == "nt" if force_windows is None else force_windows
    if component_id == "codex-desktop" and _is_codex_desktop_executable(executable):
        return command
    if not use_windows_terminal:
        return command

    command_line = subprocess.list2cmdline(command)
    title = f"LOOM Agent - {_launcher_title(component_id, executable)}"
    return ["cmd.exe", "/k", f"title {title} && {command_line}"]


def _default_launcher(executable: str, cwd: str, *, base_path: str | None = None, component_id: str | None = None) -> dict:
    command = build_visible_launcher_command(executable, cwd, base_path=base_path, component_id=component_id)
    use_windows_terminal = os.name == "nt"
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if use_windows_terminal else 0
    env = build_agent_launcher_environment(base_path, component_id)
    stream_target = None if use_windows_terminal else subprocess.DEVNULL
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=stream_target,
        stderr=stream_target,
        stdin=stream_target,
        close_fds=True,
        creationflags=creationflags,
    )
    return {"pid": process.pid, "visible": use_windows_terminal, "command": subprocess.list2cmdline(command)}


def build_agent_launcher_environment(base_path: str | None, component_id: str | None) -> dict[str, str] | None:
    if not base_path:
        return None
    root = os.path.abspath(base_path)
    env = os.environ.copy()
    if component_id in MODEL_ENV_SCRUB_COMPONENTS:
        _scrub_agent_model_environment(env)
    path_entries = [
        os.path.join(root, "data", ".installer", "npm-global"),
        os.path.join(root, "data", ".installer", "npm-global", "bin"),
        os.path.join(root, "node"),
        os.path.join(root, "_up_", "node"),
        os.path.join(root, "SystemData", ".core", "node"),
        os.path.join(root, "node_modules", ".bin"),
        os.path.join(root, "_up_", "node_modules", ".bin"),
        os.path.join(root, "SystemData", ".core", "node_modules", ".bin"),
    ]
    existing_path = env.get("Path") or env.get("PATH") or ""
    prefix = os.pathsep.join(entry for entry in path_entries if os.path.isdir(entry))
    if prefix:
        merged_path = prefix if not existing_path else f"{prefix}{os.pathsep}{existing_path}"
        env["PATH"] = merged_path
        env["Path"] = merged_path

    if component_id == "openclaw-companion":
        data_dir = os.path.join(root, "data")
        state_dir = os.path.join(data_dir, ".openclaw")
        env["OPENCLAW_HOME"] = data_dir
        env["OPENCLAW_STATE_DIR"] = state_dir
        env["OPENCLAW_CONFIG_PATH"] = os.path.join(state_dir, "openclaw.json")
    elif component_id == "opencode":
        config_dir = os.path.join(root, "data", ".opencode")
        config_file = os.path.join(config_dir, "opencode.json")
        env["OPENCODE_CONFIG_DIR"] = config_dir
        env["OPENCODE_CONFIG"] = config_file
        api_key = _opencode_api_key_from_wire(root)
        if api_key:
            env["LOOM_OPENCODE_API_KEY"] = api_key
    elif component_id == "codex-desktop":
        wire = _agent_wire_from_root(root)
        env["CODEX_HOME"] = os.path.join(root, "data", ".codex")
        _inject_openai_compatible_env(env, wire, key_name="LOOM_CODEX_API_KEY")
    elif component_id == "claude-code":
        wire = _agent_wire_from_root(root)
        api_key = _wire_api_key(wire)
        base_url = _wire_anthropic_base_url(wire)
        model = _wire_text_model(wire)
        if api_key:
            env["LOOM_CLAUDE_API_KEY"] = api_key
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
            env["ANTHROPIC_API_KEY"] = api_key
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
        if model:
            env["ANTHROPIC_MODEL"] = model
    return env


def _scrub_agent_model_environment(env: dict[str, str]) -> None:
    stale_keys = {key.upper() for key in AGENT_MODEL_ENV_KEYS}
    for key in list(env):
        if key.upper() in stale_keys:
            env.pop(key, None)


def _require_opencode_default_model(base_path: str | None) -> str:
    if not base_path:
        raise ComponentInstallError("opencode 缺少 LOOM 安装根目录，无法加载模型配置")
    config_path = os.path.join(os.path.abspath(base_path), "data", ".opencode", "opencode.json")
    if not os.path.isfile(config_path):
        raise ComponentInstallError("opencode 模型配置缺失，请先登录中转站并同步模型")
    try:
        with open(config_path, encoding="utf-8-sig") as handle:
            config = json.load(handle)
    except Exception as exc:
        raise ComponentInstallError(f"opencode 模型配置无法读取：{exc}") from exc
    model = str(config.get("model") or "").strip() if isinstance(config, dict) else ""
    if "/" not in model:
        raise ComponentInstallError("opencode 默认模型缺失，请先在模型账号页同步模型")
    provider_id = model.split("/", 1)[0]
    model_id = model.split("/", 1)[1]
    if _looks_like_non_text_model(model_id):
        raise ComponentInstallError("opencode 默认模型不能使用手机/图像/视频模型，请重新同步文本模型")
    providers = config.get("provider") if isinstance(config, dict) else {}
    provider = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(provider, dict):
        raise ComponentInstallError(f"opencode Provider {provider_id} 缺失，请重新同步模型")
    return model


def _opencode_api_key_from_wire(base_path: str) -> str:
    wire = _agent_wire_from_root(os.path.abspath(base_path))
    return _wire_api_key(wire)


def _agent_wire_from_root(root: str) -> dict:
    wire_path = os.path.join(os.path.abspath(root), "data", ".openclaw", "launcher", "wire-current.json")
    try:
        with open(wire_path, encoding="utf-8-sig") as handle:
            wire = json.load(handle)
    except Exception:
        return {}
    return wire if isinstance(wire, dict) else {}


def _wire_api_key(wire: dict) -> str:
    if not isinstance(wire, dict):
        return ""
    return unprotect_secret(wire.get("apiKey"))


def _wire_base_url(wire: dict) -> str:
    if not isinstance(wire, dict):
        return ""
    value = str(wire.get("baseUrl") or "").strip().rstrip("/")
    return value


def _wire_anthropic_base_url(wire: dict) -> str:
    value = _wire_base_url(wire)
    if value.endswith("/v1"):
        return value[:-3].rstrip("/")
    return value


def _wire_text_model(wire: dict) -> str:
    models = wire.get("models") if isinstance(wire.get("models"), dict) else {}
    model = str(models.get("text") or "").strip()
    return "" if _looks_like_non_text_model(model) else model


def _looks_like_non_text_model(model_id: object) -> bool:
    text = str(model_id or "").strip().lower()
    if not text:
        return False
    if text in PHONE_MODEL_IDS:
        return True
    return any(marker in text for marker in NON_TEXT_MODEL_MARKERS)


def _inject_openai_compatible_env(env: dict[str, str], wire: dict, *, key_name: str) -> None:
    api_key = _wire_api_key(wire)
    base_url = _wire_base_url(wire)
    model = _wire_text_model(wire)
    if api_key:
        env[key_name] = api_key
        env["OPENAI_API_KEY"] = api_key
    if base_url:
        env["OPENAI_BASE_URL"] = base_url
        env["OPENAI_API_BASE"] = base_url
    if model:
        env["OPENAI_MODEL"] = model


def _launcher_title(component_id: str | None, executable: str) -> str:
    titles = {
        "codex-desktop": "Codex",
        "claude-code": "Claude Code",
        "opencode": "opencode",
        "openclaw-companion": "OpenClaw",
        "hermes": "Hermes",
    }
    return titles.get(str(component_id or ""), os.path.basename(executable) or "runtime")


def _is_path_inside(path: str, root: str) -> bool:
    try:
        common = os.path.commonpath([os.path.abspath(path), os.path.abspath(root)])
    except ValueError:
        return False
    return common == os.path.abspath(root)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _strip_npm_package_version(package: str) -> str:
    text = str(package or "").strip()
    if not text:
        return ""
    if text.startswith("@"):
        first = text.find("@", 1)
        return text[:first] if first > 0 else text
    return text.split("@", 1)[0]


def _short_error(error: object, *, limit: int = 160) -> str:
    text = str(error or "").strip()
    if not text:
        return "没有错误输出"
    return text if len(text) <= limit else text[:limit] + "..."


def _versions_match(expected: str | None, detected: str | None) -> bool:
    expected_text = str(expected or "").strip().lower()
    detected_text = str(detected or "").strip().lower()
    if not expected_text or not detected_text:
        return True
    return expected_text == detected_text or expected_text.startswith(f"{detected_text}-") or detected_text.startswith(f"{expected_text}-")
