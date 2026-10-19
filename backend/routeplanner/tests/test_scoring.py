from django.test import SimpleTestCase

from routeplanner.domain.risk import Risk
from routeplanner.domain.scoring import (
    RouteScore,
    exposure_intervals,
    explain,
    merge_intervals,
    rank_routes,
    score_route,
)

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


def score(route_id, *, nt=0.0, severe=0.0, high=0.0, avg=0.0, hours=5.0):
    return RouteScore(route_id, (100.0, 0.0, high, severe, nt), avg, hours * 3600)


class ExposureTests(SimpleTestCase):
    def test_each_checkpoint_covers_half_way_to_neighbours(self):
        intervals = exposure_intervals([0, 10, 20, 25], [L, H, L, S])
        self.assertEqual(
            [(iv.start_mi, iv.end_mi, iv.level) for iv in intervals],
            [(0, 5, L), (5, 15, H), (15, 22.5, L), (22.5, 25, S)],
        )
        self.assertAlmostEqual(sum(iv.miles for iv in intervals), 25)

    def test_merge_joins_same_level(self):
        merged = merge_intervals(exposure_intervals([0, 10, 20, 30], [L, L, H, H]))
        self.assertEqual([(m.start_mi, m.end_mi, m.level) for m in merged], [(0, 15, L), (15, 30, H)])

    def test_score_totals_and_average(self):
        s = score_route("A", exposure_intervals([0, 10, 20], [L, H, L]), 3600)
        self.assertEqual(s.high_miles, 10)
        self.assertAlmostEqual(sum(s.miles_by_level), 20)
        self.assertAlmostEqual(s.avg_risk, 2 * 10 / 20)
        self.assertEqual(s.max_level, H)


class RankingTests(SimpleTestCase):
    def ids(self, *scores):
        return [s.route_id for s in rank_routes(scores)]

    def test_fewest_severe_miles_beats_faster_route(self):
        self.assertEqual(self.ids(score("A", severe=20, hours=4), score("B", severe=0, hours=6)), ["B", "A"])

    def test_then_fewest_high_miles(self):
        self.assertEqual(self.ids(score("A", high=30, hours=4), score("B", high=10, hours=6)), ["B", "A"])

    def test_then_lowest_average_risk(self):
        self.assertEqual(self.ids(score("A", avg=0.8, hours=4), score("B", avg=0.3, hours=6)), ["B", "A"])

    def test_then_shortest_time(self):
        self.assertEqual(self.ids(score("A", hours=6), score("B", hours=5)), ["B", "A"])

    def test_no_travel_ranks_below_severe(self):
        self.assertEqual(self.ids(score("A", nt=5), score("B", severe=200)), ["B", "A"])

    def test_tiny_differences_are_ties(self):
        # 0.04 mi of severe is noise; travel time decides.
        self.assertEqual(self.ids(score("A", severe=0.04, hours=4), score("B", severe=0.0, hours=5)), ["A", "B"])

    def test_explanation_names_decisive_criterion(self):
        ranked = rank_routes([score("A", severe=12, hours=4), score("B", hours=6), score("C", hours=7)])
        text = explain(ranked)
        self.assertTrue(text.startswith("Route B has"))
        self.assertIn("fewer Severe-risk miles than Route A", text)
        self.assertIn("shorter travel time than Route C (6h 00m vs 7h 00m)", text)
