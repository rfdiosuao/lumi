from __future__ import annotations

import os
import sys
import tempfile
import unittest
import hashlib
import io
import json
import tarfile
import zipfile
from dataclasses import dataclass
from unittest import mock


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)


from core.component_installer import ComponentInstallError, ComponentInstaller
from core import component_installer as component_installer_module
from core.component_state import ComponentStateStore
from core.paths import AppPaths
from core.release_manifest import ComponentHealthCheck, ReleaseComponent
from core.wire_config import WireService


@dataclass
class FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeHTTPResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers: dict[str, str] | None = None):
        self._body = body
        self._cursor = 0
        self.status = status
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._body) - self._cursor
        chunk = self._body[self._cursor : self._cursor + size]
        self._cursor += len(chunk)
        return chunk

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


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

    def test_verified_cache_hit_avoids_fetcher(self) -> None:
        payload = b"codex cached payload"
        component = make_payload_component(version="1.0.0", payload=payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: self.fail("verified cache should avoid fetcher"),
            )
            cache_path = installer._verified_cache_path(component)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as handle:
                handle.write(payload)

            state = installer.install(component, job_id="job_cache_hit")

            self.assertEqual(state.status, "manual_install_required")
            installed_file = os.path.join(temp_dir, "agents", component.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_invalid_verified_cache_is_discarded_and_refetched(self) -> None:
        payload = b"codex fresh payload"
        component = make_payload_component(version="1.0.0", payload=payload)
        fetch_calls = 0

        def fetcher(_url: str, _timeout: float) -> bytes:
            nonlocal fetch_calls
            fetch_calls += 1
            return payload

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(base_path=temp_dir, state_store=store, fetcher=fetcher)
            cache_path = installer._verified_cache_path(component)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as handle:
                handle.write(payload[:5])

            installer.install(component, job_id="job_cache_refetch")

            self.assertEqual(fetch_calls, 1)
            installed_file = os.path.join(temp_dir, "agents", component.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_stream_download_reports_percent_and_size(self) -> None:
        payload = (b"0123456789" * 10)
        component = make_payload_component(version="1.0.0", payload=payload)
        progress: list[tuple[str, str]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(base_path=temp_dir, state_store=store)

            with mock.patch.object(
                component_installer_module,
                "urlopen",
                return_value=FakeHTTPResponse(payload, headers={"Content-Length": str(len(payload))}),
            ):
                state = installer.install(
                    component,
                    job_id="job_stream_progress",
                    on_progress=lambda message, tone: progress.append((message, tone)),
                )

            self.assertEqual(state.status, "manual_install_required")
            download_messages = [message for message, _tone in progress if "下载 Codex" in message]
            self.assertTrue(any("%" in message and "/" in message for message in download_messages))
            self.assertTrue(any("100%" in message for message in download_messages))

    def test_partial_download_uses_range_and_appends(self) -> None:
        payload = b"prefix-suffix"
        prefix = b"prefix-"
        suffix = payload[len(prefix) :]
        component = make_payload_component(version="1.0.0", payload=payload)
        requests: list[object] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(base_path=temp_dir, state_store=store)
            partial_path = installer._verified_cache_path(component) + ".part"
            os.makedirs(os.path.dirname(partial_path), exist_ok=True)
            with open(partial_path, "wb") as handle:
                handle.write(prefix)

            def fake_urlopen(request: object, timeout: float) -> FakeHTTPResponse:
                requests.append(request)
                return FakeHTTPResponse(suffix, status=206, headers={"Content-Length": str(len(suffix))})

            with mock.patch.object(component_installer_module, "urlopen", side_effect=fake_urlopen):
                installer.install(component, job_id="job_resume_append")

            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].headers.get("Range"), f"bytes={len(prefix)}-")
            installed_file = os.path.join(temp_dir, "agents", component.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), payload)

    def test_server_ignoring_range_restarts_without_duplicate_bytes(self) -> None:
        payload = b"fresh-payload"
        prefix = b"stale-"
        component = make_payload_component(version="1.0.0", payload=payload)
        requests: list[object] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(base_path=temp_dir, state_store=store)
            partial_path = installer._verified_cache_path(component) + ".part"
            os.makedirs(os.path.dirname(partial_path), exist_ok=True)
            with open(partial_path, "wb") as handle:
                handle.write(prefix)

            def fake_urlopen(request: object, timeout: float) -> FakeHTTPResponse:
                requests.append(request)
                return FakeHTTPResponse(payload, status=200, headers={"Content-Length": str(len(payload))})

            with mock.patch.object(component_installer_module, "urlopen", side_effect=fake_urlopen):
                installer.install(component, job_id="job_resume_restart")

            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].headers.get("Range"), f"bytes={len(prefix)}-")
            installed_file = os.path.join(temp_dir, "agents", component.component_id, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), payload)

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

            self.assertEqual(calls[0][0][:3], ["cmd", "/c", npm_cmd])
            self.assertIn("--prefix", calls[0][0])
            self.assertEqual(calls[0][0][-3:], ["install", "-g", "openclaw@2026.6.10"])

    def test_npm_install_command_uses_bundled_node_and_private_prefix(self) -> None:
        payload = make_tgz_payload({"package/bin/claude.exe": b"claude package"})

        with tempfile.TemporaryDirectory() as temp_dir:
            node_exe = os.path.join(temp_dir, "node", "node.exe")
            npm_cli = os.path.join(temp_dir, "node", "node_modules", "npm", "bin", "npm-cli.js")
            private_prefix = os.path.join(temp_dir, "data", ".installer", "npm-global")
            external_entry = os.path.join(private_prefix, "claude.cmd")
            os.makedirs(os.path.dirname(npm_cli), exist_ok=True)
            with open(node_exe, "wb") as handle:
                handle.write(b"node")
            with open(npm_cli, "wb") as handle:
                handle.write(b"npm cli")
            component = ReleaseComponent(
                component_id="claude-code",
                name="Claude Code",
                version="2.1.195",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/claude-code.tgz",),
                install_path="agents/claude-code",
                entry=None,
                install_command=("npm", "install", "-g", "@anthropic-ai/claude-code@2.1.195"),
                external_paths=(external_entry,),
            )
            calls: list[list[str]] = []

            def installer_runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                if "install" in command:
                    os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                    with open(external_entry, "wb") as handle:
                        handle.write(b"claude")
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda _url, _timeout: payload,
                installer_runner=installer_runner,
            )

            installer.install(component, job_id="job_private_npm_prefix")

            install_call = next(command for command in calls if "install" in command)
            self.assertEqual(install_call[:2], [node_exe, npm_cli])
            self.assertIn("--prefix", install_call)
            self.assertIn(private_prefix, install_call)

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

    def test_detects_managed_codex_vendor_entry_with_one_direct_version_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_entry = os.path.join(
                temp_dir,
                "agents",
                "codex-desktop",
                "package",
                "vendor",
                "x86_64-pc-windows-msvc",
                "bin",
                "codex.exe",
            )
            os.makedirs(os.path.dirname(vendor_entry), exist_ok=True)
            with open(vendor_entry, "wb") as handle:
                handle.write(b"codex")
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
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            calls: list[list[str]] = []
            timeouts: list[int] = []

            def runner(command: list[str], _cwd: str, timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                timeouts.append(timeout_ms)
                self.assertEqual(command, [vendor_entry, "--version"])
                return FakeCompletedProcess(returncode=0, stdout="codex-cli 0.142.3\n")

            installer = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")), installer_runner=runner)

            state = installer.detect(component, job_id="job_detect_managed_codex")

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3")
            self.assertEqual(calls, [[vendor_entry, "--version"]])
            self.assertEqual(timeouts, [5000])

    def test_detects_external_codex_with_single_expensive_discovery_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "npm-global", "codex.cmd")
            os.makedirs(os.path.dirname(external_entry), exist_ok=True)
            with open(external_entry, "wb") as handle:
                handle.write(b"codex")
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
                external_paths=(external_entry,),
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            calls: list[list[str]] = []

            def runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                if command[:3] == ["powershell", "-NoProfile", "-Command"]:
                    return FakeCompletedProcess(returncode=1)
                if command[-2:] == ["prefix", "-g"]:
                    return FakeCompletedProcess(returncode=1)
                if command[-2:] == ["bin", "-g"]:
                    return FakeCompletedProcess(returncode=1)
                if command[-2:] == ["root", "-g"]:
                    return FakeCompletedProcess(returncode=1)
                if command[-1:] == ["--version"] and external_entry in command:
                    return FakeCompletedProcess(returncode=0, stdout="codex-cli 0.142.3\n")
                self.fail(f"unexpected runner command: {command}")

            installer = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")), installer_runner=runner)

            state = installer.detect(component, job_id="job_detect_external_codex")

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "0.142.3")
            self.assertEqual(sum(command[:3] == ["powershell", "-NoProfile", "-Command"] for command in calls), 1)
            self.assertEqual(sum(command[-2:] == ["prefix", "-g"] for command in calls), 1)
            self.assertEqual(sum(command[-2:] == ["bin", "-g"] for command in calls), 1)
            self.assertEqual(sum(command[-2:] == ["root", "-g"] for command in calls), 1)

    def test_install_skips_legacy_npm_command_for_valid_managed_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_relative_path = "package/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
            vendor_entry = os.path.join(temp_dir, "agents", "codex-desktop", *vendor_relative_path.split("/"))
            payload = make_tgz_payload({vendor_relative_path: b"codex"})
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
                entry=None,
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            calls: list[list[str]] = []

            def runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                self.assertEqual(command, [vendor_entry, "--version"])
                return FakeCompletedProcess(returncode=0, stdout="codex-cli 0.142.3\n")

            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")),
                fetcher=lambda _url, _timeout: payload,
                installer_runner=runner,
            )

            state = installer.install(component, job_id="job_install_managed_codex")

            self.assertEqual(state.status, "ready")
            self.assertEqual(calls, [[vendor_entry, "--version"]])

    def test_install_does_not_trust_failed_managed_codex_version_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_relative_path = "package/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
            vendor_entry = os.path.join(temp_dir, "agents", "codex-desktop", *vendor_relative_path.split("/"))
            payload = make_tgz_payload({vendor_relative_path: b"codex"})
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
                entry=None,
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
            )
            calls: list[list[str]] = []

            def runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                if command == [vendor_entry, "--version"]:
                    return FakeCompletedProcess(returncode=1, stdout="codex-cli 0.142.3\n")
                return FakeCompletedProcess(returncode=1, stderr="npm install failed")

            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")),
                fetcher=lambda _url, _timeout: payload,
                installer_runner=runner,
                retry_sleep=lambda _seconds: None,
            )

            with self.assertRaises(ComponentInstallError):
                installer.install(component, job_id="job_failed_managed_codex")

            self.assertEqual(installer.state_store.load()[component.component_id].status, "health_failed")
            self.assertEqual(calls[0], [vendor_entry, "--version"])
            self.assertEqual(len(calls), 1)

    def test_install_rejects_failed_managed_codex_probe_even_if_legacy_fallback_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "external", "codex.cmd")
            component_v1 = make_payload_component(version="0.130.0", payload=b"codex v1")
            vendor_relative_path = "package/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
            payload_v2 = make_tgz_payload({vendor_relative_path: b"codex v2"})
            component_v2 = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload_v2),
                sha256=hashlib.sha256(payload_v2).hexdigest(),
                urls=("https://download.example.invalid/codex-v2.tgz",),
                install_path=component_v1.install_path,
                entry=None,
                install_command=("npm", "install", "-g", "@openai/codex@0.142.3"),
                external_paths=(external_entry,),
            )
            payloads = {
                component_v1.urls[0]: b"codex v1",
                component_v2.urls[0]: payload_v2,
            }
            vendor_entry = os.path.join(temp_dir, *component_v2.install_path.split("/"), *vendor_relative_path.split("/"))
            calls: list[list[str]] = []

            def runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                calls.append(command)
                if command == [vendor_entry, "--version"]:
                    return FakeCompletedProcess(returncode=1, stdout="codex-cli 0.142.3\n")
                if "install" in command:
                    os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                    with open(external_entry, "wb") as handle:
                        handle.write(b"codex")
                    return FakeCompletedProcess(returncode=0)
                return FakeCompletedProcess(returncode=0)

            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                fetcher=lambda url, _timeout: payloads[url],
                installer_runner=runner,
            )

            installer.install(component_v1, job_id="job_v1")
            with self.assertRaisesRegex(Exception, "health check failed"):
                installer.install(component_v2, job_id="job_failed_managed_codex_restore")

            failed = store.load()[component_v2.component_id]
            self.assertEqual(failed.status, "health_failed")
            self.assertEqual(failed.previous_version, "0.130.0")
            self.assertEqual(calls, [[vendor_entry, "--version"]])
            installed_file = os.path.join(temp_dir, component_v2.install_path, "Codex-Installer.exe")
            with open(installed_file, "rb") as handle:
                self.assertEqual(handle.read(), b"codex v1")

    def test_detect_rejects_managed_codex_with_failed_version_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_entry = os.path.join(
                temp_dir,
                "agents",
                "codex-desktop",
                "package",
                "vendor",
                "x86_64-pc-windows-msvc",
                "bin",
                "codex.exe",
            )
            os.makedirs(os.path.dirname(vendor_entry), exist_ok=True)
            with open(vendor_entry, "wb") as handle:
                handle.write(b"codex")
            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1,
                sha256="c" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
            )
            store = ComponentStateStore(os.path.join(temp_dir, "state.json"))
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=store,
                installer_runner=lambda _command, _cwd, _timeout_ms: FakeCompletedProcess(
                    returncode=1,
                    stdout="codex-cli 0.142.3\n",
                ),
            )

            with self.assertRaises(ComponentInstallError):
                installer.detect(component, job_id="job_detect_failed_managed_codex")

            self.assertEqual(store.load()[component.component_id].status, "health_failed")

    def test_external_discovery_cache_reuses_positive_result_across_installers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "external", "opencode.exe")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "wb") as handle:
                handle.write(b"opencode")
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.0.0",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1,
                sha256="a" * 64,
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry=None,
                external_paths=(entry,),
            )
            candidates_called = 0

            def candidates(_component: ReleaseComponent) -> list[str]:
                nonlocal candidates_called
                candidates_called += 1
                return [entry]

            getattr(component_installer_module, "_EXTERNAL_ENTRY_CACHE", {}).clear()
            first = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "first.json")))
            second = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "second.json")))
            first._external_entry_candidates = candidates  # type: ignore[method-assign]
            second._external_entry_candidates = candidates  # type: ignore[method-assign]

            self.assertEqual(first._first_existing_external_entry(component), entry)
            self.assertEqual(second._first_existing_external_entry(component), entry)
            self.assertEqual(candidates_called, 1)

    def test_external_discovery_cache_reuses_negative_result_across_installers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.0.0",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1,
                sha256="a" * 64,
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry=None,
            )
            candidates_called = 0

            def candidates(_component: ReleaseComponent) -> list[str]:
                nonlocal candidates_called
                candidates_called += 1
                return []

            getattr(component_installer_module, "_EXTERNAL_ENTRY_CACHE", {}).clear()
            first = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "first.json")))
            second = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "second.json")))
            first._external_entry_candidates = candidates  # type: ignore[method-assign]
            second._external_entry_candidates = candidates  # type: ignore[method-assign]

            self.assertIsNone(first._first_existing_external_entry(component))
            self.assertIsNone(second._first_existing_external_entry(component))
            self.assertEqual(candidates_called, 1)

    def test_external_discovery_cache_expires_after_thirty_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "external", "opencode.exe")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "wb") as handle:
                handle.write(b"opencode")
            component = ReleaseComponent("opencode", "opencode", "1.0.0", "windows", "x64", "tgz", 1, "a" * 64, ("https://download.example.invalid/opencode.tgz",), "agents/opencode", None)
            candidates_called = 0

            def candidates(_component: ReleaseComponent) -> list[str]:
                nonlocal candidates_called
                candidates_called += 1
                return [entry]

            installer = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")))
            installer._external_entry_candidates = candidates  # type: ignore[method-assign]
            clock = [100.0]
            with mock.patch.object(component_installer_module.time, "monotonic", side_effect=lambda: clock[0]):
                self.assertEqual(installer._first_existing_external_entry(component), entry)
                clock[0] = 130.1
                self.assertEqual(installer._first_existing_external_entry(component), entry)
            self.assertEqual(candidates_called, 2)

    def test_external_discovery_cache_discards_vanished_positive_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first_entry = os.path.join(temp_dir, "external", "first.exe")
            second_entry = os.path.join(temp_dir, "external", "second.exe")
            os.makedirs(os.path.dirname(first_entry), exist_ok=True)
            for entry in (first_entry, second_entry):
                with open(entry, "wb") as handle:
                    handle.write(b"opencode")
            component = ReleaseComponent("opencode", "opencode", "1.0.0", "windows", "x64", "tgz", 1, "a" * 64, ("https://download.example.invalid/opencode.tgz",), "agents/opencode", None)
            candidates_called = 0

            def candidates(_component: ReleaseComponent) -> list[str]:
                nonlocal candidates_called
                candidates_called += 1
                return [first_entry if candidates_called == 1 else second_entry]

            installer = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")))
            installer._external_entry_candidates = candidates  # type: ignore[method-assign]
            self.assertEqual(installer._first_existing_external_entry(component), first_entry)
            os.remove(first_entry)
            self.assertEqual(installer._first_existing_external_entry(component), second_entry)
            self.assertEqual(candidates_called, 2)

    def test_external_discovery_cache_explicit_refresh_bypasses_cached_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "external", "opencode.exe")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "wb") as handle:
                handle.write(b"opencode")
            component = ReleaseComponent("opencode", "opencode", "1.0.0", "windows", "x64", "tgz", 1, "a" * 64, ("https://download.example.invalid/opencode.tgz",), "agents/opencode", None)
            candidates_called = 0

            def candidates(_component: ReleaseComponent) -> list[str]:
                nonlocal candidates_called
                candidates_called += 1
                return [entry]

            installer = ComponentInstaller(base_path=temp_dir, state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")))
            installer._external_entry_candidates = candidates  # type: ignore[method-assign]
            self.assertEqual(installer._first_existing_external_entry(component), entry)
            self.assertEqual(installer._first_existing_external_entry(component, refresh=True), entry)
            self.assertEqual(candidates_called, 2)

    def test_external_discovery_cache_isolates_base_path_and_component_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_one = os.path.join(temp_dir, "one")
            base_two = os.path.join(temp_dir, "two")
            entry_one = os.path.join(temp_dir, "external", "one.exe")
            entry_two = os.path.join(temp_dir, "external", "two.exe")
            os.makedirs(os.path.dirname(entry_one), exist_ok=True)
            for entry in (entry_one, entry_two):
                with open(entry, "wb") as handle:
                    handle.write(b"opencode")
            component_one = ReleaseComponent("opencode", "opencode", "1.0.0", "windows", "x64", "tgz", 1, "a" * 64, ("https://download.example.invalid/opencode.tgz",), "agents/opencode", None, external_paths=(entry_one,))
            changed_component = ReleaseComponent("opencode", "opencode", "1.0.0", "windows", "x64", "tgz", 1, "a" * 64, ("https://download.example.invalid/opencode.tgz",), "agents/opencode", None, external_paths=(entry_two,))
            other_component = ReleaseComponent("claude-code", "Claude", "1.0.0", "windows", "x64", "tgz", 1, "b" * 64, ("https://download.example.invalid/claude.tgz",), "agents/claude-code", None, external_paths=(entry_two,))
            getattr(component_installer_module, "_EXTERNAL_ENTRY_CACHE", {}).clear()
            installer_one = ComponentInstaller(base_path=base_one, state_store=ComponentStateStore(os.path.join(temp_dir, "one.json")))
            installer_two = ComponentInstaller(base_path=base_two, state_store=ComponentStateStore(os.path.join(temp_dir, "two.json")))
            installer_one._external_entry_candidates = lambda component: [component.external_paths[0]]  # type: ignore[method-assign]
            installer_two._external_entry_candidates = lambda component: [component.external_paths[0]]  # type: ignore[method-assign]

            self.assertEqual(installer_one._first_existing_external_entry(component_one), entry_one)
            self.assertEqual(installer_one._first_existing_external_entry(changed_component), entry_two)
            self.assertEqual(installer_one._first_existing_external_entry(other_component), entry_two)
            self.assertEqual(installer_two._first_existing_external_entry(component_one), entry_one)

    def test_install_refreshes_negative_external_discovery_cache_after_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            external_entry = os.path.join(temp_dir, "external", "opencode.cmd")
            payload = make_tgz_payload({"package/bin/opencode.exe": b"opencode"})
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="1.0.0",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
                entry="package/bin/opencode.exe",
                external_paths=(external_entry,),
                install_command=("npm", "install", "-g", "opencode-ai@1.0.0"),
            )
            installer = ComponentInstaller(
                base_path=temp_dir,
                state_store=ComponentStateStore(os.path.join(temp_dir, "state.json")),
                fetcher=lambda _url, _timeout: payload,
                retry_sleep=lambda _seconds: None,
            )
            installer._external_entry_candidates = lambda _component: [external_entry]  # type: ignore[method-assign]

            self.assertIsNone(installer._first_existing_external_entry(component))

            def runner(command: list[str], _cwd: str, _timeout_ms: int) -> FakeCompletedProcess:
                if "install" in command:
                    os.makedirs(os.path.dirname(external_entry), exist_ok=True)
                    with open(external_entry, "wb") as handle:
                        handle.write(b"opencode")
                return FakeCompletedProcess(returncode=0)

            installer.installer_runner = runner
            state = installer.install(component, job_id="job_refresh_external")

            self.assertEqual(state.status, "ready")

    def test_detect_prefers_codex_desktop_appx_over_cli_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            appx_root = os.path.join(
                temp_dir,
                "WindowsApps",
                "OpenAI.Codex_26.623.9142.0_x64__2p2nqsd0c76g0",
            )
            desktop_entry = os.path.join(appx_root, "app", "Codex.exe")
            os.makedirs(os.path.dirname(desktop_entry), exist_ok=True)
            with open(desktop_entry, "wb") as handle:
                handle.write(b"desktop codex")

            appdata = os.path.join(temp_dir, "AppData", "Roaming")
            cli_shim = os.path.join(appdata, "npm", "codex.cmd")
            os.makedirs(os.path.dirname(cli_shim), exist_ok=True)
            with open(cli_shim, "wb") as handle:
                handle.write(b"cli shim")

            component = ReleaseComponent(
                component_id="codex-desktop",
                name="Codex 桌面端",
                version="0.142.3-win32-x64",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="c" * 64,
                urls=("https://download.example.invalid/codex.tgz",),
                install_path="agents/codex-desktop",
                entry=None,
                external_paths=("%APPDATA%/npm/codex.cmd",),
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
                        returncode=0,
                        stdout=f"{appx_root}\n" if command[:3] == ["powershell", "-NoProfile", "-Command"] else "",
                    ),
                )

                state = installer.detect(component, job_id="job_detect_codex_desktop")
            finally:
                if old_appdata is None:
                    os.environ.pop("APPDATA", None)
                else:
                    os.environ["APPDATA"] = old_appdata

            self.assertEqual(state.status, "ready")
            self.assertEqual(state.version, "26.623.9142.0")

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

    def test_detect_rejects_hermes_runtime_with_python_merge_conflict_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = os.path.join(temp_dir, "hermes", "hermes-agent")
            external_entry = os.path.join(runtime_root, "venv", "Scripts", "hermes.EXE")
            os.makedirs(os.path.dirname(external_entry), exist_ok=True)
            with open(external_entry, "wb") as handle:
                handle.write(b"hermes shim")
            with open(os.path.join(runtime_root, "utils.py"), "w", encoding="utf-8") as handle:
                handle.write("<<<<<<< Updated upstream\n")
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

            with self.assertRaisesRegex(ComponentInstallError, "Hermes 运行时包损坏"):
                installer.detect(component, job_id="job_detect_hermes_bad")

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
            external_entry = os.path.join(temp_dir, "npm-global", "opencode.CMD")
            os.makedirs(os.path.dirname(external_entry), exist_ok=True)
            with open(external_entry, "wb") as handle:
                handle.write(b"opencode shim")
            component = ReleaseComponent(
                component_id="opencode",
                name="opencode",
                version="0.142.3",
                platform="windows",
                arch="x64",
                archive_type="tgz",
                size=1024,
                sha256="d" * 64,
                urls=("https://download.example.invalid/opencode.tgz",),
                install_path="agents/opencode",
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

    def test_visible_launcher_keeps_windows_agent_terminal_open(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "agents", "codex", "codex.cmd")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")

            build_command = getattr(component_installer_module, "build_visible_launcher_command", lambda *_args, **_kwargs: [])
            command = build_command(entry, os.path.dirname(entry), base_path=temp_dir, force_windows=True)

            self.assertEqual(command[:2], ["cmd.exe", "/k"])
            self.assertIn("title LOOM Agent - codex.cmd", command[2])
            self.assertIn("codex.cmd", command[2])

    def test_codex_desktop_launcher_opens_app_without_cli_terminal(self) -> None:
        entry = (
            r"C:\Program Files\WindowsApps\OpenAI.Codex_26.623.9142.0_x64__2p2nqsd0c76g0"
            r"\app\Codex.exe"
        )
        build_command = getattr(component_installer_module, "build_visible_launcher_command", lambda *_args, **_kwargs: [])

        command = build_command(entry, os.path.dirname(entry), component_id="codex-desktop", force_windows=True)

        self.assertEqual(command, ["explorer.exe", r"shell:AppsFolder\OpenAI.Codex_2p2nqsd0c76g0!App"])

    def test_default_windows_launcher_preserves_interactive_streams(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "agents", "codex", "codex.cmd")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")

            class FakeProcess:
                pid = 1234

            with (
                mock.patch.object(component_installer_module.os, "name", "nt"),
                mock.patch.object(component_installer_module.subprocess, "Popen", return_value=FakeProcess()) as popen,
            ):
                result = component_installer_module._default_launcher(
                    entry,
                    os.path.dirname(entry),
                    base_path=temp_dir,
                    component_id="codex-desktop",
                )

            _, kwargs = popen.call_args
            self.assertIsNone(kwargs["stdin"])
            self.assertIsNone(kwargs["stdout"])
            self.assertIsNone(kwargs["stderr"])
            self.assertTrue(result["visible"])

    def test_opencode_launcher_uses_private_config_and_pure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "agents", "opencode", "opencode.cmd")
            config_dir = os.path.join(temp_dir, "data", ".opencode")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            os.makedirs(config_dir, exist_ok=True)
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")
            with open(os.path.join(config_dir, "opencode.json"), "w", encoding="utf-8") as handle:
                handle.write('{"model":"loom/qwen3.7-plus","provider":{"loom":{"options":{"apiKey":"{env:LOOM_OPENCODE_API_KEY}"}}}}')

            build_command = getattr(component_installer_module, "build_agent_launcher_command", lambda *_args, **_kwargs: [])
            build_env = getattr(component_installer_module, "build_agent_launcher_environment", lambda *_args, **_kwargs: {})
            command = build_command("opencode", entry, os.path.dirname(entry), base_path=temp_dir)
            env = build_env(temp_dir, "opencode")

            self.assertEqual(command[:3], ["cmd", "/c", entry])
            self.assertEqual(command[-3:], ["--pure", "-m", "loom/qwen3.7-plus"])
            self.assertEqual(env["OPENCODE_CONFIG_DIR"], config_dir)
            self.assertEqual(env["OPENCODE_CONFIG"], os.path.join(config_dir, "opencode.json"))

    def test_opencode_launcher_rejects_stale_phone_model_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "agents", "opencode", "opencode.cmd")
            config_dir = os.path.join(temp_dir, "data", ".opencode")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            os.makedirs(config_dir, exist_ok=True)
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")
            with open(os.path.join(config_dir, "opencode.json"), "w", encoding="utf-8") as handle:
                handle.write('{"model":"loom/agnes-2.0-flash","provider":{"loom":{"options":{"apiKey":"{env:LOOM_OPENCODE_API_KEY}"}}}}')

            build_command = getattr(component_installer_module, "build_agent_launcher_command", lambda *_args, **_kwargs: [])

            with self.assertRaises(ComponentInstallError):
                build_command("opencode", entry, os.path.dirname(entry), base_path=temp_dir)

    def test_opencode_launcher_fails_without_private_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "agents", "opencode", "opencode.cmd")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")

            build_command = getattr(component_installer_module, "build_agent_launcher_command", lambda *_args, **_kwargs: [])

            with self.assertRaises(ComponentInstallError):
                build_command("opencode", entry, os.path.dirname(entry), base_path=temp_dir)

    def test_claude_code_launcher_injects_gateway_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret = "sk-claude-test-token"
            WireService(AppPaths(temp_dir)).sync_custom_provider(
                provider="LOOM",
                base_url="https://api.heang.top/v1",
                api_key=secret,
                text_model="qwen3.7-plus",
            )

            build_env = getattr(component_installer_module, "build_agent_launcher_environment", lambda *_args, **_kwargs: {})
            env = build_env(temp_dir, "claude-code")

            self.assertEqual(env["LOOM_CLAUDE_API_KEY"], secret)
            self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], secret)
            self.assertEqual(env["ANTHROPIC_API_KEY"], secret)
            self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.heang.top")
            self.assertEqual(env["ANTHROPIC_MODEL"], "qwen3.7-plus")

    def test_agent_launcher_environment_does_not_inject_phone_model_as_desktop_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = AppPaths(temp_dir)
            os.makedirs(os.path.dirname(paths.wire_current), exist_ok=True)
            with open(paths.wire_current, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "baseUrl": "https://api.heang.top/v1",
                        "apiKey": "sk-stale-phone-model",
                        "models": {"text": "agnes-2.0-flash", "phone": "agnes-2.0-flash"},
                    },
                    handle,
                )

            build_env = getattr(component_installer_module, "build_agent_launcher_environment", lambda *_args, **_kwargs: {})
            codex_env = build_env(temp_dir, "codex-desktop")
            claude_env = build_env(temp_dir, "claude-code")

            self.assertEqual(codex_env["OPENAI_API_KEY"], "sk-stale-phone-model")
            self.assertEqual(codex_env["OPENAI_BASE_URL"], "https://api.heang.top/v1")
            self.assertNotIn("OPENAI_MODEL", codex_env)
            self.assertEqual(claude_env["ANTHROPIC_API_KEY"], "sk-stale-phone-model")
            self.assertEqual(claude_env["ANTHROPIC_BASE_URL"], "https://api.heang.top")
            self.assertNotIn("ANTHROPIC_MODEL", claude_env)

    def test_agent_launcher_environment_scrubs_stale_model_env_before_injecting_loom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret = "sk-current-loom-token"
            WireService(AppPaths(temp_dir)).sync_custom_provider(
                provider="LOOM",
                base_url="https://api.heang.top/v1",
                api_key=secret,
                text_model="qwen3.7-plus",
            )
            stale_env = {
                "OPENAI_API_KEY": "sk-old-openai",
                "OPENAI_BASE_URL": "https://old-openai.example/v1",
                "OPENAI_API_BASE": "https://old-openai-base.example/v1",
                "OPENAI_MODEL": "old-openai-model",
                "ANTHROPIC_API_KEY": "sk-old-anthropic",
                "ANTHROPIC_AUTH_TOKEN": "sk-old-anthropic-token",
                "ANTHROPIC_BASE_URL": "https://old-anthropic.example",
                "ANTHROPIC_MODEL": "old-claude-model",
                "LOOM_CODEX_API_KEY": "sk-old-loom-codex",
                "LOOM_CLAUDE_API_KEY": "sk-old-loom-claude",
                "LOOM_OPENCODE_API_KEY": "sk-old-loom-opencode",
            }

            build_env = getattr(component_installer_module, "build_agent_launcher_environment", lambda *_args, **_kwargs: {})
            with mock.patch.dict(component_installer_module.os.environ, stale_env, clear=False):
                codex_env = build_env(temp_dir, "codex-desktop")
                claude_env = build_env(temp_dir, "claude-code")
                opencode_env = build_env(temp_dir, "opencode")

            self.assertEqual(codex_env["LOOM_CODEX_API_KEY"], secret)
            self.assertEqual(codex_env["OPENAI_API_KEY"], secret)
            self.assertEqual(codex_env["OPENAI_BASE_URL"], "https://api.heang.top/v1")
            self.assertEqual(codex_env["OPENAI_API_BASE"], "https://api.heang.top/v1")
            self.assertEqual(codex_env["OPENAI_MODEL"], "qwen3.7-plus")
            self.assertNotIn("ANTHROPIC_API_KEY", codex_env)
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", codex_env)
            self.assertNotIn("ANTHROPIC_BASE_URL", codex_env)
            self.assertNotIn("ANTHROPIC_MODEL", codex_env)
            self.assertNotIn("LOOM_CLAUDE_API_KEY", codex_env)
            self.assertNotIn("LOOM_OPENCODE_API_KEY", codex_env)

            self.assertEqual(claude_env["LOOM_CLAUDE_API_KEY"], secret)
            self.assertEqual(claude_env["ANTHROPIC_AUTH_TOKEN"], secret)
            self.assertEqual(claude_env["ANTHROPIC_API_KEY"], secret)
            self.assertEqual(claude_env["ANTHROPIC_BASE_URL"], "https://api.heang.top")
            self.assertEqual(claude_env["ANTHROPIC_MODEL"], "qwen3.7-plus")
            self.assertNotIn("OPENAI_API_KEY", claude_env)
            self.assertNotIn("OPENAI_BASE_URL", claude_env)
            self.assertNotIn("OPENAI_API_BASE", claude_env)
            self.assertNotIn("OPENAI_MODEL", claude_env)
            self.assertNotIn("LOOM_CODEX_API_KEY", claude_env)
            self.assertNotIn("LOOM_OPENCODE_API_KEY", claude_env)

            self.assertEqual(opencode_env["LOOM_OPENCODE_API_KEY"], secret)
            self.assertNotIn("OPENAI_API_KEY", opencode_env)
            self.assertNotIn("OPENAI_BASE_URL", opencode_env)
            self.assertNotIn("OPENAI_API_BASE", opencode_env)
            self.assertNotIn("OPENAI_MODEL", opencode_env)
            self.assertNotIn("ANTHROPIC_API_KEY", opencode_env)
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", opencode_env)
            self.assertNotIn("ANTHROPIC_BASE_URL", opencode_env)
            self.assertNotIn("ANTHROPIC_MODEL", opencode_env)
            self.assertNotIn("LOOM_CODEX_API_KEY", opencode_env)
            self.assertNotIn("LOOM_CLAUDE_API_KEY", opencode_env)

    def test_openclaw_launcher_uses_loom_state_and_local_chat(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = os.path.join(temp_dir, "agents", "openclaw", "openclaw.cmd")
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\n")

            build_command = getattr(component_installer_module, "build_agent_launcher_command", lambda *_args, **_kwargs: [])
            build_env = getattr(component_installer_module, "build_agent_launcher_environment", lambda *_args, **_kwargs: {})
            command = build_command("openclaw-companion", entry, os.path.dirname(entry), base_path=temp_dir)
            env = build_env(temp_dir, "openclaw-companion")

            self.assertEqual(command[:3], ["cmd", "/c", entry])
            self.assertEqual(command[-2:], ["chat", "--local"])
            self.assertEqual(env["OPENCLAW_HOME"], os.path.join(temp_dir, "data"))
            self.assertEqual(env["OPENCLAW_STATE_DIR"], os.path.join(temp_dir, "data", ".openclaw"))
            self.assertEqual(env["OPENCLAW_CONFIG_PATH"], os.path.join(temp_dir, "data", ".openclaw", "openclaw.json"))

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
