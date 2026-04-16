import asyncio
import unittest

from hedgingbot import (
    ChaosScenario,
    DigitalTwin,
    FaultType,
    RepairScriptGenerator,
    SimulationMode,
)


class DigitalTwinTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_scenario_records_metrics(self):
        twin = DigitalTwin(
            components={"router": {"health": 1.0, "latency_ms": 10}},
            random_seed=7,
        )
        scenario = ChaosScenario(
            name="router-latency-smoke",
            mode=SimulationMode.DIGITAL_TWIN,
            duration_seconds=1,
            target_component="router",
            fault_sequence=((FaultType.LATENCY, 0, {"latency_ms": 20}),),
            expected_behavior="health remains above threshold",
            success_criteria=lambda metrics: metrics["health"] >= 0.8,
        )

        result = await twin.run(scenario)

        self.assertTrue(result.success)
        self.assertEqual(result.faults_applied, (FaultType.LATENCY,))
        self.assertEqual(len(twin.results), 1)
        self.assertGreater(result.metrics_after["latency_ms"], result.metrics_before["latency_ms"])

    async def test_failed_scenario_rolls_back_state(self):
        twin = DigitalTwin(components={"risk": {"health": 0.15, "latency_ms": 10}})
        scenario = ChaosScenario(
            name="risk-health-failure",
            mode=SimulationMode.CHAOS_ENGINEERING,
            duration_seconds=1,
            target_component="risk",
            fault_sequence=((FaultType.CPU_SPIKE, 0, {"cpu": 95}),),
            expected_behavior="health remains above threshold",
            success_criteria=lambda metrics: metrics["health"] >= 0.95,
        )

        result = await twin.run(scenario)

        self.assertFalse(result.success)
        self.assertTrue(result.rollback_performed)
        self.assertEqual(twin.components["risk"], {"health": 0.15, "latency_ms": 10})

    async def test_custom_hook_and_rollback_are_used(self):
        async def poison(component, payload):
            component["health"] = 0
            component["fault_payload"] = payload["fault_type"].value

        async def rollback(component):
            component["health"] = 1
            component.pop("fault_payload", None)

        twin = DigitalTwin(
            components={"cache": {"health": 1}},
            fault_hooks={FaultType.CACHE_POISONING: poison},
            rollback_hooks={"cache": rollback},
        )
        scenario = ChaosScenario(
            name="cache-poison",
            mode=SimulationMode.DIGITAL_TWIN,
            duration_seconds=1,
            target_component="cache",
            fault_sequence=((FaultType.CACHE_POISONING, 0, {}),),
            expected_behavior="cache rejects poisoned values",
            success_criteria=lambda metrics: metrics["health"] > 0,
        )

        result = await twin.run(scenario)

        self.assertFalse(result.success)
        self.assertTrue(result.rollback_performed)
        self.assertEqual(twin.components["cache"], {"health": 1})

    async def test_timeout_is_reported_and_rolled_back(self):
        async def slow_hook(component, payload):
            await asyncio.sleep(0.05)
            component["health"] = 0

        twin = DigitalTwin(
            components={"executor": {"health": 1}},
            fault_hooks={FaultType.DEADLOCK: slow_hook},
        )
        scenario = ChaosScenario(
            name="executor-timeout",
            mode=SimulationMode.DIGITAL_TWIN,
            duration_seconds=1,
            target_component="executor",
            fault_sequence=((FaultType.DEADLOCK, 0, {}),),
            expected_behavior="timeout prevents stuck experiments",
            success_criteria=lambda metrics: metrics["health"] == 1,
            timeout_seconds=0.01,
        )

        result = await twin.run(scenario)

        self.assertFalse(result.success)
        self.assertTrue(result.rollback_performed)
        self.assertTrue(any("TimeoutError" in error for error in result.errors))


class ScenarioValidationTests(unittest.TestCase):
    def test_validation_rejects_empty_fault_sequence(self):
        scenario = ChaosScenario(
            name="bad",
            mode=SimulationMode.DIGITAL_TWIN,
            duration_seconds=1,
            target_component="router",
            fault_sequence=(),
            expected_behavior="nothing",
            success_criteria=lambda metrics: True,
        )

        with self.assertRaises(ValueError):
            scenario.validate()


class RepairScriptGeneratorTests(unittest.TestCase):
    def test_rate_limit_result_generates_reviewable_plan(self):
        result = asyncio.run(
            DigitalTwin(components={"exchange": {"health": 1}}).run(
                ChaosScenario(
                    name="rate-limit",
                    mode=SimulationMode.DIGITAL_TWIN,
                    duration_seconds=1,
                    target_component="exchange",
                    fault_sequence=((FaultType.RATE_LIMIT_HIT, 0, {}),),
                    expected_behavior="backoff recovers",
                    success_criteria=lambda metrics: False,
                )
            )
        )

        script = RepairScriptGenerator().generate(result)

        self.assertEqual(script.fault_type, FaultType.RATE_LIMIT_HIT)
        self.assertTrue(script.requires_human_approval)
        self.assertTrue(any("backoff" in command for command in script.commands))


if __name__ == "__main__":
    unittest.main()
