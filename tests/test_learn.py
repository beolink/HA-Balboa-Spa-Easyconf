"""Learning the parts' powers from a meter that also sees the rest of the house."""

from __future__ import annotations

import random

import pytest

from custom_components.balboa_easyconf.learn import MAX_SAMPLES, PowerLearner
from custom_components.balboa_easyconf.model import OFF, Component

HEATER = Component("heater", "heater", None, ("on",))
PUMP1 = Component("pump_1", "pump", 1, ("low", "high"))
PUMP2 = Component("pump_2", "pump", 2, ("on",))
STANDBY = Component("standby", "standby", None, ("on",))
PARTS = [HEATER, PUMP1, PUMP2, STANDBY]
TRUE = {"heater": 2950.0, "pump_1_low": 435.0, "pump_1_high": 1700.0, "pump_2": 2000.0}
IDLE = {"heater": OFF, "pump_1": OFF, "pump_2": OFF, "standby": "on"}


def spa_watts(levels: dict[str, str]) -> float:
    watts = 0.0
    if levels["heater"] == "on":
        watts += TRUE["heater"]
    if levels["pump_1"] != OFF:
        watts += TRUE[f"pump_1_{levels['pump_1']}"]
    if levels["pump_2"] == "on":
        watts += TRUE["pump_2"]
    return watts


class House:
    """A meter reading every `period` s: a wandering base load plus the spa."""

    def __init__(self, learner: PowerLearner, *, seed: int = 1, period: float = 5.0, noise: float = 15.0) -> None:
        self.learner = learner
        self.rng = random.Random(seed)
        self.period = period
        self.noise = noise
        self.t = 0.0
        self.base = 1500.0
        self.levels = dict(IDLE)
        self.next_reading = 0.0
        learner.observe_levels(self.t, self.levels)

    def run(self, seconds: float, step: float = 1.0) -> None:
        end = self.t + seconds
        while self.t < end:
            self.t += step
            if self.t >= self.next_reading:
                self.base += self.rng.uniform(-5, 5)
                watts = self.base + spa_watts(self.levels) + self.rng.gauss(0, self.noise)
                self.learner.observe_reference(self.t, watts)
                self.next_reading = self.t + self.period
            self.learner.evaluate(self.t)

    def set(self, **levels: str) -> None:
        self.levels.update(levels)
        self.learner.observe_levels(self.t, self.levels)


def test_an_isolated_pump_is_learned():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(60)
    for _ in range(5):  # like the BP2100G1 it was built on: pump 1 low for a minute every half hour
        house.set(pump_1="low")
        house.run(65)
        house.set(pump_1=OFF)
        house.run(300)
    assert learner.count("pump_1_low") == 10
    assert learner.estimate("pump_1_low") == pytest.approx(435, abs=25)
    assert learner.estimate("heater") is None


def test_needs_three_measurements():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(60)
    house.set(pump_2="on")
    house.run(60)
    house.set(pump_2=OFF)
    house.run(60)
    assert learner.count("pump_2") == 2
    assert learner.estimate("pump_2") is None
    house.set(pump_2="on")
    house.run(60)
    assert learner.estimate("pump_2") == pytest.approx(2000, abs=40)


def test_heater_following_the_pump_is_learned_once_the_pump_is_known():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(60)
    # The heater never switches alone: pump 1 starts, the heater 3 s later,
    # and both stop together.
    for _ in range(2):
        house.set(pump_1="low")
        house.run(3)
        house.set(heater="on")
        house.run(600)
        house.set(heater=OFF, pump_1=OFF)
        house.run(600)
    assert learner.estimate("heater") is None  # two unknowns at once: nothing to say yet
    for _ in range(3):
        house.set(pump_1="low")
        house.run(65)
        house.set(pump_1=OFF)
        house.run(120)
    assert learner.estimate("pump_1_low") is not None
    for _ in range(3):
        house.set(pump_1="low")
        house.run(3)
        house.set(heater="on")
        house.run(600)
        house.set(heater=OFF, pump_1=OFF)
        house.run(600)
    assert learner.estimate("heater") == pytest.approx(2950, abs=60)


def test_low_to_high_gives_high_once_low_is_known():
    learner = PowerLearner(PARTS, {"pump_1_low": [430.0, 435.0, 440.0]})
    house = House(learner)
    house.run(60)
    for _ in range(3):
        house.set(pump_1="low")
        house.run(60)
        house.set(pump_1="high")
        house.run(60)
        house.set(pump_1=OFF)
        house.run(60)
    # off->low and high->off are isolated too; low->high measures high - low.
    assert learner.estimate("pump_1_high") == pytest.approx(1700, abs=50)


def test_changes_too_close_together_are_not_measured():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(60)
    for _ in range(10):  # priming: each pump for 5 s in turn
        house.set(pump_1="low")
        house.run(5)
        house.set(pump_1=OFF, pump_2="on")
        house.run(5)
        house.set(pump_2=OFF)
        house.run(12)
    house.run(120)
    assert learner.samples == {}
    assert learner.events == 0


def test_a_change_soon_after_start_is_not_measured():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(10)  # less than the quiet time since the hub started watching
    house.set(pump_2="on")
    house.run(60)
    assert learner.count("pump_2") == 0
    house.set(pump_2=OFF)
    house.run(60)
    assert learner.count("pump_2") == 1


def test_another_load_switching_at_the_same_moment_is_dropped():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(60)
    house.set(pump_1="low")
    house.base -= 2000  # something else stops just then: the step comes out negative
    house.run(60)
    assert learner.count("pump_1_low") == 0
    assert learner.rejected == 1


def test_no_meter_no_measurement():
    learner = PowerLearner(PARTS)
    learner.observe_levels(0, IDLE)
    learner.observe_levels(100, {**IDLE, "pump_2": "on"})
    learner.evaluate(200)
    assert learner.samples == {}


def test_spa_gone_forgets_what_was_pending():
    learner = PowerLearner(PARTS)
    house = House(learner)
    house.run(60)
    house.set(pump_2="on")
    learner.lost(house.t + 1)
    house.run(60)
    assert learner.count("pump_2") == 0


def test_keeps_the_last_measurements_and_unknown_keys_are_dropped():
    learner = PowerLearner(PARTS, {"pump_2": [1.0] * 40, "pump_9": [5.0]})
    assert learner.count("pump_2") == MAX_SAMPLES
    assert "pump_9" not in learner.samples
    learner.reset()
    assert learner.samples == {}


def test_readings_are_trimmed():
    learner = PowerLearner(PARTS)
    house = House(learner, period=1.0)
    house.run(3600)
    assert len(learner._readings) < 200


def test_a_meter_that_only_reports_changes_is_enough():
    learner = PowerLearner(PARTS)
    learner.observe_levels(0, IDLE)
    learner.observe_reference(1, 1500)
    learner.observe_levels(100, {**IDLE, "pump_2": "on"})
    learner.observe_reference(101, 3500)
    learner.evaluate(200)
    assert learner.samples == {"pump_2": [2000.0]}


def test_a_stale_meter_teaches_nothing():
    learner = PowerLearner(PARTS)
    learner.observe_levels(0, IDLE)
    learner.observe_reference(1, 1500)  # and then nothing
    learner.observe_levels(100, {**IDLE, "pump_2": "on"})
    learner.evaluate(200)
    assert learner.samples == {}
