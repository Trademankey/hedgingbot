from __future__ import annotations

import asyncio
import logging

from self_healing_bot.alerting import TelegramAlerter
from self_healing_bot.config import BotConfig
from self_healing_bot.exchange import DemoExchangeAdapter
from self_healing_bot.runtime import SelfHealingBotRuntime


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def amain() -> None:
    config = BotConfig.from_env()
    alerter = TelegramAlerter(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        cooldown_seconds=config.alert_cooldown_seconds,
    )

    # Replace DemoExchangeAdapter with your real exchange adapter.
    adapter = DemoExchangeAdapter(symbols=config.symbols)

    runtime = SelfHealingBotRuntime(
        config=config,
        exchange=adapter,
        alerter=alerter,
    )
    await runtime.run()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(amain())
