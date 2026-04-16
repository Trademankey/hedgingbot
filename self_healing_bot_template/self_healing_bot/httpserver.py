from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

JsonFactory = Callable[[], dict]


class HealthHttpServer:
    def __init__(self, host: str, port: int, snapshot_factory: JsonFactory) -> None:
        self.host = host
        self.port = port
        self.snapshot_factory = snapshot_factory
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, host=self.host, port=self.port)

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                await writer.wait_closed()
                return
            line = request_line.decode("utf-8", errors="replace").strip()
            parts = line.split()
            path = parts[1] if len(parts) >= 2 else "/"
            while True:
                header = await reader.readline()
                if not header or header in {b"\r\n", b"\n"}:
                    break

            snapshot = self.snapshot_factory()
            if path == "/live":
                payload = {"alive": True, "mode": snapshot.get("mode")}
                body = json.dumps(payload).encode("utf-8")
                await self._respond(writer, 200, body)
            elif path == "/health":
                status = 200 if snapshot.get("healthy") else 503
                body = json.dumps(snapshot).encode("utf-8")
                await self._respond(writer, status, body)
            else:
                await self._respond(writer, 404, b'{"error":"not found"}')
        finally:
            writer.close()
            await writer.wait_closed()

    async def _respond(self, writer: asyncio.StreamWriter, status_code: int, body: bytes) -> None:
        reason = {
            200: "OK",
            404: "Not Found",
            503: "Service Unavailable",
        }.get(status_code, "OK")
        headers = [
            f"HTTP/1.1 {status_code} {reason}",
            "Content-Type: application/json",
            f"Content-Length: {len(body)}",
            "Connection: close",
            "",
            "",
        ]
        writer.write("\r\n".join(headers).encode("utf-8") + body)
        await writer.drain()
