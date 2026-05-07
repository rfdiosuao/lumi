"""OpenClaw process FastAPI routes."""

from __future__ import annotations

from fastapi import Request


def register_process_routes(app, ctx) -> None:
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
