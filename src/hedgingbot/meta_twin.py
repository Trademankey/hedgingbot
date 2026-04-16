"""Digital-twin and chaos-testing primitives for hedging-bot components.

The module is intentionally simulation-first. It can exercise components that
expose small async hooks, but it never places trades, mutates exchange state, or
auto-executes generated repair scripts.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping, MutableMapping, Sequence

logger = logging.getLogger(__name__)


class SimulationMode(str, Enum):
    """Supported execution modes for resilience experiments."""

    DIGITAL_TWIN = "digital_twin"
    CHAOS_ENGINEERING = "chaos"
    SHADOW_MODE = "shadow"
    CANARY = "canary"


class FaultType(str, Enum):
    """Faults the digital twin knows how to inject safely."""

    CPU_SPIKE = "cpu_spike"
    MEMORY_PRESSURE = "memory_pressure"
    NETWORK_PARTITION = "network_partition"
    DISK_FULL = "disk_full"
    LATENCY = "latency"
    DEADLOCK = "deadlock"
    EXCEPTION_STORM = "exception_storm"
    CONFIG_CORRUPTION = "config_corruption"
    DATABASE_BACKPRESSURE = "database_backpressure"
    CACHE_POISONING = "cache_poisoning"
    MESSAGE_LOSS = "message_loss"
    CLOCK_SKEW = "clock_skew"
    API_DEGRADATION = "api_degradation"
    THIRD_PARTY_OUTAGE = "third_party_outage"
    RATE_LIMIT_HIT = "rate_limit_hit"


HealthCheck = Callable[[Mapping[str, Any]], bool]
AsyncHook = Callable[[MutableMapping[str, Any], Mapping[str, Any]], Awaitable[None]]
RollbackHook = Callable[[MutableMapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class ChaosScenario:
    """Defines one bounded resilience experiment."""

    name: str
    mode: SimulationMode
    duration_seconds: float
    target_component: str
    fault_sequence: Sequence[tuple[FaultType, float, Mapping[str, Any]]]
    expected_behavior: str
    success_criteria: HealthCheck
    rollback_on_failure: bool = True
    max_blast_radius: str = "simulation"
    timeout_seconds: float | None = None

    def validate(self) -> None:
        """Reject ambiguous or unsafe scenarios before execution."""

        if not self.name.strip():
            raise ValueError("Scenario name is required.")
        if not self.target_component.strip():
            raise ValueError("target_component is required.")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when provided.")
        if not self.fault_sequence:
            raise ValueError("fault_sequence must include at least one fault.")
        for fault_type, delay_seconds, _payload in self.fault_sequence:
            if not isinstance(fault_type, FaultType):
                raise TypeError(f"Unsupported fault type: {fault_type!r}")
            if delay_seconds < 0:
                raise ValueError("fault delay cannot be negative.")


@dataclass(frozen=True)
class ScenarioResult:
    """Immutable result of one scenario run."""

    scenario_name: str
    target_component: str
    success: bool
    started_at: float
    ended_at: float
    faults_applied: tuple[FaultType, ...]
    metrics_before: Mapping[str, Any]
    metrics_after: Mapping[str, Any]
    errors: tuple[str, ...] = ()
    rollback_performed: bool = False
    lessons_learned: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)


@dataclass(frozen=True)
class RepairScript:
    """Reviewable remediation output. Callers decide whether to apply it."""

    name: str
    fault_type: FaultType
    description: str
    commands: tuple[str, ...]
    risk_level: str
    requires_human_approval: bool = True


@dataclass
class DigitalTwin:
    """Runs bounded fault simulations against in-memory component state."""

    components: MutableMapping[str, MutableMapping[str, Any]]
    fault_hooks: Mapping[FaultType, AsyncHook] = field(default_factory=dict)
    rollback_hooks: Mapping[str, RollbackHook] = field(default_factory=dict)
    random_seed: int | None = None
    history_size: int = 100

    def __post_init__(self) -> None:
        if self.history_size <= 0:
            raise ValueError("history_size must be positive.")
        self._rng = random.Random(self.random_seed)
        self.results: deque[ScenarioResult] = deque(maxlen=self.history_size)

    async def run(self, scenario: ChaosScenario) -> ScenarioResult:
        """Execute one scenario and return a complete audit-friendly result."""

        scenario.validate()
        if scenario.target_component not in self.components:
            raise KeyError(f"Unknown component: {scenario.target_component}")

        started_at = time.time()
        component = self.components[scenario.target_component]
        original_component = copy.deepcopy(component)
        metrics_before = self._capture_metrics(component)
        faults_applied: list[FaultType] = []
        errors: list[str] = []
        rollback_performed = False

        try:
            timeout = scenario.timeout_seconds or scenario.duration_seconds + 1.0
            await asyncio.wait_for(
                self._apply_fault_sequence(scenario, component, faults_applied),
                timeout=timeout,
            )
            success = bool(scenario.success_criteria(self._capture_metrics(component)))
        except asyncio.TimeoutError:
            success = False
            errors.append(f"TimeoutError: scenario exceeded {timeout:.3f}s")
            logger.info("Scenario %s timed out after %.3fs", scenario.name, timeout)
        except Exception as exc:  # noqa: BLE001 - result object records the failure.
            success = False
            errors.append(f"{type(exc).__name__}: {exc}")
            logger.warning("Scenario %s failed: %s", scenario.name, exc)

        if not success and scenario.rollback_on_failure:
            rollback_performed = await self._rollback(
                scenario.target_component,
                component,
                original_component,
                errors,
            )

        metrics_after = self._capture_metrics(component)
        ended_at = time.time()
        result = ScenarioResult(
            scenario_name=scenario.name,
            target_component=scenario.target_component,
            success=success,
            started_at=started_at,
            ended_at=ended_at,
            faults_applied=tuple(faults_applied),
            metrics_before=metrics_before,
            metrics_after=metrics_after,
            errors=tuple(errors),
            rollback_performed=rollback_performed,
            lessons_learned=tuple(self._derive_lessons(success, faults_applied, errors)),
            recommendations=tuple(self._recommend(success, faults_applied, metrics_after)),
        )
        self.results.append(result)
        return result

    async def _apply_fault_sequence(
        self,
        scenario: ChaosScenario,
        component: MutableMapping[str, Any],
        faults_applied: list[FaultType],
    ) -> None:
        for fault_type, delay_seconds, payload in scenario.fault_sequence:
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
            hook = self.fault_hooks.get(fault_type, self._default_fault_hook)
            await hook(component, {"fault_type": fault_type, **dict(payload)})
            faults_applied.append(fault_type)

    async def _default_fault_hook(
        self,
        component: MutableMapping[str, Any],
        payload: Mapping[str, Any],
    ) -> None:
        fault_type = payload["fault_type"]
        component.setdefault("faults", []).append(fault_type.value)
        component["health"] = max(0.0, float(component.get("health", 1.0)) - 0.1)
        component["latency_ms"] = float(component.get("latency_ms", 0.0)) + self._rng.uniform(5, 25)

    async def _rollback(
        self,
        component_name: str,
        component: MutableMapping[str, Any],
        original_component: MutableMapping[str, Any],
        errors: list[str],
    ) -> bool:
        try:
            hook = self.rollback_hooks.get(component_name)
            if hook is not None:
                await hook(component)
            else:
                component.clear()
                component.update(original_component)
            return True
        except Exception as exc:  # noqa: BLE001 - rollback failures must be surfaced.
            errors.append(f"Rollback failed: {type(exc).__name__}: {exc}")
            logger.exception("Rollback failed for component %s", component_name)
            return False

    @staticmethod
    def _capture_metrics(component: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "health": float(component.get("health", 1.0)),
            "latency_ms": float(component.get("latency_ms", 0.0)),
            "error_rate": float(component.get("error_rate", 0.0)),
            "open_positions": int(component.get("open_positions", 0)),
            "fault_count": len(component.get("faults", [])),
        }

    @staticmethod
    def _derive_lessons(success: bool, faults: Sequence[FaultType], errors: Sequence[str]) -> list[str]:
        if success:
            return [f"Component tolerated {len(faults)} injected fault(s)."]
        if errors:
            return ["Failure path produced explicit errors; preserve these for regression tests."]
        return ["Success criteria were not met; tighten component guardrails or recovery policy."]

    @staticmethod
    def _recommend(
        success: bool,
        faults: Sequence[FaultType],
        metrics_after: Mapping[str, Any],
    ) -> list[str]:
        recommendations: list[str] = []
        if not success:
            recommendations.append("Add a targeted recovery playbook for this scenario.")
        if metrics_after["latency_ms"] > 100:
            recommendations.append("Investigate latency budget and circuit-breaker thresholds.")
        if FaultType.RATE_LIMIT_HIT in faults:
            recommendations.append("Verify exchange API backoff and request budgeting.")
        return recommendations


class RepairScriptGenerator:
    """Maps observed failures to conservative, human-reviewed repair scripts."""

    def generate(self, result: ScenarioResult) -> RepairScript:
        if result.faults_applied:
            fault_type = result.faults_applied[-1]
        else:
            fault_type = FaultType.EXCEPTION_STORM

        if fault_type == FaultType.RATE_LIMIT_HIT:
            commands = (
                "review exchange client retry budget",
                "enable exponential backoff with jitter",
                "lower max concurrent requests for the affected venue",
            )
            description = "Reduce request pressure and make retries less bursty."
        elif fault_type == FaultType.LATENCY:
            commands = (
                "capture p95 and p99 latency traces",
                "tighten circuit-breaker open threshold",
                "shed non-critical analytics work before order-routing work",
            )
            description = "Protect trading-critical paths when latency rises."
        elif fault_type == FaultType.CONFIG_CORRUPTION:
            commands = (
                "restore last signed configuration snapshot",
                "validate config schema before restart",
                "block unsigned config changes in production",
            )
            description = "Recover trusted configuration and prevent recurrence."
        else:
            commands = (
                "isolate affected component",
                "replay the scenario in digital-twin mode",
                "add a regression test for the observed failure",
            )
            description = "Generic containment plan for an unclassified failure."

        return RepairScript(
            name=f"{result.target_component}_{fault_type.value}_repair",
            fault_type=fault_type,
            description=description,
            commands=commands,
            risk_level="low" if result.rollback_performed else "medium",
        )
