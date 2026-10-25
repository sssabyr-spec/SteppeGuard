"""v0.2: real 5 km Akkum analysis zone, MPC median composites and ERA5.

Run python -m scripts.fetch_pilot. Downloads are cached for resumable execution.
No user account or secrets are needed. SAS URLs are used in memory only.
"""
import hashlib
import json
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import planetary_computer as pc
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from shapely.geometry import Point, mapping, shape

from scripts.fetch_observations import session, fetch_climate
from src.observations import geometry_hash, read_bundle, aggregate_observations

LAT, LON, RADIUS = 44.916664, 64.712612, 5000
END = date(2026, 9, 30)
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "acquisition_cache"
OUTPUT = ROOT / "data" / "observed"
CRS = "EPSG:32641"


def analysis_geometry():
    # A local azimuthal equidistant projection preserves radial distance from center.
    local = f"+proj=aeqd +lat_0={LAT} +lon_0={LON} +datum=WGS84 +units=m +no_defs"
    return transform_geom(local, "EPSG:4326", mapping(Point(0, 0).buffer(RADIUS, quad_segs=90)))


def get_json(client, path, method, url, **kwargs):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    response = client.request(method, url, timeout=90, **kwargs)
    response.raise_for_status()
    obj = response.json()
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return obj


def radiometry(client, item):
    """Read ESA product metadata, not a hardcoded post-2022 offset guess."""
    path = CACHE / f"{item['id']}.xml"
    if not path.exists():
        response = client.get(pc.sign(item["assets"]["product-metadata"]["href"]), timeout=90)
        response.raise_for_status()
        path.write_bytes(response.content)
    root = ET.fromstring(path.read_bytes())
    def nodes(tag):
        return [node for node in root.iter() if node.tag.split("}")[-1] == tag]
    quant = nodes("BOA_QUANTIFICATION_VALUE")
    if not quant:
        raise ValueError(f"Missing BOA quantification for {item['id']}")
    factor = float(quant[0].text)
    offsets = {int(n.attrib["band_id"]): float(n.text) for n in nodes("BOA_ADD_OFFSET")}
    baseline = float(item["properties"]["s2:processing_baseline"])
    if baseline >= 4 and not {3, 7}.issubset(offsets):
        raise ValueError("Post-04.00 product lacks BOA offsets")
    return factor, offsets.get(3, 0.0), offsets.get(7, 0.0)


