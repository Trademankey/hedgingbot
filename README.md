# Hedging Bot Resilience Harness

This workspace now contains a reviewable Python implementation of the digital-twin and chaos-engineering ideas embedded in `Hedging bot .pages` and `markmap.svg`.

The current code is intentionally simulation-first:

- No live exchange calls.
- No automatic execution of generated repair plans.
- Bounded async experiments with timeout handling.
- Rollback support when a scenario fails.
- Unit tests for validation, metrics, rollback behavior, timeout handling, and repair-plan generation.

## Run Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Basic Usage

```python
import asyncio

from hedgingbot import ChaosScenario, DigitalTwin, FaultType, SimulationMode


async def main():
    twin = DigitalTwin(components={"router": {"health": 1.0, "latency_ms": 10}})
    result = await twin.run(
        ChaosScenario(
            name="router-latency-smoke",
            mode=SimulationMode.DIGITAL_TWIN,
            duration_seconds=1,
            target_component="router",
            fault_sequence=((FaultType.LATENCY, 0, {"latency_ms": 20}),),
            expected_behavior="health remains above threshold",
            success_criteria=lambda metrics: metrics["health"] >= 0.8,
        )
    )
    print(result)


asyncio.run(main())
```
