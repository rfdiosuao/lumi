from __future__ import annotations

import json
import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TAURI_CONFIG = os.path.join(ROOT, "src-tauri", "tauri.conf.json")
TAURI_LIB = os.path.join(ROOT, "src-tauri", "src", "lib.rs")
INSTALLER_HOOKS = os.path.join(ROOT, "src-tauri", "installer", "upgrade-hooks.nsh")
HANDOFF_SCRIPT = os.path.join(ROOT, "src-tauri", "installer", "update-handoff.ps1")


class LosslessUpdateContractTests(unittest.TestCase):
    def test_nsis_blocks_downgrades_and_loads_upgrade_hooks(self) -> None:
        with open(TAURI_CONFIG, "r", encoding="utf-8") as handle:
            config = json.load(handle)

        windows = config["bundle"]["windows"]
        self.assertFalse(windows["allowDowngrades"])
        self.assertEqual(windows["nsis"]["installerHooks"], "installer/upgrade-hooks.nsh")

    def test_upgrade_hooks_preserve_data_only_for_explicit_update_handoff(self) -> None:
        with open(INSTALLER_HOOKS, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("NSIS_HOOK_PREUNINSTALL", source)
        self.assertIn("NSIS_HOOK_POSTINSTALL", source)
        self.assertIn("update-pending", source)
        self.assertIn("$LOCALAPPDATA\\LOOM", source)
        self.assertNotIn("RMDir /r \"$INSTDIR\\data\"", source)

    def test_tauri_update_handoff_stops_bridge_and_uses_external_recovery_backup(self) -> None:
        with open(TAURI_LIB, "r", encoding="utf-8") as handle:
            source = handle.read()
        with open(HANDOFF_SCRIPT, "r", encoding="utf-8") as handle:
            handoff = handle.read()

        self.assertIn("prepare_update_install", source)
        self.assertIn("shutdown_backend().await", source)
        self.assertIn("upgrade-backups", source)
        self.assertIn("update-pending", source)
        self.assertIn("/D=", handoff)
        self.assertIn("LOOM_UPDATE_TEST_MODE", source)
        self.assertIn("Copy-DataTree", handoff)
        self.assertIn('state = "failed"', handoff)


if __name__ == "__main__":
    unittest.main()
