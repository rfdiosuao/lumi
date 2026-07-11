from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HANDOFF = os.path.join(ROOT, "src-tauri", "installer", "update-handoff.ps1")


@unittest.skipUnless(os.name == "nt", "Windows update handoff smoke")
class UpdateHandoffSmokeTests(unittest.TestCase):
    def _run_handoff(self, *, fail: bool) -> tuple[str, str, str]:
        temp_dir = tempfile.mkdtemp(prefix="loom-update-中文-")
        self.addCleanup(shutil.rmtree, temp_dir, True)
        install_root = os.path.join(temp_dir, "旧版本 LOOM")
        recovery_root = os.path.join(temp_dir, "外部恢复")
        marker_path = os.path.join(temp_dir, "state", "update-pending.json")
        os.makedirs(os.path.join(install_root, "data", "nested"), exist_ok=True)
        os.makedirs(os.path.dirname(marker_path), exist_ok=True)
        with open(os.path.join(install_root, "data", "nested", "lead.json"), "w", encoding="utf-8") as handle:
            handle.write('{"lead":"preserve-me"}')
        app_exe = os.path.join(install_root, "LOOM.exe")
        with open(app_exe, "wb") as handle:
            handle.write(b"old")

        installer = os.path.join(temp_dir, "fake setup.cmd")
        exit_code = 7 if fail else 0
        script = "\r\n".join(
            [
                "@echo off",
                'set "target=%~2"',
                'set "target=%target:~3%"',
                'rmdir /s /q "%target%\\data" 2>nul',
                'mkdir "%target%" 2>nul',
                'echo new>"%target%\\installed-version.txt"',
                f"exit /b {exit_code}",
            ]
        )
        with open(installer, "w", encoding="ascii", newline="") as handle:
            handle.write(script)

        command = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            HANDOFF,
            "-Installer",
            installer,
            "-InstallRoot",
            install_root,
            "-AppExe",
            app_exe,
            "-RecoveryRoot",
            recovery_root,
            "-MarkerPath",
            marker_path,
            "-ParentPid",
            "2147483647",
            "-Version",
            "2.1.62",
            "-TestMode",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
        expected = 1 if fail else 0
        self.assertEqual(completed.returncode, expected, completed.stderr or completed.stdout)
        preserved = os.path.join(install_root, "data", "nested", "lead.json")
        with open(preserved, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '{"lead":"preserve-me"}')
        return marker_path, recovery_root, install_root

    def test_successful_update_restores_data_and_clears_pending_marker(self) -> None:
        marker_path, recovery_root, install_root = self._run_handoff(fail=False)

        self.assertFalse(os.path.exists(marker_path))
        self.assertTrue(os.path.isfile(os.path.join(recovery_root, "data", "nested", "lead.json")))
        self.assertTrue(os.path.isfile(os.path.join(install_root, "installed-version.txt")))

    def test_failed_update_restores_data_and_leaves_recovery_manifest(self) -> None:
        marker_path, recovery_root, _install_root = self._run_handoff(fail=True)

        self.assertTrue(os.path.isfile(marker_path))
        with open(marker_path, "r", encoding="utf-8-sig") as handle:
            marker = json.load(handle)
        self.assertEqual(marker["state"], "failed")
        self.assertEqual(marker["version"], "2.1.62")
        self.assertTrue(os.path.isfile(os.path.join(recovery_root, "update-handoff.log")))


if __name__ == "__main__":
    unittest.main()
