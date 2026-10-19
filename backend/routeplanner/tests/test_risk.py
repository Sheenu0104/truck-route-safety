from django.test import SimpleTestCase

from routeplanner.domain.risk import Risk, assess, classify_rain, classify_snow, classify_wind, load_rule

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


class ThresholdTests(SimpleTestCase):
    def check(self, fn, cases):
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(fn(value), expected)

    def test_wind_bands(self):
        self.check(classify_wind, [
            (0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H),
            (45, S), (54.9, S), (55, N), (90, N),
        ])

    def test_rain_bands(self):
        self.check(classify_rain, [
            (0, L), (0.099, L), (0.10, M), (0.249, M), (0.25, H), (0.499, H),
            (0.50, S), (1.00, S), (1.001, N), (2.5, N),
        ])

    def test_snow_bands(self):
        self.check(classify_snow, [
            (0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H),
            (2.0, S), (3.0, S), (3.01, N),
        ])


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(load_rule(55, 0), N)
        self.assertEqual(assess(60, 0, 0, 1_000).level, N)

    def test_45_to_54_mph_over_30k_is_no_travel(self):
        self.assertIsNone(load_rule(50, 30_000))  # exactly 30,000 is not "over"
        self.assertEqual(assess(50, 0, 0, 30_000).level, S)
        self.assertEqual(assess(50, 0, 0, 30_001).level, N)
        self.assertEqual(assess(45, 0, 0, 80_000).level, N)

    def test_35_to_44_mph_over_40k_is_severe(self):
        self.assertEqual(assess(40, 0, 0, 40_000).level, H)
        self.assertEqual(assess(40, 0, 0, 40_001).level, S)
        self.assertEqual(assess(44.9, 0, 0, 80_000).level, S)

    def test_load_rule_never_lowers_risk(self):
        # Heavy snow already No Travel; light wind + heavy load must not reduce it.
        self.assertEqual(assess(36, 0, 3.5, 50_000).level, N)

    def test_no_load_rule_below_35_mph(self):
        self.assertIsNone(load_rule(34.9, 80_000))
        self.assertEqual(assess(30, 0, 0, 80_000).level, M)


class AssessTests(SimpleTestCase):
    def test_worst_condition_wins(self):
        result = assess(20, 0.3, 0.6, 10_000)
        self.assertEqual(result.level, H)
        self.assertEqual((result.wind, result.rain, result.snow), (L, H, M))
        self.assertEqual(result.drivers, ("Rain 0.30 in/hr",))

    def test_load_driver_is_explained(self):
        result = assess(40, 0, 0, 45_000)
        self.assertEqual(result.level, S)
        self.assertEqual(result.load_rule, S)
        self.assertIn("Wind 40 mph with 45,000 lb load", result.drivers)

    def test_low_has_no_drivers(self):
        self.assertEqual(assess(5, 0, 0, 20_000).drivers, ())
