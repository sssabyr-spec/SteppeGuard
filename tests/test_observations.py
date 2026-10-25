"""Synthetic fixtures test import arithmetic; these are NOT real observations."""
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.data_loader import DATA_DIR, load_data
from src.observations import geometry_hash, read_bundle, aggregate_observations, apply_observations, period_for_year
from src.recommendations import anomaly_text


def fixture_bundle(directory):
    geometry = {"type": "Polygon", "coordinates": [[[64.5, 45.1], [64.51, 45.1], [64.51, 45.11], [64.5, 45.11], [64.5, 45.1]]]}
    digest = geometry_hash(geometry)
    meta = {"schema_version": 1, "paddock_id": "Paddock 2", "polygon_sha256": digest,
            "boundary_status": "provisional", "geometry_source": "SYNTHETIC TEST FIXTURE",
            "climate_model": "era5", "ndvi_collection": "sentinel-2-l2a",
            "retrieved_at": "2026-07-10T00:00:00Z", "ndvi_source": "https://example.org/test",
            "climate_source": "https://example.org/test", "period_start": "2026-06-02", "period_end": "2026-07-01",
            "baseline_years": [2021, 2022, 2023]}
    ndvi, climate = [], []
    for year in [2021, 2022, 2023, 2026]:
        current = year == 2026
        for day in [10, 20]:
            ndvi.append({"date": f"{year}-06-{day}", "ndvi": 0.3 if current else 0.4,
                         "valid_fraction": 0.9, "scene_id": f"TEST-{year}-{day}", "polygon_sha256": digest})
        for day in pd.date_range(f"{year}-06-02", f"{year}-07-01"):
            climate.append({"date": day.strftime("%Y-%m-%d"), "precipitation_mm": 1 if current else 2,
                            "temperature_mean_c": 27 if current else 25, "polygon_sha256": digest})
    (directory / "manifest.json").write_text(json.dumps(meta), encoding="utf-8")
    (directory / "pilot.geojson").write_text(json.dumps({"type": "Feature", "geometry": geometry, "properties": {}}), encoding="utf-8")
    pd.DataFrame(ndvi).to_csv(directory / "ndvi_observations.csv", index=False)
    pd.DataFrame(climate).to_csv(directory / "climate_daily.csv", index=False)
    return meta


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        fixture_bundle(self.directory)
        self.meta, self.polygon, self.ndvi, self.climate = read_bundle(self.directory)

    def tearDown(self):
        self.temp.cleanup()

    def test_calendar_baseline_and_anomalies(self):
        values, annual = aggregate_observations(self.meta, self.ndvi, self.climate)
        self.assertAlmostEqual(values["current_ndvi"], 0.3)
        self.assertAlmostEqual(values["seasonal_ndvi"], 0.4)
        self.assertAlmostEqual(values["vegetation_anomaly_pct"], -25)
        self.assertAlmostEqual(values["rainfall_anomaly_pct"], -50)
        self.assertAlmostEqual(values["temperature_anomaly_c"], 2)
        self.assertEqual(values["precipitation_mm"], 30)
        self.assertEqual(annual[2026]["scene_count"], 2)

    def test_each_baseline_year_has_equal_weight(self):
        extra = self.ndvi.iloc[[0]].copy()
        extra["date"] = pd.Timestamp("2021-06-25")
        extra["ndvi"] = 0.8
        extra["scene_id"] = "TEST-extra"
        values, _ = aggregate_observations(self.meta, pd.concat([self.ndvi, extra]), self.climate)
        self.assertAlmostEqual(values["seasonal_ndvi"], 0.4)

    def test_cloudy_or_duplicate_dates_do_not_satisfy_minimum(self):
        ndvi = self.ndvi.copy()
        ndvi.loc[ndvi.date.eq("2026-06-20"), "valid_fraction"] = 0.69
        with self.assertRaisesRegex(ValueError, "two clear"):
            aggregate_observations(self.meta, ndvi, self.climate)
        ndvi = self.ndvi.copy()
        ndvi.loc[ndvi.date.eq("2026-06-20"), "date"] = pd.Timestamp("2026-06-10")
        with self.assertRaisesRegex(ValueError, "two clear"):
            aggregate_observations(self.meta, ndvi, self.climate)

    def test_incomplete_climate_and_zero_reference_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            aggregate_observations(self.meta, self.ndvi, self.climate.iloc[1:])
        climate = self.climate.copy()
        climate.loc[climate.date.dt.year < 2026, "precipitation_mm"] = 0
        with self.assertRaisesRegex(ValueError, "unstable"):
            aggregate_observations(self.meta, self.ndvi, climate)

    def test_future_reference_and_geometry_mismatch_rejected(self):
        self.meta["baseline_years"] = [2021, 2022, 2026]
        with self.assertRaisesRegex(ValueError, "historical"):
            aggregate_observations(self.meta, self.ndvi, self.climate)
        self.meta["polygon_sha256"] = "wrong"
        (self.directory / "manifest.json").write_text(json.dumps(self.meta), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash"):
            read_bundle(self.directory)

    def test_nonfinite_and_duplicate_records_rejected(self):
        self.ndvi.loc[0, "ndvi"] = float("inf")
        self.ndvi.to_csv(self.directory / "ndvi_observations.csv", index=False)
        with self.assertRaisesRegex(ValueError, "finite"):
            read_bundle(self.directory)
        fixture_bundle(self.directory)
        pd.concat([self.climate, self.climate.iloc[[0]]]).to_csv(self.directory / "climate_daily.csv", index=False)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_bundle(self.directory)

    def test_overlay_preserves_demo_soil_and_other_paddocks(self):
        polygons, metrics, _ = load_data(include_observed=False)
        new_polygons, mixed = apply_observations(polygons, metrics, self.directory)
        observed = mixed.loc[mixed.paddock_id.eq("Paddock 2")].iloc[0]
        self.assertEqual(observed.soil_source, "DEMO")
        self.assertEqual(observed.soil_moisture_status, metrics.iloc[1].soil_moisture_status)
        self.assertTrue(observed.vegetation_source.startswith("OBSERVED"))
        self.assertEqual(mixed.iloc[0].data_status, "DEMO")
        self.assertTrue(new_polygons.iloc[1].geometry.equals(self.polygon))
        self.assertEqual(observed.boundary_status, "provisional")

    def test_same_month_day_across_year_boundary(self):
        a, b = period_for_year(date(2025, 12, 20), date(2026, 1, 18), 2020)
        self.assertEqual((a, b), (date(2019, 12, 20), date(2020, 1, 18)))

    def test_percent_text_is_rounded(self):
        self.assertEqual(anomaly_text(-26.123456, "baseline"), "26.1% below baseline")

    def test_mixed_ui_and_invalid_bundle_error(self):
        polygons, metrics, history = load_data(include_observed=False)
        polygons, metrics = apply_observations(polygons, metrics, self.directory)
        with patch("src.data_loader.load_data", return_value=(polygons, metrics, history)):
            app = AppTest.from_file(str(DATA_DIR.parent / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("MIXED DATA" in item.value for item in app.warning))
        self.assertTrue(any("PARTLY OBSERVED" in item.value for item in app.caption))
        dashboard = next(tab for tab in app.tabs if tab.label in ("Pasture dashboard", "September 2026 assessment"))
        facts = next(item.value for item in dashboard.dataframe if "Indicator" in item.value.columns)
        self.assertIn("Source", facts.columns)
        self.assertTrue(any("REANALYSIS" in item for item in facts.Source))
        with patch("src.data_loader.load_data", side_effect=ValueError("Invalid test observations")):
            app = AppTest.from_file(str(DATA_DIR.parent / "app.py"), default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("not replaced silently" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
