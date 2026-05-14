"""Online activation and local license verification."""

from __future__ import annotations

import base64
import binascii
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

from core.constants import LICENSE_SERVER_URL
from core.paths import AppPaths
from core.storage import read_json, write_json

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

    def _volume_serial(self) -> str | None:
        root = os.path.splitdrive(os.path.abspath(self.paths.base_path))[0] + "\\"
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
            return str(volume_serial.value)
        except Exception:
            return None

    @staticmethod
    def _hash_device_payload(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def device_id(self) -> str:
        serial = self._volume_serial()
        if serial:
            # Bind to the USB volume itself, not to the assigned drive letter.
            # Windows may assign a different drive letter after unplug/replug.
            raw = f"volume:{serial}|openclaw-launcher"
        else:
            # Fallback for non-Windows or environments where volume serial is unavailable.
            # The persisted installId still keeps the license tied to this portable package.
            raw = f"fallback:{uuid.getnode()}|openclaw-launcher"
        return self._hash_device_payload(raw)

    def legacy_device_id(self) -> str:
        """Previous format kept only for already activated packages."""
        root = os.path.splitdrive(os.path.abspath(self.paths.base_path))[0] + "\\"
        serial = self._volume_serial() or str(uuid.getnode())
        return self._hash_device_payload(f"{root}|{serial}|openclaw-launcher")

    def legacy_device_id_candidates(self) -> set[str]:
        """Accept old drive-letter-bound licenses after Windows remaps the USB letter."""
        serial = self._volume_serial() or str(uuid.getnode())
        return {
            self._hash_device_payload(f"{letter}:\\|{serial}|openclaw-launcher")
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        }

    def device_id_candidates(self) -> set[str]:
        return {self.device_id(), self.legacy_device_id(), *self.legacy_device_id_candidates()}

    def current_license(self) -> dict[str, Any] | None:
        license_data = read_json(self.paths.license_file, None)
        if isinstance(license_data, dict) and self.verify(license_data):
            return license_data
        return None

    def diagnose(self) -> dict[str, Any]:
        if not os.path.exists(self.paths.license_file):
            return {
                "ok": False,
                "code": "missing",
                "message": "未授权，尚未生成 license.json",
                "detail": self.paths.license_file,
                "license": None,
            }
        try:
            with open(self.paths.license_file, "r", encoding="utf-8") as file:
                license_data = json.load(file)
        except json.JSONDecodeError as error:
            return {
                "ok": False,
                "code": "corrupt",
                "message": "授权文件损坏，无法解析 JSON",
                "detail": f"{self.paths.license_file} ({error})",
                "license": None,
            }
        except OSError as error:
            return {
                "ok": False,
                "code": "unreadable",
                "message": "授权文件无法读取",
                "detail": f"{self.paths.license_file} ({error})",
                "license": None,
            }
        if not isinstance(license_data, dict):
            return {
                "ok": False,
                "code": "corrupt",
                "message": "授权文件损坏，根节点不是对象",
                "detail": self.paths.license_file,
                "license": None,
            }

        try:
            signature = base64.b64decode(license_data["signature"], validate=True)
            payload = dict(license_data)
            payload.pop("signature", None)
            self.public_key.verify(signature, self._canonical(payload))
        except KeyError:
            return {
                "ok": False,
                "code": "signature_missing",
                "message": "授权文件缺少签名字段",
                "detail": self.paths.license_file,
                "license": license_data,
            }
        except (binascii.Error, ValueError, InvalidSignature, TypeError) as error:
            return {
                "ok": False,
                "code": "signature_invalid",
                "message": "授权签名无效，文件可能被修改或不是本产品授权",
                "detail": f"{self.paths.license_file} ({error.__class__.__name__})",
                "license": license_data,
            }

        install_id = license_data.get("installId")
        current_install_id = self.get_install_id()
        if install_id != current_install_id:
            return {
                "ok": False,
                "code": "install_id_mismatch",
                "message": "installId 不匹配，授权文件不属于当前启动器数据目录",
                "detail": f"license={install_id or '-'} current={current_install_id}",
                "license": license_data,
            }

        licensed_device = license_data.get("deviceId")
        device_candidates = self.device_id_candidates()
        if licensed_device and licensed_device not in device_candidates:
            return {
                "ok": False,
                "code": "device_id_mismatch",
                "message": "deviceId 不匹配，授权文件绑定的设备/U盘不是当前运行环境",
                "detail": f"license={licensed_device} current={', '.join(sorted(device_candidates))}",
                "license": license_data,
            }

        expires = license_data.get("expires")
        if expires:
            try:
                expires_date = date.fromisoformat(str(expires))
            except ValueError:
                return {
                    "ok": False,
                    "code": "corrupt",
                    "message": "授权文件损坏，expires 日期格式无效",
                    "detail": f"expires={expires}",
                    "license": license_data,
                }
            if expires_date < date.today():
                return {
                    "ok": False,
                    "code": "expired",
                    "message": f"授权已过期：{expires}",
                    "detail": self.paths.license_file,
                    "license": license_data,
                }

        return {
            "ok": True,
            "code": "ok",
            "message": f"已授权：{license_data.get('licensee', 'OpenClaw Customer')}",
            "detail": self.paths.license_file,
            "license": license_data,
        }

    def is_authorized(self, feature: str | None = None) -> bool:
        license_data = self.current_license()
        if not license_data:
            return False
        if feature and feature not in license_data.get("features", []):
            return False
        return True

    def verify(self, license_data: dict[str, Any]) -> bool:
        try:
            signature = base64.b64decode(license_data["signature"], validate=True)
            payload = dict(license_data)
            payload.pop("signature", None)
            self.public_key.verify(signature, self._canonical(payload))
            if payload.get("installId") != self.get_install_id():
                return False
            licensed_device = payload.get("deviceId")
            if licensed_device and licensed_device not in self.device_id_candidates():
                return False
            expires = payload.get("expires")
            if expires and date.fromisoformat(expires) < date.today():
                return False
            return True
        except (KeyError, binascii.Error, ValueError, InvalidSignature, TypeError):
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
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Lumi-Desktop/2.0",
            },
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
        theme_data = data.get("theme")
        if isinstance(theme_data, dict) and theme_data.get("colors"):
            write_json(self.paths.theme_json, theme_data)
        return license_data

    def get_brand_config(self) -> dict[str, Any] | None:
        license_data = self.current_license()
        if not isinstance(license_data, dict):
            return None
        brand_config = license_data.get("brandConfig") or license_data.get("theme")
        if isinstance(brand_config, dict):
            return brand_config
        return None

    def _canonical(self, payload: dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _read_error(self, error: urllib.error.HTTPError) -> str:
        try:
            data = json.loads(error.read().decode("utf-8"))
            return data.get("error", f"授权失败：HTTP {error.code}")
        except Exception:
            return f"授权失败：HTTP {error.code}"
