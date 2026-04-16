from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from self_healing_bot.config import BotConfig


class BotMode(str, Enum):
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    SAFE_MODE = "SAFE_MODE"
    STOPPING = "STOPPING"


@dataclass(slots=True)
class HealthState:
    config: BotConfig
    started_at: float = field(default_factory=time.time)
    last_heartbeat_at: float = field(default_factory=time.time)
    last_market_data_at: float = field(default_factory=time.time)
    last_exchange_ok_at: float = field(default_factory=time.time)
    last_reconciliation_at: float = field(default_factory=time.time)
    mode: BotMode = BotMode.STARTING
    problems: dict[str, str] = field(default_factory=dict)
    unhealthy_since: float | None = None

    def touch_heartbeat(self) -> None:
        self.last_heartbeat_at = time.time()

    def touch_market_data(self) -> None:
        self.last_market_data_at = time.time()

    def touch_exchange_ok(self) -> None:
        self.last_exchange_ok_at = time.time()

    def touch_reconciliation(self) -> None:
        self.last_reconciliation_at = time.time()

    def set_mode(self, mode: BotMode) -> None:
        self.mode = mode

    def set_problem(self, key: str, value: str) -> None:
        self.problems[key] = value

    def clear_problem(self, key: str) -> None:
        self.problems.pop(key, None)

    def ages(self) -> dict[str, float]:
        now = time.time()
        return {
            "heartbeat": round(now - self.last_heartbeat_at, 3),
            "market_data": round(now - self.last_market_data_at, 3),
            "exchange": round(now - self.last_exchange_ok_at, 3),
            "reconciliation": round(now - self.last_reconciliation_at, 3),
            "uptime": round(now - self.started_at, 3),
        }

    def healthy(self) -> bool:
        now = time.time()
        if now - self.started_at < self.config.startup_grace_seconds:
            return True
        if self.mode in {BotMode.RECONNECTING, BotMode.SAFE_MODE, BotMode.STOPPING}:
            return False
        if now - self.last_heartbeat_at > self.config.heartbeat_timeout_seconds:
            return False
        if now - self.last_market_data_at > self.config.market_data_timeout_seconds:
            return False
        if now - self.last_exchange_ok_at > self.config.exchange_timeout_seconds:
            return False
        if now - self.last_reconciliation_at > self.config.reconciliation_timeout_seconds:
            return False
        if self.problems:
            return False
        return True

    def evaluate(self) -> bool:
        result = self.healthy()
        now = time.time()
        if result:
            if self.mode == BotMode.STARTING:
                self.mode = BotMode.HEALTHY
            elif self.mode == BotMode.DEGRADED:
                self.mode = BotMode.HEALTHY
            self.unhealthy_since = None
        else:
            if self.mode not in {BotMode.RECONNECTING, BotMode.SAFE_MODE, BotMode.STOPPING}:
                self.mode = BotMode.DEGRADED
            if self.unhealthy_since is None:
                self.unhealthy_since = now
        return result

    def snapshot(self) -> dict[str, Any]:
        healthy = self.evaluate()
        return {
            "healthy": healthy,
            "mode": self.mode.value,
            "problems": dict(self.problems),
            "ages": self.ages(),
            "started_at": self.started_at,
            "unhealthy_since": self.unhealthy_since,
            "bot_name": self.config.bot_name,
        }
