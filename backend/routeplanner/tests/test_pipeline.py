import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from routeplanner.domain.geo import Place, RouteProfile
from routeplanner.services import heatmap, planner
from routeplanner.services.routing import RouteGeometry, _parse_route, _truck_seconds
from routeplanner.validation import HeatmapRequest, TripRequest

from .fakes import bent_route, storm_north_of, straight_route

DENVER = Place("Denver", 39.74, -104.99)
KC = Place("Kansas City", 39.10, -94.58)


def departure() -> datetime:
    return (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)


def three_routes():
    return [
        straight_route(DENVER.latlng, KC.latlng, hours=9, roads="I 70"),  # fastest, through the middle
        bent_route(DENVER.latlng, KC.latlng, (41.2, -99.8), hours=10, roads="I 80"),  # dips north
        bent_route(DENVER.latlng, KC.latlng, (37.8, -99.8), hours=11, roads="US 50"),  # dips south
    ]


class PlannerTests(SimpleTestCase):
    def plan(self, storm, load=35_000, interval=25, hos=True):
        req = TripRequest(DENVER, KC, departure(), load, interval, hos)
        with patch("routeplanner.services.planner.routing.fetch_routes", return_value=three_routes()), \
             patch("routeplanner.services.planner.weather.fetch_hourly", side_effect=storm):
            return planner.plan_trip(req)

    def test_calm_weather_recommends_fastest(self):
        result = self.plan(storm_north_of(90))
        self.assertEqual(result["recommendation"]["route_id"], "A")
        self.assertIn("shorter travel time", result["recommendation"]["reason"])

    def test_avoids_route_through_storm(self):
        # Wind 40 mph north of 39.5: High, but Severe for a >40,000 lb load.
        result = self.plan(storm_north_of(39.5, wind=40.0), load=45_000)
        routes = {r["id"]: r for r in result["routes"]}
        self.assertEqual(result["recommendation"]["route_id"], "C")
        self.assertGreater(routes["B"]["stats"]["severe_miles"], routes["C"]["stats"]["severe_miles"])
        self.assertTrue(routes["C"]["recommended"])
        self.assertEqual(routes["C"]["rank"], 1)

    def test_load_weight_changes_the_outcome(self):
        light = self.plan(storm_north_of(39.5, wind=40.0), load=20_000)
        heavy = self.plan(storm_north_of(39.5, wind=40.0), load=45_000)
        light_b = next(r for r in light["routes"] if r["id"] == "B")
        heavy_b = next(r for r in heavy["routes"] if r["id"] == "B")
        self.assertEqual(light_b["stats"]["severe_miles"], 0)
        self.assertGreater(light_b["stats"]["high_miles"], 0)
        self.assertGreater(heavy_b["stats"]["severe_miles"], 0)

    def test_checkpoints_and_miles(self):
        result = self.plan(storm_north_of(90), interval=25)
        for route in result["routes"]:
            cps = route["checkpoints"]
            self.assertEqual(cps[0]["mile"], 0)
            self.assertAlmostEqual(cps[-1]["mile"], route["distance_mi"], delta=0.1)
            self.assertTrue(all(b["mile"] - a["mile"] <= 25.01 for a, b in zip(cps, cps[1:])))
            self.assertTrue(all(b["eta"] >= a["eta"] for a, b in zip(cps, cps[1:])))
            self.assertAlmostEqual(sum(route["stats"]["miles_by_level"]), route["distance_mi"], delta=0.5)
            self.assertAlmostEqual(cps[-1]["eta"], route["arrival"], delta=2)

    def test_path_times_are_monotonic_and_include_rests(self):
        result = self.plan(storm_north_of(90), hos=True)
        route = next(r for r in result["routes"] if r["id"] == "C")  # 11h of driving
        times = route["path_times"]
        self.assertEqual(len(times), len(route["path"]))
        self.assertTrue(all(b >= a for a, b in zip(times, times[1:])))
        self.assertEqual([s["kind"] for s in route["rest_stops"]], ["30-min break"])
        self.assertEqual(route["duration_s"], 11 * 3600 + 1800)

    def test_no_travel_triggers_warning(self):
        result = self.plan(storm_north_of(0, wind=60.0))
        self.assertTrue(any("No-Travel" in w for w in result["recommendation"]["warnings"]))


