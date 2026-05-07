"""OpenClaw update FastAPI routes."""

from __future__ import annotations

import subprocess

from fastapi import Request


def register_update_routes(app, ctx) -> None:
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
        try:
            proc = subprocess.Popen(
                [ctx.paths.node_exe, ctx.paths.pnpm_cli, "add", "openclaw@latest"],
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
