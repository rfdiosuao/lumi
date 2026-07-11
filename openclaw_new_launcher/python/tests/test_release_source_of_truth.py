from __future__ import annotations

import json
import os
import re
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER_ROOT = os.path.dirname(PYTHON_DIR)
GIT_ROOT = os.path.dirname(LAUNCHER_ROOT)
CI_WORKFLOW = os.path.join(GIT_ROOT, ".github", "workflows", "ci.yml")
RELEASE_WORKFLOW = os.path.join(GIT_ROOT, ".github", "workflows", "release.yml")
CI_SCRIPT = os.path.join(GIT_ROOT, "scripts", "ci-check.ps1")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class ReleaseSourceOfTruthTests(unittest.TestCase):
    def test_current_ci_and_release_only_build_new_launcher(self) -> None:
        for path in (CI_WORKFLOW, RELEASE_WORKFLOW):
            source = read_text(path)
            self.assertNotIn("openclaw_ui_integration", source, path)
            self.assertIn("openclaw_new_launcher", source, path)

        release = read_text(RELEASE_WORKFLOW)
        self.assertIn(r"scripts\build-portable.ps1", release)
        self.assertIn("openclaw_new_launcher/src-tauri/target/release/bundle", release.replace("\\", "/"))
        self.assertIn('Join-Path $_.FullName "LOOM.exe"', release)
        self.assertIn('Join-Path $_.FullName "LOOMFiles"', release)

    def test_windows_release_builds_and_publishes_only_the_complete_setup(self) -> None:
        release = read_text(RELEASE_WORKFLOW)

        self.assertIn(r"scripts\build-dual-nsis.ps1", release)
        self.assertIn("CodexPackagePath", release)
        self.assertIn('LOOM-$version-setup.exe', release)
        self.assertIn(r"verify-release-secrets.ps1 -Source", release)
        self.assertNotIn("Get-ChildItem -LiteralPath $bundleDir -Recurse -File", release)

    def test_release_smoke_preserves_ascii_and_chinese_path_array(self) -> None:
        release = read_text(RELEASE_WORKFLOW)

        self.assertIn(r"& .\scripts\smoke-test-tauri-nsis.ps1", release)
        self.assertIn("-InstallPaths $paths", release)
        self.assertIn("$chineseUser", release)
        self.assertIn("$luming", release)
        self.assertNotIn(r"powershell -NoProfile -ExecutionPolicy Bypass -File scripts\smoke-test-tauri-nsis.ps1", release)

    def test_windows_bundle_uses_offline_webview2_installer(self) -> None:
        with open(os.path.join(LAUNCHER_ROOT, "src-tauri", "tauri.conf.json"), "r", encoding="utf-8") as handle:
            tauri = json.load(handle)

        self.assertEqual(
            tauri["bundle"]["windows"]["webviewInstallMode"]["type"],
            "offlineInstaller",
        )

    def test_ci_script_runs_complete_launcher_python_tests(self) -> None:
        source = read_text(CI_SCRIPT)
        self.assertIn("Python launcher unit tests", source)
        self.assertIn("-m unittest discover", source)
        self.assertIn('python\\tests', source)
        self.assertIn('test_*.py', source)

    def test_all_authoritative_version_files_are_2_1_61(self) -> None:
        with open(os.path.join(LAUNCHER_ROOT, "package.json"), "r", encoding="utf-8") as handle:
            package = json.load(handle)
        with open(os.path.join(LAUNCHER_ROOT, "package-lock.json"), "r", encoding="utf-8") as handle:
            package_lock = json.load(handle)
        with open(os.path.join(LAUNCHER_ROOT, "src-tauri", "tauri.conf.json"), "r", encoding="utf-8") as handle:
            tauri = json.load(handle)
        cargo_toml = read_text(os.path.join(LAUNCHER_ROOT, "src-tauri", "Cargo.toml"))
        cargo_lock = read_text(os.path.join(LAUNCHER_ROOT, "src-tauri", "Cargo.lock"))

        self.assertEqual(package["version"], "2.1.61")
        self.assertEqual(package_lock["version"], "2.1.61")
        self.assertEqual(package_lock["packages"][""]["version"], "2.1.61")
        self.assertEqual(tauri["version"], "2.1.61")
        self.assertRegex(cargo_toml, r'(?ms)^\[package\].*?^version\s*=\s*"2\.1\.61"')
        self.assertRegex(cargo_lock, r'(?s)\[\[package\]\]\s*name\s*=\s*"app"\s*version\s*=\s*"2\.1\.61"')


if __name__ == "__main__":
    unittest.main()
