"""Service log FastAPI routes."""

from __future__ import annotations

import os

from fastapi import Request


def register_log_routes(app, ctx) -> None:
    @app.api_route("/api/log/get", methods=["GET", "POST"])
    async def log_get(request: Request):
        if error := ctx.auth_error(request):
            return error
        try:
            offset = max(0, int(request.query_params.get("offset", "0") or "0"))
        except ValueError:
            offset = 0

        with ctx.log_lock:
            text = "".join(ctx.log_buffer)
        if not text:
            persisted_log = os.path.join(ctx.paths.data_dir, "logs", "bridge-service.log")
            if os.path.exists(persisted_log):
                with open(persisted_log, "r", encoding="utf-8", errors="replace") as file:
                    text = file.read()

        reset = offset > len(text)
        if reset:
            offset = 0
        return ctx.fastapi_json({
            "log": text[offset:],
            "offset": len(text),
            "total": len(text),
            "reset": reset,
        })

    @app.post("/api/log/clear")
    async def log_clear(request: Request):
        if error := ctx.auth_error(request):
            return error
        with ctx.log_lock:
            ctx.log_buffer.clear()
        persisted_log = os.path.join(ctx.paths.data_dir, "logs", "bridge-service.log")
        try:
            if os.path.exists(persisted_log):
                open(persisted_log, "w", encoding="utf-8").close()
        except Exception:
            pass
        return ctx.fastapi_json({"status": "cleared"})