def extract(client, item, transform, width, height, inside):
    cache = CACHE / f"{item['id']}_20m.npz"
    if cache.exists():
        with np.load(cache) as f:
            return f["ndvi"]
    quant, red_offset, nir_offset = radiometry(client, item)
    arrays = {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="90", GDAL_HTTP_MAX_RETRY="3"):
        for band in ("B04", "B08", "SCL"):
            with rasterio.open(pc.sign(item["assets"][band]["href"])) as src:
                with WarpedVRT(src, crs=CRS, transform=transform, width=width, height=height,
                               resampling=Resampling.nearest if band == "SCL" else Resampling.average) as vrt:
                    arrays[band] = vrt.read(1, masked=True).filled(0).astype("float32")
    red = (arrays["B04"] + red_offset) / quant
    nir = (arrays["B08"] + nir_offset) / quant
    valid = inside & np.isin(arrays["SCL"], [4, 5])
    valid &= (arrays["B04"] > 0) & (arrays["B08"] > 0) & (red >= 0) & (nir >= 0) & (nir + red > 0)
    ndvi = np.full((height, width), np.nan, dtype="float32")
    np.divide(nir - red, nir + red, out=ndvi, where=valid)
    np.savez_compressed(cache, ndvi=ndvi)
    return ndvi


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "manifest.json").exists():
        raise ValueError("A validated bundle already exists; preserve it before a new acquisition.")
    client = session()
    geometry = analysis_geometry()
    polygon = shape(geometry)
    digest = geometry_hash(geometry)
    # Cache is bound to this exact area/grid/configuration, avoiding wrong-area reuse.
    configuration = {"geometry": geometry, "crs": CRS, "resolution": 20, "end": str(END), "years": YEARS}
    configuration = json.loads(json.dumps(configuration))
    config_path = CACHE / "config.json"
    if config_path.exists() and json.loads(config_path.read_text()) != configuration:
        raise ValueError("Acquisition cache belongs to another configuration")
    config_path.write_text(json.dumps(configuration), encoding="utf-8")
    x0, y0, x1, y1 = shape(transform_geom("EPSG:4326", CRS, geometry)).bounds
    x0, y1 = np.floor(x0 / 20) * 20, np.ceil(y1 / 20) * 20
    width, height = int(np.ceil((x1 - x0) / 20)), int(np.ceil((y1 - y0) / 20))
    transform = from_origin(x0, y1, 20, 20)
    projected = transform_geom("EPSG:4326", CRS, geometry)
    inside = geometry_mask([projected], (height, width), transform, invert=True)
    composites, scene_rows, climate_frames, audit, window_rows = {}, [], [], [], []
    for year in YEARS:
        a, b = date(year, 9, 1), date(year, 9, 30)
        print(f"{year}: ERA5 + Sentinel-2", flush=True)
        climate_path = CACHE / f"climate_{year}.json"
        if climate_path.exists():
            climate_raw = json.loads(climate_path.read_text(encoding="utf-8"))
            daily = climate_raw["response"]["daily"]
            climate = pd.DataFrame({"date": daily["time"], "precipitation_mm": daily["precipitation_sum"],
                                    "temperature_mean_c": daily["temperature_2m_mean"],
                                    "soil_moisture_m3m3": daily["soil_moisture_0_to_7cm_mean"]})
        else:
            climate, climate_raw = fetch_climate(client, LAT, LON, a, b, include_soil=True)
            climate_path.write_text(json.dumps(climate_raw, indent=2), encoding="utf-8")
        climate["polygon_sha256"] = digest
        climate_frames.append(climate)
        body = {"collections": ["sentinel-2-l2a"], "intersects": geometry,
                "datetime": f"{a}T00:00:00Z/{b}T23:59:59Z", "limit": 100,
                "query": {"eo:cloud_cover": {"lt": 60}}}
        page = get_json(client, CACHE / f"stac_{year}.json", "POST", STAC, json=body)
        if any(link["rel"] == "next" for link in page.get("links", [])):
            raise ValueError("Unexpected >100 scenes; paginate before proceeding")
        scenes = [f for f in page["features"] if shape(f["geometry"]).covers(polygon)]
        # Use a single fully covering tile per date; lowest whole-scene cloud fraction.
        chosen = {}
        for item in sorted(scenes, key=lambda f: (f["properties"]["eo:cloud_cover"], f["id"])):
            chosen.setdefault(item["properties"]["datetime"][:10], item)
        arrays, accepted_items = [], []
        for day, item in sorted(chosen.items()):
            ndvi = extract(client, item, transform, width, height, inside)
            coverage = float(np.isfinite(ndvi).sum() / inside.sum())
            accepted = coverage >= 0.7
            audit.append({"item": item, "accepted": accepted, "valid_fraction": coverage})
            print(f"  {day}: clear land {coverage:.1%} {'accepted' if accepted else 'rejected'}", flush=True)
            if accepted:
                arrays.append(ndvi)
                accepted_items.append(item)
                scene_rows.append({"date": day, "ndvi": float(np.nanmean(ndvi)), "valid_fraction": coverage,
                                   "scene_id": item["id"], "polygon_sha256": digest})
        if len(arrays) < 2:
            raise ValueError(f"{year}: fewer than two acceptable acquisitions")
        stack = np.stack(arrays)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            composite = np.nanmedian(stack, axis=0)
        composite[(np.isfinite(stack).sum(axis=0) < 2) | ~inside] = np.nan
        composites[year] = composite
        window_rows.append({"year": year, "scene_count": len(arrays), "polygon_sha256": digest})
    # Compare EXACTLY the same pixel footprint in all current/historical composites.
    common = inside & np.logical_and.reduce([np.isfinite(c) for c in composites.values()])
    common_fraction = float(common.sum() / inside.sum())
    if common_fraction < 0.7:
        raise ValueError(f"Insufficient common valid support: {common_fraction:.1%}")
    OUTPUT.mkdir(exist_ok=True)
    for row in window_rows:
        year = row["year"]
        composite = composites[year]
        row.update(ndvi=float(composite[common].mean()), valid_fraction=common_fraction)
        with rasterio.open(OUTPUT / f"ndvi_median_{year}.tif", "w", driver="GTiff", width=width, height=height,
                           count=1, dtype="float32", crs=CRS, transform=transform, nodata=-9999, compress="deflate") as out:
            out.write(np.where(common, composite, -9999).astype("float32"), 1)
    pd.DataFrame(window_rows).to_csv(OUTPUT / "window_ndvi.csv", index=False)
    pd.DataFrame(scene_rows).to_csv(OUTPUT / "ndvi_observations.csv", index=False)
    pd.concat(climate_frames).to_csv(OUTPUT / "climate_daily.csv", index=False)
    (OUTPUT / "pilot.geojson").write_text(json.dumps({"type": "Feature", "geometry": geometry,
        "properties": {"name": "Akkum 5 km analysis zone", "boundary_status": "provisional", "radius_m": RADIUS,
                       "center_latitude": LAT, "center_longitude": LON}}, indent=2), encoding="utf-8")
    (OUTPUT / "source_records.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (OUTPUT / "climate_source_records.json").write_text(json.dumps([json.loads((CACHE / f"climate_{y}.json").read_text()) for y in YEARS], indent=2), encoding="utf-8")
    meta = {"schema_version": 2, "paddock_id": "Paddock 2", "scope": "shared_pilot_zone", "period_start": "2026-09-01",
            "period_end": "2026-09-30", "baseline_years": YEARS[:-1], "polygon_sha256": digest, "boundary_status": "provisional",
            "geometry_source": "5 km radius azimuthal-equidistant buffer around user-supplied Akkum village coordinates; approximate analysis zone, not administrative or official paddock boundaries",
            "center_latitude": LAT, "center_longitude": LON, "radius_m": RADIUS,
            "retrieved_at": datetime.now(timezone.utc).isoformat(), "ndvi_source": STAC, "ndvi_collection": "sentinel-2-l2a",
            "climate_source": "https://archive-api.open-meteo.com/v1/archive", "climate_model": "era5", "soil_depth_cm": "0-7",
            "ndvi_method": "20m B04/B08 surface reflectance, ESA metadata quantification/offsets, nearest SCL 4/5; >=70% clear land per date; pixelwise temporal median with >=2 observations; same valid pixel footprint in every year; zone mean then equal-year historical mean",
            "common_valid_fraction": common_fraction,
            "soil_status_method": "Period-mean 0-7cm volumetric soil moisture relative to same-period historical mean: below -20% Below normal; below -10% Slightly below normal; otherwise Normal. Provisional mapping to unchanged score categories.",
            "official_plan_source": "https://old.adilet.zan.kz/kaz/docs/G24LF02818M"}
    meta["artifact_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUTPUT.iterdir() if p.is_file() and p.name != "manifest.json"}
    # Validate before activating. A staged manifest is removed on validation failure.
    (OUTPUT / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    try:
        m, _, n, c = read_bundle(OUTPUT)
        values, annual = aggregate_observations(m, n, c)
    except Exception:
        (OUTPUT / "manifest.json").unlink()
        raise
    print(json.dumps({k: round(v, 1) if k.endswith("_pct") else v for k, v in values.items()}, indent=2), flush=True)


if __name__ == "__main__":
    main()
