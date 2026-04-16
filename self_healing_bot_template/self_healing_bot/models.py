from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    price: float
    timestamp: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderRecord:
    order_id: str
    symbol: str
    side: str
    quantity: float
    status: str = "open"

    def normalized_key(self) -> tuple[str, str, int]:
        return (self.symbol.upper(), self.side.lower(), round(self.quantity * 1000000))


@dataclass(slots=True)
class PositionRecord:
    symbol: str
    quantity: float
    side: str

    def normalized_key(self) -> tuple[str, str, int]:
        return (self.symbol.upper(), self.side.lower(), round(self.quantity * 1000000))


@dataclass(slots=True)
class AccountState:
    open_orders: list[OrderRecord]
    positions: list[PositionRecord]
    balances: dict[str, float]
