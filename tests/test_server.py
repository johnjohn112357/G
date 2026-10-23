"""Regression tests for the toolkit's pure engineering calculations."""
import math
import unittest

from server import calculate


class CalculationTests(unittest.TestCase):
    def test_battery_energy(self):
        result = calculate("/api/calculate/battery-energy", {
            "voltage_v": 48, "capacity_ah": 20
        })
        self.assertAlmostEqual(result["nominal_energy_wh"], 960)

    def test_battery_sag(self):
        result = calculate("/api/calculate/battery-sag", {
            "open_circuit_voltage_v": 50, "current_a": 10,
            "internal_resistance_ohm": 0.1
        })
        self.assertAlmostEqual(result["voltage_sag_v"], 1)
        self.assertAlmostEqual(result["estimated_loaded_voltage_v"], 49)

    def test_wheel_speed(self):
        result = calculate("/api/calculate/wheel-speed", {
            "rpm": 500, "wheel_diameter_mm": 200
        })
        self.assertAlmostEqual(result["ideal_speed_kmh"], 18.8495559, places=6)

    def test_ohms_law_derives_missing_resistance(self):
        result = calculate("/api/calculate/ohms-law", {
            "voltage_v": 12, "current_a": 3
        })
        self.assertAlmostEqual(result["resistance_ohm"], 4)

    def test_voltage_drop_and_dissipation(self):
        result = calculate("/api/calculate/voltage-drop", {
            "current_a": 10, "resistance_ohm": 0.02
        })
        self.assertAlmostEqual(result["voltage_drop_v"], 0.2)
        self.assertAlmostEqual(result["power_dissipation_w"], 2)

    def test_mechanical_power(self):
        result = calculate("/api/calculate/mechanical-power", {
            "torque_nm": 10, "rpm": 1000
        })
        self.assertAlmostEqual(result["power_w"], 1047.1975512, places=5)

    def test_rejects_nan(self):
        with self.assertRaises(ValueError):
            calculate("/api/calculate/battery-energy", {
                "voltage_v": float("nan"), "capacity_ah": 20
            })

    def test_rejects_negative_physical_input(self):
        with self.assertRaises(ValueError):
            calculate("/api/calculate/wheel-speed", {
                "rpm": 500, "wheel_diameter_mm": -200
            })

    def test_unknown_calculation(self):
        with self.assertRaises(KeyError):
            calculate("/api/calculate/not-a-calculation", {})


if __name__ == "__main__":
    unittest.main()
