from __future__ import annotations

import os
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENT_PAGE = os.path.join(REPO_ROOT, "src", "components", "agents", "AgentInstallerPage.tsx")
API_FILE = os.path.join(REPO_ROOT, "src", "services", "api.ts")
STARTUP_CACHE_FILE = os.path.join(REPO_ROOT, "src", "services", "startupCache.ts")
LOOM_CLIENT = os.path.join(REPO_ROOT, "src", "services", "loomClient.ts")


class AgentInstallerPageContractTests(unittest.TestCase):
    def test_agent_installer_page_uses_loom_client_facade_for_backend_calls(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()
        with open(LOOM_CLIENT, "r", encoding="utf-8") as handle:
            client_source = handle.read()

        self.assertIn("loomClient", source)
        self.assertIn("loomClient.components.status()", source)
        self.assertIn("loomClient.diagnostics.prerequisites()", source)
        self.assertIn("loomClient.jobs.list(20)", source)
        self.assertIn("loomClient.process.status()", source)
        self.assertIn("loomClient.process.waitForReady", source)
        self.assertNotIn("componentApi.", source)
        self.assertNotIn("diagnosticsApi.", source)
        self.assertNotIn("jobApi.", source)
        self.assertNotIn("processApi.", source)
        self.assertIn("jobs:", client_source)
        self.assertIn("process:", client_source)

    def test_install_page_copy_is_readable_chinese_not_mojibake(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        mojibake_markers = tuple(chr(code) for code in (
            0x93C5,
            0x7F02,
            0x935A,
            0x9353,
            0x59AB,
            0x7039,
            0x7ECB,
            0x941C,
            0x95BF,
            0x4FD9,
            0x255C,
        ))
        for marker in mojibake_markers:
            self.assertNotIn(marker, source)

    def test_install_page_exposes_retry_and_log_panel_for_demo_flow(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-agent-log-panel", source)
        self.assertIn("data-agent-retry-button", source)
        self.assertIn("安装日志", source)
        self.assertIn("重试安装", source)

    def test_install_log_is_compact_by_default_with_full_history_collapsed(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("INSTALL_LOG_VISIBLE_LIMIT = 6", source)
        self.assertIn("visibleLogEntries", source)
        self.assertIn("hiddenLogCount", source)
        self.assertIn("data-agent-log-compact", source)
        self.assertIn("data-agent-log-full", source)
        self.assertIn("查看完整日志", source)

    def test_install_log_supports_copy_and_export_without_exposing_full_history_by_default(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("copyInstallLog", source)
        self.assertIn("exportInstallLog", source)
        self.assertIn("formatInstallLogEntries", source)
        self.assertIn("data-agent-copy-log-button", source)
        self.assertIn("data-agent-export-log-button", source)
        self.assertIn("复制日志", source)
        self.assertIn("导出日志", source)

    def test_prepare_flow_installs_when_detection_finds_upgrade_available(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("needsInstallAfterDetect", source)
        self.assertIn("upgrade_available", source)
        self.assertIn("检测到需安装或升级，开始下载安装", source)

    def test_destructive_or_system_modifying_actions_are_confirmed(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("confirmPreflightRepair", source)
        self.assertIn("loomClient.diagnostics.repairPrerequisites()", source)
        self.assertIn("loomClient.components.install(component.id, { confirmed: true", source)

    def test_preflight_detection_uses_corner_busy_state_without_locking_page_scroll(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-installer-nonblocking", source)
        self.assertIn("data-agent-page-locked", source)
        self.assertIn("preflightBusy", source)
        self.assertIn("blockingBusy", source)
        self.assertIn("const pageLocked = loading", source)
        self.assertIn("const controlsLocked = loading", source)
        self.assertIn("const busyOverlayMode = (preflightBusy || componentJobBusy || Boolean(modelConfigBusy)) && !blockingBusy ? 'corner' : 'blocking'", source)
        self.assertIn("aria-busy={busyOverlayActive}", source)
        self.assertIn("overflow-y-auto", source)
        self.assertNotIn("overflow-y-hidden", source)

    def test_agent_access_copy_is_embedded_in_installer_page(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-agent-install-start-grid", source)
        self.assertIn("lg:grid-cols-[minmax(0,1.18fr)_minmax(320px,0.82fr)]", source)
        self.assertIn("grid-cols-[repeat(auto-fit,minmax(120px,1fr))]", source)
        self.assertIn("data-agent-access-inline", source)
        self.assertIn("copyAgentAccessPrompt", source)
        self.assertIn("buildOneShotAgentPrompt(buildMcpJson())", source)
        self.assertIn("复制接入提示词", source)
        self.assertIn("生图、生视频、手机矩阵", source)

    def test_codex_and_claude_model_config_controls_are_exposed(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-agent-model-config", source)
        self.assertIn("data-agent-model-source-card", source)
        self.assertIn("data-agent-one-click-config-lock", source)
        self.assertIn("data-agent-custom-provider-card", source)
        self.assertIn("data-agent-custom-provider-select", source)
        self.assertIn("data-agent-custom-base-url-input", source)
        self.assertIn("data-agent-custom-api-key-input", source)
        self.assertIn("data-agent-custom-model-input", source)
        self.assertIn("customModelPlaceholder", source)
        self.assertIn("loomClient.wire.custom", source)
        self.assertIn("type=\"password\"", source)
        self.assertIn("autoComplete=\"off\"", source)
        self.assertIn("managedBy === 'heang_account'", source)
        self.assertIn("登录后解锁", source)
        self.assertIn("loomClient.components.modelConfigStatus", source)
        self.assertIn("loomClient.components.applyModelConfig", source)
        self.assertIn("Codex / Claude Code 模型", source)

    def test_openclaw_exposes_one_click_model_config_and_web_entry(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("new Set(['codex-desktop', 'claude-code', 'openclaw-companion'])", source)
        self.assertIn("data-agent-open-web-button", source)
        self.assertIn("openWeb(selected)", source)
        self.assertIn("isOpenClawComponent(selected)", source)

    def test_openclaw_web_entry_checks_or_starts_local_service_before_opening(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("OPENCLAW_WEB_URL", source)
        self.assertIn("loomClient.process.status", source)
        self.assertIn("loomClient.process.start", source)
        self.assertIn("loomClient.process.waitForReady", source)
        self.assertIn("请先安装 OpenClaw", source)
        self.assertIn("OpenClaw 网页版已打开", source)
        self.assertIn("OpenClaw 网页版启动失败", source)

    def test_agent_detail_groups_uninstall_and_advanced_settings_like_demo_layout(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("data-agent-danger-zone", source)
        self.assertIn("卸载", source)
        self.assertIn("高级详情", source)
        self.assertIn("data-agent-advanced-settings", source)

    def test_component_warning_is_sanitized_before_ui_display(self) -> None:
        with open(API_FILE, "r", encoding="utf-8") as handle:
            source = handle.read()

        self.assertIn("sanitizeComponentSnapshot", source)
        self.assertIn("manifest_unavailable", source)
        self.assertIn("All manifest sources", source)
        self.assertIn("正式组件清单未就绪。当前仅支持本机检测", source)

    def test_install_actions_lock_when_formal_manifest_is_unavailable(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()
        with open(API_FILE, "r", encoding="utf-8") as handle:
            api_source = handle.read()

        self.assertIn("installLocked?: boolean", api_source)
        self.assertIn("manifestInstallLocked", page_source)
        self.assertIn("installActionsLocked", page_source)
        self.assertIn("安装清单未就绪，安装和启动暂不可用", page_source)
        self.assertIn("disabled={controlsLocked || installActionsLocked || !components.length}", page_source)
        self.assertIn("disabled={controlsLocked || installActionsLocked || isWorking(selected.status)}", page_source)

    def test_install_actions_lock_while_manifest_is_loading(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("if (!snapshot) return true", page_source)

    def test_first_open_does_not_run_sequential_auto_detect_scan(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertNotIn("AUTO_DETECT_COMPONENT_IDS", page_source)
        self.assertNotIn("autoDetectAttempted", page_source)
        self.assertNotIn("shouldAutoDetectOnFirstOpen", page_source)
        self.assertNotIn("for (const component of targets)", page_source)
        self.assertNotIn("loomClient.components.install(component.id, { confirmed: false", page_source)

    def test_preflight_uses_quick_prerequisite_api_and_scoped_repair(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("loomClient.diagnostics.prerequisites()", page_source)
        self.assertIn("loomClient.diagnostics.repairPrerequisites()", page_source)
        self.assertNotIn("loomClient.diagnostics.run()", page_source)
        self.assertNotIn("loomClient.diagnostics.repair({ confirmed: true })", page_source)

    def test_job_polling_and_component_actions_are_scoped_to_active_component_jobs(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("data-installer-active-job", page_source)
        self.assertIn("activeJobComponentIds", page_source)
        self.assertIn("const componentJobBusy = activeJobComponentIds.size > 0", page_source)
        self.assertIn("const selectedBusy = Boolean(selected && activeJobComponentIds.has(selected.id))", page_source)
        self.assertIn("if (!jobs.some((job) => job.status === 'running' || job.status === 'queued')) return undefined;", page_source)
        self.assertIn("setSelectedId(component.id)", page_source)

    def test_first_open_uses_cached_preflight_until_user_refreshes(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()
        with open(STARTUP_CACHE_FILE, "r", encoding="utf-8") as handle:
            cache_source = handle.read()

        self.assertIn("loadCachedPreflight", page_source)
        self.assertIn("saveCachedPreflight", page_source)
        self.assertIn("preflightCacheUsable", page_source)
        self.assertIn("const reusablePreflight", page_source)
        self.assertIn("const cached = loadCachedPreflight()", page_source)
        self.assertIn("if (reusablePreflight)", page_source)
        self.assertIn("refreshPreflight({ preferCache: true })", page_source)
        self.assertIn("refreshPreflight({ force: true })", page_source)
        self.assertIn("measuredAt", page_source)
        self.assertIn("totalMs", page_source)
        self.assertIn("LOOM_PREFLIGHT_CACHE_KEY", cache_source)
        self.assertIn("STARTUP_CACHE_TTL_MS", cache_source)
        self.assertIn("PREFLIGHT_NON_OK_CACHE_TTL_MS", cache_source)
        self.assertIn("status === 'ok'", cache_source)
        self.assertIn("readCacheWithTtl<DiagnosticReport>(LOOM_PREFLIGHT_CACHE_KEY, PREFLIGHT_NON_OK_CACHE_TTL_MS)", cache_source)
        self.assertIn("Array.isArray(report.checks)", cache_source)

    def test_refresh_preflight_returns_immediately_on_cache_hit_without_prerequisite_recheck(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        cached_branch = """if (options.preferCache && cached) {
      cachedPreflight.current = cached;
      setPreflight(cached);
      setPreflightError('');
      setPreflightLoading(false);
      return;
    }"""
        self.assertIn(cached_branch, page_source)
        self.assertIn("const report = await loomClient.diagnostics.prerequisites();", page_source)

    def test_cached_preflight_is_not_rechecked_on_page_return_even_when_not_all_ok(self) -> None:
        with open(STARTUP_CACHE_FILE, "r", encoding="utf-8") as handle:
            cache_source = handle.read()

        self.assertIn("export const PREFLIGHT_NON_OK_CACHE_TTL_MS = STARTUP_CACHE_TTL_MS", cache_source)
        self.assertNotIn("5 * 60 * 1000", cache_source)

    def test_old_auto_detection_deep_scan_effect_is_removed(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertNotIn("pushLog(`自动检测", page_source)
        self.assertNotIn("for (const component of [])", page_source)
        self.assertNotIn("return;\n    void (async () => {", page_source)

    def test_agent_install_repairs_cached_missing_prerequisites_before_component_install(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("prerequisiteNeedsRepair", page_source)
        self.assertIn("blockingPrerequisiteIssues", page_source)
        self.assertIn("repairMissingPrerequisites", page_source)
        self.assertIn("await repairMissingPrerequisites", page_source)
        self.assertIn("const blocking = blockingPrerequisiteIssues(report, componentId)", page_source)

    def test_managed_codex_only_requires_bundled_core_prerequisites(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("COMPONENT_REQUIRED_PREREQ_IDS", page_source)
        self.assertIn("'codex-desktop': new Set(['python_runtime', 'data_dir'])", page_source)
        self.assertIn("requiredPrerequisiteIdsForComponent", page_source)
        self.assertIn("ensurePreflightReady(component.id)", page_source)
        self.assertIn("repairMissingPrerequisites(report, componentId)", page_source)
        self.assertIn("blockingPrerequisiteIssues(report, componentId)", page_source)

    def test_codex_install_retries_model_config_without_failing_the_binary_install(self) -> None:
        with open(AGENT_PAGE, "r", encoding="utf-8") as handle:
            page_source = handle.read()

        self.assertIn("ensureAgentModelConfig", page_source)
        self.assertIn("loomClient.components.applyModelConfig", page_source)
        self.assertIn("Codex 已安装，但模型配置尚未就绪", page_source)


if __name__ == "__main__":
    unittest.main()
