from datetime import datetime, timezone
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from routeplanner.services import met_norway, weather
from routeplanner.services.http import UpstreamError

HOUR = 3600
T0 = int(datetime(2026, 10, 20, 12, tzinfo=timezone.utc).timestamp())


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def met_doc() -> dict:
    """Three hourly entries, then one 6-hourly entry, like the real API."""
    def entry(t, wind, temp, next1=None, next6=None):
        data = {"instant": {"details": {"wind_speed": wind, "wind_speed_of_gust": wind * 1.5, "air_temperature": temp}}}
        if next1:
            data["next_1_hours"] = {"summary": {"symbol_code": next1[1]}, "details": {"precipitation_amount": next1[0]}}
        if next6:
            data["next_6_hours"] = {"summary": {"symbol_code": next6[1]}, "details": {"precipitation_amount": next6[0]}}
        return {"time": iso(t), "data": data}

    return {"properties": {"timeseries": [
        entry(T0, 10.0, 5.0, next1=(2.54, "rain")),
        entry(T0 + HOUR, 20.0, -2.0, next1=(10.0, "heavysnow")),
        entry(T0 + 2 * HOUR, 10.0, 0.0, next1=(4.0, "sleet")),
        entry(T0 + 3 * HOUR, 10.0, 0.0, next6=(6.0, None)),
        entry(T0 + 9 * HOUR, 10.0, 0.0),
    ]}}


class ParseTests(SimpleTestCase):
    def setUp(self):
        self.s = met_norway.parse(met_doc(), T0, T0 + 10 * HOUR)

    def test_wind_converted_and_interpolated(self):
        self.assertAlmostEqual(self.s.wind[1], 20 * 2.236936, places=3)
        self.assertAlmostEqual(self.s.sample(T0 + HOUR / 2).wind_mph, 15 * 2.236936, places=3)
        self.assertAlmostEqual(self.s.gust[0], 15 * 2.236936, places=3)

    def test_precip_lands_in_following_bucket(self):
        self.assertIsNone(self.s.rain[0])  # nothing reported for the hour ending at T0
        self.assertAlmostEqual(self.s.rain[1], 0.1)  # 2.54 mm of rain in [T0, T0+1h)
        self.assertEqual(self.s.snow[1], 0.0)

    def test_snow_split_and_depth(self):
        self.assertAlmostEqual(self.s.snow[2], 10 * 0.7 / 2.54)  # 10 mm water -> 7 cm snow
        self.assertEqual(self.s.rain[2], 0.0)
        self.assertAlmostEqual(self.s.snow[3], 4 * 0.5 * 0.7 / 2.54)  # sleet: half snow
        self.assertAlmostEqual(self.s.rain[3], 4 * 0.5 / 25.4)

    def test_six_hour_amount_spread_and_temperature_decides(self):
        # 6 mm over 6 h with no symbol at ~0 °C -> 1 mm/h of snow
        for h in range(4, 10):
            self.assertAlmostEqual(self.s.snow[h], 0.7 / 2.54, places=6)
        self.assertIsNone(self.s.rain[10])  # beyond the data
        self.assertIsNone(self.s.wind[10])

    def test_temperature_in_fahrenheit(self):
        self.assertAlmostEqual(self.s.temp[0], 41.0)


class SnapTests(SimpleTestCase):
    def test_coarsens_until_within_budget(self):
        points = [(40 + i * 0.01, -100.0) for i in range(500)]
        keys = met_norway.snap(points, max_locations=50)
        self.assertLessEqual(len(set(keys)), 50)
        self.assertEqual(len(keys), 500)

    def test_nearby_points_share_a_request(self):
        keys = met_norway.snap([(40.001, -100.001), (40.002, -100.002)])
        self.assertEqual(keys[0], keys[1])


class FallbackTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_falls_back_on_rate_limit_and_pauses_open_meteo(self):
        limited = UpstreamError("Weather (Open-Meteo)", "HTTP 429", status=429)
        with patch.object(weather, "_fetch_open_meteo", side_effect=limited) as om, \
             patch.object(met_norway, "get_json", return_value=met_doc()) as met:
            out = weather.fetch_hourly([(40.0, -100.0)], T0, T0 + 3 * HOUR)
            self.assertEqual(len(out), 1)
            self.assertEqual(met.call_count, 1)
            self.assertIn("User-Agent", met.call_args.kwargs["headers"])
            weather.fetch_hourly([(41.0, -100.0)], T0, T0 + 3 * HOUR)
        self.assertEqual(om.call_count, 1)  # skipped on the second call

    def test_uses_open_meteo_when_it_works(self):
        with patch.object(weather, "_fetch_open_meteo", return_value=["ok"]) as om, \
             patch.object(met_norway, "fetch_hourly") as met:
            self.assertEqual(weather.fetch_hourly([(40.0, -100.0)], T0, T0 + HOUR), ["ok"])
        om.assert_called_once()
        met.assert_not_called()
