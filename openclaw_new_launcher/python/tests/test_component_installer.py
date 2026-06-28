from __future__ import annotations

import os
import sys
import tempfile
import unittest
import hashlib
import io
import tarfile
import zipfile
from dataclasses import dataclass


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.component_installer import ComponentInstaller
from core import component_installer as component_installer_module
from core.component_state import ComponentStateStore
from core.release_manifest import ComponentHealthCheck, ReleaseComponent


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def make_component(component_id: str = "codex-desktop") -> ReleaseComponent:
    return ReleaseComponent(
        component_id=component_id,
        name="Codex",
        version="1.0.0",
        platform="windows",
        arch="x64",
        archive_type="installer",
        size=1024,
        sha256="a" * 64,
        urls=("https://download.example.invalid/codex.exe",),
        install_path=f"agents/{component_id}",
        entry="Codex-Installer.exe",
    )


def with_health_check(component: ReleaseComponent) -> ReleaseComponent:
    return ReleaseComponent(
        component_id=component.component_id,
        name=component.name,
        version=component.version,
        platform=component.platform,
        arch=component.arch,
        archive_type=component.archive_type,
        size=component.size,
        sha256=component.sha256,
        urls=component.urls,
        install_path=component.install_path,
        entry=component.entry,
        category=component.category,
        official_url=component.official_url,
        description=component.description,
        health_check=ComponentHealthCheck(kind="http", url="http://127.0.0.1:18080/health", timeout_ms=1000),
        rollback=component.rollback,
    )


def make_payload_component(
    *,
    component_id: str = "codex-desktop",
    version: str,
    payload: bytes,
) -> ReleaseComponent:
    return ReleaseComponent(
        component_id=component_id,
        name="Codex",
        version=version,
        platform="windows",
        arch="x64",
        archive_type="installer",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        urls=(f"https://download.example.invalid/{component_id}-{version}.exe",),
        install_path=f"agents/{component_id}",
        entry="Codex-Installer.exe",
    )


