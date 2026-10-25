"""Synthetic unit fixtures test historical evaluation logic, not historical claims."""
from datetime import date
import unittest
import pandas as pd
from src.historical import evaluate_windows, PLANS
from src.recommendations import recommend


def fixtures():
    records, daily = [], []
    for year in range(2021, 2026):
        stressed = year == 2021
        records.append({"period_start": f"{year}-06-01", "assessment_date": f"{year}-06-30", "year": year,
                        "month": 6, "status": "ready", "current_ndvi": 0.15 if stressed else 0.4,
                        "scene_count": 3, "common_valid_fraction": 0.9})
        for day in pd.date_range(f"{year}-06-01", f"{year}-06-30"):
            daily.append({"date": str(day.date()), "precipitation_mm": 0.1 if stressed else 1.0,
                          "temperature_mean_c": 30 if stressed else 26, "soil_moisture_m3m3": 0.1 if stressed else 0.2})
    return records, pd.DataFrame(daily)


class HistoricalEvaluationTests(unittest.TestCase):
    def test_leave_one_out_and_real_rule_conflict(self):
        records, climate = fixtures()
        table = evaluate_windows(records, climate)
        row = table.iloc[0]
        self.assertEqual(row.baseline_years, "2022, 2023, 2024, 2025")
        self.assertAlmostEqual(row.seasonal_ndvi, 0.4)
        self.assertEqual(row.stress_score, 100)
        self.assertTrue(row.conflict)
        self.assertEqual(row.grazing_paddocks, "Paddock 2, Paddock 3")
        decision = recommend({**row.to_dict(), "official_plan": PLANS["Paddock 2"]}, date(2021, 6, 30))
        self.assertEqual(decision["decision"], "DELAY GRAZING")
        pd.testing.assert_frame_equal(table.sort_values("year").reset_index(drop=True),
                                      evaluate_windows(list(reversed(records)), climate).sort_values("year").reset_index(drop=True))

    def test_no_conflict_for_favorable_values(self):
        records, climate = fixtures()
        for r in records:
            r["current_ndvi"] = 0.4
        climate["precipitation_mm"], climate["temperature_mean_c"], climate["soil_moisture_m3m3"] = 1, 26, 0.2
        table = evaluate_windows(records, climate)
        self.assertFalse(table.conflict.any())
        self.assertTrue(table.stress_score.eq(0).all())

    def test_missing_observations_remain_unscored(self):
        records, climate = fixtures()
        records[0]["status"] = "insufficient_satellite"
        table = evaluate_windows(records, climate)
        self.assertTrue(pd.isna(table.iloc[0].stress_score))
        self.assertFalse(table.iloc[0].conflict)
        self.assertEqual(table.iloc[0].status, "insufficient_satellite")
        records[1]["status"] = "insufficient_satellite"
        table = evaluate_windows(records, climate)
        self.assertEqual(set(table.status), {"insufficient_satellite", "insufficient_reference_years"})

    def test_incomplete_climate_and_zero_rain_reference(self):
        records, climate = fixtures()
        table = evaluate_windows(records, climate.iloc[1:])
        self.assertEqual(table.iloc[0].status, "incomplete_climate")
        climate["precipitation_mm"] = 0
        table = evaluate_windows(records, climate)
        self.assertTrue(table.status.eq("unstable_reference").all())


if __name__ == "__main__":
    unittest.main()
