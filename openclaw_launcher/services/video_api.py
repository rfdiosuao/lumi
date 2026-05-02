"""DashScope video generation client."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from openclaw_launcher.constants import DASHSCOPE_TASK_URL, DASHSCOPE_VIDEO_URL, VIDEO_MODEL_I2V, VIDEO_MODEL_T2V

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
        on_status: StatusCallback | None = None,
    ) -> bytes:
        try:
            body = self._build_body(prompt, mode, resolution, duration, ratio, image_path)
            task_id = self._submit_task(dash_key, body)
            if on_status:
                on_status(f"任务已提交：{task_id[:8]}...，等待生成", "accent")
            return self._poll_and_download(dash_key, task_id, on_status)
        except urllib.error.HTTPError as error:
            raise VideoApiError(_http_error_message(error)) from error
        except Exception as error:
            raise VideoApiError(str(error)) from error

    def _build_body(self, prompt: str, mode: str, resolution: str, duration: int, ratio: str, image_path: str | None) -> dict:
        if mode == "t2v":
            return {
                "model": VIDEO_MODEL_T2V,
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
            "model": VIDEO_MODEL_I2V,
            "input": {"prompt": prompt, "media": [{"type": "first_frame", "url": data_url}]},
            "parameters": {"resolution": resolution, "duration": duration},
        }

    def _submit_task(self, dash_key: str, body: dict) -> str:
        request = urllib.request.Request(
            DASHSCOPE_VIDEO_URL,
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

    def _poll_and_download(self, dash_key: str, task_id: str, on_status: StatusCallback | None) -> bytes:
        poll_url = DASHSCOPE_TASK_URL.format(task_id=task_id)
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
                with urllib.request.urlopen(video_url, timeout=120) as response:
                    return response.read()
            if status == "FAILED":
                raise VideoApiError(output.get("message", "生成失败"))
            if on_status:
                on_status(f"状态：{status or 'RUNNING'}... ({(attempt + 1) * 5}s)", "accent")
        raise VideoApiError("生成超时，请稍后重试")

    def _extract_video_url(self, output: dict) -> str | None:
        results = output.get("video_url") or output.get("results", [])
        if isinstance(results, str):
            return results
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                return first.get("url")
        return output.get("video_url")

