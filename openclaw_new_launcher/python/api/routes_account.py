"""New API account login routes."""

from __future__ import annotations

import re

from fastapi import Request

from core.newapi_account_manager import NewApiAccountError


SECRET_RESULT_KEYS = {
    "apiKey",
    "accessToken",
    "gatewayImageAccessToken",
    "gatewayVideoAccessToken",
    "memberToken",
    "sessionCookie",
    "token",
}
PUBLIC_EMAIL_CODE_KEYS = {
    "sent",
    "email",
    "maskedEmail",
    "retryAfter",
    "expiresIn",
    "message",
}


SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|session[_-]?cookie|password|secret|token)(\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)\b(bearer\s+)([a-z0-9._~+/=-]{8,})"),
    re.compile(r"\b(sk-[A-Za-z0-9._-]+|sess-[A-Za-z0-9._-]+|eyJ[A-Za-z0-9._=-]+)"),
)


def _account_response(
    *,
    account: dict,
    session: dict | None = None,
    extra_sync_results: list[dict] | None = None,
) -> dict:
    sync_results = []
    if isinstance(session, dict) and isinstance(session.get("lastSyncResults"), list):
        sync_results.extend(session.get("lastSyncResults") or [])
    if extra_sync_results:
        sync_results.extend(extra_sync_results)
    return {
        "account": account,
        "syncResults": [_public_sync_result(item) for item in sync_results if isinstance(item, dict)],
    }


def _public_sync_result(item: dict) -> dict:
    payload = {
        key: value
        for key, value in item.items()
        if key not in SECRET_RESULT_KEYS and "token" not in key.lower() and "cookie" not in key.lower()
    }
    if isinstance(payload.get("error"), str):
        payload["error"] = _redact_secret_text(payload["error"])
    return payload


def _redact_secret_text(value: str) -> str:
    text = str(value or "")
    for pattern in SECRET_TEXT_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", text)
        elif pattern.groups == 2:
            text = pattern.sub(lambda match: f"{match.group(1)}[redacted]", text)
        else:
            text = pattern.sub("[redacted]", text)
    return text


def _public_email_code_response(payload: dict, email: str) -> dict:
    result = {
        key: value
        for key, value in (payload or {}).items()
        if key in PUBLIC_EMAIL_CODE_KEYS and value not in ("", None)
    }
    result.setdefault("sent", True)
    result.setdefault("email", email)
    return result


def register_account_routes(app, ctx) -> None:
    @app.api_route("/api/account/current", methods=["GET", "POST"])
    async def account_current(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json({"account": ctx.get_newapi_account_mgr().public_session()})

    @app.post("/api/account/email-code/send")
    async def account_email_code_send(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        email = str(body.get("email") or "").strip()
        base_url = str(body.get("baseUrl") or "").strip()
        try:
            result = ctx.get_newapi_account_mgr().send_email_code(
                email,
                base_url=base_url,
            )
            return ctx.fastapi_json(_public_email_code_response(result, email))
        except NewApiAccountError as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 400)

    @app.post("/api/account/email-code/login")
    async def account_email_code_login(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        email = str(body.get("email") or "").strip()
        code = str(body.get("code") or body.get("emailCode") or "").strip()
        base_url = str(body.get("baseUrl") or "").strip()
        try:
            session = ctx.get_newapi_account_mgr().login_with_email_code(
                email,
                code,
                base_url=base_url,
            )
            return ctx.fastapi_json(_account_response(account=ctx.get_newapi_account_mgr().public_session(), session=session))
        except NewApiAccountError as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 400)

    @app.post("/api/account/login")
    async def account_login(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        username = str(body.get("username") or body.get("email") or "").strip()
        password = str(body.get("password") or "").strip()
        base_url = str(body.get("baseUrl") or "").strip()
        api_token = str(body.get("apiToken") or "").strip()
        try:
            session = ctx.get_newapi_account_mgr().login(
                username,
                password,
                base_url=base_url,
                api_token=api_token,
            )
            return ctx.fastapi_json(_account_response(account=ctx.get_newapi_account_mgr().public_session(), session=session))
        except NewApiAccountError as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 400)

    @app.post("/api/account/bind-ticket")
    async def account_bind_ticket(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        ticket = str(body.get("ticket") or body.get("code") or "").strip()
        base_url = str(body.get("baseUrl") or "").strip()
        try:
            session = ctx.get_newapi_account_mgr().bind_ticket(
                ticket,
                base_url=base_url,
            )
            return ctx.fastapi_json(_account_response(account=ctx.get_newapi_account_mgr().public_session(), session=session))
        except NewApiAccountError as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 400)

    @app.post("/api/account/sync")
    async def account_sync(request: Request):
        if error := ctx.auth_error(request):
            return error
        try:
            session = ctx.get_newapi_account_mgr().refresh_current()
            return ctx.fastapi_json(
                _account_response(
                    account=ctx.get_newapi_account_mgr().public_session(),
                    session=session,
                )
            )
        except NewApiAccountError as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 400)
        except Exception as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 500)

    @app.post("/api/account/models/select")
    async def account_select_models(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        try:
            account = ctx.get_newapi_account_mgr().select_models(
                text_model=str(body.get("textModel") or body.get("text") or "").strip(),
                image_model=str(body.get("imageModel") or body.get("image") or "").strip(),
                video_model=str(body.get("videoModel") or body.get("video") or "").strip(),
            )
            return ctx.fastapi_json({"account": account})
        except NewApiAccountError as exc:
            return ctx.fastapi_json({"error": _redact_secret_text(str(exc))}, 400)

    @app.post("/api/account/logout")
    async def account_logout(request: Request):
        if error := ctx.auth_error(request):
            return error
        removed = ctx.get_newapi_account_mgr().logout()
        return ctx.fastapi_json({
            "loggedOut": removed,
            "account": ctx.get_newapi_account_mgr().public_session(),
        })
