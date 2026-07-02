from __future__ import annotations

import os
import re
import unittest


LAUNCHER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(LAUNCHER_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")


def read_script(name: str) -> str:
    with open(os.path.join(SCRIPTS_DIR, name), "r", encoding="utf-8-sig") as handle:
        return handle.read()


class ReleaseScriptsContractTests(unittest.TestCase):
    def test_online_installer_requires_package_inputs_instead_of_old_defaults(self) -> None:
        source = read_script("build-online-exe-installer.ps1")

        self.assertIn("[Parameter(Mandatory = $true)]", source)
        self.assertNotIn("LOOM-Online-v2.1.21-20260629-rc3.zip", source)
        self.assertNotIn("744734BBA7542C49CF95C154D898B2B9D08596331DA8F306DAF3804D537CCB6D", source)
        self.assertRegex(source, r"if \(\$PackageRootName -notmatch \[regex\]::Escape\(\$Version\)")

    def test_online_installer_blocks_non_loom_non_empty_target_dirs(self) -> None:
        source = read_script("build-online-exe-installer.ps1")

        self.assertIn("IsRecognizedLoomInstallDirectory", source)
        self.assertIn("DirectoryContainsUserFiles", source)
        self.assertIn("\\u76ee\\u6807\\u76ee\\u5f55\\u4e0d\\u662f LOOM \\u5b89\\u88c5\\u76ee\\u5f55", source)
        self.assertIn("LOOMFiles", source)

    def test_online_package_rewrites_runtime_package_name(self) -> None:
        source = read_script("build-online-portable.ps1")

        self.assertIn("Update-LauncherRuntimePackageName", source)
        self.assertIn("launcher_runtime.json", source)
        self.assertIn("packageName", source)

    def test_verify_release_checks_online_runtime_package_name(self) -> None:
        source = read_script("verify-release.ps1")

        self.assertIn("launcher_runtime.json packageName mismatch", source)
        self.assertRegex(source, re.escape("$script:LauncherRuntimePackageName") + r"\s+-ne\s+\$packageName")

    def test_verify_release_blocks_runtime_state_and_logs(self) -> None:
        source = read_script("verify-release.ps1")

        self.assertIn("member-session\\.json", source)
        self.assertIn("wire-current\\.json", source)
        self.assertIn("agent-model-configs", source)
        self.assertIn("data/logs/.*\\.(log|jsonl)", source)

    def test_portable_build_cleans_runtime_state_after_smoke(self) -> None:
        source = read_script("build-portable.ps1")

        self.assertIn("function Remove-PortableRuntimeStateArtifacts", source)
        self.assertIn("data\\.openclaw\\launcher\\member-session.json", source)
        self.assertIn("data\\.openclaw\\launcher\\wire-current.json", source)
        self.assertIn("data\\logs", source)
        self.assertRegex(source, r"Remove-PortableRuntimeStateArtifacts\s+-PackageDir\s+\$payloadDir")

    def test_portable_smoke_rejects_runtime_state(self) -> None:
        source = read_script("verify-portable-smoke.ps1")

        self.assertIn("data\\.openclaw\\launcher\\member-session.json", source)
        self.assertIn("data\\.openclaw\\launcher\\wire-current.json", source)
        self.assertIn("data\\logs\\bridge-service.log", source)


if __name__ == "__main__":
    unittest.main()
