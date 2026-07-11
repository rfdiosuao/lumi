"""Installable component routes for the launcher bridge."""

from __future__ import annotations

import threading

from fastapi import Request

from core.component_catalog import ComponentCatalog, default_component_state_path, default_manifest_path, load_installable_manifest
from core.component_installer import ComponentInstallError, ComponentInstaller
from core.component_state import ComponentState, ComponentStateStore
from core.release_manifest import ReleaseComponent, default_release_manifest_public_key, load_release_manifest_file
from core.wire_config import WireConfigError


RUNNING_JOB_STATUSES = {"queued", "running"}

SIMULATION_COMPONENTS: dict[str, ReleaseComponent] = {
    "codex-desktop": ReleaseComponent(
        component_id="codex-desktop",
        name="Codex 桌面端",
        version="待正式清单",
        platform="windows",
        arch="x64",
        archive_type="installer",
        size=1,
        sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        urls=(),
        install_path="agents/codex-desktop",
        entry=None,
        category="agent",
        description="OpenAI Codex 桌面应用",
    ),
    "claude-code": ReleaseComponent(
        component_id="claude-code",
        name="Claude Code",
        version="待正式清单",
        platform="windows",
        arch="x64",
        archive_type="tgz",
        size=1,
        sha256="123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
        urls=(),
        install_path="agents/claude-code",
        entry="claude-code.tgz",
        category="agent",
        description="Anthropic 命令行编程智能体",
    ),
    "opencode": ReleaseComponent(
        component_id="opencode",
        name="opencode",
        version="待正式清单",
        platform="windows",
        arch="x64",
        archive_type="zip",
        size=1,
        sha256="23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01",
        urls=(),
        install_path="agents/opencode",
        entry="package/bin/opencode.exe",
        category="agent",
        description="终端优先 AI 编程工具",
    ),
    "openclaw-companion": ReleaseComponent(
        component_id="openclaw-companion",
        name="OpenClaw 兼容运行时",
        version="待正式清单",
        platform="windows",
        arch="x64",
        archive_type="installer",
        size=1,
        sha256="3456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef012",
        urls=(),
        install_path="agents/openclaw-companion",
        entry="package/openclaw.mjs",
        category="agent",
        description="协议兼容组件",
    ),
    "hermes": ReleaseComponent(
        component_id="hermes",
        name="Hermes",
        version="待正式清单",
        platform="windows",
        arch="x64",
        archive_type="installer",
        size=1,
        sha256="456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123",
        urls=(),
        install_path="agents/hermes",
        entry="Hermes-Setup.exe",
        category="agent",
        description="Hermes 智能体运行时",
    ),
}


def _resolve_component_for_action(
    manifest_path: str,
    component_id: str,
    *,
    allow_fallback: bool,
) -> tuple[ReleaseComponent | None, str | None]:
    try:
        manifest, _manifest_warning = load_installable_manifest(manifest_path)
        component = manifest.component_by_id(component_id)
        if component is None:
            return None, f"Unknown component: {component_id}"
        return component, None
    except Exception as manifest_error:
        if allow_fallback:
            component = SIMULATION_COMPONENTS.get(component_id)
            if component is not None:
                return component, f"正式组件清单未就绪：release-manifest.json：{manifest_error}"
        return None, f"正式安装需要 release-manifest.json：{manifest_error}"


