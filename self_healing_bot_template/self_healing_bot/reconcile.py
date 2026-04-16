from __future__ import annotations

from dataclasses import dataclass, field

from self_healing_bot.models import AccountState, OrderRecord, PositionRecord


@dataclass(slots=True)
class ReconciliationDiff:
    unexpected_orders: list[OrderRecord] = field(default_factory=list)
    missing_orders: list[OrderRecord] = field(default_factory=list)
    unexpected_positions: list[PositionRecord] = field(default_factory=list)
    missing_positions: list[PositionRecord] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not any([
            self.unexpected_orders,
            self.missing_orders,
            self.unexpected_positions,
            self.missing_positions,
        ])

    def summary(self) -> str:
        parts: list[str] = []
        if self.unexpected_orders:
            parts.append(f"unexpected_orders={len(self.unexpected_orders)}")
        if self.missing_orders:
            parts.append(f"missing_orders={len(self.missing_orders)}")
        if self.unexpected_positions:
            parts.append(f"unexpected_positions={len(self.unexpected_positions)}")
        if self.missing_positions:
            parts.append(f"missing_positions={len(self.missing_positions)}")
        return ", ".join(parts) if parts else "clean"


@dataclass(slots=True)
class Reconciler:
    expected_orders: list[OrderRecord] = field(default_factory=list)
    expected_positions: list[PositionRecord] = field(default_factory=list)

    def set_expected_orders(self, orders: list[OrderRecord]) -> None:
        self.expected_orders = list(orders)

    def set_expected_positions(self, positions: list[PositionRecord]) -> None:
        self.expected_positions = list(positions)

    def diff(self, actual: AccountState) -> ReconciliationDiff:
        expected_order_keys = {order.normalized_key(): order for order in self.expected_orders}
        actual_order_keys = {order.normalized_key(): order for order in actual.open_orders}
        expected_position_keys = {position.normalized_key(): position for position in self.expected_positions}
        actual_position_keys = {position.normalized_key(): position for position in actual.positions}

        return ReconciliationDiff(
            unexpected_orders=[actual_order_keys[key] for key in actual_order_keys.keys() - expected_order_keys.keys()],
            missing_orders=[expected_order_keys[key] for key in expected_order_keys.keys() - actual_order_keys.keys()],
            unexpected_positions=[actual_position_keys[key] for key in actual_position_keys.keys() - expected_position_keys.keys()],
            missing_positions=[expected_position_keys[key] for key in expected_position_keys.keys() - actual_position_keys.keys()],
        )
