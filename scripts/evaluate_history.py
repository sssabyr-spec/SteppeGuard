"""Retrospective monthly Akkum screening; no tuning to force grazing conflicts.

30-day month-end windows March-November 2021-2025, March-September 2026.
Leave-one-year-out same-calendar references. This is NOT a predictive hindcast.
Run python -m scripts.evaluate_history. Reuses the unchanged v0.2 spatial grid.
"""
import calendar
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import shape

from scripts import fetch_pilot as pilot
from scripts.fetch_observations import session, fetch_climate
from src.observations import geometry_hash
from src.historical import evaluate_windows

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "historical"
CACHE = ROOT / "data" / "history_cache"
CUTOFF = date(2026, 9, 30)


def windows():
    for year in range(2021, 2027):
        for month in range(3, 12):
            end = date(year, month, calendar.monthrange(year, month)[1])
            if end <= CUTOFF:
                yield end - timedelta(days=29), end


def extract_window(start, end, geometry, transform, width, height, inside):
    client = session()
    name = end.isoformat()
    record_path = CACHE / f"{name}.json"
    array_path = CACHE / f"{name}.npz"
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record["status"] != "network_error":
            return record
    record = {"period_start": str(start), "assessment_date": str(end), "year": end.year, "month": end.month,
              "status": "insufficient_satellite", "scene_count": 0, "scene_records": []}
    try:
        body = {"collections": ["sentinel-2-l2a"], "intersects": geometry,
                "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100,
                "query": {"eo:cloud_cover": {"lt": 60}}}
        page = pilot.get_json(client, CACHE / f"stac_{name}.json", "POST", pilot.STAC, json=body)
        items = page["features"]
        page_num = 1
        while any(link["rel"] == "next" for link in page.get("links", [])):
            link = next(link for link in page["links"] if link["rel"] == "next")
            method = link.get("method", "GET")
            page = pilot.get_json(client, CACHE / f"stac_{name}_{page_num}.json", method, link["href"],
                                  **({"json": link.get("body", body)} if method == "POST" else {}))
            items.extend(page["features"])
            page_num += 1
        polygon = shape(geometry)
        chosen = {}
        for item in sorted(items, key=lambda f: (f["properties"]["eo:cloud_cover"], f["id"])):
            if shape(item["geometry"]).covers(polygon):
                chosen.setdefault(item["properties"]["datetime"][:10], item)
        arrays = []
        for day, item in sorted(chosen.items()):
            ndvi = pilot.extract(client, item, transform, width, height, inside)
            coverage = float(np.isfinite(ndvi).sum() / inside.sum())
            accepted = coverage >= 0.7
            record["scene_records"].append({"date": day, "scene_id": item["id"], "valid_fraction": coverage,
                                             "accepted": accepted, "item": item})
            if accepted:
                arrays.append(ndvi)
        record["scene_count"] = len(arrays)
        if len(arrays) >= 2:
            stack = np.stack(arrays)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                composite = np.nanmedian(stack, axis=0)
            composite[(np.isfinite(stack).sum(axis=0) < 2) | ~inside] = np.nan
            record["valid_fraction"] = float(np.isfinite(composite).sum() / inside.sum())
            np.savez_compressed(array_path, ndvi=composite)
            record["status"] = "ready" if record["valid_fraction"] >= 0.7 else "insufficient_composite_coverage"
    except Exception as exc:
        # Record missing evidence, never silently generate replacement measurements.
        # Do not persist expiring SAS query parameters from a network error.
        record["status"] = "network_error"
        record["error_type"] = type(exc).__name__
        print(f"{name}: retrieval failed ({type(exc).__name__}); rerun retries it", flush=True)
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"{name}: {record['status']}, {record['scene_count']} accepted dates", flush=True)
    return record


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    geometry = pilot.analysis_geometry()
    config = {"geometry": geometry, "crs": pilot.CRS, "resolution": 20, "cutoff": str(CUTOFF), "method": "pixel_median_scl45_v1"}
    config = json.loads(json.dumps(config))
    config_file = CACHE / "config.json"
    if config_file.exists() and json.loads(config_file.read_text()) != config:
        raise ValueError("History cache configuration mismatch")
    config_file.write_text(json.dumps(config), encoding="utf-8")
    # Shared scene cache must have been built on exactly the same spatial grid.
    pilot.CACHE.mkdir(parents=True, exist_ok=True)
    pilot_config_path = pilot.CACHE / "config.json"
    if not pilot_config_path.exists():
        if any(pilot.CACHE.glob("*.npz")):
            raise ValueError("Unverified scene cache: configuration is missing")
        pilot_config_path.write_text(json.dumps({"geometry": geometry, "crs": pilot.CRS, "resolution": 20,
                                                "end": str(pilot.END), "years": pilot.YEARS}), encoding="utf-8")
    pilot_config = json.loads(pilot_config_path.read_text())
    for key in ("geometry", "crs", "resolution"):
        if pilot_config[key] != config[key]:
            raise ValueError("v0.2 scene cache grid mismatch")
    x0, y0, x1, y1 = shape(transform_geom("EPSG:4326", pilot.CRS, geometry)).bounds
    x0, y1 = np.floor(x0 / 20) * 20, np.ceil(y1 / 20) * 20
    width, height = int(np.ceil((x1 - x0) / 20)), int(np.ceil((y1 - y0) / 20))
    transform = from_origin(x0, y1, 20, 20)
    inside = geometry_mask([transform_geom("EPSG:4326", pilot.CRS, geometry)], (height, width), transform, invert=True)
    client = session()
    climate_frames, climate_audit = [], []
    for year in range(2021, 2027):
        start, end = date(year, 3, 1), min(date(year, 11, 30), CUTOFF)
        path = CACHE / f"climate_{year}.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            d = raw["response"]["daily"]
            frame = pd.DataFrame({"date": d["time"], "precipitation_mm": d["precipitation_sum"],
                                  "temperature_mean_c": d["temperature_2m_mean"], "soil_moisture_m3m3": d["soil_moisture_0_to_7cm_mean"]})
        else:
            frame, raw = fetch_climate(client, pilot.LAT, pilot.LON, start, end, include_soil=True)
            path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        climate_frames.append(frame)
        climate_audit.append(raw)
        print(f"Climate {year}: {len(frame)} daily records", flush=True)
    climate = pd.concat(climate_frames, ignore_index=True)
    records = []
    # Three independent windows in parallel, not parallel agents; cache caps repeated downloads.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(extract_window, start, end, geometry, transform, width, height, inside) for start, end in windows()]
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda r: r["assessment_date"])
    # Uniform monthly common support; reject a month if its joint support is inadequate.
    for month in range(3, 12):
        cohort = [r for r in records if r["month"] == month and r["status"] == "ready"]
        if not cohort:
            continue
        arrays = {r["assessment_date"]: np.load(CACHE / f"{r['assessment_date']}.npz")["ndvi"] for r in cohort}
        common = inside & np.logical_and.reduce([np.isfinite(a) for a in arrays.values()])
        fraction = float(common.sum() / inside.sum())
        for record in cohort:
            record["common_valid_fraction"] = fraction
            if fraction < 0.7:
                record["status"] = "insufficient_common_coverage"
            else:
                record["current_ndvi"] = float(arrays[record["assessment_date"]][common].mean())
    table = evaluate_windows(records, climate)
    eligible = table.loc[table.status.eq("evaluated") & table.conflict.eq(True)].sort_values(["stress_score", "assessment_date"], ascending=[False, True])
    selected_date = None if eligible.empty else eligible.iloc[0].assessment_date
    OUTPUT.mkdir(exist_ok=True)
    # Raw precision retained in evaluation for exact score reproduction; downloadable/UI percentages are rounded.
    table.to_csv(OUTPUT / "evaluation.csv", index=False)
    climate.to_csv(OUTPUT / "climate_daily.csv", index=False)
    (OUTPUT / "climate_source_records.json").write_text(json.dumps(climate_audit, indent=2), encoding="utf-8")
    (OUTPUT / "source_records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    # Archive the selected case and its reference composites on the common pixel footprint.
    if selected_date:
        month = int(selected_date[5:7])
        cohort = [r for r in records if r["month"] == month and r["status"] == "ready"]
        arrays = {r["assessment_date"]: np.load(CACHE / f"{r['assessment_date']}.npz")["ndvi"] for r in cohort}
        common = inside & np.logical_and.reduce([np.isfinite(a) for a in arrays.values()])
        for name, arr in arrays.items():
            with rasterio.open(OUTPUT / f"case_composite_{name}.tif", "w", driver="GTiff", width=width, height=height,
                               count=1, dtype="float32", crs=pilot.CRS, transform=transform, nodata=-9999, compress="deflate") as dst:
                dst.write(np.where(common, arr, -9999).astype("float32"), 1)
    manifest = {"schema_version": 1, "polygon_sha256": geometry_hash(geometry), "coverage_start": "2021-03-01",
                "coverage_end": str(CUTOFF), "cadence": "Monthly: trailing 30 days ending on month-end, March-November",
                "reference_method": "Leave-one-year-out same-calendar windows; >=3 other evaluable years; shared monthly pixel support",
                "retrospective_only": True, "selected_date": selected_date,
                "selection_rule": "Highest unchanged integer stress score among evaluable grazing windows; earliest date breaks ties",
                "requested_windows": len(table), "evaluated_windows": int(table.status.eq("evaluated").sum()),
                "conflict_windows": len(eligible), "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "satellite_source": pilot.STAC, "climate_source": "https://archive-api.open-meteo.com/v1/archive",
                "official_plan_source": "https://old.adilet.zan.kz/kaz/docs/G24LF02818M",
                "limitations": "Monthly sample, not daily extrema. Retrospective references can include later years. 2026 October-November not yet complete. Scenario applies 2026-style seasons to past dates; not evidence of actual historical grazing or predictive skill."}
    manifest["artifact_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUTPUT.iterdir() if p.is_file() and p.name != "manifest.json"}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Evaluated {manifest['evaluated_windows']}/{len(table)}; conflicts {len(eligible)}; selected {selected_date}", flush=True)
    print(eligible.head(8)[["assessment_date", "stress_score", "vegetation_anomaly_pct", "rainfall_anomaly_pct", "temperature_anomaly_c", "soil_moisture_status"]].round(1).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
