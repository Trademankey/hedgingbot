from __future__ import annotations

import abc
import asyncio
import random
import time
from typing import Sequence

from self_healing_bot.models import AccountState, MarketSnapshot, OrderRecord, PositionRecord


class ExchangeAdapter(abc.ABC):
    @abc.abstractmethod
    async def ping(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def poll_market_snapshot(self, symbols: Sequence[str]) -> list[MarketSnapshot]:
        raise NotImplementedError

    @abc.abstractmethod
    async def fetch_open_orders(self) -> list[OrderRecord]:
        raise NotImplementedError

    @abc.abstractmethod
    async def fetch_positions(self) -> list[PositionRecord]:
        raise NotImplementedError

    @abc.abstractmethod
    async def fetch_balances(self) -> dict[str, float]:
        raise NotImplementedError

    @abc.abstractmethod
    async def reconnect(self, reason: str) -> None:
        raise NotImplementedError

    async def fetch_account_state(self) -> AccountState:
        orders, positions, balances = await asyncio.gather(
            self.fetch_open_orders(),
            self.fetch_positions(),
            self.fetch_balances(),
        )
        return AccountState(open_orders=orders, positions=positions, balances=balances)


class DemoExchangeAdapter(ExchangeAdapter):
    """
    Demo adapter so the framework runs immediately.

    Replace this with your real exchange implementation.
    """

    def __init__(self, symbols: Sequence[str]) -> None:
        self.symbols = list(symbols)
        self._prices = {symbol: 100.0 + idx * 50 for idx, symbol in enumerate(self.symbols)}
        self._online = True

    async def ping(self) -> None:
        await asyncio.sleep(0.05)
        if not self._online:
            raise RuntimeError("demo exchange offline")

    async def poll_market_snapshot(self, symbols: Sequence[str]) -> list[MarketSnapshot]:
        await asyncio.sleep(0.1)
        if not self._online:
            raise RuntimeError("market data unavailable")
        snapshots: list[MarketSnapshot] = []
        ts = time.time()
        for symbol in symbols:
            base = self._prices.setdefault(symbol, 100.0)
            base += random.uniform(-0.8, 0.8)
            self._prices[symbol] = max(1.0, base)
            snapshots.append(MarketSnapshot(symbol=symbol, price=base, timestamp=ts))
        return snapshots

    async def fetch_open_orders(self) -> list[OrderRecord]:
        await asyncio.sleep(0.1)
        return []

    async def fetch_positions(self) -> list[PositionRecord]:
        await asyncio.sleep(0.1)
        return []

    async def fetch_balances(self) -> dict[str, float]:
        await asyncio.sleep(0.1)
        return {"USDT": 10000.0}

    async def reconnect(self, reason: str) -> None:
        await asyncio.sleep(0.5)
        self._online = True
