"""Matrix control plane FastAPI routes."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time

from fastapi import Request
from fastapi.responses import StreamingResponse

from api.routes_phone import (
    _ensure_phone_event_syncs_for_saved_devices,
    _phone_cli_failure_message,
    _phone_execution_contract,
    _phone_max_wait_for_layer,
    _phone_step_timeout_sec,
    _phone_task_tuning,
    _sanitize_cli_output,
    _script_path,
)
from core.phone_matrix import MatrixControlPlane, MatrixSafetyError


def register_matrix_routes(app, ctx) -> None:
    @app.api_route("/api/matrix/status", methods=["GET", "POST"])
    async def matrix_status(request: Request):
        if error := ctx.auth_error(request):
            return error
        _matrix_event_sync_best_effort(ctx)
        return ctx.fastapi_json(_matrix(ctx).status())

    @app.post("/api/matrix/device/register")
    async def matrix_device_register(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        device = _matrix(ctx).register_device(body)
        return ctx.fastapi_json({"device": device, "status": _matrix(ctx).status()})

    @app.post("/api/matrix/dispatch")
    async def matrix_dispatch(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        matrix = _matrix(ctx)
        try:
            task = matrix.dispatch(body)
        except MatrixSafetyError as exc:
            return ctx.fastapi_json({"error": exc.message, "code": exc.code}, 403)

        def run(job_id: str) -> dict:
            ctx.get_job_mgr().progress(
                job_id,
                "Matrix 任务已开始执行",
                "neutral",
                phase="matrix.dispatch.running",
                commandId="matrix.dispatch",
                campaignId=task.get("campaignId"),
            )
            return _run_matrix_campaign(ctx, matrix, task, body, job_id)

        job = ctx.get_job_mgr().submit_progress(
            "matrix.dispatch",
            "Matrix 任务派发",
            run,
            initial_progress={
                "message": "Matrix 任务已排队",
                "phase": "matrix.dispatch.queued",
                "commandId": "matrix.dispatch",
                "campaignId": task.get("campaignId"),
            },
        )
        return ctx.fastapi_json({"jobId": job.get("id"), "job": job, "task": task, "status": matrix.status()}, 202)

    @app.api_route("/api/matrix/watch", methods=["GET", "POST"])
    async def matrix_watch(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request) if request.method == "POST" else {}
        campaign_id = str(body.get("campaignId") or request.query_params.get("campaignId") or "").strip()
        limit_raw = body.get("limit") or request.query_params.get("limit") or 100
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 100
        return ctx.fastapi_json(_matrix(ctx).watch(campaign_id or None, limit=limit))

    @app.get("/api/matrix/events/stream")
    async def matrix_events_stream(request: Request):
        # Native EventSource cannot attach X-Bridge-Token. This stream is read-only
        # and the Bridge is bound to localhost; mutating actions still use protected HTTP.
        _matrix_event_sync_best_effort(ctx)
        once = str(request.query_params.get("once") or "").strip() == "1"
        try:
            interval_ms = int(request.query_params.get("intervalMs") or 1000)
        except (TypeError, ValueError):
            interval_ms = 1000
        interval_ms = max(300, min(5000, interval_ms))

        async def event_rows():
            last_payload = ""
            while True:
                payload = {
                    "schema": "loom.matrix.stream.v1",
                    "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
                    "status": _matrix(ctx).status(),
                    "events": _matrix(ctx).watch(limit=100).get("events", []),
                }
                text = json.dumps(payload, ensure_ascii=False)
                if once or text != last_payload:
                    yield _sse_event("matrix", payload)
                    last_payload = text
                if once:
                    break
                await asyncio.sleep(interval_ms / 1000)

        return StreamingResponse(
            event_rows(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "http://tauri.localhost",
            },
        )

    @app.post("/api/matrix/cancel")
    async def matrix_cancel(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        campaign_id = str(body.get("campaignId") or body.get("id") or "").strip()
        if not campaign_id:
            return ctx.fastapi_json({"error": "campaignId is required"}, 400)
        return ctx.fastapi_json(_matrix(ctx).cancel(campaign_id))

    @app.post("/api/matrix/retry")
    async def matrix_retry(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        campaign_id = str(body.get("campaignId") or body.get("id") or "").strip()
        if not campaign_id:
            return ctx.fastapi_json({"error": "campaignId is required"}, 400)
        matrix = _matrix(ctx)
        try:
            retry = matrix.retry_failed(campaign_id, body)
        except MatrixSafetyError as exc:
            return ctx.fastapi_json({"error": exc.message, "code": exc.code}, 403)
        task = retry.get("task") if isinstance(retry.get("task"), dict) else None
        dispatch_body = retry.get("dispatchBody") if isinstance(retry.get("dispatchBody"), dict) else body
        if not task:
            return ctx.fastapi_json({"retry": retry, "status": matrix.status()})

        def run(job_id: str) -> dict:
            ctx.get_job_mgr().progress(
                job_id,
                "Matrix 重试任务已开始执行",
                "neutral",
                phase="matrix.retry.running",
                commandId="matrix.retry",
                campaignId=task.get("campaignId"),
            )
            return _run_matrix_campaign(ctx, matrix, task, dispatch_body, job_id)

        job = ctx.get_job_mgr().submit_progress(
            "matrix.retry",
            "Matrix 任务重试",
            run,
            initial_progress={
                "message": "Matrix 重试任务已排队",
                "phase": "matrix.retry.queued",
                "commandId": "matrix.retry",
                "campaignId": task.get("campaignId"),
                "retryOf": campaign_id,
            },
        )
        return ctx.fastapi_json({"jobId": job.get("id"), "job": job, "retry": retry, "status": matrix.status()}, 202)

    @app.api_route("/api/matrix/leads", methods=["GET", "POST"])
    async def matrix_leads(request: Request):
        if error := ctx.auth_error(request):
            return error
        matrix = _matrix(ctx)
        if request.method == "GET":
            try:
                limit = int(request.query_params.get("limit") or 100)
            except (TypeError, ValueError):
                limit = 100
            return ctx.fastapi_json(matrix.list_leads(limit=limit))
        body = await ctx.body(request)
        return ctx.fastapi_json({"lead": matrix.record_lead(body), "leads": matrix.list_leads(limit=20)})

    @app.post("/api/matrix/template/run")
    async def matrix_template_run(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        template = str(body.get("template") or body.get("templateId") or "read-screen").strip()
        prompt = _template_prompt(template)
        payload = {
            **body,
            "template": template,
            "prompt": str(body.get("prompt") or prompt),
            "mode": str(body.get("mode") or ("observe" if template in {"read-screen", "screen-summary"} else "safe")),
            "profile": str(body.get("profile") or "fast"),
        }
        try:
            task = _matrix(ctx).dispatch(payload)
        except MatrixSafetyError as exc:
            return ctx.fastapi_json({"error": exc.message, "code": exc.code}, 403)
        return ctx.fastapi_json({"task": task, "status": _matrix(ctx).status()}, 202)

    @app.api_route("/api/matrix/experience", methods=["GET", "POST"])
    async def matrix_experience(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json(_matrix(ctx).experience_report())


def _matrix(ctx) -> MatrixControlPlane:
    return MatrixControlPlane(ctx.paths)


def _matrix_event_sync_best_effort(ctx) -> dict:
    try:
        return _ensure_phone_event_syncs_for_saved_devices(ctx)
    except Exception as exc:
        return {"started": False, "devices": [], "error": str(exc)[:200]}


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _run_matrix_campaign(ctx, matrix: MatrixControlPlane, task: dict, body: dict, job_id: str) -> dict:
    started = time.monotonic()
    results = []
    device_tasks = _matrix_device_tasks(task)
    if not device_tasks:
        return {"success": True, "task": task, "status": matrix.status(), "message": "没有可执行的目标设备"}
    for index, device_task in enumerate(device_tasks, start=1):
        device_task_id = str(device_task.get("deviceTaskId") or "")
        device_id = str(device_task.get("deviceId") or "")
        ctx.get_job_mgr().progress(
            job_id,
            f"正在执行 {device_id or index}",
            "neutral",
            phase="matrix.dispatch.device",
            commandId="matrix.dispatch",
            campaignId=task.get("campaignId"),
            deviceTaskId=device_task_id,
            deviceId=device_id,
        )
        result = _run_matrix_device_task(ctx, matrix, body, device_task)
        results.append(result)
    ok = all(item.get("success") for item in results)
    ctx.get_job_mgr().progress(
        job_id,
        "Matrix 任务执行完成" if ok else "Matrix 任务执行失败",
        "success" if ok else "danger",
        phase="matrix.dispatch.done" if ok else "matrix.dispatch.failed",
        commandId="matrix.dispatch",
        campaignId=task.get("campaignId"),
    )
    result = {
        "success": ok,
        "task": task,
        "status": matrix.status(),
        "results": results,
        "durationMs": int((time.monotonic() - started) * 1000),
    }
    _record_matrix_task_evidence(body, result, started)
    return result


def _matrix_device_tasks(task: dict) -> list[dict]:
    rows: list[dict] = []
    for mission in task.get("missions", []):
        for device_task in mission.get("deviceTasks", []):
            if isinstance(device_task, dict):
                rows.append(device_task)
    return rows


def _run_matrix_device_task(ctx, matrix: MatrixControlPlane, body: dict, device_task: dict) -> dict:
    device_task_id = str(device_task.get("deviceTaskId") or "")
    started = time.monotonic()
    try:
        matrix.mark_step(device_task_id, str(device_task.get("currentStep") or "step_prepare"), status="running", message="准备单机执行")
        command = _matrix_phone_command(ctx, body, device_task)
        matrix.append_task_event("step", device_task_id, f"{command['layer']} 路径已选择")
        completed = subprocess.run(
            [command["node"], command["script"], *command["args"]],
            cwd=ctx.paths.base_path,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=command["timeoutSec"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        stdout = _redact_matrix_output(_sanitize_cli_output(ctx, completed.stdout or "", kind="phone.task"))
        stderr = _redact_matrix_output(_sanitize_cli_output(ctx, completed.stderr or "", kind="phone.task"))
        ok = completed.returncode == 0
        error = "" if ok else _phone_cli_failure_message(stdout, stderr)
        duration_ms = int((time.monotonic() - started) * 1000)
        matrix.record_result(device_task_id, ok=ok, duration_ms=duration_ms, failure_reason=error)
        return {
            "success": ok,
            "deviceTaskId": device_task_id,
            "deviceId": device_task.get("deviceId"),
            "executionLayer": command["layer"],
            "script": os.path.basename(command["script"]),
            "durationMs": duration_ms,
            "error": error,
            "stdoutPreview": stdout[:800],
            "stderrPreview": stderr[:800],
        }
    except subprocess.TimeoutExpired as exc:
        stdout = _redact_matrix_output(_sanitize_cli_output(ctx, exc.stdout if isinstance(exc.stdout, str) else "", kind="phone.task"))
        stderr = _redact_matrix_output(_sanitize_cli_output(ctx, exc.stderr if isinstance(exc.stderr, str) else "", kind="phone.task"))
        error = "手机任务执行超时，请检查手机连接、锁屏状态和 APKClaw 运行状态。"
        duration_ms = int((time.monotonic() - started) * 1000)
        matrix.record_result(device_task_id, ok=False, duration_ms=duration_ms, failure_reason=error)
        return {
            "success": False,
            "deviceTaskId": device_task_id,
            "deviceId": device_task.get("deviceId"),
            "durationMs": duration_ms,
            "error": error,
            "stdoutPreview": stdout[:800],
            "stderrPreview": stderr[:800],
        }
    except Exception as exc:
        error = _redact_matrix_output(str(exc))[:300]
        duration_ms = int((time.monotonic() - started) * 1000)
        matrix.record_result(device_task_id, ok=False, duration_ms=duration_ms, failure_reason=error)
        return {
            "success": False,
            "deviceTaskId": device_task_id,
            "deviceId": device_task.get("deviceId"),
            "durationMs": duration_ms,
            "error": error,
        }


def _matrix_phone_command(ctx, body: dict, device_task: dict) -> dict:
    node_exe = str(getattr(ctx.paths, "node_exe", "") or "")
    if not node_exe or not os.path.exists(node_exe):
        raise RuntimeError("Node.js 运行时缺失，无法执行手机任务")
    layer = str(device_task.get("executionLayer") or body.get("executionLayer") or "agent")
    mode = str(device_task.get("mode") or body.get("mode") or "safe")
    profile = str(device_task.get("profile") or body.get("profile") or "fast")
    prompt = str(body.get("prompt") or "")
    template = str(device_task.get("template") or body.get("template") or "")
    direct_action = str(device_task.get("directAction") or body.get("action") or "")
    timeout_sec, max_wait_sec, max_rounds, poll_ms = _phone_task_tuning(mode, profile, body)
    step_timeout_sec = _phone_step_timeout_sec(layer, profile)
    max_wait_sec = _phone_max_wait_for_layer(layer, profile, max_wait_sec, max_rounds, step_timeout_sec)
    device_args = ["--device-id", str(device_task.get("deviceId") or "")] if device_task.get("deviceId") else []
    execution = _phone_execution_contract(
        layer=layer,
        profile=profile,
        mode=mode,
        timeout_sec=timeout_sec,
        max_wait_sec=max_wait_sec,
        max_rounds=max_rounds,
        poll_ms=poll_ms,
        step_timeout_sec=step_timeout_sec,
        direct_action=direct_action,
        template_name=template,
    )
    if layer == "direct" and direct_action:
        action_body = {
            "action": direct_action,
            "targetLabel": "system navigation",
            "reason": "LOOM Matrix direct action",
        }
        script = _script_path(ctx, "openclaw-phone-vision.mjs")
        args = [
            "action",
            *device_args,
            "--force-action",
            "--allow-unknown-target",
            "--action-body",
            json.dumps(action_body, ensure_ascii=False),
            "--json",
        ]
    elif layer == "direct" or template in {"read-screen", "screen-summary"}:
        script = _script_path(ctx, "openclaw-phone-vision.mjs")
        args = ["read", *device_args, "--prompt", prompt, "--json"]
        max_wait_sec = min(max_wait_sec, 25)
    else:
        script = _script_path(ctx, "openclaw-phone-agent.mjs")
        args = [
            "run",
            *device_args,
            "--prompt",
            prompt,
            "--mode",
            mode,
            "--timeout-sec",
            str(timeout_sec),
            "--max-wait-sec",
            str(max_wait_sec),
            "--max-rounds",
            str(max_rounds),
            "--poll-ms",
            str(poll_ms),
            "--execution-layer",
            "template" if layer == "template" else "agent",
            "--step-timeout-sec",
            str(step_timeout_sec),
            "--json",
        ]
        if template:
            args.extend(["--template", template])
    if not os.path.exists(script):
        raise RuntimeError("手机能力脚本缺失")
    return {
        "node": node_exe,
        "script": script,
        "args": args,
        "layer": layer,
        "timeoutSec": max(5, min(max_wait_sec + 5, 1800)),
        "execution": execution,
    }


def _redact_matrix_output(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"sk-[A-Za-z0-9_\-]{4,}", "sk-***", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", text, flags=re.I)
    text = re.sub(r'("(?:token|secret|password|apiKey|api_key)"\s*:\s*)"[^"]+"', r'\1"***"', text, flags=re.I)
    return text


def _record_matrix_task_evidence(body: dict, result: dict, started_at: float) -> None:
    try:
        from loom_cli import _write_task_evidence

        ok = result.get("success") is True
        payload = {
            "ok": ok,
            "command": "matrix.dispatch",
            "data": {
                "method": "POST",
                "endpoint": "/api/matrix/dispatch",
                "body": _redact_matrix_json(body),
                "result": _redact_matrix_json(result),
            },
        }
        if not ok:
            payload["error"] = {"code": "matrix_dispatch_failed", "message": "Matrix 任务执行失败"}
        evidence_ctx = type("BridgeEvidenceContext", (), {"permission": "control", "source": "bridge"})()
        _write_task_evidence(
            ["matrix.dispatch"],
            "matrix.dispatch",
            evidence_ctx,
            payload,
            (time.monotonic() - started_at) * 1000,
            source="bridge",
        )
    except Exception:
        return


def _redact_matrix_json(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(mark in lowered for mark in ("token", "secret", "password", "apikey", "api_key", "credential")):
                safe[str(key)] = "***"
            else:
                safe[str(key)] = _redact_matrix_json(item)
        return safe
    if isinstance(value, list):
        return [_redact_matrix_json(item) for item in value[:200]]
    if isinstance(value, str):
        return _redact_matrix_output(value)
    return value


def _template_prompt(template: str) -> str:
    if template == "screen-summary":
        return "读取当前页面，返回页面名称和三个可见按钮。"
    if template == "back":
        return "返回上一页"
    if template == "home":
        return "回到桌面"
    if template == "open-settings":
        return "打开系统设置"
    return "读取当前手机屏幕，返回当前页面名称和三个可见内容。"
