"""Verified LOOM desktop application update support."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from core.paths import AppPaths


DEFAULT_RELEASE_API_URLS = (
    "https://gitee.com/api/v5/repos/rfdiosuao/lumi/releases/latest",
    "https://api.github.com/repos/rfdiosuao/lumi/releases/latest",
)
SETUP_NAME_RE = re.compile(r"^LOOM-(?P<version>\d+\.\d+\.\d+)-setup\.exe$", re.IGNORECASE)
SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")


@dataclass(frozen=True)
class LoomRelease:
    version: str
    filename: str
    url: str
    size: int
    sha256: str
    source: str


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)\.(\d+)\s*", str(value or ""))
    if not match:
        return (0, 0, 0)
    return tuple(int(item) for item in match.groups())


def _safe_https_url(value: Any) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("更新地址必须使用 HTTPS")
    if parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        raise ValueError("更新地址不能指向本机")
    return text


class LoomAppUpdater:
    def __init__(
        self,
        paths: AppPaths,
        *,
        current_version: str = "",
        release_api_urls: Iterable[str] = DEFAULT_RELEASE_API_URLS,
        opener: Callable[..., Any] = urllib.request.urlopen,
        launcher: Callable[[str], None] | None = None,
    ) -> None:
        self.paths = paths
        self._current_version = str(current_version or os.environ.get("LOOM_APP_VERSION") or "0.0.0").strip()
        self.release_api_urls = tuple(str(url).strip() for url in release_api_urls if str(url).strip())
        self.opener = opener
        self.launcher = launcher or self._launch_installer
        self.cached_release: LoomRelease | None = None

    def current_version(self) -> str:
        return self._current_version

    def latest_version(self) -> tuple[str | None, str | None]:
        errors: list[str] = []
        releases: list[LoomRelease] = []
        for source_url in self.release_api_urls:
            try:
                releases.append(self._fetch_release(source_url))
            except Exception as error:
                errors.append(f"{urlparse(source_url).hostname or 'release'}: {error}")
        if not releases:
            return None, "；".join(errors) or "没有可用的 LOOM 更新源"

        release = max(releases, key=lambda item: _version_tuple(item.version))
        self.cached_release = release
        if _version_tuple(release.version) <= _version_tuple(self.current_version()):
            return self.current_version(), None
        return release.version, None

    def install_latest(self) -> tuple[bool, str, list[str]]:
        latest, error = self.latest_version()
        if error or not latest or not self.cached_release:
            return False, self.current_version(), [error or "没有可用的 LOOM 更新"]
        release = self.cached_release
        if _version_tuple(release.version) <= _version_tuple(self.current_version()):
            return True, self.current_version(), ["当前已是最新版本"]

        updates_dir = os.path.join(self.paths.data_dir, "updates")
        os.makedirs(updates_dir, exist_ok=True)
        final_path = os.path.join(updates_dir, release.filename)
        partial_path = final_path + ".part"
        try:
            digest = hashlib.sha256()
            written = 0
            request = urllib.request.Request(release.url, headers={"User-Agent": "LOOM-Updater/1"})
            with self.opener(request, timeout=120) as response, open(partial_path, "wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
            if release.size > 0 and written != release.size:
                raise ValueError(f"安装包大小不一致：应为 {release.size}，实际 {written}")
            actual_sha = digest.hexdigest().lower()
            if actual_sha != release.sha256:
                raise ValueError(f"SHA256 校验失败：应为 {release.sha256}，实际 {actual_sha}")
            os.replace(partial_path, final_path)
            self.launcher(final_path)
            return True, release.version, [
                f"已验证 SHA256：{actual_sha}",
                f"已启动 LOOM {release.version} 安装器，请按安装器提示完成覆盖安装。",
            ]
        except Exception as error:
            try:
                if os.path.exists(partial_path):
                    os.remove(partial_path)
            except OSError:
                pass
            return False, self.current_version(), [str(error)]

    def _fetch_release(self, source_url: str) -> LoomRelease:
        source_url = _safe_https_url(source_url)
        request = urllib.request.Request(
            source_url,
            headers={"Accept": "application/json", "User-Agent": "LOOM-Updater/1"},
        )
        with self.opener(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or bool(payload.get("draft")) or bool(payload.get("prerelease")):
            raise ValueError("更新源没有正式发布版本")
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise ValueError("更新源缺少附件列表")

        setup: dict[str, Any] | None = None
        version = ""
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or asset.get("filename") or "").strip()
            match = SETUP_NAME_RE.fullmatch(name)
            if match:
                setup = asset
                version = match.group("version")
                break
        if setup is None:
            raise ValueError("正式发布中没有唯一推荐的 LOOM 完整安装包")

        filename = str(setup.get("name") or setup.get("filename") or "").strip()
        url = _safe_https_url(setup.get("browser_download_url") or setup.get("download_url"))
        size = int(setup.get("size") or 0)
        if size < 0:
            raise ValueError("安装包大小无效")
        digest = str(setup.get("digest") or "").strip().lower()
        sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
        if not SHA256_RE.fullmatch(sha256):
            sha256 = self._fetch_sidecar_sha(assets, filename)
        if not SHA256_RE.fullmatch(sha256):
            raise ValueError("正式发布缺少可验证的 SHA256")
        return LoomRelease(
            version=version,
            filename=filename,
            url=url,
            size=size,
            sha256=sha256.lower(),
            source=urlparse(source_url).hostname or source_url,
        )

    def _fetch_sidecar_sha(self, assets: list[Any], filename: str) -> str:
        expected_name = filename + ".sha256.txt"
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or asset.get("filename") or "").strip()
            if name.lower() != expected_name.lower():
                continue
            url = _safe_https_url(asset.get("browser_download_url") or asset.get("download_url"))
            request = urllib.request.Request(url, headers={"User-Agent": "LOOM-Updater/1"})
            with self.opener(request, timeout=15) as response:
                text = response.read(4096).decode("ascii", errors="replace")
            match = SHA256_RE.search(text)
            return match.group(1).lower() if match else ""
        return ""

    @staticmethod
    def _launch_installer(path: str) -> None:
        subprocess.Popen([path], cwd=os.path.dirname(path))
