from __future__ import annotations

import os
import socket
from typing import Iterable


class SystemdNotifier:
    def __init__(self) -> None:
        self._socket_path = os.getenv("NOTIFY_SOCKET")

    def enabled(self) -> bool:
        return bool(self._socket_path)

    def _normalize_path(self, path: str) -> str:
        if path.startswith("@"):
            return "\0" + path[1:]
        return path

    def _send_lines(self, lines: Iterable[str]) -> None:
        if not self._socket_path:
            return
        address = self._normalize_path(self._socket_path)
        message = "\n".join(lines).encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(message)

    def ready(self, status: str | None = None) -> None:
        lines = ["READY=1"]
        if status:
            lines.append(f"STATUS={status}")
        self._send_lines(lines)

    def watchdog(self, status: str | None = None) -> None:
        lines = ["WATCHDOG=1"]
        if status:
            lines.append(f"STATUS={status}")
        self._send_lines(lines)

    def stopping(self, status: str | None = None) -> None:
        lines = ["STOPPING=1"]
        if status:
            lines.append(f"STATUS={status}")
        self._send_lines(lines)

    def status(self, status: str) -> None:
        self._send_lines([f"STATUS={status}"])