def _component_error_status(error: str | None) -> int:
    return 404 if str(error or "").startswith("Unknown component") else 400


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def register_component_routes(app, ctx) -> None:
    start_jobs_lock = threading.Lock()
    active_start_jobs: dict[str, str] = {}

    @app.api_route("/api/components/status", methods=["GET", "POST"])
    async def components_status(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json(_component_catalog(ctx).status())

    @app.get("/api/components/model-config/status")
    async def components_model_config_status(request: Request):
        if error := ctx.auth_error(request):
            return error
        component_id = str(request.query_params.get("componentId") or request.query_params.get("id") or "").strip()
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        status = _model_config_status(ctx, component_id)
        return ctx.fastapi_json({"status": status})

    @app.post("/api/components/model-config/apply")
    async def components_model_config_apply(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        model = str(body.get("model") or "").strip()
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        if not _truthy(body.get("confirmed")):
            return ctx.fastapi_json({"error": "写入模型配置需要确认"}, 403)
        current = _model_config_status(ctx, component_id)
        if current.get("installed") is False:
            return ctx.fastapi_json({"error": "请先安装或检测该智能体", "status": current}, 400)
        try:
            status = ctx.get_wire_svc().sync_agent_model_config(component_id, model=model)
        except WireConfigError as exc:
            failed = _model_config_status(ctx, component_id)
            failed["status"] = "failed"
            failed["message"] = str(exc)
            return ctx.fastapi_json({"error": str(exc), "status": failed}, 400)
        status = dict(status)
        status["installed"] = current.get("installed")
        status["componentStatus"] = current.get("componentStatus")
        return ctx.fastapi_json({"status": status})

    @app.post("/api/components/model-config/rollback")
    async def components_model_config_rollback(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        if not _truthy(body.get("confirmed")):
            return ctx.fastapi_json({"error": "回滚模型配置需要确认"}, 403)
        try:
            status = ctx.get_wire_svc().rollback_agent_model_config(component_id)
        except WireConfigError as exc:
            failed = _model_config_status(ctx, component_id)
            failed["status"] = "failed"
            failed["message"] = str(exc)
            return ctx.fastapi_json({"error": str(exc), "status": failed}, 400)
        return ctx.fastapi_json({"status": _with_install_state(ctx, component_id, status)})

    @app.post("/api/components/install")
    async def components_install(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        mode = str(body.get("mode") or "").strip().lower()
        simulate = bool(body.get("dryRun")) or mode == "simulate"
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        if not simulate and not _truthy(body.get("confirmed")):
            return ctx.fastapi_json({"error": "安装组件需要确认"}, 403)

        manifest_path = default_manifest_path(ctx.paths.base_path)
        state_store = _component_state_store(ctx)
        existing_state = state_store.load().get(component_id)
        if existing_state and existing_state.job_id:
            existing_job = ctx.get_job_mgr().get(existing_state.job_id)
            if existing_job and str(existing_job.get("status") or "").lower() in RUNNING_JOB_STATUSES:
                return ctx.fastapi_json({
                    "jobId": existing_state.job_id,
                    "job": existing_job,
                    "state": existing_state.to_json(),
                    "catalog": _component_catalog(ctx).status(),
                }, 202)

        try:
            component, manifest_error = _resolve_component_for_action(
                manifest_path,
                component_id,
                allow_fallback=simulate,
            )
            if component is None:
                return ctx.fastapi_json({"error": manifest_error or f"Unknown component: {component_id}"}, _component_error_status(manifest_error))

            if not simulate:
                state_store.mark(component.component_id, "resolving_manifest", version=component.version)
            job_mgr = ctx.get_job_mgr()

            def run(job_id: str) -> dict:
                def on_progress(message: str, tone: str = "neutral") -> None:
                    job_mgr.progress(job_id, message, tone, componentId=component.component_id)
                    ctx.append_log(f"[Components] {component.component_id}: {message}\n")

                installer = _component_installer(ctx)
                state = installer.install(component, simulate=simulate, job_id=job_id, on_progress=on_progress)
                return {
                    "success": True,
                    "state": state.to_json(),
                    "catalog": _component_catalog(ctx).status(state_overrides=[state] if simulate else []),
                }

            job_kind = "component.install.simulate" if simulate else "component.install"
            job_label = f"Dry run install {component.name}" if simulate else f"Install {component.name}"
            job = job_mgr.submit_progress(job_kind, job_label, run)
            current_state = ComponentState(component.component_id, "resolving_manifest", version=component.version, job_id=str(job.get("id") or "")) if simulate else state_store.load().get(component.component_id)
            if not simulate and current_state and current_state.status == "resolving_manifest":
                current_state = state_store.mark(component.component_id, "resolving_manifest", version=component.version, job_id=str(job.get("id") or ""))
            return ctx.fastapi_json({
                "jobId": job.get("id"),
                "job": job,
                "state": current_state.to_json() if current_state else None,
                "catalog": _component_catalog(ctx).status(),
            }, 202)
        except ComponentInstallError as exc:
            return ctx.fastapi_json({"error": str(exc), "catalog": _component_catalog(ctx).status()}, 500)
        except Exception as exc:
            ctx.append_log(f"[Components] install failed: {exc}\n")
            return ctx.fastapi_json({"error": str(exc)}, 500)

    @app.post("/api/components/detect")
    async def components_detect(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        force_external_probe = _truthy(body.get("force"))
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)

        manifest_path = default_manifest_path(ctx.paths.base_path)
        component, manifest_error = _resolve_component_for_action(manifest_path, component_id, allow_fallback=False)
        if component is None:
            return ctx.fastapi_json({"error": manifest_error or f"Unknown component: {component_id}"}, _component_error_status(manifest_error))

        job_mgr = ctx.get_job_mgr()

        def run(job_id: str) -> dict:
            def on_progress(message: str, tone: str = "neutral") -> None:
                job_mgr.progress(job_id, message, tone, componentId=component.component_id)
                ctx.append_log(f"[Components] {component.component_id}: {message}\n")

            installer = _component_installer(ctx)
            try:
                state = installer.detect(
                    component,
                    job_id=job_id,
                    on_progress=on_progress,
                    force_external_probe=force_external_probe,
                )
            except ComponentInstallError as exc:
                return {
                    "success": False,
                    "error": str(exc),
                    "catalog": _component_catalog(ctx).status(),
                }
            return {
                "success": True,
                "state": state.to_json(),
                "catalog": _component_catalog(ctx).status(),
                "manifestWarning": manifest_error,
            }

        job = job_mgr.submit_progress("component.detect", f"Detect {component.name}", run)
        current_state = ComponentState(component.component_id, "health_checking", version=component.version, job_id=str(job.get("id") or ""))
        return ctx.fastapi_json({
            "jobId": job.get("id"),
            "job": job,
            "state": current_state.to_json(),
            "catalog": _component_catalog(ctx).status(state_overrides=[current_state]),
            "manifestWarning": manifest_error,
        }, 202)

    @app.post("/api/components/start")
    async def components_start(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        if not _truthy(body.get("confirmed")):
            return ctx.fastapi_json({"error": "启动组件需要确认"}, 403)

        job_mgr = ctx.get_job_mgr()
        state_store = _component_state_store(ctx)
        with start_jobs_lock:
            existing_state = state_store.load().get(component_id)
            existing_job_id = active_start_jobs.get(component_id) or (existing_state.job_id if existing_state else None)
            if existing_job_id:
                existing_job = job_mgr.get(existing_job_id)
                if existing_job and str(existing_job.get("status") or "").lower() in RUNNING_JOB_STATUSES:
                    return ctx.fastapi_json({
                        "jobId": existing_job_id,
                        "job": existing_job,
                        "state": existing_state.to_json() if existing_state else None,
                        "catalog": _component_catalog(ctx).status(),
                    }, 202)
                active_start_jobs.pop(component_id, None)

        manifest_path = default_manifest_path(ctx.paths.base_path)
        component, manifest_error = _resolve_component_for_action(manifest_path, component_id, allow_fallback=False)
        if component is None:
            return ctx.fastapi_json({"error": manifest_error or f"Unknown component: {component_id}"}, _component_error_status(manifest_error))

        registration_ready = threading.Event()

        def run(job_id: str) -> dict:
            registration_ready.wait(2.0)
            try:
                job_mgr.progress(job_id, f"启动 {component.name}", "neutral", componentId=component.component_id)
                ctx.append_log(f"[Components] {component.component_id}: 启动 {component.name}\n")
                try:
                    launch = _component_installer(ctx).launch(component, job_id=job_id)
                except ComponentInstallError as exc:
                    return {
                        "success": False,
                        "error": str(exc),
                        "catalog": _component_catalog(ctx).status(),
                    }
                return {
                    "success": True,
                    "launch": launch,
                    "catalog": _component_catalog(ctx).status(),
                    "manifestWarning": manifest_error,
                }
            finally:
                with start_jobs_lock:
                    if active_start_jobs.get(component_id) == job_id:
                        active_start_jobs.pop(component_id, None)

        with start_jobs_lock:
            existing_job_id = active_start_jobs.get(component_id)
            existing_state = state_store.load().get(component_id)
            if not existing_job_id and existing_state and existing_state.job_id:
                existing_job_id = existing_state.job_id
            if existing_job_id:
                existing_job = job_mgr.get(existing_job_id)
                if existing_job and str(existing_job.get("status") or "").lower() in RUNNING_JOB_STATUSES:
                    current_state = existing_state or ComponentState(
                        component.component_id,
                        "starting",
                        version=component.version,
                        job_id=existing_job_id,
                    )
                    return ctx.fastapi_json({
                        "jobId": existing_job_id,
                        "job": existing_job,
                        "state": current_state.to_json(),
                        "catalog": _component_catalog(ctx).status(state_overrides=[current_state]),
                    }, 202)
                active_start_jobs.pop(component_id, None)

            job = job_mgr.submit_progress("component.start", f"Start {component.name}", run)
            job_id = str(job.get("id") or "")
            active_start_jobs[component_id] = job_id
            current_state = state_store.mark(
                component.component_id,
                "starting",
                version=component.version,
                job_id=job_id,
            )
            registration_ready.set()
        return ctx.fastapi_json({
            "jobId": job_id,
            "job": job,
            "state": current_state.to_json(),
            "catalog": _component_catalog(ctx).status(state_overrides=[current_state]),
            "manifestWarning": manifest_error,
        }, 202)

    @app.post("/api/components/uninstall")
    async def components_uninstall(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        if not _truthy(body.get("confirmed")):
            return ctx.fastapi_json({"error": "卸载组件需要确认"}, 403)

        manifest_path = default_manifest_path(ctx.paths.base_path)
        component, manifest_error = _resolve_component_for_action(manifest_path, component_id, allow_fallback=False)
        if component is None:
            return ctx.fastapi_json({"error": manifest_error or f"Unknown component: {component_id}"}, _component_error_status(manifest_error))

        state_store = _component_state_store(ctx)
        existing_state = state_store.load().get(component_id)
        if existing_state and existing_state.job_id:
            existing_job = ctx.get_job_mgr().get(existing_state.job_id)
            if existing_job and str(existing_job.get("status") or "").lower() in RUNNING_JOB_STATUSES:
                return ctx.fastapi_json({
                    "jobId": existing_state.job_id,
                    "job": existing_job,
                    "state": existing_state.to_json(),
                    "catalog": _component_catalog(ctx).status(),
                }, 202)

        job_mgr = ctx.get_job_mgr()

        def run(job_id: str) -> dict:
            def on_progress(message: str, tone: str = "neutral") -> None:
                job_mgr.progress(job_id, message, tone, componentId=component.component_id)
                ctx.append_log(f"[Components] {component.component_id}: {message}\n")

            try:
                state = _component_installer(ctx).uninstall(component, job_id=job_id, on_progress=on_progress)
            except ComponentInstallError as exc:
                return {
                    "success": False,
                    "error": str(exc),
                    "catalog": _component_catalog(ctx).status(),
                }
            return {
                "success": True,
                "state": state.to_json(),
                "catalog": _component_catalog(ctx).status(),
                "manifestWarning": manifest_error,
            }

        job = job_mgr.submit_progress("component.uninstall", f"Uninstall {component.name}", run)
        current_state = state_store.mark(component.component_id, "uninstalling", version=component.version, job_id=str(job.get("id") or ""))
        return ctx.fastapi_json({
            "jobId": job.get("id"),
            "job": job,
            "state": current_state.to_json(),
            "catalog": _component_catalog(ctx).status(state_overrides=[current_state]),
            "manifestWarning": manifest_error,
        }, 202)

    @app.post("/api/components/rollback")
    async def components_rollback(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        component_id = str(body.get("componentId") or body.get("id") or "").strip()
        if not component_id:
            return ctx.fastapi_json({"error": "componentId is required"}, 400)
        if not _truthy(body.get("confirmed")):
            return ctx.fastapi_json({"error": "回滚组件需要确认"}, 403)

        state_store = _component_state_store(ctx)
        existing_state = state_store.load().get(component_id)
        if existing_state and existing_state.job_id:
            existing_job = ctx.get_job_mgr().get(existing_state.job_id)
            if existing_job and str(existing_job.get("status") or "").lower() in RUNNING_JOB_STATUSES:
                return ctx.fastapi_json({
                    "jobId": existing_state.job_id,
                    "job": existing_job,
                    "state": existing_state.to_json(),
                    "catalog": _component_catalog(ctx).status(),
                }, 202)

        job_mgr = ctx.get_job_mgr()

        def run(job_id: str) -> dict:
            job_mgr.progress(job_id, f"回滚 {component_id}", "neutral", phase="rollback", componentId=component_id)
            ctx.append_log(f"[Components] {component_id}: 回滚\n")
            try:
                state = _component_installer(ctx).rollback(component_id)
            except ComponentInstallError as exc:
                failed = state_store.mark(
                    component_id,
                    "rollback_failed",
                    job_id=job_id,
                    error_code="rollback_failed",
                    error_message=str(exc),
                )
                return {
                    "success": False,
                    "error": str(exc),
                    "state": failed.to_json(),
                    "catalog": _component_catalog(ctx).status(),
                }
            return {
                "success": True,
                "state": state.to_json(),
                "catalog": _component_catalog(ctx).status(),
            }

        job = job_mgr.submit_progress("component.rollback", f"Rollback {component_id}", run)
        current_state = state_store.mark(component_id, "rolling_back", job_id=str(job.get("id") or ""))
        return ctx.fastapi_json({
            "jobId": job.get("id"),
            "job": job,
            "state": current_state.to_json(),
            "catalog": _component_catalog(ctx).status(state_overrides=[current_state]),
        }, 202)


def _component_catalog(ctx) -> ComponentCatalog:
    return ComponentCatalog(
        manifest_path=default_manifest_path(ctx.paths.base_path),
        state_store=_component_state_store(ctx),
        fallback_components=SIMULATION_COMPONENTS.values(),
    )


def _component_installer(ctx) -> ComponentInstaller:
    return ComponentInstaller(
        base_path=ctx.paths.base_path,
        state_store=_component_state_store(ctx),
    )


def _component_state_store(ctx) -> ComponentStateStore:
    return ComponentStateStore(default_component_state_path(ctx.paths.base_path))


def _model_config_status(ctx, component_id: str) -> dict:
    status = ctx.get_wire_svc().agent_model_config_status(component_id)
    return _with_install_state(ctx, component_id, status)


def _with_install_state(ctx, component_id: str, status: dict) -> dict:
    item = _component_by_id(ctx, component_id)
    component_status = str((item or {}).get("status") or "not_installed")
    installed = component_status in {"ready", "started", "upgrade_available"}
    result = dict(status)
    result["installed"] = installed
    result["componentStatus"] = component_status
    if result.get("supported") and not installed:
        result["configured"] = False
        result["status"] = "not_installed"
        result["message"] = "请先安装或检测该智能体"
    return result


def _component_by_id(ctx, component_id: str) -> dict | None:
    try:
        for item in _component_catalog(ctx).status().get("components", []):
            if item.get("id") == component_id:
                return item
    except Exception:
        return None
    return None
