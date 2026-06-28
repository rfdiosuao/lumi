"""Component download, verification, extraction, and rollback."""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Callable
from urllib.request import Request, urlopen

from core.component_state import ComponentState, ComponentStateStore
from core.release_manifest import ReleaseComponent


ComponentFetcher = Callable[[str, float], bytes]
ComponentHealthChecker = Callable[[ReleaseComponent, str], None]
ComponentLauncher = Callable[[str, str], dict]
ComponentInstallerRunner = Callable[[list[str], str, int], subprocess.CompletedProcess]
ProgressCallback = Callable[[str, str], None]


class ComponentInstallError(RuntimeError):
    """Raised when a component cannot be installed safely."""


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
        timeout: float = 30.0,
    ):
        self.base_path = os.path.abspath(base_path)
        self.state_store = state_store
        self.fetcher = fetcher or _default_fetcher
        self.health_checker = health_checker or _default_health_checker
        self.launcher = launcher or self._default_launcher
        self.installer_runner = installer_runner or _default_installer_runner
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
            package = self._download(component)
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
        if component.archive_type == "installer" and getattr(component, "installer_args", ()):
            try:
                if on_progress:
                    on_progress(f"运行 {component.name} 静默安装器", "neutral")
                self._run_silent_installer(component, install_path)
                silent_installer_ran = True
                self._assert_external_install_available(component)
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
        if getattr(component, "install_command", ()):
            try:
                if on_progress:
                    on_progress(f"执行 {component.name} 安装命令", "neutral")
                self._run_install_command(component, install_path)
                self._assert_external_install_available(component)
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
    ) -> ComponentState:
        install_path = self._safe_install_path(component.install_path)
        self._mark(component, "health_checking", job_id=job_id, on_progress=on_progress, message=f"检测 {component.name}")
        try:
            self._assert_component_available(component, install_path)
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

        installed_version = self._detect_installed_version(component, install_path)
        if installed_version and not _versions_match(component.version, installed_version):
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
        if state is None or state.status != "ready":
            raise ComponentInstallError("组件尚未就绪，请先检测或安装")
        install_path = self._safe_install_path(component.install_path)
        entry_path = self._component_entry_path(component, install_path)
        self.state_store.mark(component.component_id, "starting", version=state.version or component.version, job_id=job_id)
        try:
            result = self.launcher(entry_path, self._component_cwd(install_path))
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

    def _download(self, component: ReleaseComponent) -> bytes:
        errors = []
        for url in component.urls:
            try:
                return self.fetcher(url, self.timeout)
            except Exception as exc:
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

    def _assert_component_available(self, component: ReleaseComponent, install_path: str) -> None:
        has_internal_install = os.path.exists(install_path)
        has_external_entry = bool(self._first_existing_external_entry(component))
        if not has_internal_install and not has_external_entry:
            raise ComponentInstallError("未找到组件目录，请先安装或重新安装")
        if component.entry:
            self._component_entry_path(component, install_path)

    def _component_entry_path(self, component: ReleaseComponent, install_path: str) -> str:
        if not component.entry:
            external_entry = self._first_existing_external_entry(component)
            if external_entry:
                return external_entry
            raise ComponentInstallError("组件缺少启动入口")
        target = self._safe_join(install_path, component.entry)
        if not os.path.isfile(target):
            external_entry = self._first_existing_external_entry(component)
            if external_entry:
                return external_entry
            raise ComponentInstallError("未找到组件文件，请先安装或重新安装")
        return target

    def _first_existing_external_entry(self, component: ReleaseComponent) -> str | None:
        for candidate in self._external_entry_candidates(component):
            if os.path.isfile(candidate):
                return candidate
        return None

    def _external_entry_candidates(self, component: ReleaseComponent) -> list[str]:
        candidates: list[str] = []
        for raw_path in getattr(component, "external_paths", ()):
            candidate = self._expand_external_path(raw_path)
            _append_unique(candidates, candidate)

        command_names = self._external_command_names(component)
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

    def _external_command_names(self, component: ReleaseComponent) -> tuple[str, ...]:
        names: list[str] = []
        for raw_path in getattr(component, "external_paths", ()):
            base_name = os.path.basename(raw_path.replace("\\", "/")).strip()
            if not base_name:
                continue
            _append_unique(names, base_name)
            stem, ext = os.path.splitext(base_name)
            if stem:
                _append_unique(names, stem)
                for suffix in (".cmd", ".exe", ".ps1", ".bat"):
                    _append_unique(names, f"{stem}{suffix}")
        return tuple(names)

    def _npm_global_bin_dirs(self) -> tuple[str, ...]:
        directories: list[str] = []
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

    def _assert_external_install_available(self, component: ReleaseComponent) -> None:
        if not getattr(component, "external_paths", ()):
            return
        if self._first_existing_external_entry(component):
            return
        raise ComponentInstallError("静默安装已执行，但未检测到组件入口，请打开诊断或手动重试")

    def _expand_external_path(self, path: str) -> str:
        expanded = os.path.expandvars(os.path.expanduser(path))
        return os.path.abspath(expanded)

    def _default_launcher(self, executable: str, cwd: str) -> dict:
        return _default_launcher(executable, cwd, base_path=self.base_path)

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
            self._resolve_command(command),
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

    def _run_install_command(self, component: ReleaseComponent, install_path: str) -> None:
        command = [self._expand_command_part(part) for part in getattr(component, "install_command", ())]
        if not command:
            return
        result = self.installer_runner(
            self._resolve_command(command),
            install_path,
            int(getattr(component, "command_timeout_ms", 900000) or 900000),
        )
        code = int(getattr(result, "returncode", 0) or 0)
        if code in (0, 3010):
            return
        output = ((getattr(result, "stdout", "") or "") + "\n" + (getattr(result, "stderr", "") or "")).strip()
        if len(output) > 240:
            output = output[:240] + "..."
        raise ComponentInstallError(f"安装命令返回 {code}：{output or '没有输出'}")

    def _detect_installed_version(self, component: ReleaseComponent, install_path: str) -> str | None:
        try:
            entry_path = self._component_entry_path(component, install_path)
            cwd = self._component_cwd(install_path)
            command = [*build_launcher_command(entry_path, cwd, base_path=self.base_path), "--version"]
            result = self.installer_runner(command, cwd, 15000)
        except Exception:
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


