from django.test import SimpleTestCase

from routeplanner.domain import hos
from routeplanner.domain.geo import (
    RouteProfile,
    checkpoint_miles,
    decimate_indices,
    haversine_mi,
    min_distance_mi,
    overlap_fraction,
)

HOUR = 3600


class GeoTests(SimpleTestCase):
    def test_haversine_known_distance(self):
        # New York -> Los Angeles is ~2,445 miles great-circle.
        self.assertAlmostEqual(haversine_mi((40.7128, -74.0060), (34.0522, -118.2437)), 2445, delta=10)

    def test_checkpoint_miles(self):
        self.assertEqual(checkpoint_miles(103, 25), [0, 25, 50, 75, 100, 103])
        self.assertEqual(checkpoint_miles(100, 25), [0, 25, 50, 75, 100])
        self.assertEqual(checkpoint_miles(8, 10), [0, 8])

    def test_profile_interpolation(self):
        coords = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]
        profile = RouteProfile.from_segments(coords, [HOUR, 2 * HOUR])
        half = profile.total_miles / 2
        lat, lng, drive = profile.locate(half)
        self.assertAlmostEqual(lng, 1.0, places=6)
        self.assertAlmostEqual(drive, HOUR, places=3)
        lat, lng, mile = profile.locate_drive_time(2 * HOUR)
        self.assertAlmostEqual(lng, 1.5, places=6)
        self.assertEqual(profile.locate(10_000)[:2], (0.0, 2.0))  # clamps past the end

    def test_slice_has_interpolated_ends(self):
        coords = [(0.0, float(i)) for i in range(5)]
        profile = RouteProfile.from_segments(coords, [60.0] * 4)
        mile = profile.total_miles / 4
        part = profile.slice(mile * 0.5, mile * 2.5)
        self.assertAlmostEqual(part[0][1], 0.5, places=6)
        self.assertEqual(part[1:-1], [(0.0, 1.0), (0.0, 2.0)])
        self.assertAlmostEqual(part[-1][1], 2.5, places=6)

    def test_decimate_keeps_ends(self):
        self.assertEqual(decimate_indices([0, 0.1, 0.2, 1.0, 1.05, 2.0], 0.5), [0, 3, 5])

    def test_distance_and_overlap(self):
        line = [(40.0, -100 + i * 0.01) for i in range(200)]
        shifted = [(40.5, -100 + i * 0.01) for i in range(200)]  # ~35 miles north
        self.assertAlmostEqual(float(min_distance_mi([(40.0, -99.5)], line)[0]), 0.0, places=3)
        self.assertEqual(overlap_fraction(line, line), 1.0)
        self.assertEqual(overlap_fraction(line, shifted), 0.0)


class HoursOfServiceTests(SimpleTestCase):
    def test_disabled_is_pure_driving_time(self):
        self.assertEqual(hos.elapsed_for_drive(30 * HOUR, enabled=False), 30 * HOUR)
        self.assertEqual(hos.rest_events(30 * HOUR, enabled=False), [])

    def test_break_after_eight_hours(self):
        self.assertEqual(hos.elapsed_for_drive(8 * HOUR), 8 * HOUR)
        self.assertEqual(hos.elapsed_for_drive(9 * HOUR), 9.5 * HOUR)
        self.assertEqual(hos.elapsed_for_drive(11 * HOUR), 11.5 * HOUR)

    def test_ten_hour_rest_after_eleven_hours(self):
        self.assertEqual(hos.elapsed_for_drive(12 * HOUR), 12 * HOUR + 10.5 * HOUR)
        self.assertEqual(hos.elapsed_for_drive(22 * HOUR), 22 * HOUR + 11 * HOUR)

    def test_rest_events_line_up_with_elapsed_time(self):
        events = hos.rest_events(25 * HOUR)
        self.assertEqual([(e.at_drive_s / HOUR, e.kind) for e in events], [
            (8, "30-min break"), (11, "10-hr rest"), (19, "30-min break"), (22, "10-hr rest"),
        ])
        total_stops = sum(e.duration_s for e in events)
        self.assertEqual(hos.elapsed_for_drive(25 * HOUR), 25 * HOUR + total_stops)

    def test_no_break_needed_for_short_trip(self):
        self.assertEqual(hos.rest_events(8 * HOUR), [])
