from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import unittest

from core.paths import AppPaths
from services.app_updater import LoomAppUpdater


class _Response:
    def __init__(self, payload: bytes, *, url: str = "https://example.invalid/value") -> None:
        self._stream = io.BytesIO(payload)
        self.url = url

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class LoomAppUpdaterTests(unittest.TestCase):
    def test_latest_release_chooses_highest_valid_version_across_sources(self) -> None:
        def release(version: str) -> dict:
            payload = f"installer-{version}".encode("ascii")
            digest = hashlib.sha256(payload).hexdigest()
            return {
                "assets": [
                    {
                        "name": f"LOOM-{version}-setup.exe",
                        "size": len(payload),
                        "digest": f"sha256:{digest}",
                        "browser_download_url": f"https://downloads.example/LOOM-{version}-setup.exe",
                    }
                ]
            }

        releases = {
            "https://gitee.example/releases/latest": release("2.1.45"),
            "https://github.example/releases/latest": release("2.1.58"),
        }

        def opener(request, timeout=0):
            del timeout
            url = request.full_url if hasattr(request, "full_url") else str(request)
            return _Response(json.dumps(releases[url]).encode("utf-8"), url=url)

        with tempfile.TemporaryDirectory() as temp_dir:
            updater = LoomAppUpdater(
                AppPaths(temp_dir),
                current_version="2.1.57",
                release_api_urls=tuple(releases),
                opener=opener,
            )
            latest, error = updater.latest_version()

        self.assertIsNone(error)
        self.assertEqual(latest, "2.1.58")
        self.assertEqual(updater.cached_release.version, "2.1.58")
        self.assertEqual(updater.cached_release.source, "github.example")

    def test_latest_release_prefers_complete_setup_with_verified_digest(self) -> None:
        installer = b"complete-installer"
        digest = hashlib.sha256(installer).hexdigest()
        release = {
            "tag_name": "v2.1.58",
            "assets": [
                {
                    "name": "LOOM-2.1.58-setup.exe",
                    "size": len(installer),
                    "digest": f"sha256:{digest}",
                    "browser_download_url": "https://downloads.example/LOOM-2.1.58-setup.exe",
                },
                {
                    "name": "LOOM-2.1.58-online-setup.exe",
                    "size": 3,
                    "digest": "sha256:" + ("0" * 64),
                    "browser_download_url": "https://downloads.example/online.exe",
                },
            ],
        }

        def opener(request, timeout=0):
            del timeout
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if url.endswith("/releases/latest"):
                return _Response(json.dumps(release).encode("utf-8"), url=url)
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as temp_dir:
            updater = LoomAppUpdater(
                AppPaths(temp_dir),
                current_version="2.1.57",
                release_api_urls=("https://api.example/releases/latest",),
                opener=opener,
            )

            latest, error = updater.latest_version()

        self.assertIsNone(error)
        self.assertEqual(latest, "2.1.58")
        self.assertEqual(updater.cached_release.sha256, digest)
        self.assertTrue(updater.cached_release.url.endswith("LOOM-2.1.58-setup.exe"))

    def test_gitee_release_can_use_sidecar_sha_when_size_and_digest_are_omitted(self) -> None:
        digest = hashlib.sha256(b"gitee-installer").hexdigest()
        release = {
            "tag_name": "v2.1.58",
            "assets": [
                {
                    "name": "LOOM-2.1.58-setup.exe",
                    "browser_download_url": "https://gitee.example/LOOM-2.1.58-setup.exe",
                },
                {
                    "name": "LOOM-2.1.58-setup.exe.sha256.txt",
                    "browser_download_url": "https://gitee.example/LOOM-2.1.58-setup.exe.sha256.txt",
                },
            ],
        }

        def opener(request, timeout=0):
            del timeout
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if url.endswith("/releases/latest"):
                return _Response(json.dumps(release).encode("utf-8"), url=url)
            if url.endswith(".sha256.txt"):
                return _Response(f"{digest} *LOOM-2.1.58-setup.exe".encode("ascii"), url=url)
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as temp_dir:
            updater = LoomAppUpdater(
                AppPaths(temp_dir),
                current_version="2.1.57",
                release_api_urls=("https://gitee.example/releases/latest",),
                opener=opener,
            )
            latest, error = updater.latest_version()

        self.assertIsNone(error)
        self.assertEqual(latest, "2.1.58")
        self.assertEqual(updater.cached_release.size, 0)
        self.assertEqual(updater.cached_release.sha256, digest)

    def test_install_latest_verifies_sha256_before_launching(self) -> None:
        installer = b"verified-installer-bytes"
        digest = hashlib.sha256(installer).hexdigest()
        release = {
            "tag_name": "v2.1.58",
            "assets": [
                {
                    "name": "LOOM-2.1.58-setup.exe",
                    "size": len(installer),
                    "digest": f"sha256:{digest}",
                    "browser_download_url": "https://downloads.example/LOOM-2.1.58-setup.exe",
                }
            ],
        }
        launched: list[str] = []

        def opener(request, timeout=0):
            del timeout
            url = request.full_url if hasattr(request, "full_url") else str(request)
            if url.endswith("/releases/latest"):
                return _Response(json.dumps(release).encode("utf-8"), url=url)
            if url.endswith("LOOM-2.1.58-setup.exe"):
                return _Response(installer, url=url)
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as temp_dir:
            updater = LoomAppUpdater(
                AppPaths(temp_dir),
                current_version="2.1.57",
                release_api_urls=("https://api.example/releases/latest",),
                opener=opener,
                launcher=lambda path: launched.append(path),
            )

            success, version, output = updater.install_latest()

            self.assertTrue(success)
            self.assertEqual(version, "2.1.58")
            self.assertEqual(len(launched), 1)
            with open(launched[0], "rb") as handle:
                self.assertEqual(handle.read(), installer)
            self.assertTrue(any("SHA256" in line for line in output))

    def test_install_latest_refuses_a_digest_mismatch(self) -> None:
        installer = b"tampered"
        release = {
            "tag_name": "v2.1.58",
            "assets": [
                {
                    "name": "LOOM-2.1.58-setup.exe",
                    "size": len(installer),
                    "digest": "sha256:" + ("a" * 64),
                    "browser_download_url": "https://downloads.example/LOOM-2.1.58-setup.exe",
                }
            ],
        }
        launched: list[str] = []

        def opener(request, timeout=0):
            del timeout
            url = request.full_url if hasattr(request, "full_url") else str(request)
            payload = json.dumps(release).encode("utf-8") if url.endswith("/releases/latest") else installer
            return _Response(payload, url=url)

        with tempfile.TemporaryDirectory() as temp_dir:
            updater = LoomAppUpdater(
                AppPaths(temp_dir),
                current_version="2.1.57",
                release_api_urls=("https://api.example/releases/latest",),
                opener=opener,
                launcher=lambda path: launched.append(path),
            )
            success, _version, output = updater.install_latest()

        self.assertFalse(success)
        self.assertFalse(launched)
        self.assertTrue(any("SHA256" in line for line in output))


if __name__ == "__main__":
    unittest.main()
