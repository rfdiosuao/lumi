"""Image and video generation FastAPI routes."""

from __future__ import annotations

import base64
import datetime
import os

from fastapi import Request

from core.storage import read_json, write_json
from services.image_api import ImageApiError
from services.video_api import VideoApiError


def _text(value: object) -> str:
    return str(value or "").strip()


def _read_config(path: str) -> dict:
    payload = read_json(path, {})
    return payload if isinstance(payload, dict) else {}


def _write_merged_config(path: str, incoming: dict) -> dict:
    current = _read_config(path)
    merged = dict(current)
    for key, value in incoming.items():
        if key in {"apiKey", "dashKey"} and not _text(value):
            continue
        if value is None:
            continue
        merged[key] = value
    write_json(path, merged)
    return merged


def _public_image_config(config: dict) -> dict:
    return {
        "baseUrl": _text(config.get("baseUrl")),
        "model": _text(config.get("model")),
        "size": _text(config.get("size")) or "1024x1024",
        "count": int(config.get("count") or 1),
        "hasApiKey": bool(_text(config.get("apiKey"))),
        "updatedAt": _text(config.get("updatedAt")),
    }


def _public_video_config(config: dict) -> dict:
    return {
        "providerId": _text(config.get("providerId")) or "dashscope",
        "apiBase": _text(config.get("apiBase")),
        "model": _text(config.get("model")),
        "mode": _text(config.get("mode")) or "t2v",
        "resolution": _text(config.get("resolution")) or "720P",
        "duration": int(config.get("duration") or 5),
        "ratio": _text(config.get("ratio")) or "16:9",
        "hasApiKey": bool(_text(config.get("apiKey")) or _text(config.get("dashKey"))),
        "updatedAt": _text(config.get("updatedAt")),
    }


def _image_config_fallback(ctx) -> dict:
    return _read_config(ctx.paths.image_config)


def _video_config_fallback(ctx) -> dict:
    config = _read_config(ctx.paths.video_config)
    if not _text(config.get("apiKey")) and _text(config.get("dashKey")):
        config["apiKey"] = _text(config.get("dashKey"))
    return config


def _media_config_snapshot(ctx) -> dict:
    return {
        "image": _public_image_config(_image_config_fallback(ctx)),
        "video": _public_video_config(_video_config_fallback(ctx)),
    }


def _save_media_config(ctx, body: dict) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    image = body.get("image") if isinstance(body.get("image"), dict) else {}
    video = body.get("video") if isinstance(body.get("video"), dict) else {}

    if image:
        try:
            count = max(1, min(int(image.get("count", 1) or 1), 9))
        except (TypeError, ValueError):
            raise ValueError("图片数量必须是数字")
        _write_merged_config(ctx.paths.image_config, {
            "baseUrl": _text(image.get("baseUrl")),
            "apiKey": _text(image.get("apiKey")),
            "model": _text(image.get("model")),
            "size": _text(image.get("size")) or "1024x1024",
            "count": count,
            "updatedAt": now,
        })

    if video:
        try:
            duration = max(1, min(int(video.get("duration", 5) or 5), 30))
        except (TypeError, ValueError):
            raise ValueError("视频时长必须是数字")
        api_key = _text(video.get("apiKey")) or _text(video.get("dashKey"))
        _write_merged_config(ctx.paths.video_config, {
            "providerId": _text(video.get("providerId")) or "dashscope",
            "apiBase": _text(video.get("apiBase")),
            "apiKey": api_key,
            "dashKey": api_key,
            "model": _text(video.get("model")),
            "mode": _text(video.get("mode")) or "t2v",
            "resolution": _text(video.get("resolution")) or "720P",
            "duration": duration,
            "ratio": _text(video.get("ratio")) or "16:9",
            "updatedAt": now,
        })

    return _media_config_snapshot(ctx)


