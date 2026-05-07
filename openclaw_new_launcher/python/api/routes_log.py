"""Service log FastAPI routes."""

from __future__ import annotations

from fastapi import Request


def register_log_routes(app, ctx) -> None:
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
