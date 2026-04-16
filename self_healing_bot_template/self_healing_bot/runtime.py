from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress

from self_healing_bot.alerting import TelegramAlerter
from self_healing_bot.config import BotConfig
from self_healing_bot.exchange import ExchangeAdapter
from self_healing_bot.health import BotMode, HealthState
from self_healing_bot.httpserver import HealthHttpServer
from self_healing_bot.notify import SystemdNotifier
from self_healing_bot.reconcile import Reconciler

logger = logging.getLogger(__name__)


class SelfHealingBotRuntime:
    def __init__(self, config: BotConfig, exchange: ExchangeAdapter, alerter: TelegramAlerter) -> None:
        self.config = config
        self.exchange = exchange
        self.alerter = alerter
        self.health = HealthState(config=config)
        self.reconciler = Reconciler()
        self.notifier = SystemdNotifier()
        self.health_server = HealthHttpServer(
            host=config.health_host,
            port=config.health_port,
            snapshot_factory=self.health.snapshot,
        )
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def run(self) -> None:
        self._install_signal_handlers()
        await self.health_server.start()
        self.health.set_mode(BotMode.HEALTHY)
        self.notifier.ready(f"{self.config.bot_name} ready")
        await self.alerter.send(f"✅ {self.config.bot_name} started", dedupe_key="started")

        stop_task = asyncio.create_task(self._stop_event.wait(), name="stop_waiter")
        self._tasks = [
            asyncio.create_task(self._market_data_loop(), name="market_data_loop"),
            asyncio.create_task(self._ping_loop(), name="ping_loop"),
            asyncio.create_task(self._reconciliation_loop(), name="reconciliation_loop"),
            asyncio.create_task(self._watchdog_loop(), name="watchdog_loop"),
            asyncio.create_task(self._systemd_watchdog_loop(), name="systemd_watchdog_loop"),
            stop_task,
        ]

        done, pending = await asyncio.wait(
            self._tasks,
            return_when=asyncio.FIRST_EXCEPTION,
        )

        first_exc: BaseException | None = None
        for task in done:
            with suppress(asyncio.CancelledError):
                exc = task.exception()
                if exc is not None:
                    first_exc = exc
                    break

        if first_exc is not None:
            logger.exception("Fatal task failure: %s", first_exc)
            await self.alerter.send(
                f"🛑 {self.config.bot_name} fatal failure: {first_exc}",
                dedupe_key="fatal_failure",
            )
            await self.shutdown(exit_code=1)
            raise SystemExit(1)

        for task in pending:
            task.cancel()
        await self.shutdown(exit_code=0)

    async def shutdown(self, exit_code: int) -> None:
        self.health.set_mode(BotMode.STOPPING)
        self.notifier.stopping(f"{self.config.bot_name} stopping")
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        await self.health_server.stop()
        await self.alerter.send(
            f"ℹ️ {self.config.bot_name} stopped with exit code {exit_code}",
            dedupe_key=f"stopped_{exit_code}",
        )

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._stop_event.set)

    async def _market_data_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                snapshots = await asyncio.wait_for(
                    self.exchange.poll_market_snapshot(self.config.symbols),
                    timeout=self.config.api_timeout_seconds,
                )
                if snapshots:
                    self.health.touch_market_data()
                    self.health.touch_heartbeat()
                    self.health.clear_problem("market_data")
                    if self.health.mode == BotMode.DEGRADED:
                        self.health.set_mode(BotMode.HEALTHY)
                logger.debug("Market snapshots received: %s", len(snapshots))
            except Exception as exc:
                await self._handle_reconnect("market_data", exc)
            await asyncio.sleep(self.config.market_poll_seconds)

    async def _ping_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self.exchange.ping(), timeout=self.config.api_timeout_seconds)
                self.health.touch_exchange_ok()
                self.health.touch_heartbeat()
                self.health.clear_problem("exchange_ping")
            except Exception as exc:
                self.health.set_problem("exchange_ping", str(exc))
                logger.warning("Exchange ping failed: %s", exc)
            await asyncio.sleep(self.config.ping_interval_seconds)

    async def _reconciliation_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                account_state = await asyncio.wait_for(
                    self.exchange.fetch_account_state(),
                    timeout=self.config.api_timeout_seconds,
                )
                diff = self.reconciler.diff(account_state)
                self.health.touch_reconciliation()
                self.health.touch_heartbeat()
                if diff.is_clean():
                    self.health.clear_problem("reconciliation")
                else:
                    summary = diff.summary()
                    self.health.set_problem("reconciliation", summary)
                    logger.error("Reconciliation mismatch: %s", summary)
                    await self.alerter.send(
                        f"⚠️ {self.config.bot_name} reconciliation mismatch: {summary}",
                        dedupe_key="reconciliation_mismatch",
                    )
                    if self.config.safe_mode_on_mismatch:
                        self.health.set_mode(BotMode.SAFE_MODE)
                logger.debug("Reconciliation completed")
            except Exception as exc:
                self.health.set_problem("reconciliation", str(exc))
                logger.warning("Reconciliation failed: %s", exc)
            await asyncio.sleep(self.config.reconciliation_interval_seconds)

    async def _watchdog_loop(self) -> None:
        while not self._stop_event.is_set():
            snapshot = self.health.snapshot()
            healthy = snapshot["healthy"]
            mode = snapshot["mode"]
            if healthy:
                logger.info("STATE=%s ages=%s", mode, snapshot["ages"])
            else:
                logger.warning("STATE=%s problems=%s ages=%s", mode, snapshot["problems"], snapshot["ages"])
                unhealthy_since = snapshot.get("unhealthy_since")
                if unhealthy_since is not None:
                    unhealthy_for = max(0.0, __import__("time").time() - unhealthy_since)
                    if unhealthy_for >= self.config.watchdog_interval_seconds * 3:
                        await self.alerter.send(
                            f"🧯 {self.config.bot_name} watchdog forcing restart. mode={mode} problems={snapshot['problems']}",
                            dedupe_key="watchdog_restart",
                        )
                        raise RuntimeError("watchdog forced restart due to prolonged unhealthy state")
            await asyncio.sleep(self.config.watchdog_interval_seconds)

    async def _systemd_watchdog_loop(self) -> None:
        while not self._stop_event.is_set():
            self.notifier.watchdog(f"{self.config.bot_name} mode={self.health.mode.value}")
            await asyncio.sleep(max(1.0, self.config.watchdog_interval_seconds))

    async def _handle_reconnect(self, component: str, exc: Exception) -> None:
        self.health.set_problem(component, str(exc))
        self.health.set_mode(BotMode.RECONNECTING)
        logger.warning("%s failure: %s", component, exc)
        await self.alerter.send(
            f"🔌 {self.config.bot_name} reconnecting after {component} failure: {exc}",
            dedupe_key=f"reconnect_{component}",
        )

        delay = self.config.reconnect_initial_delay_seconds
        for attempt in range(1, self.config.reconnect_max_attempts + 1):
            try:
                await asyncio.wait_for(
                    self.exchange.reconnect(reason=f"{component}:{exc}"),
                    timeout=self.config.api_timeout_seconds,
                )
                self.health.clear_problem(component)
                self.health.clear_problem("exchange_ping")
                self.health.touch_exchange_ok()
                self.health.touch_market_data()
                self.health.touch_heartbeat()
                self.health.set_mode(BotMode.HEALTHY)
                await self.alerter.send(
                    f"✅ {self.config.bot_name} recovered after {component} failure on attempt {attempt}",
                    dedupe_key=f"recovered_{component}",
                )
                return
            except Exception as reconnect_exc:
                logger.warning(
                    "Reconnect attempt %s/%s failed for %s: %s",
                    attempt,
                    self.config.reconnect_max_attempts,
                    component,
                    reconnect_exc,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.reconnect_max_delay_seconds)

        self.health.set_problem(component, f"reconnect attempts exhausted after error: {exc}")
