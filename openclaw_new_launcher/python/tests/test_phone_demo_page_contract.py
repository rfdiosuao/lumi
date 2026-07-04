from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHONE_PAGE = os.path.join(REPO_ROOT, "src", "components", "phone", "PhoneDemoPage.tsx")
API_FILE = os.path.join(REPO_ROOT, "src", "services", "api.ts")
PHONE_AGENT_QR = os.path.join(REPO_ROOT, "public", "phone-agent-apk-qr.svg")


class PhoneDemoPageContractTests(unittest.TestCase):
    def test_phone_demo_keeps_minimal_connection_config_entry(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("手机连接配置", source)
        self.assertIn("手机 IP", source)
        self.assertIn("端口固定 9527", source)
        self.assertIn("displayPhoneAddress", source)
        self.assertIn("连接令牌", source)
        self.assertIn("保存并检测", source)
        self.assertIn("phoneApi.saveDevice", source)
        self.assertIn("tokenAvailable", source)
        self.assertIn("setPhoneToken('')", source)

    def test_phone_demo_exposes_multi_phone_add_and_select_flow(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("phoneConfigSnapshot", source)
        self.assertIn("nextPhoneDeviceId", source)
        self.assertIn("startAddPhone", source)
        self.assertIn("selectConfiguredPhone", source)
        self.assertIn("添加手机", source)
        self.assertIn("已保存 {configuredPhones.length} 台", source)
        self.assertIn("id: deviceId", source)
        self.assertIn("selectedDeviceId: deviceId", source)
        self.assertIn("await checkConnection(deviceId)", source)

    def test_phone_actions_are_disabled_until_connection_config_exists(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("const canUsePhone", source)
        self.assertIn("!canUsePhone", source)
        self.assertIn("请先保存手机 IP 和连接令牌", source)

    def test_phone_demo_exposes_bridge_owned_model_sync_action(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("同步模型到手机", source)
        self.assertIn("phoneApi.syncModel", source)
        self.assertIn("busy === 'syncModel'", source)
        self.assertNotIn("phone-agent.json", source)

    def test_phone_api_exposes_config_without_secret_echo(self) -> None:
        with open(API_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("PhoneConfigSnapshot", source)
        self.assertIn("config: ()", source)
        self.assertIn("saveDevice", source)
        self.assertIn("syncModel", source)
        self.assertIn("api('/api/phone/config')", source)
        self.assertIn("api('/api/phone/config/device', 'POST'", source)
        self.assertIn("api('/api/phone/sync-model', 'POST')", source)

    def test_phone_demo_exposes_safe_and_full_agent_task_modes(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()
        with open(API_FILE, "r", encoding="utf-8") as handle:
            api_source = handle.read()

        self.assertIn("taskMode", page_source)
        self.assertIn("受控", page_source)
        self.assertIn("完整控制", page_source)
        self.assertIn("读取屏幕", page_source)
        self.assertIn("执行中...", page_source)
        self.assertIn("phoneApi.task", page_source)
        self.assertIn("api('/api/phone/task', 'POST'", api_source)


    def test_phone_demo_exposes_performance_profiles_and_fast_defaults(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()
        with open(API_FILE, "r", encoding="utf-8") as handle:
            api_source = handle.read()

        self.assertIn("PhoneTaskProfile", api_source)
        self.assertIn("taskProfile", page_source)
        self.assertIn("TASK_PROFILE_OPTIONS", page_source)
        self.assertIn("fast", page_source)
        self.assertIn("standard", page_source)
        self.assertIn("deep", page_source)
        self.assertIn("profile: taskProfile", page_source)
        self.assertIn("pollMs", page_source)
        self.assertIn("timeoutSec: 120", page_source)
        self.assertIn("maxRounds: 12", page_source)

    def test_phone_demo_keeps_submitted_job_visible_while_polling(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("mergePhoneJob", page_source)
        self.assertIn("setLastJob(submittedJob", page_source)
        self.assertIn("onProgress", page_source)

    def test_phone_demo_enters_running_state_before_bridge_returns(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("createOptimisticPhoneJob", page_source)
        self.assertIn("setLastJob(optimisticJob)", page_source)
        self.assertIn("setJobs((current) => mergePhoneJob(current, optimisticJob))", page_source)
        self.assertIn("setPhoneExecutionStage", page_source)

    def test_phone_demo_uses_full_busy_overlay_and_keeps_inline_stage(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("active={Boolean(busy)}", page_source)
        self.assertIn("const phoneTaskRunning", page_source)
        self.assertIn("phoneExecutionStage || lastJob?.progress?.message", page_source)
        self.assertNotIn("active={Boolean(blockingBusy)}", page_source)

    def test_phone_demo_restores_running_job_when_returning_to_page(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("pickActivePhoneJob", page_source)
        self.assertIn("pickLatestPhoneJob", page_source)
        self.assertIn("current.id === updatedJob.id", page_source)
        self.assertIn("current.id.startsWith('pending_')", page_source)
        self.assertIn("setPhoneExecutionStage(activePhoneJob.progress?.message", page_source)
        self.assertIn("screenshotPath(latestPhoneJob)", page_source)

    def test_phone_demo_releases_long_tasks_after_submit_instead_of_waiting_for_completion(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("maxWaitSec", page_source)
        self.assertIn("releaseWhenSubmitted", page_source)
        self.assertIn("releaseWhenSubmitted: true", page_source)
        self.assertIn("waitForPhoneJob(jobId, waitBudgetMs", page_source)
        self.assertIn("if (options.releaseWhenSubmitted)", page_source)
        self.assertNotIn("4 * 60 * 1000", page_source)

    def test_phone_task_buttons_use_handler_feedback_when_device_is_missing(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("onClick={executePhoneTask}", page_source)
        self.assertIn("onClick={readScreen}", page_source)
        self.assertNotRegex(
            page_source,
            r"onClick=\{executePhoneTask\}\s+disabled=\{Boolean\(busy\) \|\| !canUsePhone\}",
        )
        self.assertNotRegex(
            page_source,
            r"onClick=\{readScreen\}\s+disabled=\{Boolean\(busy\) \|\| !canUsePhone\}",
        )

    def test_phone_demo_has_builtin_phone_app_download_modal(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("PHONE_AGENT_APK_URL", page_source)
        self.assertIn("PHONE_AGENT_QR_SRC", page_source)
        self.assertIn("https://gitee.com/rfdiosuao/lumiapkclaw/releases/download/lumiclaw13241/OpenClaw-AgentPhone.apk", page_source)
        self.assertIn("phone-agent-apk-qr.svg", page_source)
        with open(PHONE_AGENT_QR, "r", encoding="utf-8") as handle:
            qr_source = handle.read()
        self.assertIn("https://gitee.com/rfdiosuao/lumiapkclaw/releases/download/lumiclaw13241/OpenClaw-AgentPhone.apk", qr_source)
        self.assertIn("手机端 App 下载链接已准备", page_source)
        self.assertNotIn("break-all rounded-[12px]", page_source)
        self.assertIn("phoneAppModalOpen", page_source)
        self.assertIn("setPhoneAppModalOpen", page_source)
        self.assertIn("copyPhoneAgentApkUrl", page_source)
        self.assertIn("navigator.clipboard.writeText", page_source)
        self.assertIn("下载手机端 App", page_source)
        self.assertIn("安装三步", page_source)

    def test_phone_demo_exposes_user_facing_device_list_and_task_record(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()
        with open(API_FILE, "r", encoding="utf-8") as handle:
            api_source = handle.read()

        self.assertIn("matrixApi.status", page_source)
        self.assertIn("matrixApi.watch", page_source)
        self.assertIn("我的手机", page_source)
        self.assertIn("执行记录", page_source)
        self.assertIn("连接手机、输入任务、查看结果", page_source)
        self.assertIn("online", page_source)
        self.assertIn("busy", page_source)
        self.assertIn("currentTaskId", page_source)
        self.assertIn("lastResult", page_source)
        self.assertIn("MatrixStatusSnapshot", api_source)
        self.assertIn("watch: (campaignId?: string)", api_source)

    def test_phone_connection_check_updates_matrix_presence(self) -> None:
        with open(PHONE_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("updateMatrixDevicePresence", page_source)
        self.assertIn("heartbeatAt: new Date().toISOString()", page_source)
        self.assertIn("online: Boolean(online)", page_source)
        self.assertIn("void updateMatrixDevicePresence(ok", page_source)
        self.assertIn("currentScreenSummary: summary", page_source)


if __name__ == "__main__":
    unittest.main()
