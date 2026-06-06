from __future__ import annotations

import base64
import importlib.util
import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = ROOT / "license_server" / "server.py"


def load_server(temp_dir: Path):
    private_key = Ed25519PrivateKey.generate()
    raw_key = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = temp_dir / "private_key.b64"
    key_file.write_text(base64.b64encode(raw_key).decode("ascii"), encoding="utf-8")

    os.environ["LICENSE_DB"] = str(temp_dir / "license.db")
    os.environ["LICENSE_BACKUP_DIR"] = str(temp_dir / "backups")
    os.environ["LICENSE_PRIVATE_KEY_FILE"] = str(key_file)
    os.environ["LICENSE_ADMIN_TOKEN"] = "test-admin-token"
    os.environ["MEMBER_GATEWAY_BASE_URL"] = ""
    os.environ["MEMBER_GATEWAY_IMAGE_BASE_URL"] = ""
    os.environ["MEMBER_GATEWAY_VIDEO_BASE_URL"] = ""
    os.environ["MEMBER_GATEWAY_TOKEN"] = ""
    os.environ["MEMBER_GATEWAY_IMAGE_TOKEN"] = ""
    os.environ["MEMBER_GATEWAY_VIDEO_TOKEN"] = ""
    os.environ["OPENCLAW_PUBLISH_RELAY_TOKEN"] = "test-relay-token"

    module_name = f"openclaw_license_server_test_{next(tempfile._get_candidate_names())}"
    spec = importlib.util.spec_from_file_location(module_name, SERVER_PATH)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class LicenseServerFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.server = load_server(self.temp_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def expires(self) -> str:
        return (date.today() + timedelta(days=365)).isoformat()

    def start_http_server(self) -> str:
        from http.server import ThreadingHTTPServer
        import threading

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def cleanup() -> None:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

        self.addCleanup(cleanup)
        return f"http://127.0.0.1:{httpd.server_address[1]}"

    def request_raw(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
    ):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        import json

        base_url = self.start_http_server()
        data = None
        request_headers = dict(headers or {})
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(f"{base_url}{path}", method=method, headers=request_headers, data=data)
        try:
            response = urlopen(request, timeout=5)
            status = response.status
            body = response.read()
            response_headers = response.headers
        except HTTPError as error:
            status = error.code
            body = error.read()
            response_headers = error.headers
        self.assertEqual(status, expected_status, body.decode("utf-8", errors="replace"))
        return body, response_headers

    def request_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
    ) -> dict[str, object]:
        import json

        body, _ = self.request_raw(
            method,
            path,
            payload=payload,
            headers=headers,
            expected_status=expected_status,
        )
        return json.loads(body.decode("utf-8") or "{}")

    def test_public_card_site_config_is_validated_and_exposed_to_clients(self) -> None:
        initial = self.server.client_public_config()
        self.assertEqual(initial["cardSite"]["enabled"], False)
        self.assertEqual(initial["cardSite"]["url"], "")

        with self.assertRaises(self.server.ActivationError):
            self.server.update_public_settings({"cardSiteUrl": "ftp://invalid.example"})

        updated = self.server.update_public_settings(
            {
                "cardSiteEnabled": True,
                "cardSiteLabel": "Buy license",
                "cardSiteUrl": "https://shop.example.com/cdk",
            }
        )
        self.assertEqual(updated["cardSiteLabel"], "Buy license")

        client_config = self.server.client_public_config()
        self.assertEqual(
            client_config,
            {
                "cardSite": {
                    "enabled": True,
                    "label": "Buy license",
                    "url": "https://shop.example.com/cdk",
                }
            },
        )

    def test_merchant_cannot_update_public_settings(self) -> None:
        from http.server import ThreadingHTTPServer
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        import json
        import threading

        merchant, _ = self.server.create_account_record(
            username="merchant-settings",
            display_name="Merchant Settings",
            password="merchant-password-123",
            role=self.server.ACCOUNT_ROLE_MERCHANT,
        )
        merchant_session, _ = self.server.create_admin_session(merchant["accountId"])

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/admin/api/public-settings"
            request = Request(
                url,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-Session": merchant_session,
                },
                data=json.dumps(
                    {
                        "cardSiteEnabled": False,
                        "cardSiteLabel": "Blocked",
                        "cardSiteUrl": "",
                    }
                ).encode("utf-8"),
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 403)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_bootstrap_requires_password_and_does_not_return_temporary_password(self) -> None:
        missing_password = self.request_json(
            "POST",
            "/admin/api/auth/bootstrap",
            payload={"username": "admin"},
            headers={"X-Admin-Token": "test-admin-token"},
            expected_status=400,
        )
        self.assertIn("error", missing_password)
        self.assertEqual(self.server.count_accounts(), 0)

        created = self.request_json(
            "POST",
            "/admin/api/auth/bootstrap",
            payload={"username": "admin", "password": "admin-password-123"},
            headers={"X-Admin-Token": "test-admin-token"},
            expected_status=200,
        )
        self.assertTrue(created["ok"])
        self.assertNotIn("temporaryPassword", created)
        self.assertTrue(self.server.verify_password("admin-password-123", self.server.get_account_by_username("admin")["password_hash"]))

    def test_admin_http_account_creation_requires_password_and_hides_temporary_password(self) -> None:
        admin, _ = self.server.create_account_record(
            username="admin",
            display_name="Root",
            password="admin-password-123",
            role=self.server.ACCOUNT_ROLE_SUPER_ADMIN,
        )
        session_token, _ = self.server.create_admin_session(admin["accountId"])
        headers = {"X-Admin-Session": session_token}

        blank = self.request_json(
            "POST",
            "/admin/api/accounts",
            payload={"username": "merchant-blank", "password": ""},
            headers=headers,
            expected_status=400,
        )
        self.assertIn("error", blank)

        created = self.request_json(
            "POST",
            "/admin/api/accounts",
            payload={
                "username": "merchant-created",
                "displayName": "Merchant Created",
                "password": "merchant-password-123",
                "role": self.server.ACCOUNT_ROLE_MERCHANT,
            },
            headers=headers,
            expected_status=200,
        )
        self.assertTrue(created["ok"])
        self.assertNotIn("temporaryPassword", created)
        self.assertEqual(created["account"]["username"], "merchant-created")

    def test_admin_cors_restricts_admin_origins_but_keeps_public_api_open(self) -> None:
        _, blocked_headers = self.request_raw(
            "OPTIONS",
            "/admin/api/auth/login",
            headers={"Origin": "https://evil.example"},
            expected_status=204,
        )
        self.assertIsNone(blocked_headers.get("Access-Control-Allow-Origin"))

        _, allowed_headers = self.request_raw(
            "OPTIONS",
            "/admin/api/auth/login",
            headers={"Origin": "http://127.0.0.1:3000"},
            expected_status=204,
        )
        self.assertEqual(allowed_headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:3000")

        _, public_headers = self.request_raw(
            "OPTIONS",
            "/api/client/config",
            headers={"Origin": "https://anywhere.example"},
            expected_status=204,
        )
        self.assertEqual(public_headers.get("Access-Control-Allow-Origin"), "*")

    def test_login_and_register_rate_limits_block_repeated_attempts(self) -> None:
        self.server.create_account_record(
            username="rate-user",
            password="correct-password-123",
            role=self.server.ACCOUNT_ROLE_SUPER_ADMIN,
        )
        for _ in range(self.server.LOGIN_RATE_LIMIT_ATTEMPTS):
            self.request_json(
                "POST",
                "/admin/api/auth/login",
                payload={"username": "rate-user", "password": "wrong-password"},
                expected_status=401,
            )
        self.request_json(
            "POST",
            "/admin/api/auth/login",
            payload={"username": "rate-user", "password": "wrong-password"},
            expected_status=429,
        )

        for idx in range(self.server.REGISTER_RATE_LIMIT_ATTEMPTS):
            self.request_json(
                "POST",
                "/admin/api/auth/register",
                payload={
                    "inviteCode": "INV-DOES-NOT-EXIST",
                    "username": f"blocked-register-{idx}",
                    "password": "merchant-password-123",
                },
                expected_status=404,
            )
        self.request_json(
            "POST",
            "/admin/api/auth/register",
            payload={
                "inviteCode": "INV-DOES-NOT-EXIST",
                "username": "blocked-register-next",
                "password": "merchant-password-123",
            },
            expected_status=429,
        )

    def test_merchant_gateway_defaults_are_used_when_creating_codes(self) -> None:
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        import json
        import threading

        merchant, _ = self.server.create_account_record(
            username="merchant-gateway",
            display_name="Merchant Gateway",
            password="merchant-password-123",
            role=self.server.ACCOUNT_ROLE_MERCHANT,
        )
        merchant_session, _ = self.server.create_admin_session(merchant["accountId"])

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{httpd.server_address[1]}/admin"

            save_request = Request(
                f"{base_url}/api/account-gateway",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-Session": merchant_session,
                },
                data=json.dumps(
                    {
                        "gatewayBaseUrl": "https://llm.merchant.example/v1",
                        "gatewayImageBaseUrl": "https://image.merchant.example/v1",
                        "gatewayVideoBaseUrl": "https://video.merchant.example/v1",
                        "gatewayToken": "merchant-llm-token",
                        "gatewayImageToken": "merchant-image-token",
                        "gatewayVideoToken": "merchant-video-token",
                        "gatewayDefaultModel": "merchant-chat",
                        "gatewayImageModel": "merchant-image",
                        "gatewayVideoModel": "merchant-video",
                        "gatewayModels": "merchant-chat,merchant-pro",
                    }
                ).encode("utf-8"),
            )
            save_response = json.loads(urlopen(save_request, timeout=5).read().decode("utf-8"))
            self.assertTrue(save_response["settings"]["gatewayConfigured"])
            self.assertNotIn("merchant-llm-token", json.dumps(save_response, ensure_ascii=False))

            create_request = Request(
                f"{base_url}/api/codes",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-Session": merchant_session,
                },
                data=json.dumps(
                    {
                        "licensee": "Gateway Customer",
                        "edition": "pro",
                        "count": 1,
                        "expires": self.expires(),
                        "maxActivations": 1,
                        "features": "openclaw,image,video",
                        "memberMode": True,
                        "plan": "merchant_custom",
                    }
                ).encode("utf-8"),
            )
            create_response = json.loads(urlopen(create_request, timeout=5).read().decode("utf-8"))
            code = create_response["codes"][0]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

        merchant_context = {
            "accountId": merchant["accountId"],
            "role": self.server.ACCOUNT_ROLE_MERCHANT,
        }
        rows = self.server.get_code_rows(merchant_context)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["gatewayConfigured"])
        self.assertTrue(rows[0]["gatewayImageConfigured"])
        self.assertTrue(rows[0]["gatewayVideoConfigured"])
        self.assertEqual(rows[0]["gatewayDefaultModel"], "merchant-chat")
        self.assertEqual(rows[0]["gatewayImageModel"], "merchant-image")
        self.assertEqual(rows[0]["gatewayVideoModel"], "merchant-video")
        self.assertNotEqual(rows[0]["gatewayToken"], "merchant-llm-token")

        license_data = self.server.activate_code(
            {"code": code, "installId": "merchant-install", "deviceId": "merchant-device"}
        )
        self.assertEqual(license_data["gatewayBaseUrl"], "https://llm.merchant.example/v1")
        self.assertEqual(license_data["gatewayAccessToken"], "merchant-llm-token")
        self.assertEqual(license_data["gatewayImageAccessToken"], "merchant-image-token")
        self.assertEqual(license_data["gatewayVideoAccessToken"], "merchant-video-token")

    def test_member_activation_preserves_separate_llm_image_and_video_gateway_config(self) -> None:
        code = self.server.create_code_records(
            count=1,
            licensee="Flow Customer",
            edition="pro",
            features=["openclaw", "image", "video", "storyboard"],
            expires=self.expires(),
            max_activations=1,
            member_mode=True,
            plan="monthly",
            gateway_base_url="https://llm.example.com/v1",
            gateway_image_base_url="https://image.example.com/v1",
            gateway_video_base_url="https://video.example.com/v1",
            gateway_token="llm-token",
            gateway_image_token="image-token",
            gateway_video_token="video-token",
            gateway_default_model="gpt-4.1-mini",
            gateway_image_model="gpt-image-2",
            gateway_video_model="happyhorse-1.0-t2v",
            gateway_models=["gpt-4.1-mini", "gpt-4.1"],
            quotas={},
        )[0]

        license_data = self.server.activate_code(
            {"code": code, "installId": "install-a", "deviceId": "device-a"}
        )

        expected_last8 = "".join(ch for ch in code if ch.isalnum())[-8:]
        self.assertTrue(license_data["memberMode"])
        self.assertEqual(license_data["activationCodeLast8"], expected_last8)
        self.assertEqual(license_data["gatewayBaseUrl"], "https://llm.example.com/v1")
        self.assertEqual(license_data["gatewayImageBaseUrl"], "https://image.example.com/v1")
        self.assertEqual(license_data["gatewayVideoBaseUrl"], "https://video.example.com/v1")
        self.assertEqual(license_data["gatewayAccessToken"], "llm-token")
        self.assertEqual(license_data["gatewayImageAccessToken"], "image-token")
        self.assertEqual(license_data["gatewayVideoAccessToken"], "video-token")
        self.assertEqual(license_data["gatewayDefaultModel"], "gpt-4.1-mini")
        self.assertEqual(license_data["gatewayImageModel"], "gpt-image-2")
        self.assertEqual(license_data["gatewayVideoModel"], "happyhorse-1.0-t2v")

        response = self.server.member_response(license_data)
        self.assertEqual(response["gateway"]["baseUrl"], "https://llm.example.com/v1")
        self.assertEqual(response["gateway"]["imageBaseUrl"], "https://image.example.com/v1")
        self.assertEqual(response["gateway"]["videoBaseUrl"], "https://video.example.com/v1")
        self.assertEqual(response["member"]["gatewayImageToken"], "image-token")
        self.assertEqual(response["member"]["gatewayVideoToken"], "video-token")

        refreshed = self.server.find_member_license(
            {"installId": "install-a", "gatewayImageAccessToken": "image-token"}
        )
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["gatewayImageModel"], "gpt-image-2")

        rows = self.server.get_code_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fullCode"], code)
        self.assertEqual(rows[0]["activations"], 1)

    def test_member_current_rejects_empty_or_token_only_lookup(self) -> None:
        from http.server import ThreadingHTTPServer
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        import json
        import threading

        code = self.server.create_code_records(
            count=1,
            licensee="Secure Member",
            edition="pro",
            features=["openclaw", "image", "video"],
            expires=self.expires(),
            max_activations=1,
            member_mode=True,
            plan="monthly",
            gateway_base_url="https://llm.example.com/v1",
            gateway_token="llm-token",
        )[0]
        license_data = self.server.activate_code(
            {"code": code, "installId": "install-secure", "deviceId": "device-secure"}
        )

        self.assertIsNone(self.server.find_member_license({}))
        self.assertIsNone(self.server.find_member_license({"gatewayAccessToken": "llm-token"}))
        self.assertIsNone(self.server.find_member_license({"memberId": license_data["memberId"]}))
        self.assertIsNone(
            self.server.find_member_license(
                {"memberId": license_data["memberId"], "gatewayAccessToken": "llm-token"}
            )
        )
        self.assertIsNone(
            self.server.find_member_license(
                {
                    "installId": "install-secure",
                    "deviceId": "wrong-device",
                    "memberId": license_data["memberId"],
                    "gatewayAccessToken": "llm-token",
                }
            )
        )
        self.assertIsNotNone(
            self.server.find_member_license(
                {
                    "installId": "install-secure",
                    "deviceId": "device-secure",
                    "memberId": license_data["memberId"],
                    "gatewayAccessToken": "llm-token",
                }
            )
        )

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/member/current",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=json.dumps({}).encode("utf-8"),
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 404)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

    def test_merchant_cannot_apply_global_plan_template_gateway_secret(self) -> None:
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        import json
        import threading

        self.server.DEFAULT_GATEWAY_BASE_URL = "https://platform-default.example/v1"
        self.server.DEFAULT_GATEWAY_TOKEN = "platform-default-token"
        self.server.upsert_plan_record(
            {
                "planKey": "platform_secret",
                "displayName": "Platform Secret",
                "durationDays": 31,
                "features": "openclaw,image,video",
                "gatewayBaseUrl": "https://platform.example/v1",
                "gatewayToken": "platform-secret-token",
                "gatewayDefaultModel": "platform-model",
                "quotas": '{"image":100,"video":20}',
            }
        )
        merchant, _ = self.server.create_account_record(
            username="merchant-no-template",
            display_name="Merchant No Template",
            password="merchant-password-123",
            role=self.server.ACCOUNT_ROLE_MERCHANT,
        )
        merchant_session, _ = self.server.create_admin_session(merchant["accountId"])

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/admin/api/codes",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Admin-Session": merchant_session,
                },
                data=json.dumps(
                    {
                        "licensee": "Merchant Customer",
                        "edition": "pro",
                        "count": 1,
                        "planTemplate": "platform_secret",
                        "memberMode": True,
                        "maxActivations": 1,
                        "features": "openclaw,image,video",
                        "expires": self.expires(),
                    }
                ).encode("utf-8"),
            )
            response = json.loads(urlopen(request, timeout=5).read().decode("utf-8"))
            code = response["codes"][0]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)

        merchant_context = {
            "accountId": merchant["accountId"],
            "role": self.server.ACCOUNT_ROLE_MERCHANT,
        }
        rows = self.server.get_code_rows(merchant_context)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fullCode"], code)
        self.assertFalse(rows[0]["gatewayConfigured"])
        self.assertNotEqual(rows[0]["gatewayBaseUrl"], "https://platform.example/v1")
        with self.assertRaises(self.server.ActivationError):
            self.server.activate_code({"code": code, "installId": "install-a", "deviceId": "device-a"})

    def test_activation_limit_blocks_second_install(self) -> None:
        code = self.server.create_code_records(
            count=1,
            licensee="Single Device",
            edition="pro",
            features=["openclaw"],
            expires=self.expires(),
            max_activations=1,
        )[0]

        first = self.server.activate_code(
            {"code": code, "installId": "install-a", "deviceId": "device-a"}
        )
        self.assertEqual(first["installId"], "install-a")

        with self.assertRaises(self.server.ActivationError) as raised:
            self.server.activate_code(
                {"code": code, "installId": "install-b", "deviceId": "device-b"}
            )
        self.assertEqual(raised.exception.status, 403)

    def test_bulk_update_validates_code_hash_count_and_format(self) -> None:
        with self.assertRaises(self.server.ActivationError) as bad_hash:
            self.server.bulk_update_code_records({"codeHashes": ["not-a-sha256"]})
        self.assertEqual(bad_hash.exception.status, 400)

        with self.assertRaises(self.server.ActivationError) as too_many:
            self.server.bulk_update_code_records(
                {"codeHashes": ["a" * 64 for _ in range(self.server.MAX_BULK_CODE_HASHES + 1)]}
            )
        self.assertEqual(too_many.exception.status, 400)

    def test_admin_sessions_and_merchant_code_scope(self) -> None:
        admin, admin_temporary_password = self.server.create_account_record(
            username="admin",
            display_name="Root",
            password="admin-password-123",
            role=self.server.ACCOUNT_ROLE_SUPER_ADMIN,
        )
        merchant, merchant_temporary_password = self.server.create_account_record(
            username="merchant-one",
            display_name="Merchant One",
            password="merchant-password-123",
            role=self.server.ACCOUNT_ROLE_MERCHANT,
        )
        other, _ = self.server.create_account_record(
            username="merchant-two",
            display_name="Merchant Two",
            password="merchant-password-456",
            role=self.server.ACCOUNT_ROLE_MERCHANT,
        )
        self.assertEqual(admin_temporary_password, "")
        self.assertEqual(merchant_temporary_password, "")
        self.assertTrue(self.server.verify_password("merchant-password-123", self.server.get_account_by_id(merchant["accountId"])["password_hash"]))

        session_token, _ = self.server.create_admin_session(merchant["accountId"])
        merchant_context = self.server.load_admin_context_from_session(session_token)
        self.assertIsNotNone(merchant_context)
        assert merchant_context is not None
        self.assertEqual(merchant_context["role"], self.server.ACCOUNT_ROLE_MERCHANT)

        code = self.server.create_code_records(
            count=1,
            licensee="Owned Customer",
            edition="pro",
            features=["openclaw"],
            expires=self.expires(),
            max_activations=1,
            owner_account_id=merchant["accountId"],
        )[0]
        other_context = {"accountId": other["accountId"], "role": self.server.ACCOUNT_ROLE_MERCHANT}
        admin_context = {"accountId": admin["accountId"], "role": self.server.ACCOUNT_ROLE_SUPER_ADMIN}

        self.assertEqual([row["fullCode"] for row in self.server.get_code_rows(merchant_context)], [code])
        self.assertEqual(self.server.get_code_rows(other_context), [])
        self.assertEqual(len(self.server.get_code_rows(admin_context)), 1)

        with self.assertRaises(self.server.ActivationError) as raised:
            self.server.update_code_record(
                {
                    "codeHash": self.server.code_hash(code),
                    "licensee": "Forbidden Edit",
                    "edition": "pro",
                    "features": "openclaw",
                    "expires": self.expires(),
                    "maxActivations": 1,
                },
                current_account=other_context,
            )
        self.assertEqual(raised.exception.status, 403)
        self.assertTrue(self.server.revoke_admin_session(session_token))
        self.assertIsNone(self.server.load_admin_context_from_session(session_token))

    def test_account_generated_password_and_minimum_length(self) -> None:
        account, temporary_password = self.server.create_account_record(username="new-merchant")
        self.assertTrue(temporary_password)
        self.assertTrue(
            self.server.verify_password(
                temporary_password,
                self.server.get_account_by_id(account["accountId"])["password_hash"],
            )
        )
        with self.assertRaises(self.server.ActivationError):
            self.server.create_account_record(username="short-pass", password="short")

    def test_invite_registration_creates_merchant_and_consumes_code(self) -> None:
        admin, _ = self.server.create_account_record(
            username="admin",
            display_name="Root",
            password="admin-password-123",
            role=self.server.ACCOUNT_ROLE_SUPER_ADMIN,
        )
        invite, raw_code = self.server.create_invite_record(
            note="seller invite",
            max_uses=1,
            expires_at=(date.today() + timedelta(days=30)).isoformat(),
            created_by=admin["accountId"],
        )

        self.assertEqual(invite["status"], "active")
        self.assertEqual(self.server.count_invites(active_only=True), 1)

        account, used_code, _ = self.server.register_account_with_invite(
            invite_code=raw_code.lower(),
            username="merchant-invite",
            display_name="Invite Merchant",
            password="merchant-password-123",
            request_ip="127.0.0.1",
        )

        self.assertEqual(used_code, raw_code)
        self.assertEqual(account["role"], self.server.ACCOUNT_ROLE_MERCHANT)
        self.assertEqual(account["displayName"], "Invite Merchant")
        self.assertEqual(self.server.count_invites(active_only=True), 0)

        rows = self.server.list_invite_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "used")
        self.assertEqual(rows[0]["usedCount"], 1)
        self.assertEqual(rows[0]["lastUsedUsername"], "merchant-invite")

        session_token, _ = self.server.create_admin_session(account["accountId"])
        context = self.server.load_admin_context_from_session(session_token)
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context["role"], self.server.ACCOUNT_ROLE_MERCHANT)

        with self.assertRaises(self.server.ActivationError) as raised:
            self.server.register_account_with_invite(
                invite_code=raw_code,
                username="merchant-second",
                password="merchant-password-456",
            )
        self.assertEqual(raised.exception.status, 403)

    def test_publish_relay_queue_claim_complete_and_auth(self) -> None:
        self.assertTrue(
            self.server.publish_relay_token_valid(
                {"Authorization": "Bearer test-relay-token"}
            )
        )
        self.assertFalse(
            self.server.publish_relay_token_valid(
                {"Authorization": "Bearer wrong-token"}
            )
        )

        packet = {
            "schema": "openclaw.publish.packet.v1",
            "channelId": "test-channel",
            "platformId": "custom",
            "title": "relay test",
            "body": "relay test",
            "media": [],
        }
        queued = self.server.publish_relay_enqueue(packet)
        self.assertEqual(queued["status"], "pending")
        self.assertEqual(queued["channelId"], "test-channel")

        stats = self.server.publish_relay_stats("test-channel")
        self.assertEqual(stats["pending"], 1)

        claimed = self.server.publish_relay_claim("test-channel", "test-client", 30_000)
        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed["packet"]["schema"], "openclaw.publish.packet.v1")
        self.assertEqual(claimed["attempts"], 1)
        self.assertEqual(claimed["leasedBy"], "test-client")

        already_leased = self.server.publish_relay_claim("test-channel", "other-client", 30_000)
        self.assertIsNone(already_leased)

        completed = self.server.publish_relay_complete(
            {
                "packetId": claimed["id"],
                "leaseId": claimed["leaseId"],
                "clientId": "test-client",
                "success": True,
                "result": {"ok": True},
            }
        )
        self.assertEqual(completed["status"], "done")
        final = self.server.publish_relay_status(claimed["id"])
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["packet"]["title"], "relay test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
