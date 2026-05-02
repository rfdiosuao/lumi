"""Online activation and local license verification."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import uuid
import urllib.error
import urllib.request
from datetime import date
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from openclaw_launcher.constants import LICENSE_SERVER_URL
from openclaw_launcher.paths import AppPaths
from openclaw_launcher.storage import read_json, write_json

LICENSE_PUBLIC_KEY_B64 = "njEIf3io24DAXRYVp37p2gIT5u2KZaWoGvBPD0JlTZ4="


class LicenseError(RuntimeError):
    pass


class LicenseManager:
    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(LICENSE_PUBLIC_KEY_B64))

    def get_install_id(self) -> str:
        os.makedirs(self.paths.data_dir, exist_ok=True)
        if os.path.exists(self.paths.install_id_file):
            try:
                with open(self.paths.install_id_file, "r", encoding="utf-8") as file:
                    install_id = file.read().strip()
                if install_id:
                    return install_id
            except OSError:
                pass
        install_id = str(uuid.uuid4())
        with open(self.paths.install_id_file, "w", encoding="utf-8") as file:
            file.write(install_id)
        return install_id

    def device_id(self) -> str:
        root = os.path.splitdrive(os.path.abspath(self.paths.base_path))[0] + "\\"
        serial = None
        try:
            volume_serial = ctypes.c_ulong()
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(root),
                None,
                0,
                ctypes.byref(volume_serial),
                None,
                None,
                None,
                0,
            )
            serial = str(volume_serial.value)
        except Exception:
            pass
        if serial is None:
            # 卷序列号获取失败时用 MAC 地址作备选，避免所有机器返回同一 deviceId
            serial = str(uuid.getnode())
        raw = f"{root}|{serial}|openclaw-launcher"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def current_license(self) -> dict[str, Any] | None:
        license_data = read_json(self.paths.license_file, None)
        if isinstance(license_data, dict) and self.verify(license_data):
            return license_data
        return None

    def is_authorized(self, feature: str | None = None) -> bool:
        license_data = self.current_license()
        if not license_data:
            return False
        if feature and feature not in license_data.get("features", []):
            return False
        return True

    def verify(self, license_data: dict[str, Any]) -> bool:
        try:
            signature = base64.b64decode(license_data["signature"])
            payload = dict(license_data)
            payload.pop("signature", None)
            self.public_key.verify(signature, self._canonical(payload))
            if payload.get("installId") != self.get_install_id():
                return False
            # 防止复制文件夹绕过：如果 license 包含 deviceId 则校验硬件绑定
            licensed_device = payload.get("deviceId")
            if licensed_device and licensed_device != self.device_id():
                return False
            expires = payload.get("expires")
            if expires and date.fromisoformat(expires) < date.today():
                return False
            return True
        except (KeyError, ValueError, InvalidSignature, TypeError):
            return False

    def activate(self, code: str) -> dict[str, Any]:
        code = code.strip().upper()
        if not code:
            raise LicenseError("请输入授权码")
        payload = {
            "code": code,
            "installId": self.get_install_id(),
            "deviceId": self.device_id(),
            "appVersion": "desktop",
        }
        request = urllib.request.Request(
            f"{LICENSE_SERVER_URL.rstrip('/')}/activate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise LicenseError(self._read_error(error)) from error
        except Exception as error:
            raise LicenseError(f"无法连接授权服务器：{error}") from error
        license_data = data.get("license")
        if not isinstance(license_data, dict) or not self.verify(license_data):
            raise LicenseError("授权服务器返回的许可证无效")
        write_json(self.paths.license_file, license_data)
        return license_data

    def _canonical(self, payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _read_error(self, error: urllib.error.HTTPError) -> str:
        try:
            data = json.loads(error.read().decode("utf-8"))
            return data.get("error", f"授权失败：HTTP {error.code}")
        except Exception:
            return f"授权失败：HTTP {error.code}"

