"""DashScope video generation client."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable

from core.constants import DASHSCOPE_TASK_URL, DASHSCOPE_VIDEO_URL, VIDEO_MODEL_I2V, VIDEO_MODEL_T2V

StatusCallback = Callable[[str, str], None]


class VideoApiError(RuntimeError):
    pass


def _http_error_message(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read().decode("utf-8")
        data = json.loads(body)
        return data.get("message") or data.get("error", {}).get("message") or f"HTTP {error.code}"
    except Exception:
        return f"HTTP {error.code}"


def _api_error_message(data: dict, fallback: str) -> str:
    message = data.get("message")
    if isinstance(message, str) and message:
        return message
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    if isinstance(error, str) and error:
        return error
    return fallback


class DashScopeVideoClient:
    def generate(
        self,
        dash_key: str,
        prompt: str,
        mode: str,
        resolution: str,
        duration: int,
        ratio: str,
        image_path: str | None = None,
        provider_id: str = "dashscope",
        api_base: str = "",
        model: str = "",
        on_status: StatusCallback | None = None,
    ) -> bytes:
        try:
            provider_id = (provider_id or "dashscope").strip().lower()
            if provider_id in ("seedance", "custom"):
                return self._generate_seedance_compatible(
                    dash_key, prompt, mode, resolution, duration, ratio, image_path,
                    api_base=api_base, model=model, on_status=on_status
                )

            submit_url, task_url = self._dashscope_urls(api_base)
            body = self._build_dashscope_body(prompt, mode, resolution, duration, ratio, image_path, model)
            task_id = self._submit_dashscope_task(dash_key, body, submit_url)
            if on_status:
                on_status(f"任务已提交：{task_id[:8]}...，等待生成", "accent")
            return self._poll_dashscope_and_download(dash_key, task_id, on_status, task_url)
        except urllib.error.HTTPError as error:
            raise VideoApiError(_http_error_message(error)) from error
        except Exception as error:
            raise VideoApiError(str(error)) from error

    def _build_dashscope_body(
        self,
        prompt: str,
        mode: str,
        resolution: str,
        duration: int,
        ratio: str,
        image_path: str | None,
        model: str = "",
    ) -> dict:
        if mode == "t2v":
            return {
                "model": model or VIDEO_MODEL_T2V,
                "input": {"prompt": prompt},
                "parameters": {"resolution": resolution, "ratio": ratio, "duration": duration},
            }
        if not image_path:
            raise VideoApiError("图生视频需要上传参考图")
        with open(image_path, "rb") as file:
            image_data = file.read()
        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "image/png")
        data_url = f"data:{mime};base64,{base64.b64encode(image_data).decode('utf-8')}"
        return {
            "model": model or VIDEO_MODEL_I2V,
            "input": {"prompt": prompt, "media": [{"type": "first_frame", "url": data_url}]},
            "parameters": {"resolution": resolution, "duration": duration},
        }

    def _dashscope_urls(self, api_base: str) -> tuple[str, str]:
        """Resolve the DashScope-compatible submit/poll URLs.

        When ``api_base`` is empty this reproduces the official Aliyun
        endpoints.  When the member gateway (or a "快乐马"/中转站) supplies a
        compatible base URL we derive the submit and task-poll URLs from it so
        the gateway token is sent to the gateway instead of real Aliyun.
        """
        base = (api_base or "").strip().rstrip("/")
        if not base:
            return DASHSCOPE_VIDEO_URL, DASHSCOPE_TASK_URL
        submit_suffix = "/services/aigc/video-generation/video-synthesis"
        root = base[: -len(submit_suffix)] if base.endswith(submit_suffix) else base
        return f"{root}{submit_suffix}", f"{root}/tasks/{{task_id}}"

    def _submit_dashscope_task(self, dash_key: str, body: dict, submit_url: str = DASHSCOPE_VIDEO_URL) -> str:
        request = urllib.request.Request(
            submit_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {dash_key}",
                "X-DashScope-Async": "enable",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise VideoApiError(data.get("message", "任务提交失败"))
        return task_id

    def _poll_dashscope_and_download(
        self,
        dash_key: str,
        task_id: str,
        on_status: StatusCallback | None,
        task_url_template: str = DASHSCOPE_TASK_URL,
    ) -> bytes:
        poll_url = task_url_template.format(task_id=task_id)
        for attempt in range(120):
            time.sleep(5)
            request = urllib.request.Request(poll_url, headers={"Authorization": f"Bearer {dash_key}"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            output = data.get("output", {})
            status = output.get("task_status", "")
            if status == "SUCCEEDED":
                video_url = self._extract_video_url(output)
                if not video_url:
                    raise VideoApiError("未获取到视频地址")
                if on_status:
                    on_status("正在下载视频...", "accent")
                return self._download_video(video_url)
            if status == "FAILED":
                raise VideoApiError(output.get("message", "生成失败"))
            if on_status:
                on_status(f"状态：{status or 'RUNNING'}... ({(attempt + 1) * 5}s)", "accent")
        raise VideoApiError("生成超时，请稍后重试")

    def _generate_seedance_compatible(
        self,
        api_key: str,
        prompt: str,
        mode: str,
        resolution: str,
        duration: int,
        ratio: str,
        image_path: str | None,
        api_base: str,
        model: str,
        on_status: StatusCallback | None,
    ) -> bytes:
        if not model:
            raise VideoApiError("火山引擎 Seedance 需要填写模型 ID")
        if mode == "i2v" and not image_path:
            raise VideoApiError("图生视频需要上传参考图")

        task_url = self._seedance_task_url(api_base)
        body = self._build_seedance_body(prompt, mode, resolution, duration, ratio, image_path, model)
        task_id = self._submit_seedance_task(api_key, task_url, body)
        if on_status:
            on_status(f"Seedance 任务已提交：{task_id[:8]}...，等待生成", "accent")
        return self._poll_seedance_and_download(api_key, task_url, task_id, on_status)

    def _seedance_task_url(self, api_base: str) -> str:
        base = (api_base or "https://ark.cn-beijing.volces.com").strip().rstrip("/")
        if base.endswith("/contents/generations/tasks"):
            return base
        if base.endswith("/api/v3"):
            return f"{base}/contents/generations/tasks"
        return f"{base}/api/v3/contents/generations/tasks"

    def _build_seedance_body(
        self,
        prompt: str,
        mode: str,
        resolution: str,
        duration: int,
        ratio: str,
        image_path: str | None,
        model: str,
    ) -> dict:
        content: list[dict] = [{"type": "text", "text": prompt}]
        if mode == "i2v" and image_path:
            content.append({
                "type": "image_url",
                "image_url": {"url": self._image_reference_url(image_path)},
                "role": "first_frame",
            })
        return {
            "model": model,
            "content": content,
            "parameters": {
                "resolution": str(resolution).lower(),
                "duration": int(duration),
                "ratio": ratio,
            },
        }

    def _image_reference_url(self, image_path: str) -> str:
        if image_path.startswith(("http://", "https://", "data:")):
            return image_path
        with open(image_path, "rb") as file:
            image_data = file.read()
        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "image/png")
        return f"data:{mime};base64,{base64.b64encode(image_data).decode('utf-8')}"

    def _submit_seedance_task(self, api_key: str, task_url: str, body: dict) -> str:
        request = urllib.request.Request(
            task_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        task_id = data.get("id") or data.get("task_id") or data.get("output", {}).get("task_id")
        if not task_id:
            raise VideoApiError(_api_error_message(data, "Seedance 任务提交失败"))
        return task_id

    def _poll_seedance_and_download(
        self,
        api_key: str,
        task_url: str,
        task_id: str,
        on_status: StatusCallback | None,
    ) -> bytes:
        poll_url = f"{task_url.rstrip('/')}/{task_id}"
        for attempt in range(180):
            time.sleep(4)
            request = urllib.request.Request(poll_url, headers={"Authorization": f"Bearer {api_key}"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            status = str(data.get("status") or data.get("task_status") or data.get("output", {}).get("task_status") or "").lower()
            if status in ("succeeded", "success", "completed", "done"):
                video_url = self._extract_seedance_video_url(data)
                if not video_url:
                    raise VideoApiError("Seedance 未返回视频地址")
                if on_status:
                    on_status("正在下载 Seedance 视频...", "accent")
                return self._download_video(video_url)
            if status in ("failed", "error", "canceled", "cancelled"):
                raise VideoApiError(_api_error_message(data, "Seedance 生成失败"))
            if on_status:
                on_status(f"Seedance 状态：{status or 'running'}... ({(attempt + 1) * 4}s)", "accent")
        raise VideoApiError("Seedance 生成超时，请稍后重试")

    def _extract_seedance_video_url(self, data: dict) -> str | None:
        candidates = [
            data,
            data.get("output", {}) if isinstance(data.get("output"), dict) else {},
            data.get("result", {}) if isinstance(data.get("result"), dict) else {},
        ]
        for candidate in candidates:
            url = candidate.get("video_url") or candidate.get("url")
            if isinstance(url, str) and url:
                return url
            content = candidate.get("content")
            if isinstance(content, dict):
                url = content.get("video_url") or content.get("url")
                if isinstance(url, str) and url:
                    return url
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    url = item.get("video_url") or item.get("url")
                    if isinstance(url, str) and url:
                        return url
                    video_url = item.get("video_url")
                    if isinstance(video_url, dict) and isinstance(video_url.get("url"), str):
                        return video_url["url"]
        return None

    def _extract_video_url(self, output: dict) -> str | None:
        results = output.get("video_url") or output.get("results", [])
        if isinstance(results, str):
            return results
        if isinstance(results, dict):
            return results.get("video_url") or results.get("url")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                return first.get("video_url") or first.get("url")
        return output.get("video_url")

    def _download_video(self, video_url: str) -> bytes:
        request = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=180) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
        if not data:
            raise VideoApiError("视频下载结果为空")
        if not self._looks_like_video(data, content_type):
            preview = data[:160].decode("utf-8", errors="replace").replace("\n", " ")
            raise VideoApiError(
                f"视频下载结果不是可播放的 MP4：content-type={content_type or 'unknown'}, "
                f"size={len(data)}, preview={preview[:100]}"
            )
        return data

    def _looks_like_video(self, data: bytes, content_type: str) -> bool:
        lower_type = (content_type or "").lower()
        if lower_type.startswith("video/") and len(data) > 1024:
            return True
        head = data[:128]
        return b"ftyp" in head or head.startswith(b"\x1aE\xdf\xa3")

