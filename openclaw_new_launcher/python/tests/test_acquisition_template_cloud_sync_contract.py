from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

REPO_ROOT = os.path.dirname(PYTHON_DIR)


class AcquisitionTemplateCloudSyncContractTests(unittest.TestCase):
    def test_template_save_queues_cloud_upload_when_server_is_not_configured(self) -> None:
        from core.acquisition_templates import AcquisitionTemplateLibrary
        from core.paths import AppPaths

        env = {
            "LOOM_TEMPLATE_DISABLE_DEFAULT_CLOUD": "1",
            "LOOM_TEMPLATE_SERVER_URL": "",
            "LOOM_TEMPLATE_CLOUD_URL": "",
            "LOOM_TEMPLATE_SERVER_TOKEN": "",
            "LOOM_TEMPLATE_CLOUD_TOKEN": "",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env, clear=False):
            library = AcquisitionTemplateLibrary(AppPaths(base_path=temp_dir))
            result = library.save_from_acquisition(
                {
                    "name": "美业本地获客模板",
                    "industry": "美业",
                    "platforms": ["douyin"],
                    "targetCustomer": "本地美容老板",
                    "keywords": ["皮肤管理", "附近美容院"],
                    "leadRules": ["询价", "问地址"],
                    "replyStyle": "自然、不强推",
                }
            )
            status = library.status()

        self.assertEqual(result["template"]["uploadStatus"], "pending_upload")
        self.assertEqual(result["upload"]["status"], "pending_config")
        self.assertEqual(status["stats"]["pendingUpload"], 1)
        self.assertEqual(status["cloud"]["configured"], False)

    def test_template_save_uploads_to_default_cloud_without_client_token(self) -> None:
        from core.acquisition_templates import AcquisitionTemplateLibrary
        from core.paths import AppPaths

        calls: list[dict] = []

        def fake_uploader(url: str, token: str, payload: dict, timeout: int = 20) -> dict:
            calls.append({"url": url, "token": token, "payload": payload, "timeout": timeout})
            return {"ok": True, "templateId": "remote_default_tpl", "version": 1, "url": "https://api.heang.top/template-admin/?templateId=remote_default_tpl"}

        env = {
            "LOOM_TEMPLATE_SERVER_URL": "",
            "LOOM_TEMPLATE_CLOUD_URL": "",
            "LOOM_TEMPLATE_SERVER_TOKEN": "",
            "LOOM_TEMPLATE_CLOUD_TOKEN": "",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env, clear=False):
            library = AcquisitionTemplateLibrary(AppPaths(base_path=temp_dir), uploader=fake_uploader)
            result = library.save_from_acquisition(
                {
                    "name": "榛樿浜戠妯℃澘",
                    "industry": "閫氱敤",
                    "platforms": ["manual"],
                    "leadRules": ["浜哄伐纭"],
                }
            )

        self.assertEqual(result["template"]["uploadStatus"], "uploaded")
        self.assertEqual(result["upload"]["status"], "uploaded")
        self.assertEqual(calls[0]["url"], "https://api.heang.top/api/loom/templates")
        self.assertEqual(calls[0]["token"], "")

    def test_template_save_auto_uploads_to_configured_server_and_redacts_secret(self) -> None:
        from core.acquisition_templates import AcquisitionTemplateLibrary
        from core.paths import AppPaths

        calls: list[dict] = []

        def fake_uploader(url: str, token: str, payload: dict, timeout: int = 20) -> dict:
            calls.append({"url": url, "token": token, "payload": payload, "timeout": timeout})
            return {"ok": True, "templateId": "remote_tpl_1", "version": 3, "url": "https://templates.example.test/t/remote_tpl_1"}

        env = {
            "LOOM_TEMPLATE_SERVER_URL": "https://templates.example.test/api/loom/templates",
            "LOOM_TEMPLATE_SERVER_TOKEN": "server-secret-token",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env, clear=False):
            library = AcquisitionTemplateLibrary(AppPaths(base_path=temp_dir), uploader=fake_uploader)
            result = library.save_from_acquisition(
                {
                    "name": "装修客户评论区模板",
                    "industry": "装修",
                    "platforms": ["douyin", "xiaohongshu"],
                    "targetCustomer": "准备装修的本地业主",
                    "keywords": ["装修报价", "旧房翻新"],
                    "leadRules": ["问预算", "问工期"],
                    "replyStyle": "先问需求，再给案例",
                    "token": "raw-template-secret",
                }
            )
            status = library.status()

        serialized = json.dumps({"result": result, "status": status, "payload": calls[0]["payload"]}, ensure_ascii=False)
        self.assertEqual(result["template"]["uploadStatus"], "uploaded")
        self.assertEqual(result["template"]["remote"]["templateId"], "remote_tpl_1")
        self.assertEqual(result["upload"]["status"], "uploaded")
        self.assertEqual(status["stats"]["uploaded"], 1)
        self.assertEqual(calls[0]["url"], "https://templates.example.test/api/loom/templates")
        self.assertEqual(calls[0]["token"], "server-secret-token")
        self.assertEqual(calls[0]["payload"]["schema"], "loom.acquisition_template.v1")
        self.assertNotIn("server-secret-token", serialized)
        self.assertNotIn("raw-template-secret", serialized)

    def test_matrix_routes_expose_template_save_and_retry(self) -> None:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient

        from api.routes_matrix import register_matrix_routes

        async def body(request):
            try:
                payload = await request.json()
            except Exception:
                payload = {}
            return payload if isinstance(payload, dict) else {}

        def fastapi_json(data: dict, status_code: int = 200):
            payload = dict(data)
            payload["_meta"] = {"ok": 200 <= status_code < 400 and "error" not in payload, "status": status_code}
            return JSONResponse(status_code=status_code, content=payload)

        env = {
            "LOOM_TEMPLATE_DISABLE_DEFAULT_CLOUD": "1",
            "LOOM_TEMPLATE_SERVER_URL": "",
            "LOOM_TEMPLATE_CLOUD_URL": "",
            "LOOM_TEMPLATE_SERVER_TOKEN": "",
            "LOOM_TEMPLATE_CLOUD_TOKEN": "",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env, clear=False):
            app = FastAPI()
            register_matrix_routes(
                app,
                SimpleNamespace(
                    auth_error=lambda _request: None,
                    body=body,
                    fastapi_json=fastapi_json,
                    paths=SimpleNamespace(base_path=temp_dir, launcher_dir=temp_dir, node_exe=sys.executable),
                ),
            )
            client = TestClient(app)
            saved = client.post(
                "/api/matrix/acquisition/templates/save",
                json={"name": "家政获客模板", "industry": "家政", "platforms": ["manual"], "leadRules": ["问价格"]},
            )
            listed = client.get("/api/matrix/acquisition/templates")
            retried = client.post("/api/matrix/acquisition/templates/retry")

        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()["template"]["uploadStatus"], "pending_upload")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["stats"]["total"], 1)
        self.assertEqual(retried.status_code, 200)

    def test_ui_contract_exposes_template_cloud_sync(self) -> None:
        page_path = os.path.join(REPO_ROOT, "src", "components", "acquisition", "AcquisitionWorkbenchPage.tsx")
        api_path = os.path.join(REPO_ROOT, "src", "services", "api.ts")

        with open(page_path, "r", encoding="utf-8") as handle:
            page = handle.read()
        with open(api_path, "r", encoding="utf-8") as handle:
            api = handle.read()

        for marker in [
            "data-template-cloud-panel",
            "沉淀为模板并上传服务器",
            "云端模板库",
            "自动上传",
            "待上传",
        ]:
            self.assertIn(marker, page)
        self.assertIn("saveTemplate", api)
        self.assertIn("/api/matrix/acquisition/templates/save", api)
        self.assertIn("retryTemplates", api)

    def test_loom_cli_exposes_template_cloud_sync_commands(self) -> None:
        from loom_cli import dispatch

        cases = [
            (
                [
                    "template",
                    "save",
                    "--name",
                    "美业模板",
                    "--industry",
                    "美业",
                    "--platform",
                    "douyin",
                    "--permission",
                    "control",
                    "--json",
                    "--dry-run",
                ],
                "POST",
                "/api/matrix/acquisition/templates/save",
            ),
            (
                ["template", "retry", "--permission", "control", "--json", "--dry-run"],
                "POST",
                "/api/matrix/acquisition/templates/retry",
            ),
            (
                ["template", "list", "--json", "--dry-run"],
                "GET",
                "/api/matrix/acquisition/templates",
            ),
        ]
        for argv, method, endpoint in cases:
            with self.subTest(argv=argv):
                code, payload = dispatch(argv)
                self.assertEqual(code, 0)
                self.assertEqual(payload["data"]["method"], method)
                self.assertEqual(payload["data"]["endpoint"], endpoint)


if __name__ == "__main__":
    unittest.main()
