from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

REPO_ROOT = os.path.dirname(PYTHON_DIR)


class CustomerAcquisitionMvpContractTests(unittest.TestCase):
    def test_acquisition_nav_page_and_api_contract_are_registered(self) -> None:
        registry_path = os.path.join(REPO_ROOT, "src", "features", "registry.ts")
        pages_path = os.path.join(REPO_ROOT, "src", "features", "pages.tsx")
        api_path = os.path.join(REPO_ROOT, "src", "services", "api.ts")

        with open(registry_path, "r", encoding="utf-8") as handle:
            registry = handle.read()
        with open(pages_path, "r", encoding="utf-8") as handle:
            pages = handle.read()
        with open(api_path, "r", encoding="utf-8") as handle:
            api = handle.read()

        self.assertRegex(registry, r"key:\s*'acquisition'[\s\S]+?requiresLicense:\s*true")
        self.assertIn("AcquisitionWorkbenchPage", pages)
        self.assertIn("acquisitionApi", api)
        self.assertIn("/api/matrix/acquisition", api)
        self.assertIn("/api/matrix/acquisition/demo", api)
        self.assertIn("/api/matrix/acquisition/draft/confirm", api)

    def test_acquisition_page_exposes_marketing_workbench_contract(self) -> None:
        page_path = os.path.join(REPO_ROOT, "src", "components", "acquisition", "AcquisitionWorkbenchPage.tsx")

        with open(page_path, "r", encoding="utf-8") as handle:
            source = handle.read()

        for marker in [
            "data-acquisition-workbench",
            "data-marketing-mission-control",
            "data-lead-source-panel",
            "data-ai-qualification-panel",
            "data-feishu-sync-panel",
            "data-safe-outreach-queue",
            "data-followup-log-panel",
            "data-acquisition-lead-pool",
            "data-acquisition-draft-review",
            "data-acquisition-task-log",
            "data-acquisition-stats",
            "自动营销工作台",
            "获客任务",
            "线索来源",
            "AI 筛选",
            "飞书入表",
            "待确认触达",
            "人工确认",
            "不会自动发送",
            "白名单",
            "频控",
            "多台手机矩阵，自动帮你发现潜在客户",
            "多台设备统一调度",
            "适合本地商家和销售团队",
            "自动找线索",
            "AI 写话术",
            "沉淀客户池",
            "同步飞书线索表",
            "安全触达队列",
        ]:
            self.assertIn(marker, source)

        self.assertNotIn("autoSend", source)
        self.assertNotIn("batchSend", source)

    def test_acquisition_demo_flow_is_local_draft_only_and_redacted(self) -> None:
        from core.paths import AppPaths
        from core.phone_matrix import MatrixControlPlane

        with tempfile.TemporaryDirectory() as temp_dir:
            matrix = MatrixControlPlane(AppPaths(base_path=temp_dir))
            flow = matrix.create_acquisition_demo_flow(
                {
                    "topic": "企业知识库获客",
                    "platform": "douyin",
                    "leadSummary": "用户想加微信 13800000000，邮箱 test@example.com，Bearer secret-token",
                    "channel": "comment",
                    "knowledge": "先确认场景，再给案例和预约入口。",
                    "token": "secret-token",
                }
            )
            snapshot = matrix.acquisition_snapshot()
            confirmed = matrix.confirm_acquisition_draft(flow["draft"]["draftId"], {"operator": "demo"})

        serialized = json.dumps({"flow": flow, "snapshot": snapshot, "confirmed": confirmed}, ensure_ascii=False)
        self.assertEqual(snapshot["schema"], "loom.customer_acquisition.v1")
        self.assertEqual(flow["draft"]["status"], "pending_manual_review")
        self.assertEqual(confirmed["draft"]["status"], "approved_pending_manual_send")
        self.assertFalse(flow["draft"]["sendEnabled"])
        self.assertTrue(flow["draft"]["requiresHumanReview"])
        self.assertIn("manual_confirm", flow["draft"]["policy"])
        self.assertIn("frequency_cap", flow["draft"]["policy"])
        self.assertGreaterEqual(snapshot["stats"]["leads"], 1)
        self.assertGreaterEqual(snapshot["stats"]["draftsPending"], 1)
        self.assertGreaterEqual(len(snapshot["logs"]), 3)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("13800000000", serialized)
        self.assertNotIn("test@example.com", serialized)


if __name__ == "__main__":
    unittest.main()
