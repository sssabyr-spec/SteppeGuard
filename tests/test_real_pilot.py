"""Regression checks on the delivered observed Akkum bundle, no network calls."""
from datetime import date
import importlib.util
import unittest
import numpy as np
from streamlit.testing.v1 import AppTest
from src.data_loader import DATA_DIR, load_data
from src.observations import read_bundle, aggregate_observations
from src.scoring import calculate_stress
from src.recommendations import recommend


@unittest.skipUnless((DATA_DIR / "observed/manifest.json").exists(), "Real pilot bundle not downloaded")
class RealPilotTests(unittest.TestCase):
    def test_real_inputs_and_retained_schedule(self):
        polygons, metrics, _ = load_data()
        self.assertTrue(metrics.vegetation_source.eq("Observed satellite data · Sentinel-2").all())
        self.assertTrue(metrics.soil_source.eq("ERA5 reanalysis data").all())
        self.assertEqual(metrics.official_plan.tolist(), ["Rest", "Spring–summer grazing", "Summer grazing", "Autumn grazing"])
        self.assertTrue(metrics.current_ndvi.between(0.33, 0.34).all())
        self.assertTrue(metrics.precipitation_mm.eq(0.8).all())
        self.assertTrue(metrics.assessment_date.eq("2026-09-30").all())
        self.assertEqual(calculate_stress(metrics.iloc[0])["stress_score"], 34)
        decisions = []
        for _, row in metrics.iterrows():
            values = row.to_dict()
            values.update(calculate_stress(row))
            decisions.append(recommend(values, date(2026, 9, 30))["decision"])
        self.assertEqual(decisions, ["KEEP RESTING", "CONTINUE PLANNED REST", "CONTINUE PLANNED REST", "MONITOR / REDUCE PRESSURE"])
        # Schematic sectors are within, and together cover, the analysis zone.
        from shapely.geometry import shape
        zone = shape(polygons.attrs["analysis_geometry"])
        from shapely.ops import unary_union
        self.assertLess(unary_union(polygons.geometry).symmetric_difference(zone).area, 1e-10)

    def test_real_dashboard_without_global_demo_warning(self):
        app = AppTest.from_file(str(DATA_DIR.parent / "app.py"), default_timeout=40)
        app.session_state["language"] = "en"
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual([item.value for item in app.tabs[1].metric[:4]], ["4", "0", "4", "0"])
        self.assertFalse(any("DEMO DATA" in warning.value or "MIXED DATA" in warning.value for warning in app.warning))
        self.assertTrue(any("Approximate analysis zone" in caption.value for caption in app.caption))
        app.selectbox[0].select("Paddock 4").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("MONITOR / REDUCE PRESSURE" in message.value for message in app.warning))
        self.assertEqual([tab.label for tab in app.tabs], ["Observed case study", "September 2026 assessment", "About the pilot"])
        self.assertFalse(any("DEMO DATA" in caption.value for caption in app.caption))
        self.assertEqual(app.select_slider[0].value, "2025-10-31")
        self.assertTrue(any("Official seasonal rule: GRAZE" in item.value and "REDUCE GRAZING PRESSURE AND MONITOR" in item.value for item in app.info))
        app.select_slider[0].set_value("2021-05-31").run()
        self.assertFalse(app.exception)
        self.assertTrue(any(item.value == "50 / 100" for item in app.metric))

    @unittest.skipUnless(importlib.util.find_spec("rasterio"), "Optional acquisition dependency")
    def test_saved_composites_and_five_km_radius(self):
        import rasterio
        from rasterio.warp import transform_geom
        from shapely.geometry import shape, mapping
        meta, polygon, ndvi, climate = read_bundle(DATA_DIR / "observed")
        values, yearly = aggregate_observations(meta, ndvi, climate)
        footprints = []
        for year in [*meta["baseline_years"], 2026]:
            with rasterio.open(DATA_DIR / "observed" / f"ndvi_median_{year}.tif") as src:
                arr = src.read(1, masked=True)
                footprints.append(~np.ma.getmaskarray(arr))
                self.assertAlmostEqual(float(arr.mean()), yearly[year]["ndvi"], places=6)
        for footprint in footprints[1:]:
            np.testing.assert_array_equal(footprint, footprints[0])
        local = "+proj=aeqd +lat_0=44.916664 +lon_0=64.712612 +datum=WGS84 +units=m +no_defs"
        ring = shape(transform_geom("EPSG:4326", local, mapping(polygon))).exterior.coords
        radii = np.hypot(*np.array(ring).T)
        np.testing.assert_allclose(radii, 5000, atol=0.01)
        self.assertAlmostEqual(values["precipitation_mm"], climate.loc[climate.date.dt.year.eq(2026), "precipitation_mm"].sum())


if __name__ == "__main__":
    unittest.main()
