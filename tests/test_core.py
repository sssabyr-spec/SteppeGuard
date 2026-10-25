"""Run with python -m unittest discover -s tests -v."""
import unittest
from datetime import date
from src.data_loader import load_data
from src.scoring import calculate_stress, stress_level
from src.recommendations import recommend


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.polygons, self.metrics, self.history = load_data(include_observed=False)

    def test_data_and_expected_scores(self):
        self.assertEqual(len(self.polygons), 4)
        scores = [calculate_stress(r)["stress_score"] for _, r in self.metrics.iterrows()]
        self.assertEqual(scores, [15, 76, 22, 46])
        self.assertEqual(len(self.history), 4)

    def test_score_bounds_and_monotonicity(self):
        r = self.metrics.iloc[0].to_dict()
        r.update(vegetation_anomaly_pct=20, rainfall_anomaly_pct=10, temperature_anomaly_c=-2)
        self.assertEqual(calculate_stress(r)["stress_score"], 0)
        r.update(vegetation_anomaly_pct=-100, rainfall_anomaly_pct=-100, temperature_anomaly_c=10, soil_moisture_status="Below normal")
        self.assertEqual(calculate_stress(r)["stress_score"], 100)
        values = []
        for anomaly in (0, -5, -15, -25, -35):
            r["vegetation_anomaly_pct"] = anomaly
            values.append(calculate_stress(r)["stress_score"])
        self.assertEqual(values, sorted(values))

    def test_thresholds(self):
        r = self.metrics.iloc[1].to_dict()
        for score, level, decision in [(0, "LOW", "SUITABLE FOR PLANNED GRAZING"), (30, "LOW", "SUITABLE FOR PLANNED GRAZING"),
                                       (31, "MODERATE", "MONITOR / REDUCE PRESSURE"), (60, "MODERATE", "MONITOR / REDUCE PRESSURE"),
                                       (61, "HIGH", "DELAY GRAZING"), (100, "HIGH", "DELAY GRAZING")]:
            r["stress_score"] = score
            self.assertEqual(stress_level(score), level)
            self.assertEqual(recommend(r, date(2026, 7, 1))["decision"], decision)

    def test_rest_and_seasons(self):
        r = self.metrics.iloc[0].to_dict()
        r["stress_score"] = 100
        self.assertEqual(recommend(r, date(2026, 7, 1))["decision"], "KEEP RESTING")
        r["official_plan"] = "Autumn grazing"
        self.assertFalse(recommend(r, date(2026, 7, 1))["changed"])
        self.assertEqual(recommend(r, date(2026, 7, 1))["decision"], "CONTINUE PLANNED REST")
        self.assertEqual(recommend(r, date(2026, 9, 1))["decision"], "DELAY GRAZING")

    def test_replay_deteriorates(self):
        scores = [calculate_stress(r)["stress_score"] for _, r in self.history.iterrows()]
        self.assertEqual(scores, sorted(scores))
        self.assertLessEqual(scores[0], 30)
        self.assertGreater(scores[2], 60)
        self.assertLess(scores[2], scores[3])


if __name__ == "__main__":
    unittest.main()
