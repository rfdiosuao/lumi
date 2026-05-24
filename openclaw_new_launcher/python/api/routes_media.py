"""Image and video generation FastAPI routes."""

from __future__ import annotations

import base64
import datetime
import os

from fastapi import Request

from services.image_api import ImageApiError
from services.video_api import VideoApiError


def register_media_routes(app, ctx) -> None:
    @app.post("/api/image/generate")
    async def image_generate(request: Request):
        if error := ctx.auth_error(request):
            return error
        if error := ctx.protected_error("/api/image/generate"):
            return error

        body = await ctx.body(request)
        client = ctx.get_image_client()
        gateway_profile = ctx.get_license_mgr().current_gateway_profile()
        base_url = str(body.get("baseUrl", "") or "").strip() or str((gateway_profile or {}).get("baseUrl") or "").strip()
        api_key = str(body.get("apiKey", "") or "").strip() or str((gateway_profile or {}).get("apiKey") or "").strip()
        prompt = body.get("prompt", "")
        size = body.get("size", "1024x1024")
        model = str(body.get("model", "") or "").strip() or str((gateway_profile or {}).get("imageModel") or "").strip()
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
            results = client.generate_many(base_url, api_key, prompt, size, count=count, edit_image_path=edit_path, model=model)
            images_b64 = [base64.b64encode(result).decode() for result in results]
            image_dir = os.path.join(ctx.paths.data_dir, "generated-images")
            os.makedirs(image_dir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            files = []
            for index, image_bytes in enumerate(results):
                suffix = "" if len(results) == 1 else f"-{index + 1}"
                filename = f"openclaw-image-{stamp}{suffix}.png"
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
            return ctx.fastapi_json({"images": images_b64, "files": files, "count": len(images_b64)})
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
        gateway_profile = ctx.get_license_mgr().current_gateway_profile()
        api_base = str(body.get("apiBase", "") or "").strip() or str((gateway_profile or {}).get("baseUrl") or "").strip()
        model = (
            str(body.get("model", "") or "").strip()
            or str((gateway_profile or {}).get("videoModel") or "").strip()
            or str((gateway_profile or {}).get("defaultModel") or "").strip()
        )
        dash_key = str(body.get("dashKey", "") or "").strip() or str((gateway_profile or {}).get("apiKey") or "").strip()
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
