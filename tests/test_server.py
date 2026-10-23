"""Regression tests for the toolkit's pure engineering calculations."""
import math
import unittest

from server import calculate, parse_os_tile_path


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

    def test_battery_runtime(self):
        result = calculate("/api/calculate/battery-runtime", {
            "capacity_ah": 20, "current_a": 5
        })
        self.assertAlmostEqual(result["ideal_runtime_hours"], 4)

    def test_kinetic_energy(self):
        result = calculate("/api/calculate/kinetic-energy", {
            "mass_kg": 100, "speed_kmh": 36
        })
        self.assertAlmostEqual(result["kinetic_energy_j"], 5000)

    def test_torque_from_power(self):
        result = calculate("/api/calculate/torque-from-power", {
            "power_w": 1000, "rpm": 1000
        })
        self.assertAlmostEqual(result["torque_nm"], 9.5492966, places=6)

    def test_gear_ratio(self):
        result = calculate("/api/calculate/gear-ratio", {
            "input_rpm": 3000, "output_rpm": 1000
        })
        self.assertAlmostEqual(result["reduction_ratio"], 3)

    def test_wheel_circumference(self):
        result = calculate("/api/calculate/wheel-circumference", {
            "wheel_diameter_mm": 200
        })
        self.assertAlmostEqual(result["circumference_mm"], math.pi * 200)

    def test_battery_runtime_rejects_zero_current(self):
        with self.assertRaises(ValueError):
            calculate("/api/calculate/battery-runtime", {
                "capacity_ah": 20, "current_a": 0
            })

    def test_os_tile_path_valid(self):
        self.assertEqual(parse_os_tile_path("/api/maps/os/Leisure/7/63/42.png"),
                         ("Leisure", 7, 63, 42))

    def test_os_tile_path_rejects_unknown_style(self):
        with self.assertRaises(ValueError):
            parse_os_tile_path("/api/maps/os/Unknown/7/63/42.png")

    def test_os_tile_path_rejects_out_of_range_coordinates(self):
        with self.assertRaises(ValueError):
            parse_os_tile_path("/api/maps/os/Leisure/3/8/0.png")

    def test_resistor_divider(self):
        result = calculate("/api/calculate/resistor-divider", {"input_voltage_v":12,"r1_ohm":1000,"r2_ohm":1000})
        self.assertAlmostEqual(result["output_voltage_v"], 6)
        self.assertAlmostEqual(result["divider_current_a"], 0.006)

    def test_led_resistor(self):
        result = calculate("/api/calculate/led-resistor", {"supply_voltage_v":12,"led_forward_voltage_v":2,"led_current_ma":20})
        self.assertAlmostEqual(result["minimum_ideal_resistance_ohm"], 500)
        self.assertAlmostEqual(result["resistor_power_w"], 0.2)

    def test_solar_energy(self):
        result = calculate("/api/calculate/solar-energy", {"panel_power_w":400,"peak_sun_hours":4,"system_efficiency":0.75})
        self.assertAlmostEqual(result["estimated_daily_energy_wh"], 1200)

    def test_thermal_expansion(self):
        result = calculate("/api/calculate/thermal-expansion", {"length_m":2,"alpha_per_c":0.000012,"delta_temp_c":50})
        self.assertAlmostEqual(result["length_change_m"], 0.0012)

    def test_pressure_and_density(self):
        self.assertAlmostEqual(calculate("/api/calculate/pressure", {"force_n":100,"area_m2":0.01})["pressure_pa"], 10000)
        self.assertAlmostEqual(calculate("/api/calculate/density", {"mass_kg":2,"volume_m3":0.001})["density_kg_m3"], 2000)

    def test_unit_conversion(self):
        result = calculate("/api/convert/unit", {"category":"speed","value":60,"from_unit":"mph","to_unit":"km/h"})
        self.assertAlmostEqual(result["value"], 96.56064)

    def test_temperature_conversion(self):
        result = calculate("/api/convert/unit", {"category":"temperature","value":100,"from_unit":"C","to_unit":"F"})
        self.assertAlmostEqual(result["value"], 212)
    def test_gps_distance_same_point(self):
        result = calculate("/api/calculate/gps-distance", {"lat1":51.5,"lon1":-0.1,"lat2":51.5,"lon2":-0.1})
        self.assertAlmostEqual(result["distance_m"], 0)

    def test_track_stats_distance_and_elevation(self):
        result = calculate("/api/calculate/track-stats", {"coordinates":[[-0.1,51.5,100],[-0.11,51.51,110],[-0.12,51.52,105]]})
        self.assertEqual(result["point_count"], 3)
        self.assertGreater(result["distance_m"], 0)
        self.assertAlmostEqual(result["ascent_m"], 10)
        self.assertAlmostEqual(result["descent_m"], 5)

    def test_gps_distance_rejects_invalid_coordinates(self):
        with self.assertRaises(ValueError):
            calculate("/api/calculate/gps-distance", {"lat1":100,"lon1":0,"lat2":0,"lon2":0})
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
