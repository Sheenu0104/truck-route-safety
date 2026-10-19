from django.test import SimpleTestCase

from routeplanner.services.weather import HourlySeries, parse_location

HOUR = 3600


class SampleTests(SimpleTestCase):
    def setUp(self):
        self.series = HourlySeries(
            times=[0, HOUR, 2 * HOUR],
            wind=[10.0, 20.0, 30.0],
            gust=[15.0, 25.0, 35.0],
            rain=[0.0, 0.2, 0.4],
            snow=[0.0, 0.0, 1.0],
            temp=[30.0, 32.0, 34.0],
            code=[0, 61, 71],
        )

    def test_wind_is_interpolated(self):
        self.assertAlmostEqual(self.series.sample(HOUR / 2).wind_mph, 15.0)
        self.assertAlmostEqual(self.series.sample(1.75 * HOUR).gust_mph, 32.5)

    def test_precipitation_uses_the_hour_bucket_containing_the_time(self):
        # Values are totals over the preceding hour, so 01:30 falls in the bucket stamped 02:00.
        self.assertEqual(self.series.sample(1.5 * HOUR).rain_in_hr, 0.4)
        self.assertEqual(self.series.sample(1.5 * HOUR).snow_in_hr, 1.0)
        self.assertEqual(self.series.sample(HOUR).rain_in_hr, 0.2)

    def test_clamps_outside_range(self):
        late = self.series.sample(2 * HOUR + 600)
        self.assertEqual(late.wind_mph, 30.0)
        self.assertFalse(late.missing)

    def test_missing_values_are_flagged(self):
        self.series.rain[1] = None
        self.assertTrue(self.series.sample(HOUR).missing)


class ParseTests(SimpleTestCase):
    def test_metric_units_are_converted(self):
        item = {
            "hourly_units": {"wind_speed_10m": "km/h", "wind_gusts_10m": "km/h", "rain": "mm",
                             "showers": "mm", "snowfall": "cm", "temperature_2m": "°C"},
            "hourly": {
                "time": [0, HOUR],
                "wind_speed_10m": [100.0, 0.0],
                "wind_gusts_10m": [120.0, 0.0],
                "rain": [25.4, None],
                "showers": [2.54, None],
                "snowfall": [2.54, 0.0],
                "temperature_2m": [0.0, 10.0],
                "weather_code": [61, None],
            },
        }
        s = parse_location(item)
        self.assertAlmostEqual(s.wind[0], 62.1371, places=3)
        self.assertAlmostEqual(s.rain[0], 1.1, places=6)  # rain + showers
        self.assertIsNone(s.rain[1])
        self.assertAlmostEqual(s.snow[0], 1.0, places=6)
        self.assertAlmostEqual(s.temp[0], 32.0)
        self.assertEqual(s.code, [61, None])
