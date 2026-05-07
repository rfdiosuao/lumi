"""FastAPI route registration for the launcher bridge."""

from __future__ import annotations

import base64
import datetime
import json
import os
import subprocess
import traceback
import zipfile

from fastapi import Request

from core.license_manager import LicenseError
from services.image_api import ImageApiError
from services.skills import SkillError
from services.video_api import VideoApiError


def register_fastapi_routes(app, ctx) -> None:
    """Register all native FastAPI endpoints.

    The bridge still owns service construction and shared state; this module
    owns only HTTP route wiring so the bridge entrypoint stays readable.
    """

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        ctx.append_log(f"[Bridge Error] {request.url.path}: {exc}\n{traceback.format_exc()}\n")
        return ctx.fastapi_json({"error": str(exc)}, 500)

    @app.api_route("/api/system/info", methods=["GET", "POST"])
    async def system_info(request: Request):
        if error := ctx.auth_error(request):
            return error
        updater = ctx.get_updater()
        return ctx.fastapi_json({
            "node_path": ctx.paths.node_exe,
            "base_path": ctx.paths.base_path,
            "openclaw_version": updater.current_version(),
        })

    @app.api_route("/api/process/status", methods=["GET", "POST"])
    async def process_status(request: Request):
        if error := ctx.auth_error(request):
            return error
        svc = ctx.get_process_svc()
        return ctx.fastapi_json({
            "running": svc.running,
            "pid": svc.process.pid if svc.process and svc.process.poll() is None else None,
        })

    @app.post("/api/process/start")
    async def process_start(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/process/start"):
            return error

        svc = ctx.get_process_svc()
        if svc.running:
            return ctx.fastapi_json({"status": "already_running"})

        def on_exit(code: int | None) -> None:
            ctx.append_log(f"\n[OpenClaw] Process ended (exit: {code})\n")

        svc.start(on_exit=on_exit)
        return ctx.fastapi_json({"status": "started", "pid": svc.process.pid if svc.process else None})

    @app.post("/api/process/stop")
    async def process_stop(request: Request):
        if error := ctx.auth_error(request):
            return error
        message = ctx.get_process_svc().stop()
        return ctx.fastapi_json({"status": "stopped", "message": message})

    @app.api_route("/api/log/get", methods=["GET", "POST"])
    async def log_get(request: Request):
        if error := ctx.auth_error(request):
            return error
        with ctx.log_lock:
            text = "".join(ctx.log_buffer)
        return ctx.fastapi_json({"log": text})

    @app.post("/api/log/clear")
    async def log_clear(request: Request):
        if error := ctx.auth_error(request):
            return error
        with ctx.log_lock:
            ctx.log_buffer.clear()
        return ctx.fastapi_json({"status": "cleared"})

    @app.api_route("/api/license/current", methods=["GET", "POST"])
    async def license_current(request: Request):
        if error := ctx.auth_error(request):
            return error
        license_data = ctx.get_license_mgr().current_license()
        return ctx.fastapi_json({"license": license_data})

    @app.post("/api/license/authorized")
    async def license_authorized(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        return ctx.fastapi_json({"authorized": ctx.get_license_mgr().is_authorized(body.get("feature"))})

    @app.post("/api/license/activate")
    async def license_activate(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        code = body.get("code", "")
        if not code:
            return ctx.fastapi_json({"error": "授权码不能为空"}, 400)
        try:
            result = ctx.get_license_mgr().activate(code)
            theme = ctx.get_theme_mgr().get_current(ctx.get_license_mgr().current_license())
            return ctx.fastapi_json({"license": result, "theme": theme})
        except LicenseError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)

    @app.post("/api/image/generate")
    async def image_generate(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/image/generate"):
            return error

        body = await ctx.body(request)
        client = ctx.get_image_client()
        base_url = body.get("baseUrl", "")
        api_key = body.get("apiKey", "")
        prompt = body.get("prompt", "")
        size = body.get("size", "1024x1024")
        edit_path = body.get("editImagePath")
        count = body.get("count", 1)

        if not base_url:
            return ctx.fastapi_json({"error": "中转站地址不能为空"}, 400)
        if not prompt:
            return ctx.fastapi_json({"error": "提示词不能为空"}, 400)

        temp_file: str | None = None
        if edit_path and edit_path.startswith("data:"):
            try:
                edit_path, temp_file = ctx.data_url_to_temp_file(edit_path)
            except ValueError as exc:
                return ctx.fastapi_json({"error": str(exc)}, 400)

        try:
            results = client.generate_many(base_url, api_key, prompt, size, count=count, edit_image_path=edit_path)
            images_b64 = [base64.b64encode(result).decode() for result in results]
            return ctx.fastapi_json({"images": images_b64, "count": len(images_b64)})
        except ImageApiError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 500)
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    @app.post("/api/video/generate")
    async def video_generate(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/video/generate"):
            return error

        body = await ctx.body(request)
        client = ctx.get_video_client()
        provider_id = body.get("providerId", "dashscope")
        api_base = body.get("apiBase", "")
        model = body.get("model", "")
        dash_key = body.get("dashKey", "")
        prompt = body.get("prompt", "")
        mode = body.get("mode", "t2v")
        resolution = body.get("resolution", "720P")
        duration = body.get("duration", 5)
        ratio = body.get("ratio", "16:9")
        image_path = body.get("imagePath")

        if not dash_key:
            return ctx.fastapi_json({"error": "视频服务密钥不能为空"}, 400)
        if not prompt:
            return ctx.fastapi_json({"error": "提示词不能为空"}, 400)

        temp_file: str | None = None
        if image_path and image_path.startswith("data:"):
            try:
                image_path, temp_file = ctx.data_url_to_temp_file(image_path)
            except ValueError as exc:
                return ctx.fastapi_json({"error": str(exc)}, 400)

        try:
            video_bytes = client.generate(
                dash_key,
                prompt,
                mode,
                resolution,
                duration,
                ratio,
                image_path,
                provider_id=provider_id,
                api_base=api_base,
                model=model,
            )
            video_dir = os.path.join(ctx.paths.data_dir, "videos")
            os.makedirs(video_dir, exist_ok=True)
            filename = f"lumi-video-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
            save_path = os.path.join(video_dir, filename)
            with open(save_path, "wb") as file:
                file.write(video_bytes)
            return ctx.fastapi_json({
                "video": base64.b64encode(video_bytes).decode(),
                "mime": "video/mp4",
                "size": len(video_bytes),
                "path": save_path,
                "directory": video_dir,
                "filename": filename,
            })
        except VideoApiError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 500)
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    @app.api_route("/api/theme/current", methods=["GET", "POST"])
    async def theme_current(request: Request):
        if error := ctx.auth_error(request):
            return error
        license_data = ctx.get_license_mgr().current_license()
        theme = ctx.get_theme_mgr().get_current(license_data)
        return ctx.fastapi_json({"theme": theme})

    @app.post("/api/theme/by_merchant")
    async def theme_by_merchant(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        merchant_id = body.get("merchantId", "")
        if not merchant_id:
            return ctx.fastapi_json({"error": "merchantId 不能为空"}, 400)
        theme = ctx.get_theme_mgr().get_by_merchant(merchant_id)
        if theme is None:
            return ctx.fastapi_json({"error": f"未找到商户 {merchant_id} 的主题"}, 404)
        return ctx.fastapi_json({"theme": theme})

    @app.api_route("/api/theme/list", methods=["GET", "POST"])
    async def theme_list(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json({"themes": ctx.get_theme_mgr().list_themes()})

    @app.post("/api/config/read")
    async def config_read(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        safe = ctx.safe_config_path(body.get("path", ""))
        if safe is None:
            return ctx.fastapi_json({"error": "路径不在允许的范围内"}, 403)
        return ctx.fastapi_json({"data": ctx.read_json(safe, body.get("default", {}))})

    @app.post("/api/config/write")
    async def config_write(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        file_path = body.get("path", "")
        safe = ctx.safe_config_path(file_path)
        if safe is None:
            return ctx.fastapi_json({"error": "路径不在允许的范围内"}, 403)
        ctx.write_json(safe, body["data"])
        if file_path.replace("\\", "/").endswith(("auth-profiles.json", "openclaw.json")):
            ctx.sync_openclaw_models_from_api_profiles()
        return ctx.fastapi_json({"status": "ok"})

    @app.api_route("/api/auth/profiles", methods=["GET", "POST", "PUT"])
    async def auth_profiles(request: Request):
        if error := ctx.auth_error(request):
            return error
        if request.method == "PUT":
            body = await ctx.body(request)
            profiles = ctx.read_json(ctx.paths.auth_profiles, {"models": {"providers": {}}})
            profiles.update(body)
            ctx.write_json(ctx.paths.auth_profiles, profiles)
            ctx.sync_openclaw_models_from_api_profiles()
            return ctx.fastapi_json({"status": "ok"})
        return ctx.fastapi_json({"profiles": ctx.read_json(ctx.paths.auth_profiles, {})})

    @app.api_route("/api/diagnostics/run", methods=["GET", "POST"])
    async def diagnostics_run(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json(ctx.build_diagnostics_payload())

    @app.api_route("/api/diagnostics/repair", methods=["GET", "POST"])
    async def diagnostics_repair(request: Request):
        if error := ctx.auth_error(request):
            return error
        result = ctx.get_process_svc().repair_environment()
        result["diagnostics"] = ctx.append_runtime_checks(result.get("diagnostics", {}))
        return ctx.fastapi_json(result)

    @app.api_route("/api/diagnostics/export", methods=["GET", "POST"])
    async def diagnostics_export(request: Request):
        if error := ctx.auth_error(request):
            return error

        diagnostics = ctx.build_diagnostics_payload()
        now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        export_dir = os.path.join(ctx.paths.data_dir, "diagnostics")
        os.makedirs(export_dir, exist_ok=True)
        filename = f"openclaw-diagnostics-{now}.zip"
        zip_path = os.path.join(export_dir, filename)

        system_info = {
            "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
            "basePath": ctx.paths.base_path,
            "nodePath": ctx.paths.node_exe,
            "openclawMjs": ctx.paths.openclaw_mjs,
            "stateDir": ctx.paths.state_dir,
            "diagnosticSummary": diagnostics.get("summary", {}),
        }

        with ctx.log_lock:
            service_log = ctx.sanitize_text("".join(ctx.log_buffer))

        readme = (
            "OpenClaw diagnostics package\n\n"
            "This package is generated by the launcher for troubleshooting.\n"
            "Secrets such as API keys, tokens, passwords, signatures and app secrets are masked.\n"
        )

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("README.txt", readme)
            archive.writestr("diagnostics.json", json.dumps(diagnostics, ensure_ascii=False, indent=2))
            archive.writestr("system.json", json.dumps(system_info, ensure_ascii=False, indent=2))
            archive.writestr("service.log", service_log)
            archive.writestr("configs/openclaw.json", json.dumps(ctx.read_sanitized_json(ctx.paths.openclaw_config, {}), ensure_ascii=False, indent=2))
            archive.writestr("configs/auth-profiles.json", json.dumps(ctx.read_sanitized_json(ctx.paths.auth_profiles, {}), ensure_ascii=False, indent=2))
            archive.writestr("configs/imgapi_config.json", json.dumps(ctx.read_sanitized_json(ctx.paths.image_config, {}), ensure_ascii=False, indent=2))
            archive.writestr("configs/video_config.json", json.dumps(ctx.read_sanitized_json(ctx.paths.video_config, {}), ensure_ascii=False, indent=2))

        return ctx.fastapi_json({
            "path": zip_path,
            "directory": export_dir,
            "filename": filename,
            "size": os.path.getsize(zip_path),
        })

    @app.api_route("/api/update/check", methods=["GET", "POST"])
    async def update_check(request: Request):
        if error := ctx.auth_error(request):
            return error
        updater = ctx.get_updater()
        current = updater.current_version()
        latest, error_message = updater.latest_version()
        if error_message:
            return ctx.fastapi_json({"error": error_message}, 500)
        return ctx.fastapi_json({"current": current, "latest": latest, "hasUpdate": current != latest})

    @app.post("/api/update/do")
    async def update_do(request: Request):
        if error := ctx.auth_error(request):
            return error

        updater = ctx.get_updater()
        node_exe = ctx.paths.node_exe
        pnpm_cli = ctx.paths.pnpm_cli
        try:
            proc = subprocess.Popen(
                [node_exe, pnpm_cli, "add", "openclaw@latest"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                cwd=ctx.paths.base_path,
            )
            output = []
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        output.append(line)
                        ctx.append_log(line)
            exit_code = proc.wait()
            current = updater.current_version()
            return ctx.fastapi_json({"success": exit_code == 0, "current_version": current, "log": output})
        except Exception as exc:
            return ctx.fastapi_json({"error": str(exc)}, 500)

    @app.api_route("/api/skills/list", methods=["GET", "POST"])
    async def skills_list(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json(ctx.get_skill_svc().list_skills())

    @app.post("/api/skills/install_zip")
    async def skills_install_zip(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        filename = body.get("filename", "skill.zip")
        data = body.get("data", "")
        if not data:
            return ctx.fastapi_json({"error": "Skill 包数据不能为空"}, 400)
        try:
            return ctx.fastapi_json(ctx.get_skill_svc().install_zip(filename, data))
        except SkillError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)

    @app.post("/api/skills/enable")
    async def skills_enable(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        skill_id = body.get("id", "")
        if not skill_id:
            return ctx.fastapi_json({"error": "Skill ID 不能为空"}, 400)
        try:
            return ctx.fastapi_json(ctx.get_skill_svc().set_enabled(skill_id, bool(body.get("enabled"))))
        except SkillError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)

    @app.post("/api/skills/uninstall")
    async def skills_uninstall(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        skill_id = body.get("id", "")
        if not skill_id:
            return ctx.fastapi_json({"error": "Skill ID 不能为空"}, 400)
        try:
            return ctx.fastapi_json(ctx.get_skill_svc().uninstall(skill_id))
        except SkillError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)

    @app.post("/api/skills/readme")
    async def skills_readme(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        skill_id = body.get("id", "")
        if not skill_id:
            return ctx.fastapi_json({"error": "Skill ID 不能为空"}, 400)
        try:
            return ctx.fastapi_json(ctx.get_skill_svc().read_readme(skill_id))
        except SkillError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)

    @app.api_route("/api/skills/paths", methods=["GET", "POST"])
    async def skills_paths(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json(ctx.get_skill_svc().paths_payload())

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT"])
    async def route_all(path: str, request: Request):
        return await ctx.dispatch(request)