def build_launcher_command(executable: str, cwd: str, *, base_path: str | None = None) -> list[str]:
    extension = os.path.splitext(executable)[1].lower()
    if extension in {".js", ".mjs", ".cjs"}:
        node_candidates = []
        if base_path:
            node_candidates.extend([
                os.path.join(base_path, "node", "node.exe"),
                os.path.join(base_path, "_up_", "node", "node.exe"),
                os.path.join(base_path, "runtime", "node", "node.exe"),
            ])
        node_from_path = shutil.which("node")
        if node_from_path:
            node_candidates.append(node_from_path)
        node = next((candidate for candidate in node_candidates if os.path.isfile(candidate)), "")
        if not node:
            raise ComponentInstallError("未找到 Node.js，无法启动 JavaScript 组件")
        return [node, executable]
    if extension in {".cmd", ".bat"}:
        return ["cmd", "/c", executable]
    return [executable]


def _default_launcher(executable: str, cwd: str, *, base_path: str | None = None) -> dict:
    process = subprocess.Popen(
        build_launcher_command(executable, cwd, base_path=base_path),
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {"pid": process.pid}


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


def _versions_match(expected: str | None, detected: str | None) -> bool:
    expected_text = str(expected or "").strip().lower()
    detected_text = str(detected or "").strip().lower()
    if not expected_text or not detected_text:
        return True
    return expected_text == detected_text or expected_text.startswith(f"{detected_text}-") or detected_text.startswith(f"{expected_text}-")
