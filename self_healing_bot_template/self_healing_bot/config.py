from __future__ import annotations

import os
from dataclasses import dataclass



def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]



def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class BotConfig:
    bot_name: str
    health_host: str
    health_port: int
    symbols: list[str]
    market_poll_seconds: float
    ping_interval_seconds: float
    reconciliation_interval_seconds: float
    watchdog_interval_seconds: float
    startup_grace_seconds: float
    api_timeout_seconds: float
    heartbeat_timeout_seconds: float
    market_data_timeout_seconds: float
    exchange_timeout_seconds: float
    reconciliation_timeout_seconds: float
    reconnect_initial_delay_seconds: float
    reconnect_max_delay_seconds: float
    reconnect_max_attempts: int
    alert_cooldown_seconds: float
    safe_mode_on_mismatch: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None

    @classmethod
    def from_env(cls) -> "BotConfig":
        return cls(
            bot_name=os.getenv("BOT_NAME", "self-healing-bot"),
            health_host=os.getenv("HEALTH_HOST", "127.0.0.1"),
            health_port=int(os.getenv("HEALTH_PORT", "8080")),
            symbols=_split_csv(os.getenv("SYMBOLS", "BTCUSDT")),
            market_poll_seconds=float(os.getenv("MARKET_POLL_SECONDS", "2")),
            ping_interval_seconds=float(os.getenv("PING_INTERVAL_SECONDS", "5")),
            reconciliation_interval_seconds=float(os.getenv("RECONCILIATION_INTERVAL_SECONDS", "20")),
            watchdog_interval_seconds=float(os.getenv("WATCHDOG_INTERVAL_SECONDS", "5")),
            startup_grace_seconds=float(os.getenv("STARTUP_GRACE_SECONDS", "30")),
            api_timeout_seconds=float(os.getenv("API_TIMEOUT_SECONDS", "10")),
            heartbeat_timeout_seconds=float(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "25")),
            market_data_timeout_seconds=float(os.getenv("MARKET_DATA_TIMEOUT_SECONDS", "30")),
            exchange_timeout_seconds=float(os.getenv("EXCHANGE_TIMEOUT_SECONDS", "30")),
            reconciliation_timeout_seconds=float(os.getenv("RECONCILIATION_TIMEOUT_SECONDS", "90")),
            reconnect_initial_delay_seconds=float(os.getenv("RECONNECT_INITIAL_DELAY_SECONDS", "2")),
            reconnect_max_delay_seconds=float(os.getenv("RECONNECT_MAX_DELAY_SECONDS", "30")),
            reconnect_max_attempts=int(os.getenv("RECONNECT_MAX_ATTEMPTS", "5")),
            alert_cooldown_seconds=float(os.getenv("ALERT_COOLDOWN_SECONDS", "120")),
            safe_mode_on_mismatch=_env_bool("SAFE_MODE_ON_MISMATCH", True),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID") or None,
        )