def _test_media_config(ctx, body: dict) -> dict:
    kind = _text(body.get("kind")) or "image"
    snapshot = _save_media_config(ctx, body) if ("image" in body or "video" in body) else _media_config_snapshot(ctx)
    target = snapshot["video"] if kind == "video" else snapshot["image"]
    missing = []
    if kind == "video":
        if not target.get("hasApiKey"):
            missing.append("API Key")
        if not target.get("model"):
            missing.append("模型")
    else:
        if not target.get("baseUrl"):
            missing.append("Base URL")
        if not target.get("hasApiKey"):
            missing.append("API Key")
        if not target.get("model"):
            missing.append("模型")
    if missing:
        return {"ok": False, "message": f"请补全：{'、'.join(missing)}", "config": snapshot}
    return {"ok": True, "message": "配置已就绪，可提交生成任务验证", "config": snapshot}


def _image_generate_payload(ctx, body: dict) -> dict:
    client = ctx.get_image_client()
    gateway_profile = ctx.get_license_mgr().current_gateway_profile()
    saved_config = _image_config_fallback(ctx)
    base_url = (
        str(body.get("baseUrl", "") or "").strip()
        or str(saved_config.get("baseUrl") or "").strip()
        or str((gateway_profile or {}).get("imageBaseUrl") or "").strip()
        or str((gateway_profile or {}).get("baseUrl") or "").strip()
    )
    api_key = (
        str(body.get("apiKey", "") or "").strip()
        or str(saved_config.get("apiKey") or "").strip()
        or str((gateway_profile or {}).get("imageApiKey") or "").strip()
        or str((gateway_profile or {}).get("apiKey") or "").strip()
    )
    prompt = body.get("prompt", "")
    size = body.get("size") or saved_config.get("size") or "1024x1024"
    model = (
        str(body.get("model", "") or "").strip()
        or str(saved_config.get("model") or "").strip()
        or str((gateway_profile or {}).get("imageModel") or "").strip()
    )
    edit_path = body.get("editImagePath")
    try:
        count = max(1, min(int(body.get("count", 1) or 1), 9))
    except (TypeError, ValueError):
        raise ImageApiError("图片数量必须是数字")

    if not base_url:
        diag = ctx.get_license_mgr().gateway_diagnosis()
        if not diag.get("ok") and diag.get("code") == "gateway_fields_missing":
            raise ImageApiError(str(diag["message"]))
        raise ImageApiError("中转站地址不能为空")
    if not prompt:
        raise ImageApiError("提示词不能为空")

    temp_file: str | None = None
    if edit_path and edit_path.startswith("data:"):
        edit_path, temp_file = ctx.data_url_to_temp_file(edit_path)

    try:
        results = client.generate_many(base_url, api_key, prompt, size, count=count, edit_image_path=edit_path, model=model)
        images_b64 = [base64.b64encode(result).decode() for result in results]
        image_dir = os.path.join(ctx.paths.data_dir, "generated-images")
        os.makedirs(image_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        files = []
        for index, image_bytes in enumerate(results):
            suffix = "" if len(results) == 1 else f"-{index + 1}"
            filename = f"loom-image-{stamp}{suffix}.png"
            save_path = os.path.join(image_dir, filename)
            with open(save_path, "wb") as file:
                file.write(image_bytes)
            files.append({
                "path": save_path,
                "directory": image_dir,
                "filename": filename,
                "size": len(image_bytes),
                "mime": "image/png",
            })
        return {"images": images_b64, "files": files, "count": len(images_b64)}
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError:
                pass


def _video_generate_payload(ctx, body: dict, on_status=None) -> dict:
    client = ctx.get_video_client()
    saved_config = _video_config_fallback(ctx)
    provider_id = body.get("providerId") or saved_config.get("providerId") or "dashscope"
    gateway_profile = ctx.get_license_mgr().current_gateway_profile()
    api_base = (
        str(body.get("apiBase", "") or "").strip()
        or str(saved_config.get("apiBase") or "").strip()
        or str((gateway_profile or {}).get("videoBaseUrl") or "").strip()
        or str((gateway_profile or {}).get("baseUrl") or "").strip()
    )
    model = (
        str(body.get("model", "") or "").strip()
        or str(saved_config.get("model") or "").strip()
        or str((gateway_profile or {}).get("videoDraftModel") or "").strip()
        or str((gateway_profile or {}).get("defaultModel") or "").strip()
    )
    dash_key = (
        str(body.get("dashKey", "") or "").strip()
        or str(body.get("apiKey", "") or "").strip()
        or str(saved_config.get("apiKey") or "").strip()
        or str(saved_config.get("dashKey") or "").strip()
        or str((gateway_profile or {}).get("videoApiKey") or "").strip()
        or str((gateway_profile or {}).get("apiKey") or "").strip()
    )
    prompt = body.get("prompt", "")
    mode = body.get("mode") or saved_config.get("mode") or "t2v"
    resolution = body.get("resolution") or saved_config.get("resolution") or "720P"
    duration = body.get("duration") or saved_config.get("duration") or 5
    ratio = body.get("ratio") or saved_config.get("ratio") or "16:9"
    image_path = body.get("imagePath")

    if not dash_key:
        diag = ctx.get_license_mgr().gateway_diagnosis()
        if not diag.get("ok") and diag.get("code") == "gateway_fields_missing":
            raise VideoApiError(str(diag["message"]))
        raise VideoApiError("视频服务密钥不能为空")
    if not prompt:
        raise VideoApiError("提示词不能为空")

    temp_file: str | None = None
    if image_path and image_path.startswith("data:"):
        image_path, temp_file = ctx.data_url_to_temp_file(image_path)

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
            on_status=on_status,
        )
        video_dir = os.path.join(ctx.paths.data_dir, "videos")
        os.makedirs(video_dir, exist_ok=True)
        filename = f"loom-video-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.mp4"
        save_path = os.path.join(video_dir, filename)
        with open(save_path, "wb") as file:
            file.write(video_bytes)
        return {
            "video": base64.b64encode(video_bytes).decode(),
            "mime": "video/mp4",
            "size": len(video_bytes),
            "path": save_path,
            "directory": video_dir,
            "filename": filename,
        }
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError:
                pass