class TruckSpeedTests(SimpleTestCase):
    def test_speed_cap(self):
        self.assertEqual(_truck_seconds(3600, 75, 65), 75 / 65 * 3600)  # car at 75 mph -> truck at 65
        self.assertEqual(_truck_seconds(3600, 50, 65), 3600)  # already slower than the cap

    def test_parse_osrm_steps(self):
        raw = {
            "legs": [{
                "summary": "I 70, I 25",
                "steps": [
                    {"duration": 600, "geometry": {"coordinates": [[-105.0, 39.0], [-104.9, 39.0], [-104.8, 39.0]]}},
                    {"duration": 300, "geometry": {"coordinates": [[-104.8, 39.0], [-104.7, 39.0]]}},
                    {"duration": 0, "geometry": {"coordinates": [[-104.7, 39.0], [-104.7, 39.0]]}},
                ],
            }]
        }
        route = _parse_route(raw)
        self.assertEqual(len(route.coords), 4)
        self.assertEqual(route.roads, "I 70, I 25")
        self.assertAlmostEqual(route.drive_s, 900, delta=1)
        self.assertEqual(route.coords[0], (39.0, -105.0))


class HeatmapTests(SimpleTestCase):
    def test_grid_stays_within_budget_and_corridor(self):
        paths = [r.coords for r in three_routes()]
        grid = heatmap.corridor_grid(paths, radius_mi=40, max_cells=350)
        self.assertLessEqual(len(grid.cells), 350)
        self.assertGreater(len(grid.cells), 50)
        self.assertEqual(len(grid.cells), len(grid.centers))
        self.assertTrue(all(0 <= c < grid.rows * grid.cols for c in grid.cells))

    def test_layers_shape(self):
        paths = [r.coords[::10] for r in three_routes()]
        req = HeatmapRequest(paths, departure(), 45_000)
        with patch("routeplanner.services.heatmap.weather.fetch_hourly", side_effect=storm_north_of(39.5, wind=40.0)):
            data = heatmap.build_heatmap(req)
        self.assertEqual(len(data["hours"]), 49)
        for name in ("risk", "wind", "rain", "snow"):
            self.assertEqual(len(data["layers"][name]), 49)
            self.assertEqual(len(data["layers"][name][0]), len(data["cells"]))
        self.assertIn(3, data["layers"]["risk"][0])  # heavy load + 40 mph -> Severe in the storm


class ApiTests(SimpleTestCase):
    def post(self, url, body):
        return self.client.post(url, data=json.dumps(body), content_type="application/json")

    def test_validation_errors(self):
        resp = self.post("/api/plan", {"origin": "", "destination": {"lat": 200, "lng": 0},
                                       "departure": "2020-01-01T00:00:00Z", "load_lb": -5, "interval_mi": 15})
        self.assertEqual(resp.status_code, 400)
        fields = resp.json()["fields"]
        self.assertEqual(set(fields), {"origin", "destination", "departure", "load_lb", "interval_mi"})

    def test_naive_departure_rejected(self):
        resp = self.post("/api/plan", {"origin": "Denver", "destination": "Kansas City",
                                       "departure": "2030-01-01T00:00", "load_lb": 1000})
        self.assertIn("time zone", resp.json()["fields"]["departure"])

    def test_wrong_method(self):
        self.assertEqual(self.client.get("/api/plan").status_code, 405)

    def test_short_geocode_query(self):
        self.assertEqual(self.client.get("/api/geocode?q=ab").json(), {"results": []})

    def test_plan_end_to_end(self):
        body = {"origin": DENVER.as_dict(), "destination": KC.as_dict(),
                "departure": departure().isoformat(), "load_lb": 30_000, "interval_mi": 50}
        with patch("routeplanner.services.planner.routing.fetch_routes", return_value=three_routes()), \
             patch("routeplanner.services.planner.weather.fetch_hourly", side_effect=storm_north_of(90)):
            resp = self.post("/api/plan", body)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(len(data["routes"]), 3)
        self.assertEqual(data["recommendation"]["route_id"], "A")

    def test_upstream_failure_is_502(self):
        from routeplanner.services.http import UpstreamError

        body = {"origin": DENVER.as_dict(), "destination": KC.as_dict(),
                "departure": departure().isoformat(), "load_lb": 30_000}
        with patch("routeplanner.services.planner.routing.fetch_routes",
                   side_effect=UpstreamError("Routing (OSRM)", "HTTP 503")):
            resp = self.post("/api/plan", body)
        self.assertEqual(resp.status_code, 502)
        self.assertIn("Routing (OSRM)", resp.json()["error"])
