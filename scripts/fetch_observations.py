"""Fetch real Sentinel-2/ERA5 records for a user-specified pilot polygon.

No credentials. Run with python -m scripts.fetch_observations --help.
Writes an atomic manifest last, after validating the full staged bundle.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import shutil
import tempfile

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from shapely.geometry import box, mapping, shape

from src.observations import geometry_hash, period_for_year, read_bundle, aggregate_observations

STAC = "https://earth-search.aws.element84.com/v1/search"
CLIMATE = "https://archive-api.open-meteo.com/v1/archive"
COLLECTION = "sentinel-2-l2a"


def session():
    client = requests.Session()
    client.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET", "POST"])))
    return client


def search_scenes(client, geometry, start, end):
    body = {"collections": [COLLECTION], "intersects": geometry,
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100}
    response = client.post(STAC, json=body, timeout=90)
    response.raise_for_status()
    page = response.json()
    features = page["features"]
    while any(link["rel"] == "next" for link in page.get("links", [])):
        link = next(link for link in page["links"] if link["rel"] == "next")
        if link.get("method", "GET") == "POST":
            response = client.post(link["href"], json=link.get("body", body), timeout=90)
        else:
            response = client.get(link["href"], timeout=90)
        response.raise_for_status()
        page = response.json()
        features.extend(page["features"])
    # One tile must cover the pilot completely. No misleading partial-polygon means.
    polygon = shape(geometry)
    return sorted([f for f in features if shape(f["geometry"]).covers(polygon)], key=lambda f: f["id"])


def scene_ndvi(item, geometry):
    import rasterio
    from rasterio.features import geometry_mask, geometry_window
    from rasterio.warp import transform_geom
    from rasterio.vrt import WarpedVRT
    from rasterio.enums import Resampling
    assets = item["assets"]
    # Earth Search's COG assets have explicit scale/offset, including post-2022 offsets.
    for name in ("red", "nir", "scl"):
        if not assets[name]["href"].startswith("https://"):
            raise ValueError("Only public HTTPS assets are supported.")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="90", GDAL_HTTP_MAX_RETRY="3"):
        with rasterio.open(assets["red"]["href"]) as red_ds:
            projected = transform_geom("EPSG:4326", red_ds.crs, geometry)
            window = geometry_window(red_ds, [projected])
            transform = red_ds.window_transform(window)
            rows, cols = int(window.height), int(window.width)
            if rows * cols > 2_000_000:
                raise ValueError("Pilot too large for this small-area importer.")
            inside = geometry_mask([projected], (rows, cols), transform, invert=True)
            red = red_ds.read(1, window=window, masked=True)
            crs = red_ds.crs
        def aligned(name):
            with rasterio.open(assets[name]["href"]) as ds:
                with WarpedVRT(ds, crs=crs, transform=transform, width=cols, height=rows,
                               resampling=Resampling.nearest) as vrt:
                    return vrt.read(1, masked=True)
        nir, scl = aligned("nir"), aligned("scl")
    def reflectance(array, name):
        band = assets[name].get("raster:bands", [{}])[0]
        if "scale" not in band or "offset" not in band:
            raise ValueError(f"{item['id']}: missing explicit radiometric scale/offset.")
        return array.astype(float) * band["scale"] + band["offset"]
    red, nir = reflectance(red, "red"), reflectance(nir, "nir")
    # SCL 4=vegetation, 5=bare soil; exclude clouds, shadows, snow, water and unclassified.
    valid = inside & np.isin(scl.filled(0), [4, 5])
    valid &= ~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir)
    valid &= (red.filled(-1) >= 0) & (nir.filled(-1) >= 0) & ((red + nir).filled(0) > 0)
    fraction = float(valid.sum() / inside.sum()) if inside.sum() else 0.0
    if fraction < 0.7:
        return None
    pixel_ndvi = ((nir - red) / (nir + red))[valid]
    return {"date": item["properties"]["datetime"][:10], "ndvi": float(pixel_ndvi.mean()),
            "valid_fraction": fraction, "scene_id": item["id"], "polygon_sha256": geometry_hash(geometry)}


def fetch_climate(client, latitude, longitude, start, end, include_soil=False):
    params = {"latitude": latitude, "longitude": longitude, "start_date": str(start), "end_date": str(end),
              "daily": "precipitation_sum,temperature_2m_mean", "models": "era5", "timezone": "Asia/Qyzylorda",
              "temperature_unit": "celsius", "precipitation_unit": "mm"}
    if include_soil:
        params["daily"] += ",soil_moisture_0_to_7cm_mean"
    response = client.get(CLIMATE, params=params, timeout=90)
    response.raise_for_status()
    payload = response.json()
    daily = payload["daily"]
    frame = pd.DataFrame({"date": daily["time"], "precipitation_mm": daily["precipitation_sum"],
                          "temperature_mean_c": daily["temperature_2m_mean"]})
    if include_soil:
        frame["soil_moisture_m3m3"] = daily["soil_moisture_0_to_7cm_mean"]
    return frame, {"url": response.url, "response": payload}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--polygon", type=Path, help="One WGS84 GeoJSON Feature with a Polygon")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--paddock", default="Paddock 2", choices=[f"Paddock {i}" for i in range(1, 5)])
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 1))
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2019, 2026)))
    parser.add_argument("--output", type=Path, default=Path("data/observed"))
    args = parser.parse_args()
    if args.polygon:
        feature = json.loads(args.polygon.read_text(encoding="utf-8"))
        if feature.get("type") != "Feature":
            parser.error("--polygon requires one Feature")
        geometry = feature["geometry"]
        status = feature.get("properties", {}).get("boundary_status", "provisional")
        source = feature.get("properties", {}).get("geometry_source", f"User-supplied file: {args.polygon.name}")
    else:
        if args.latitude is None or args.longitude is None:
            parser.error("Provide --polygon or both --latitude and --longitude. No demo-location default is used.")
        if not (-80 < args.latitude < 80 and -180 <= args.longitude <= 180):
            parser.error("Invalid pilot coordinates")
        dy = 0.5 / 111.32
        dx = 0.5 / (111.32 * math.cos(math.radians(args.latitude)))
        geometry = mapping(box(args.longitude - dx, args.latitude - dy, args.longitude + dx, args.latitude + dy))
        status, source = "provisional", "Approximate 1 km square centered on user-provided coordinates; not an official pasture boundary"
    polygon = shape(geometry)
    if polygon.geom_type != "Polygon" or polygon.is_empty or not polygon.is_valid:
        parser.error("Pilot must be one valid Polygon")
    if (args.output / "manifest.json").exists():
        parser.error("Output already contains an observation bundle; choose a new directory to preserve it.")
    start = args.end - timedelta(days=29)
    if args.end > date.today() - timedelta(days=7):
        parser.error("Use an end date at least seven days ago for reanalysis availability")
    if len(set(args.years)) != len(args.years) or len(args.years) < 3 or any(y >= args.end.year for y in args.years):
        parser.error("Provide at least three distinct baseline years before the assessment year")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="observations-", dir=args.output.parent))
    print(f"Staging real downloads in {staging}", flush=True)
    client = session()
    ndvi_records, climate_frames, requests_log, scene_log = [], [], [], []
    center = polygon.centroid
    for year in [*args.years, args.end.year]:
        a, b = period_for_year(start, args.end, year)
        print(f"{year}: downloading ERA5 and searching Sentinel-2 ({a} to {b})", flush=True)
        frame, raw = fetch_climate(client, center.y, center.x, a, b)
        frame["polygon_sha256"] = geometry_hash(geometry)
        climate_frames.append(frame)
        requests_log.append(raw)
        scenes = search_scenes(client, geometry, a, b)
        # Never silently skip a network/raster error. Re-run after resolving it.
        for scene in scenes:
            result = scene_ndvi(scene, geometry)
            scene_log.append({"item": scene, "accepted": result is not None})
            if result:
                ndvi_records.append(result)
            print(f"  {scene['id']}: {'accepted' if result else 'insufficient clear land coverage'}", flush=True)
        (staging / "source_records.json").write_text(json.dumps({"climate": requests_log, "sentinel": scene_log}, indent=2), encoding="utf-8")
    meta = {"schema_version": 1, "paddock_id": args.paddock, "period_start": str(start), "period_end": str(args.end),
            "baseline_years": args.years, "polygon_sha256": geometry_hash(geometry), "boundary_status": status,
            "geometry_source": source, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "ndvi_source": STAC, "ndvi_collection": COLLECTION, "climate_source": CLIMATE, "climate_model": "era5",
            "climate_spatial_method": "Open-Meteo ERA5 grid estimate at polygon centroid, not a polygon mean or weather station",
            "ndvi_method": "10m red/NIR reflectance with asset scale/offset; nearest-neighbor SCL 4/5 mask; >=70% clear-land coverage; polygon mean per scene; median per window; equal-year baseline mean",
            "climate_units": {"precipitation_mm": "mm", "temperature_mean_c": "degC"}}
    (staging / "pilot.geojson").write_text(json.dumps({"type": "Feature", "properties": {"boundary_status": status}, "geometry": geometry}, indent=2), encoding="utf-8")
    pd.DataFrame(ndvi_records).to_csv(staging / "ndvi_observations.csv", index=False)
    pd.concat(climate_frames).to_csv(staging / "climate_daily.csv", index=False)
    (staging / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    validated, _, ndvi, climate = read_bundle(staging)
    values, summaries = aggregate_observations(validated, ndvi, climate)
    display_values = {key: round(value, 1) if key.endswith("_pct") else value for key, value in values.items()}
    (staging / "aggregation.json").write_text(json.dumps({"assessment": display_values, "annual_windows": summaries}, indent=2), encoding="utf-8")
    # Publish only a completely validated folder; never replace an existing bundle.
    if args.output.exists():
        raise ValueError(f"Output directory already exists: {args.output}. Use a new directory.")
    shutil.move(str(staging), str(args.output))
    print(f"Saved validated observations: {args.output}\n{json.dumps(display_values, indent=2)}", flush=True)


if __name__ == "__main__":
    main()