def make_tgz_payload(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def make_zip_payload(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_tgz_component(payload: bytes) -> ReleaseComponent:
    return ReleaseComponent(
        component_id="claude-code",
        name="Claude Code",
        version="1.0.0",
        platform="windows",
        arch="x64",
        archive_type="tgz",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        urls=("https://download.example.invalid/claude-code.tgz",),
        install_path="agents/claude-code",
        entry="bin/claude.exe",
    )


def make_archive_component(payload: bytes, *, archive_type: str, entry: str) -> ReleaseComponent:
    return ReleaseComponent(
        component_id=f"archive-{archive_type}",
        name=f"Archive {archive_type}",
        version="1.0.0",
        platform="windows",
        arch="x64",
        archive_type=archive_type,
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        urls=(f"https://download.example.invalid/archive.{archive_type}",),
        install_path=f"agents/archive-{archive_type}",
        entry=entry,
    )


class ComponentInstallerSimulationTests(unittest.TestCase):
    def test_simulate_install_marks_simulation_ready_without_fetching_or_writing_install_path(self) -> None:
        progress: list[tuple[str, str]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: self.fail("simulate install must not download"),
            )

            state = installer.install(
                make_component(),
                simulate=True,
                job_id="job_sim",
                on_progress=lambda message, tone: progress.append((message, tone)),
            )

            self.assertEqual(state.status, "simulation_ready")
            self.assertEqual(state.job_id, "job_sim")
            self.assertFalse(os.path.exists(os.path.join(temp_dir, "agents", "codex-desktop")))
            self.assertEqual(store.load(), {})
            self.assertEqual(
                [message for message, _tone in progress],
                [
                    "准备 Codex",
                    "下载 Codex",
                    "校验 Codex",
                    "安装 Codex",
                    "配置 Codex",
                    "检测 Codex",
                    "Codex 流程预检已完成",
                ],
            )

    def test_download_failure_records_failed_state_and_retry_can_install(self) -> None:
        payload = b"codex retry payload"
        component = make_payload_component(version="1.0.0", payload=payload)
        attempts = 0

        def fetcher(_url: str, _timeout: float) -> bytes:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("network unavailable")
            return payload

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=fetcher,
                retry_sleep=lambda _delay: None,
            )

            ready = installer.install(component, job_id="job_retry")

            self.assertEqual(ready.status, "manual_install_required")
            self.assertEqual(ready.job_id, "job_retry")
            self.assertEqual(attempts, 2)
            installed_file = os.path.join(temp_dir, "agents", component.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_download_failure_after_retries_records_failed_state(self) -> None:
        payload = b"codex retry payload"
        component = make_payload_component(version="1.0.0", payload=payload)
        attempts = 0

        def fetcher(_url: str, _timeout: float) -> bytes:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("network unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=fetcher,
                retry_sleep=lambda _delay: None,
            )

            with self.assertRaisesRegex(Exception, "download failed"):
                installer.install(component, job_id="job_fail")

            failed = store.load()[component.component_id]
            self.assertEqual(failed.status, "download_failed")
            self.assertIn("network unavailable", failed.error_message or "")
            self.assertEqual(attempts, 3)

    def test_tgz_component_extracts_archive_entries(self) -> None:
        payload = make_tgz_payload(
            {
                "bin/claude.exe": b"claude launcher",
                "README.txt": b"offline component notes",
            }
        )
        component = make_tgz_component(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
            )

            state = installer.install(component, job_id="job_tgz")

            self.assertEqual(state.status, "ready")
            installed_root = os.path.join(temp_dir, "agents", "claude-code")
            with open(os.path.join(installed_root, "bin", "claude.exe"), "rb") as handle:
                self.assertEqual(handle.read(), b"claude launcher")
            with open(os.path.join(installed_root, "README.txt"), "rb") as handle:
                self.assertEqual(handle.read(), b"offline component notes")

    def test_tgz_component_missing_entry_fails_install(self) -> None:
        payload = make_tgz_payload({"README.txt": b"no executable"})
        component = make_tgz_component(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
            )

            with self.assertRaisesRegex(Exception, "entry"):
                installer.install(component, job_id="job_missing_tgz_entry")

            failed = store.load()[component.component_id]
            self.assertEqual(failed.status, "extract_failed")

    def test_zip_component_missing_entry_fails_install(self) -> None:
        payload = make_zip_payload({"README.txt": b"no executable"})
        component = make_archive_component(payload, archive_type="zip", entry="bin/tool.exe")

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
            )

            with self.assertRaisesRegex(Exception, "entry"):
                installer.install(component, job_id="job_missing_zip_entry")

            failed = store.load()[component.component_id]
            self.assertEqual(failed.status, "extract_failed")

    def test_installer_without_health_check_requires_manual_completion(self) -> None:
        payload = b"codex setup executable"
        component = make_payload_component(version="1.0.0", payload=payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
            )

            state = installer.install(component, job_id="job_manual")

            self.assertEqual(state.status, "manual_install_required")
            self.assertEqual(store.load()[component.component_id].status, "manual_install_required")
            installed_file = os.path.join(temp_dir, "agents", component.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_silent_installer_runs_and_detects_external_entry(self) -> None:
        payload = b"hermes setup executable"

        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "localappdata", "hermes", "hermes-agent", "venv", "Scripts", "hermes.EXE")
            try:
                component = ReleaseComponent(
                    component_id="hermes",
                    name="Hermes",
                    version="0.12.0",
                    platform="windows",
                    arch="x64",
                    archive_type="installer",
                    size=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    urls=("https://download.example.invalid/Hermes-Setup.exe",),
                    install_path="agents/hermes",
                    entry="Hermes-Setup.exe",
                    external_paths=(external_entry,),
                    installer_args=("/S",),
                    installer_timeout_ms=123000,
                )
            except TypeError as exc:
                self.fail(f"ReleaseComponent should accept installer_args: {exc}")
            calls: list[tuple[list[str], str, int]] = []

            def installer_runner(command: list[str], cwd: str, timeout_ms: int) -> FakeCompletedProcess:
                calls.append((command, cwd, timeout_ms))
                os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                with open(external_entry, "wb") as handle:
                    handle.write(b"hermes")
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            try:
                installer = ComponentInstaller(
                    base_path=temp_dir,
                    state_store=store,
                    fetcher=lambda _url, _timeout: payload,
                    installer_runner=installer_runner,
                )
            except TypeError as exc:
                self.fail(f"ComponentInstaller should accept installer_runner: {exc}")

            state = installer.install(component, job_id="job_silent_installer")

            install_dir = os.path.join(temp_dir, "agents", "hermes")
            self.assertEqual(state.status, "ready")
            self.assertEqual(
                calls,
                [([os.path.join(install_dir, "Hermes-Setup.exe"), "/S"], install_dir, 123000)],
            )

    def test_install_runs_declared_install_command_and_detects_external_entry(self) -> None:
        payload = make_tgz_payload({"package/bin/opencode.exe": b"opencode package"})

        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "npm-global", "opencode.CMD")
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.17.11",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry="package/bin/opencode.exe",
                install_command=("npm", "install", "-g", "opencode-ai@1.17.11"),
                command_timeout_ms=234000,
                external_paths=(external_entry,),
            )
            calls: list[tuple[list[str], str, int]] = []

            def installer_runner(command: list[str], cwd: str, timeout_ms: int) -> FakeCompletedProcess:
                calls.append((command, cwd, timeout_ms))
                os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                with open(external_entry, "wb") as handle:
                    handle.write(b"opencode")
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
                installer_runner=installer_runner,
            )

            state = installer.install(component, job_id="job_install_command")

            install_dir = os.path.join(temp_dir, "agents", "opencode")
            self.assertEqual(state.status, "ready")
            self.assertEqual(calls[0][0][-3:], ["install", "-g", "opencode-ai@1.17.11"])
            self.assertEqual(calls[0][1], install_dir)
            self.assertEqual(calls[0][2], 234000)
            self.assertTrue(os.path.isfile(external_entry))

    def test_install_command_retries_transient_failure_and_then_detects_external_entry(self) -> None:
        payload = make_tgz_payload({"package/bin/opencode.exe": b"opencode package"})

        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "npm-global", "opencode.CMD")
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.17.11",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry="package/bin/opencode.exe",
                install_command=("npm", "install", "-g", "opencode-ai@1.17.11"),
                external_paths=(external_entry,),
            )
            calls: list[list[str]] = []
            progress: list[tuple[str, str]] = []

            def installer_runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                if len(calls) == 1:
                    return FakeCompletedProcess(returncode=1, stderr="registry timeout")
                os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                with open(external_entry, "wb") as handle:
                    handle.write(b"opencode")
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
                installer_runner=installer_runner,
                retry_sleep=lambda _delay: None,
            )

            state = installer.install(
                component,
                job_id="job_install_command_retry",
                on_progress=lambda message, tone: progress.append((message, tone)),
            )

            self.assertEqual(state.status, "ready")
            install_calls = [command for command in calls if command[-3:] == ["install", "-g", "opencode-ai@1.17.11"]]
            self.assertEqual(len(install_calls), 2)
            self.assertTrue(any("重试" in message for message, _tone in progress))

    def test_upgrade_available_component_uses_pinned_install_command_to_update(self) -> None:
        payload = make_tgz_payload({"package/bin/codex.exe": b"codex package"})

        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "npm-global", "codex.CMD")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry="package/bin/codex.exe",
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
                external_paths=(external_entry,),
            )
            calls: list[list[str]] = []

            def installer_runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                with open(external_entry, "wb") as handle:
                    handle.write(b"codex")
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            store.mark(component.component_id, "upgrade_available", version="0.130.0")
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
                installer_runner=installer_runner,
            )

            state = installer.install(component, job_id="job_upgrade")

            install_calls = [command for command in calls if command[-3:] == ["install", "-g", "@openai/codex@0.142.3"]]
            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3-win32-x64")
            self.assertEqual(len(install_calls), 1)

    def test_install_command_persistent_failure_records_config_failed_after_retries(self) -> None:
        payload = make_tgz_payload({"package/bin/opencode.exe": b"opencode package"})

        with tempfile.TemporaryDirectory() as temp_dir:
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.17.11",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry="package/bin/opencode.exe",
                install_command=("npm", "install", "-g", "opencode-ai@1.17.11"),
                external_paths=(os.path.join(temp_dir, "npm-global", "opencode.CMD"),),
            )
            calls: list[list[str]] = []

            def installer_runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                return FakeCompletedProcess(returncode=1, stderr="registry timeout")

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
                installer_runner=installer_runner,
                retry_sleep=lambda _delay: None,
            )

            with self.assertRaisesRegex(Exception, "install command failed"):
                installer.install(component, job_id="job_install_command_retry_fail")

            failed = store.load()[component.component_id]
            self.assertEqual(failed.status, "config_failed")
            install_calls = [command for command in calls if command[-3:] == ["install", "-g", "opencode-ai@1.17.11"]]
            self.assertEqual(len(install_calls), 3)
            self.assertIn("registry timeout", failed.error_message or "")

    def test_install_command_resolves_windows_npm_cmd_shim(self) -> None:
        payload = make_tgz_payload({"package/openclaw.mjs": b"openclaw package"})

        with tempfile.TemporaryDirectory() as temp_dir:
            npm_cmd = os.path.join(temp_dir, "node", "npm.cmd")
            os.makedirs(os.path.dirname(npm_cmd), exist_ok=True)
            with open(npm_cmd, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")
            external_entry = os.path.join(temp_dir, "npm-global", "openclaw.CMD")
            component = ReleaseComponent(
                component_id="openclaw-companion",
                name="OpenClaw",
                version="2026.6.10",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/openclaw.tgz",),
                install_path="agents/openclaw-companion",
                entry=None,
                install_command=("npm", "install", "-g", "openclaw@2026.6.10"),
                external_paths=(external_entry,),
            )
            calls: list[tuple[list[str], str, int]] = []

            def installer_runner(command: list[str], cwd: str, timeout_ms: int) -> FakeCompletedProcess:
                calls.append((command, cwd, timeout_ms))
                os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                with open(external_entry, "wb") as handle:
                    handle.write(b"openclaw")
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
                installer_runner=installer_runner,
            )

            installer.install(component, job_id="job_install_npm_cmd")

            self.assertEqual(calls[0][0], ["cmd", "/c", npm_cmd, "install", "-g", "openclaw@2026.6.10"])

    def test_detect_existing_entry_marks_component_ready(self) -> None:
        component = make_component()

        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "agents", component.component_id)
            os.makedirs(install_dir)
            with open(os.path.join(install_dir, "Codex-Installer.exe"), "wb") as handle:
                handle.write(b"codex")
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(base_path=temp_dir, state_store=store)

            state = installer.detect(component, job_id="job_detect")

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, component.version)
            self.assertEqual(state.job_id, "job_detect")

    def test_detect_existing_external_entry_marks_component_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_root = os.path.join(temp_dir, "localappdata")
            external_entry = os.path.join(external_root, "hermes", "hermes-agent", "venv", "Scripts", "hermes.EXE")
            os.makedirs(os.path.dirname(external_entry), exist_ok=True)
            with open(external_entry, "wb") as handle:
                handle.write(b"hermes")
            try:
                component = ReleaseComponent(
                    component_id="hermes",
                    name="Hermes",
                    version="0.12.0",
                    platform="windows",
                    arch="x64",
                    archive_type="installer",
                    size=1024,
                    sha256="b" * 64,
                    urls=("https://download.example.invalid/Hermes-Setup.exe",),
                    install_path="agents/hermes",
                    entry="Hermes-Setup.exe",
                    external_paths=(external_entry,),
                )
            except TypeError as exc:
                self.fail(f"ReleaseComponent should accept external_paths: {exc}")
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(base_path=temp_dir, state_store=store)

            try:
                state = installer.detect(component, job_id="job_detect_external")
            except Exception as exc:
                self.fail(f"external component path should be detected as ready: {exc}")

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, component.version)

    def test_detect_finds_codex_from_npm_prefix_when_fixed_path_misses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            npm_prefix = os.path.join(temp_dir, "custom-npm-global")
            codex_shim = os.path.join(npm_prefix, "codex.cmd")
            os.makedirs(os.path.dirname(codex_shim), exist_ok=True)
            with open(codex_shim, "wb") as handle:
                handle.write(b"codex shim")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="c" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
                external_paths=("%LOCALAPPDATA%/loom-test-missing/codex.cmd",),
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            calls: list[list[str]] = []

            def runner(command: list[str], cwd: str, timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                if command[-2:] == ["prefix", "-g"]:
                    return FakeCompletedProcess(returncode=0, stdout=f"{npm_prefix}\n")
                if command[-1:] == ["--version"]:
                    return FakeCompletedProcess(returncode=0, stdout="codex 0.142.3\n")
                return FakeCompletedProcess(returncode=1)

            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                installer_runner=runner,
            )

            state = installer.detect(component, job_id="job_detect_codex_prefix")

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3")
            self.assertTrue(any(command[-2:] == ["prefix", "-g"] for command in calls))

    def test_detect_finds_codex_from_path_when_fixed_path_misses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_shim = os.path.join(temp_dir, "path-bin", "codex.cmd")
            os.makedirs(os.path.dirname(codex_shim), exist_ok=True)
            with open(codex_shim, "wb") as handle:
                handle.write(b"codex shim")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="d" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
                external_paths=("%LOCALAPPDATA%/loom-test-missing/codex.cmd",),
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            original_which = component_installer_module.shutil.which

            def fake_which(name: str) -> str | None:
                if name.lower() in {"codex", "codex.cmd"}:
                    return codex_shim
                return original_which(name)

            component_installer_module.shutil.which = fake_which
            try:
                installer = ComponentInstaller(
                    base_path=temp_dir,
                    state_store=store,
                    installer_runner=lambda command, _cwd, _timeout_ms: FakeCompletedProcess(
                        returncode=0,
                        stdout="0.142.3\n" if command[-1:] == ["--version"] else "",
                    ),
                )

                state = installer.detect(component, job_id="job_detect_codex_path")
            finally:
                component_installer_module.shutil.which = original_which

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3")

    def test_detect_finds_external_entry_sibling_variant_when_manifest_lists_cmd(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            appdata = os.path.join(temp_dir, "AppData", "Roaming")
            codex_ps1 = os.path.join(appdata, "npm", "codex.ps1")
            os.makedirs(os.path.dirname(codex_ps1), exist_ok=True)
            with open(codex_ps1, "wb") as handle:
                handle.write(b"codex shim")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="d" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
                external_paths=("%APPDATA%/npm/codex.cmd",),
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            old_appdata = os.environ.get("APPDATA")
            original_which = component_installer_module.shutil.which
            os.environ["APPDATA"] = appdata
            component_installer_module.shutil.which = lambda _name: None
            try:
                installer = ComponentInstaller(
                    base_path=temp_dir,
                    state_store=store,
                    installer_runner=lambda command, _cwd, _timeout_ms: FakeCompletedProcess(
                        returncode=0 if command[-1:] == ["--version"] else 1,
                        stdout="0.142.3\n" if command[-1:] == ["--version"] else "",
                    ),
                )

                state = installer.detect(component, job_id="job_detect_codex_ps1")
            finally:
                component_installer_module.shutil.which = original_which
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3")

    def test_detect_finds_codex_in_default_appdata_npm_without_manifest_external_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            appdata = os.path.join(temp_dir, "AppData", "Roaming")
            codex_cmd = os.path.join(appdata, "npm", "codex.cmd")
            os.makedirs(os.path.dirname(codex_cmd), exist_ok=True)
            with open(codex_cmd, "wb") as handle:
                handle.write(b"codex shim")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="d" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
                external_paths=(),
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            old_appdata = os.environ.get("APPDATA")
            os.environ["APPDATA"] = appdata
            try:
                installer = ComponentInstaller(
                    base_path=temp_dir,
                    state_store=store,
                    installer_runner=lambda command, _cwd, _timeout_ms: FakeCompletedProcess(
                        returncode=0 if command[-1:] == ["--version"] else 1,
                        stdout="0.142.3\n" if command[-1:] == ["--version"] else "",
                    ),
                )

                state = installer.detect(component, job_id="job_detect_codex_default_appdata")
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3")

    def test_detect_finds_claude_in_default_user_local_bin_without_manifest_external_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            userprofile = os.path.join(temp_dir, "User")
            claude_exe = os.path.join(userprofile, ".local", "bin", "claude.exe")
            os.makedirs(os.path.dirname(claude_exe), exist_ok=True)
            with open(claude_exe, "wb") as handle:
                handle.write(b"claude shim")
            component = ReleaseComponent(
                component_id="claude-code",
                name="Claude Code",
                version="2.1.195",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="c" * 64,
                urls=("https://download.example.invalid/claude-code.tgz",),
                install_path="agents/claude-code",
                entry=None,
                external_paths=(),
                install_command=("npm", "install", "-g", "@anthropic-ai/claude-code@2.1.195"),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            old_userprofile = os.environ.get("USERPROFILE")
            os.environ["USERPROFILE"] = userprofile
            try:
                installer = ComponentInstaller(
                    base_path=temp_dir,
                    state_store=store,
                    installer_runner=lambda command, _cwd, _timeout_ms: FakeCompletedProcess(
                        returncode=0 if command[-1:] == ["--version"] else 1,
                        stdout="2.1.195\n" if command[-1:] == ["--version"] else "",
                    ),
                )

                state = installer.detect(component, job_id="job_detect_claude_default_local_bin")
            finally:
                if old_userprofile is None:
                    os.environ.pop("USERPROFILE", None)
                else:
                    os.environ["USERPROFILE"] = old_userprofile

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "2.1.195")

    def test_detect_existing_external_entry_marks_upgrade_available_when_version_is_old(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "npm-global", "opencode.CMD")
            os.makedirs(os.path.dirname(external_entry), exist_ok=True)
            with open(external_entry, "wb") as handle:
                handle.write(b"opencode shim")
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.17.11",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="e" * 64,
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry=None,
                external_paths=(external_entry,),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            version_calls: list[tuple[list[str], str, int]] = []

            def version_runner(command: list[str], cwd: str, timeout_ms: int) -> FakeCompletedProcess:
                version_calls.append((command, cwd, timeout_ms))
                if not os.path.isdir(cwd):
                    return FakeCompletedProcess(returncode=1, stderr=f"missing cwd: {cwd}")
                return FakeCompletedProcess(returncode=0, stdout="1.3.0\n")

            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                installer_runner=version_runner,
            )

            state = installer.detect(component, job_id="job_detect_old")

            self.assertEqual(state.status, "upgrade_available")
            self.assertEqual(state.version, "1.3.0")
            self.assertEqual(version_calls[0][1], temp_dir)

    def test_detect_parses_v_prefixed_version_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "hermes.EXE")
            with open(external_entry, "wb") as handle:
                handle.write(b"hermes shim")
            component = ReleaseComponent(
                component_id="hermes",
                name="Hermes",
                version="0.12.0",
                platform="windows",
                arch="x64",
                archive_type="installer",
                size=1024,
                sha256="f" * 64,
                urls=("https://download.example.invalid/hermes.exe",),
                install_path="agents/hermes",
                entry=None,
                external_paths=(external_entry,),
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                installer_runner=lambda _command, _cwd, _timeout_ms: FakeCompletedProcess(
                    returncode=0,
                    stdout="Hermes Agent v0.12.0 (2026.4.30)\n",
                ),
            )

            state = installer.detect(component, job_id="job_detect_hermes")

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.12.0")

    def test_launch_ready_component_uses_validated_entry_path(self) -> None:
        component = make_component()
        launched: list[tuple[str, str]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "agents", component.component_id)
            os.makedirs(install_dir)
            entry_path = os.path.join(install_dir, "Codex-Installer.exe")
            with open(entry_path, "wb") as handle:
                handle.write(b"codex")
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            store.mark(component.component_id, "ready", version=component.version)
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                launcher=lambda executable, cwd: launched.append((executable, cwd)) or {"pid": 42},
            )

            result = installer.launch(component, job_id="job_start")

            self.assertTrue(result["success"])
            self.assertEqual(result["pid"], 42)
            self.assertEqual(launched, [(entry_path, install_dir)])
            started = store.load()[component.component_id]
            self.assertEqual(started.status, "started")
            self.assertEqual(started.job_id, "job_start")

    def test_launch_uses_external_entry_when_manifest_entry_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "npm-global", "codex.CMD")
            os.makedirs(os.path.dirname(external_entry), exist_ok=True)
            with open(external_entry, "wb") as handle:
                handle.write(b"codex shim")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="d" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
                external_paths=(external_entry,),
            )
            launched: list[tuple[str, str]] = []
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            store.mark(component.component_id, "ready", version=component.version)
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                launcher=lambda executable, cwd: launched.append((executable, cwd)) or {"pid": 4242},
            )

            result = installer.launch(component, job_id="job_external_start")

            self.assertTrue(result["success"])
            self.assertEqual(result["pid"], 4242)
            self.assertEqual(launched, [(external_entry, temp_dir)])

    def test_uninstall_runs_declared_command_and_removes_managed_payload(self) -> None:
        component = ReleaseComponent(
            component_id="opencode",
            name="opencode",
            version="1.0.0",
            platform="windows",
            arch="x64",
            archive_type="tgz",
            size=1024,
            sha256="c" * 64,
            urls=("https://download.example.invalid/opencode.tgz",),
            install_path="agents/opencode",
            entry="package/bin/opencode.exe",
            uninstall_command=("npm", "uninstall", "-g", "opencode-ai"),
            command_timeout_ms=123000,
        )
        calls: list[tuple[list[str], str, int]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "agents", "opencode")
            rollback_dir = os.path.join(temp_dir, "data", ".installer", "rollback", "opencode")
            os.makedirs(os.path.join(install_dir, "package", "bin"), exist_ok=True)
            os.makedirs(rollback_dir, exist_ok=True)
            with open(os.path.join(install_dir, "package", "bin", "opencode.exe"), "wb") as handle:
                handle.write(b"opencode")
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            store.mark(component.component_id, "ready", version=component.version, previous_version="0.9.0")

            try:
                installer = ComponentInstaller(
                    base_path=temp_dir,
                    state_store=store,
                    installer_runner=lambda command, cwd, timeout_ms: calls.append((command, cwd, timeout_ms)) or FakeCompletedProcess(returncode=0),
                )
                state = installer.uninstall(component, job_id="job_uninstall")
            except AttributeError as exc:
                self.fail(f"ComponentInstaller should expose uninstall: {exc}")

            self.assertEqual(calls[0][0][-3:], ["uninstall", "-g", "opencode-ai"])
            self.assertEqual(calls[0][1], temp_dir)
            self.assertEqual(calls[0][2], 123000)
            self.assertFalse(os.path.exists(install_dir))
            self.assertFalse(os.path.exists(rollback_dir))
            self.assertEqual(state.status, "not_installed")
            self.assertEqual(state.job_id, "job_uninstall")

    def test_launcher_command_uses_bundled_node_for_mjs_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            node_exe = os.path.join(temp_dir, "node", "node.exe")
            script = os.path.join(temp_dir, "agents", "openclaw", "package", "openclaw.mjs")
            os.makedirs(os.path.dirname(node_exe), exist_ok=True)
            os.makedirs(os.path.dirname(script), exist_ok=True)
            with open(node_exe, "wb") as handle:
                handle.write(b"node")
            with open(script, "wb") as handle:
                handle.write(b"console.log('openclaw')")

            build_command = getattr(component_installer_module, "build_launcher_command", lambda *_args, **_kwargs: [])
            command = build_command(script, os.path.dirname(script), base_path=temp_dir)

            self.assertEqual(command, [node_exe, script])

    def test_launch_failure_marks_component_start_failed(self) -> None:
        component = make_component()

        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, "agents", component.component_id)
            os.makedirs(install_dir)
            with open(os.path.join(install_dir, "Codex-Installer.exe"), "wb") as handle:
                handle.write(b"codex")
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            store.mark(component.component_id, "ready", version=component.version)
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                launcher=lambda _executable, _cwd: (_ for _ in ()).throw(RuntimeError("process denied")),
            )

            with self.assertRaisesRegex(Exception, "启动失败"):
                installer.launch(component, job_id="job_start_fail")

            failed = store.load()[component.component_id]
            self.assertEqual(failed.status, "start_failed")
            self.assertEqual(failed.job_id, "job_start_fail")
            self.assertIn("process denied", failed.error_message or "")

    def test_second_install_creates_rollback_and_rollback_restores_previous_payload(self) -> None:
        component_v1 = with_health_check(make_payload_component(version="1.0.0", payload=b"codex v1"))
        component_v2 = with_health_check(make_payload_component(version="2.0.0", payload=b"codex v2"))
        payloads = {
            component_v1.urls[0]: b"codex v1",
            component_v2.urls[0]: b"codex v2",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda url, _timeout: payloads[url],
                health_checker=lambda _component, _path: None,
            )

            installer.install(component_v1, job_id="job_v1")
            upgraded = installer.install(component_v2, job_id="job_v2")

            self.assertEqual(upgraded.status, "ready")
            self.assertEqual(upgraded.previous_version, "1.0.0")
            restored = installer.rollback(component_v2.component_id)

            self.assertEqual(restored.status, "ready")
            self.assertEqual(restored.version, "1.0.0")
            installed_file = os.path.join(temp_dir, "agents", component_v2.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), b"codex v1")

    def test_health_check_failure_marks_failed_and_keeps_previous_for_rollback(self) -> None:
        component_v1 = make_payload_component(version="1.0.0", payload=b"codex v1")
        component_v2 = with_health_check(make_payload_component(version="2.0.0", payload=b"codex v2"))
        payloads = {
            component_v1.urls[0]: b"codex v1",
            component_v2.urls[0]: b"codex v2",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda url, _timeout: payloads[url],
                health_checker=lambda _component, _path: (_ for _ in ()).throw(RuntimeError("health endpoint unavailable")),
            )

            installer.install(component_v1, job_id="job_v1")
            with self.assertRaisesRegex(Exception, "health check failed"):
                installer.install(component_v2, job_id="job_v2")

            failed = store.load()[component_v2.component_id]
            self.assertEqual(failed.status, "health_failed")
            self.assertEqual(failed.previous_version, "1.0.0")
            self.assertIn("health endpoint unavailable", failed.error_message or "")

            restored = installer.rollback(component_v2.component_id)

            self.assertEqual(restored.status, "ready")
            self.assertEqual(restored.version, "1.0.0")

    def test_health_check_failure_restores_previous_active_payload(self) -> None:
        component_v1 = with_health_check(make_payload_component(version="1.0.0", payload=b"codex v1"))
        component_v2 = with_health_check(make_payload_component(version="2.0.0", payload=b"codex v2"))
        payloads = {
            component_v1.urls[0]: b"codex v1",
            component_v2.urls[0]: b"codex v2",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            health_calls = 0

            def health_checker(_component: ReleaseComponent, _path: str) -> None:
                nonlocal health_calls
                health_calls += 1
                if health_calls == 2:
                    raise RuntimeError("health endpoint unavailable")

            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda url, _timeout: payloads[url],
                health_checker=health_checker,
            )

            installer.install(component_v1, job_id="job_v1")
            with self.assertRaisesRegex(Exception, "health check failed"):
                installer.install(component_v2, job_id="job_v2")

            installed_file = os.path.join(temp_dir, "agents", component_v2.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), b"codex v1")

    def test_legacy_payload_prefix_does_not_double_nest_inside_loomfiles_base(self) -> None:
        payload = b"codex setup executable"
        component = ReleaseComponent(
            component_id="codex-desktop",
            name="Codex",
            version="1.0.0",
            platform="windows",
            arch="x64",
            archive_type="installer",
            size=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            urls=("https://download.example.invalid/codex.exe",),
            install_path="LOOMFiles/agents/codex-desktop",
            entry="Codex-Installer.exe",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            payload_root = os.path.join(temp_dir, "LOOMFiles")
            os.makedirs(payload_root)
            store = ComponentStateStore(os.path.join(payload_root, "state.json"))
            installer = ComponentInstaller(
                base_path=payload_root,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
            )

            installer.install(component, job_id="job_legacy_prefix")

            self.assertTrue(os.path.exists(os.path.join(payload_root, "agents", "codex-desktop", "Codex-Installer.exe")))
            self.assertFalse(os.path.exists(os.path.join(payload_root, "LOOMFiles", "agents", "codex-desktop")))


if __name__ == "__main__":
    unittest.main()
