from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramAlerter:
    bot_token: str | None
    chat_id: str | None
    cooldown_seconds: float = 120.0
    _sent_at: dict[str, float] = field(default_factory=dict)

    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _allow(self, dedupe_key: str) -> bool:
        now = time.time()
        last = self._sent_at.get(dedupe_key, 0.0)
        if now - last < self.cooldown_seconds:
            return False
        self._sent_at[dedupe_key] = now
        return True

    async def send(self, text: str, *, dedupe_key: str = "default") -> None:
        if not self.configured():
            return
        if not self._allow(dedupe_key):
            return
        await asyncio.to_thread(self._send_sync, text)

    def _send_sync(self, text: str) -> None:
        assert self.bot_token is not None
        assert self.chat_id is not None
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read().decode("utf-8", errors="replace")
                parsed = json.loads(body)
                if not parsed.get("ok"):
                    logger.warning("Telegram alert not accepted: %s", parsed)
        except Exception as exc:
            logger.warning("Telegram alert failed: %s", exc)
