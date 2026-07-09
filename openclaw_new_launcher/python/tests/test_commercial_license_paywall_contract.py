from __future__ import annotations

import os
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PYTHON_DIR)
GATE_FILE = os.path.join(REPO_ROOT, "src", "components", "license", "licenseGate.ts")
STORE_FILE = os.path.join(REPO_ROOT, "src", "stores", "appStore.ts")
API_FILE = os.path.join(REPO_ROOT, "src", "services", "api.ts")
TYPES_FILE = os.path.join(REPO_ROOT, "src", "types", "index.ts")


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class CommercialLicenseGateStateContractTests(unittest.TestCase):
    def test_gate_has_finite_explicit_states_and_normalizer(self) -> None:
        self.assertTrue(os.path.exists(GATE_FILE), "license gate state module is missing")
        source = read_text(GATE_FILE)

        for status in (
            "checking",
            "authorized",
            "unauthorized",
            "expired",
            "disabled",
            "device_mismatch",
            "offline_grace",
            "service_error",
        ):
            self.assertIn(f"'{status}'", source)

        self.assertIn("export function normalizeLicenseGate", source)
        self.assertIn("LICENSE_CHECK_TIMEOUT_MS", source)
        self.assertIn("LICENSE_EXPIRED", source)
        self.assertIn("DEVICE_MISMATCH", source)
        self.assertIn("LICENSE_DISABLED", source)

    def test_store_uses_signed_license_gate_without_gateway_profile_bypass(self) -> None:
        source = read_text(STORE_FILE)

        self.assertIn("licenseGate", source)
        self.assertIn("normalizeLicenseGate", source)
        self.assertIn("withLicenseCheckTimeout", source)
        self.assertIn("licenseInfo?.signature", source)
        self.assertNotIn("else if (gatewayProfile", source)
        self.assertNotIn("gatewayProfile as License", source)

    def test_api_and_types_expose_typed_commercial_license_fields(self) -> None:
        api_source = read_text(API_FILE)
        types_source = read_text(TYPES_FILE)

        self.assertIn("LicenseCurrentResponse", api_source)
        self.assertIn("LicenseClientConfig", api_source)
        self.assertIn("LicenseAuthorizationResponse", api_source)
        self.assertIn("LicenseActivationResponse", api_source)
        self.assertIn("expiresAt?: string | null", types_source)
        self.assertIn("deviceLimit?: number", types_source)
        self.assertIn("status?: string", types_source)
        self.assertIn("code?: string", types_source)


if __name__ == "__main__":
    unittest.main()
