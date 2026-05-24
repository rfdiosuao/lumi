#!/usr/bin/env python3
"""Deploy the license server membership update over SSH.

Usage:
  set LICENSE_SSH_PASSWORD=...
  python deploy_member_update.py
"""

from __future__ import annotations

import os
import posixpath
import socket
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import paramiko
import socks


HOST = os.environ.get("LICENSE_SSH_HOST", "119.145.98.220")
PORT = int(os.environ.get("LICENSE_SSH_PORT", "22"))
USER = os.environ.get("LICENSE_SSH_USER", "root")
PASSWORD = os.environ.get("LICENSE_SSH_PASSWORD", "")
REMOTE_DIR = os.environ.get("LICENSE_REMOTE_DIR", "/opt/openclaw-license")
SERVICE_NAME = os.environ.get("LICENSE_SERVICE_NAME", "openclaw-license")
LOCAL_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
LOCAL_ADMIN_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_console.html")
SSH_PROXY = os.environ.get("LICENSE_SSH_PROXY", "").strip()


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def run(client: paramiko.SSHClient, command: str) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=60)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if code != 0:
        fail(f"remote command failed ({code}): {command}\n{out}\n{err}")
    return out.strip()


def main() -> None:
    if not PASSWORD:
        fail("LICENSE_SSH_PASSWORD is required")
    if not os.path.exists(LOCAL_SERVER):
        fail(f"local server.py not found: {LOCAL_SERVER}")
    if not os.path.exists(LOCAL_ADMIN_HTML):
        fail(f"local admin_console.html not found: {LOCAL_ADMIN_HTML}")

    backup_name = "server.py.bak-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    html_backup_name = "admin_console.html.bak-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    remote_server = posixpath.join(REMOTE_DIR, "server.py")
    remote_admin_html = posixpath.join(REMOTE_DIR, "admin_console.html")
    remote_tmp = posixpath.join(REMOTE_DIR, "server.py.uploading")
    remote_html_tmp = posixpath.join(REMOTE_DIR, "admin_console.html.uploading")
    remote_backup = posixpath.join(REMOTE_DIR, backup_name)
    remote_html_backup = posixpath.join(REMOTE_DIR, html_backup_name)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sock: socket.socket | None = None
    if SSH_PROXY:
        parsed = urlparse(SSH_PROXY)
        proxy_type = socks.SOCKS5 if parsed.scheme.lower().startswith("socks") else socks.HTTP
        sock = socks.socksocket()
        sock.set_proxy(proxy_type, parsed.hostname or "127.0.0.1", parsed.port or 7897)
        sock.settimeout(30)
        sock.connect((HOST, PORT))
    client.connect(
        hostname=HOST,
        port=PORT,
        username=USER,
        password=PASSWORD,
        sock=sock,
        timeout=20,
        banner_timeout=20,
        auth_timeout=20,
    )
    try:
        run(client, f"test -d {REMOTE_DIR!r} && test -f {remote_server!r}")
        sftp = client.open_sftp()
        try:
            sftp.put(LOCAL_SERVER, remote_tmp)
            sftp.put(LOCAL_ADMIN_HTML, remote_html_tmp)
        finally:
            sftp.close()
        run(client, f"python3 -m py_compile {remote_tmp!r}")
        run(
            client,
            f"cp {remote_server!r} {remote_backup!r} && "
            f"if [ -f {remote_admin_html!r} ]; then cp {remote_admin_html!r} {remote_html_backup!r}; fi && "
            f"mv {remote_tmp!r} {remote_server!r} && mv {remote_html_tmp!r} {remote_admin_html!r}",
        )
        run(client, f"systemctl restart {SERVICE_NAME!r}")
        health = run(client, "python3 - <<'PY'\nimport urllib.request\nprint(urllib.request.urlopen('http://127.0.0.1:18791/health', timeout=10).read().decode())\nPY")
        print("deployed")
        print(f"backup={remote_backup}")
        print(health)
    finally:
        client.close()


if __name__ == "__main__":
    main()
