"""Reproduce the delivered case from archived observations, without network access."""
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from src.historical import load_history, evaluate_windows, PLANS
from src.recommendations import recommend
from src.scoring import calculate_stress

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/historical"


@unittest.skipUnless((DATA / "manifest.json").exists(), "Historical observations not downloaded")
class RealHistoryTests(unittest.TestCase):
    def test_reproduce_every_interval_and_selection(self):
        meta, saved = load_history()
        records = json.loads((DATA / "source_records.json").read_text())
        climate = pd.read_csv(DATA / "climate_daily.csv")
        recomputed = evaluate_windows(records, climate)
        self.assertEqual(len(saved), 52)
        self.assertFalse(saved.assessment_date.duplicated().any())
        self.assertEqual(saved.status.tolist(), recomputed.status.tolist())
        for column in ["current_ndvi", "seasonal_ndvi", "vegetation_anomaly_pct", "rainfall_anomaly_pct", "temperature_anomaly_c", "soil_moisture_anomaly_pct", "stress_score"]:
            np.testing.assert_allclose(saved[column], recomputed[column], equal_nan=True, atol=1e-10)
        good = saved.loc[saved.status.eq("evaluated")]
        self.assertEqual(len(good), meta["evaluated_windows"])
        self.assertEqual(int(good.conflict.sum()), meta["conflict_windows"])
        for _, row in good.iterrows():
            years = [int(y.strip()) for y in row.baseline_years.split(",")]
            self.assertNotIn(row.year, years)
            self.assertGreaterEqual(len(years), 3)
            refs = saved.loc[saved.year.isin(years) & saved.month.eq(row.month)]
            self.assertAlmostEqual(row.seasonal_ndvi, refs.current_ndvi.mean())
            self.assertAlmostEqual(row.baseline_precipitation_mm, refs.precipitation_mm.mean())
            self.assertEqual(row.stress_score, calculate_stress(row)["stress_score"])
            self.assertGreaterEqual(row.common_valid_fraction, .7)
        ranked = good.loc[good.conflict].sort_values(["stress_score", "assessment_date"], ascending=[False, True])
        self.assertEqual(meta["selected_date"], ranked.iloc[0].assessment_date)
        chosen = ranked.iloc[0]
        self.assertEqual(chosen.assessment_date, "2025-10-31")
        self.assertEqual(chosen.stress_score, 54)
        decision = recommend({**chosen.to_dict(), "official_plan": PLANS["Paddock 4"]}, date(2025, 10, 31))
        self.assertEqual(decision["plan_now"], "Graze")
        self.assertEqual(decision["decision"], "MONITOR / REDUCE PRESSURE")
        self.assertTrue(saved.loc[saved.status.ne("evaluated"), "stress_score"].isna().all())
        self.assertFalse(good.stress_level.eq("HIGH").any())

    @unittest.skipUnless(importlib.util.find_spec("rasterio"), "Optional acquisition dependency")
    def test_case_raster_means_and_common_footprint(self):
        import rasterio
        _, rows = load_history()
        masks = []
        for path in sorted(DATA.glob("case_composite_*.tif")):
            day = path.stem.removeprefix("case_composite_")
            row = rows.loc[rows.assessment_date.eq(day)].iloc[0]
            with rasterio.open(path) as src:
                arr = src.read(1, masked=True)
                self.assertAlmostEqual(float(arr.mean()), row.current_ndvi, places=6)
                masks.append(np.ma.getmaskarray(arr))
        self.assertEqual(len(masks), 5)
        for mask in masks[1:]:
            np.testing.assert_array_equal(mask, masks[0])

    def test_invalid_history_is_not_silently_replaced_with_demo(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evaluation.csv").write_text("tampered")
            (root / "manifest.json").write_text(json.dumps({"schema_version": 1, "retrospective_only": True,
                                                         "artifact_sha256": {"evaluation.csv": "wrong"}}))
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_history(root)
        with patch("src.historical.load_history", side_effect=ValueError("checksum mismatch")):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=40)
            app.session_state["language"] = "en"
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any("failed validation" in e.value for e in app.error))
            self.assertEqual(app.metric[0].value, "4")
            self.assertFalse(app.select_slider)

    def test_no_conflict_displays_finding_without_synthetic_replay(self):
        meta, rows = load_history()
        meta.update(selected_date=None, conflict_windows=0)
        with patch("src.historical.load_history", return_value=(meta, rows)):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=40)
            app.session_state["language"] = "en"
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.tabs[1].label, "Historical evaluation")
            self.assertTrue(any("No meaningful observed grazing conflict" in e.value for e in app.info))
            self.assertFalse(app.select_slider)


if __name__ == "__main__":
    unittest.main()