def register_media_routes(app, ctx) -> None:
    @app.get("/api/media/config")
    async def media_config(request: Request):
        if error := ctx.auth_error(request):
            return error
        return ctx.fastapi_json({"config": _media_config_snapshot(ctx)})

    @app.post("/api/media/config")
    async def media_config_save(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        try:
            return ctx.fastapi_json({"config": _save_media_config(ctx, body)})
        except ValueError as exc:
            return ctx.fastapi_json({"error": str(exc)}, 400)

    @app.post("/api/media/test")
    async def media_config_test(request: Request):
        if error := ctx.auth_error(request):
            return error
        body = await ctx.body(request)
        try:
            return ctx.fastapi_json(_test_media_config(ctx, body))
        except ValueError as exc:
            return ctx.fastapi_json({"ok": False, "error": str(exc)}, 400)

    @app.post("/api/image/generate")
    async def image_generate(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/image/generate"):
            return error

        body = await ctx.body(request)
        try:
            return ctx.fastapi_json(_image_generate_payload(ctx, body))
        except (ImageApiError, ValueError) as exc:
            return ctx.fastapi_json({"error": str(exc)}, 500)

    @app.post("/api/image/generate/submit")
    async def image_generate_submit(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/image/generate"):
            return error

        body = await ctx.body(request)

        def target(job_id: str) -> dict:
            ctx.get_job_mgr().progress(job_id, "正在生成图片", "neutral")
            return _image_generate_payload(ctx, body)

        job = ctx.get_job_mgr().submit_progress("image", "图片生成", target)
        return ctx.fastapi_json({"jobId": job["id"], "job": job})

    @app.post("/api/video/generate")
    async def video_generate(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/video/generate"):
            return error

        body = await ctx.body(request)
        try:
            return ctx.fastapi_json(_video_generate_payload(ctx, body))
        except (VideoApiError, ValueError) as exc:
            return ctx.fastapi_json({"error": str(exc)}, 500)

    @app.post("/api/video/generate/submit")
    async def video_generate_submit(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/video/generate"):
            return error

        body = await ctx.body(request)

        def target(job_id: str) -> dict:
            ctx.get_job_mgr().progress(job_id, "正在提交视频任务", "neutral", phase="submitting")
            return _video_generate_payload(
                ctx,
                body,
                on_status=lambda message, tone="neutral": ctx.get_job_mgr().progress(
                    job_id,
                    message,
                    tone,
                    phase="generating",
                ),
            )

        job = ctx.get_job_mgr().submit_progress("video", "视频生成", target)
        return ctx.fastapi_json({"jobId": job["id"], "job": job})
