"""Small generated rasters verify radiometry/masking, not real field observations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


@unittest.skipUnless(importlib.util.find_spec("rasterio"), "Install requirements-data.txt for extraction tests")
class RasterExtractionTests(unittest.TestCase):
    def test_scale_offset_mask_and_small_window(self):
        import rasterio
        from rasterio.transform import from_origin
        from rasterio.warp import transform_geom
        from shapely.geometry import box, mapping
        from scripts.fetch_observations import scene_ndvi

        with tempfile.TemporaryDirectory() as folder:
            paths = {name: Path(folder) / f"{name}.tif" for name in ("red", "nir", "scl")}
            for name, value in [("red", 2000), ("nir", 4000), ("scl", 5)]:
                with rasterio.open(paths[name], "w", driver="GTiff", height=10, width=10, count=1,
                                   dtype="uint16", crs="EPSG:32641", transform=from_origin(500000, 5000000, 10, 10), nodata=0) as output:
                    output.write(np.full((10, 10), value, dtype="uint16"), 1)
            geometry = transform_geom("EPSG:32641", "EPSG:4326", mapping(box(500010, 4999910, 500090, 4999990)))
            item = {"id": "SYNTHETIC-TEST", "properties": {"datetime": "2026-06-10T05:00:00Z"},
                    "assets": {name: {"href": f"https://test.invalid/{name}", "raster:bands": [{"scale": 0.0001, "offset": -0.1}]}
                               for name in paths}}
            original_open = rasterio.open
            def local_open(url, *args, **kwargs):
                return original_open(paths[str(url).rsplit("/", 1)[-1]], *args, **kwargs)
            with patch("rasterio.open", side_effect=local_open):
                row = scene_ndvi(item, geometry)
            self.assertAlmostEqual(row["ndvi"], 0.5, places=6)
            self.assertAlmostEqual(row["valid_fraction"], 1)
            with original_open(paths["scl"], "r+") as output:
                output.write(np.full((10, 10), 9, dtype="uint16"), 1)
            with patch("rasterio.open", side_effect=local_open):
                self.assertIsNone(scene_ndvi(item, geometry))


if __name__ == "__main__":
    unittest.main()
