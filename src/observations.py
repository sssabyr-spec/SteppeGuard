"""Validated local observations. No network requests and no score-rule changes.

Sentinel-2 is satellite-observed; ERA5 is reanalysis, not a local station.
Missing/invalid observations never silently fall back to synthetic values.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape, box, mapping

DEMO_DATE = "2026-07-01"


def geometry_hash(geometry):
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def period_for_year(start, end, year):
    """Same month/day boundaries, including year-crossing windows. Reject Feb 29."""
    shift = year - end.year
    return start.replace(year=start.year + shift), end.replace(year=year)


def read_bundle(directory):
    directory = Path(directory)
    meta = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    feature = json.loads((directory / "pilot.geojson").read_text(encoding="utf-8"))
    if feature.get("type") != "Feature":
        raise ValueError("pilot.geojson must contain one GeoJSON Feature.")
    geometry = feature["geometry"]
    polygon = shape(geometry)
    if polygon.geom_type != "Polygon" or not polygon.is_valid or polygon.is_empty:
        raise ValueError("Pilot must be one valid, nonempty Polygon.")
    bounds = polygon.bounds
    if not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90):
        raise ValueError("Pilot coordinates must be WGS84 longitude/latitude.")
    digest = geometry_hash(geometry)
    if meta.get("schema_version") not in (1, 2) or meta.get("polygon_sha256") != digest:
        raise ValueError("Unsupported manifest or polygon hash mismatch.")
    if meta.get("boundary_status") not in ("provisional", "verified"):
        raise ValueError("Declare boundary_status as provisional or verified.")
    if meta.get("climate_model") != "era5" or meta.get("ndvi_collection") != "sentinel-2-l2a":
        raise ValueError("This importer supports Sentinel-2 L2A and ERA5 only.")
    for field in ("retrieved_at", "geometry_source", "ndvi_source", "climate_source", "paddock_id"):
        if not isinstance(meta.get(field), str) or not meta[field].strip():
            raise ValueError(f"Missing provenance: {field}")
    ndvi = pd.read_csv(directory / "ndvi_observations.csv")
    climate = pd.read_csv(directory / "climate_daily.csv")
    if meta["schema_version"] == 2:
        hashes = meta.get("artifact_sha256", {})
        required = {"pilot.geojson", "window_ndvi.csv", "ndvi_observations.csv", "climate_daily.csv"}
        if not required.issubset(hashes):
            raise ValueError("Composite bundle must include artifact checksums.")
        for name, expected_hash in hashes.items():
            if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected_hash:
                raise ValueError(f"Observation artifact checksum mismatch: {name}")
        windows = pd.read_csv(directory / "window_ndvi.csv")
        required = ["year", "ndvi", "scene_count", "valid_fraction", "polygon_sha256"]
        if not set(required).issubset(windows) or windows[required].isna().any().any():
            raise ValueError("Invalid composite summary.")
        if windows.year.duplicated().any() or not windows.polygon_sha256.eq(digest).all():
            raise ValueError("Composite years or geometry inconsistent.")
        if not windows.ndvi.between(-1, 1).all() or not windows.valid_fraction.between(0.7, 1).all() or (windows.scene_count < 2).any():
            raise ValueError("Insufficient composite quality.")
        meta["window_composites"] = windows.set_index("year").to_dict("index")
        if "soil_moisture_m3m3" not in climate or not climate.soil_moisture_m3m3.between(0, 1).all():
            raise ValueError("Complete ERA5 soil moisture is required for a v0.2 bundle.")
    for frame, columns in [(ndvi, ["date", "ndvi", "valid_fraction", "scene_id", "polygon_sha256"]),
                           (climate, ["date", "precipitation_mm", "temperature_mean_c", "polygon_sha256"])]:
        if not set(columns).issubset(frame.columns) or frame[columns].isna().any().any():
            raise ValueError(f"Missing columns or values: {columns}")
        if not frame.polygon_sha256.eq(digest).all():
            raise ValueError("Observations refer to a different polygon.")
        frame["date"] = pd.to_datetime(frame.date, format="%Y-%m-%d", errors="raise")
    if ndvi.scene_id.duplicated().any() or climate.date.duplicated().any():
        raise ValueError("Duplicate scene IDs or climate dates are not allowed.")
    for frame, cols in [(ndvi, ["ndvi", "valid_fraction"]), (climate, ["precipitation_mm", "temperature_mean_c"])]:
        frame[cols] = frame[cols].apply(pd.to_numeric, errors="raise")
        if not np.isfinite(frame[cols].to_numpy()).all():
            raise ValueError("Observation values must be finite.")
    if not ndvi.ndvi.between(-1, 1).all() or not ndvi.valid_fraction.between(0, 1).all():
        raise ValueError("Invalid NDVI or coverage fraction.")
    if (climate.precipitation_mm < 0).any() or not climate.temperature_mean_c.between(-90, 65).all():
        raise ValueError("Invalid precipitation or temperature.")
    return meta, polygon, ndvi, climate


def aggregate_observations(meta, ndvi, climate):
    start, end = date.fromisoformat(meta["period_start"]), date.fromisoformat(meta["period_end"])
    if not 1 <= (end - start).days + 1 <= 62:
        raise ValueError("Observation window must contain 1–62 days.")
    years = meta["baseline_years"]
    if len(set(years)) != len(years) or len(years) < 3 or any(not isinstance(y, int) or y >= end.year for y in years):
        raise ValueError("At least three distinct historical years before the assessment are required.")
    summaries = {}
    for year in [*years, end.year]:
        a, b = period_for_year(start, end, year)
        scenes = ndvi.loc[ndvi.date.between(pd.Timestamp(a), pd.Timestamp(b)) & (ndvi.valid_fraction >= 0.7)].copy()
        # Overlapping tiles/acquisitions on one date count once, choosing best coverage.
        scenes = scenes.sort_values(["valid_fraction", "scene_id"], ascending=[False, True]).drop_duplicates("date")
        if len(scenes) < 2:
            raise ValueError(f"{year}: need two clear Sentinel-2 dates with at least 70% valid polygon coverage.")
        daily = climate.loc[climate.date.between(pd.Timestamp(a), pd.Timestamp(b))]
        if set(daily.date) != set(pd.date_range(a, b)):
            raise ValueError(f"{year}: incomplete daily climate coverage; no partial-period totals allowed.")
        summaries[year] = {"ndvi": float(scenes.ndvi.median()), "precipitation_mm": float(daily.precipitation_mm.sum()),
                           "temperature_mean_c": float(daily.temperature_mean_c.mean()), "scene_count": len(scenes),
                           "latest_scene": scenes.date.max().date().isoformat()}
        if meta.get("schema_version") == 2:
            composite = meta["window_composites"].get(year)
            if composite is None or composite["scene_count"] != len(scenes):
                raise ValueError(f"{year}: composite scene count does not match observations.")
            summaries[year]["ndvi"] = float(composite["ndvi"])
            summaries[year]["soil_moisture_m3m3"] = float(daily.soil_moisture_m3m3.mean())
    baseline_ndvi = float(np.mean([summaries[y]["ndvi"] for y in years]))
    baseline_rain = float(np.mean([summaries[y]["precipitation_mm"] for y in years]))
    baseline_temp = float(np.mean([summaries[y]["temperature_mean_c"] for y in years]))
    if baseline_ndvi <= 0.05 or baseline_rain <= 0.1:
        raise ValueError("Reference NDVI ≤0.05 or precipitation ≤0.1 mm: relative anomalies are unstable; assessment withheld.")
    current = summaries[end.year]
    result = {"current_ndvi": current["ndvi"], "seasonal_ndvi": baseline_ndvi,
            "vegetation_anomaly_pct": (current["ndvi"] / baseline_ndvi - 1) * 100,
            "rainfall_anomaly_pct": (current["precipitation_mm"] / baseline_rain - 1) * 100,
            "temperature_anomaly_c": current["temperature_mean_c"] - baseline_temp,
            "precipitation_mm": current["precipitation_mm"], "baseline_precipitation_mm": baseline_rain,
            "temperature_mean_c": current["temperature_mean_c"], "baseline_temperature_c": baseline_temp,
            "ndvi_scene_count": current["scene_count"], "latest_scene": current["latest_scene"],
            "assessment_date": end.isoformat(), "period_start": start.isoformat(),
            "baseline_years": ", ".join(map(str, years))}
    if meta.get("schema_version") == 2:
        soil_baseline = float(np.mean([summaries[y]["soil_moisture_m3m3"] for y in years]))
        if soil_baseline <= 0:
            raise ValueError("Soil moisture reference must be positive.")
        soil_anomaly = (current["soil_moisture_m3m3"] / soil_baseline - 1) * 100
        result.update(soil_moisture_m3m3=current["soil_moisture_m3m3"], baseline_soil_moisture_m3m3=soil_baseline,
                      soil_moisture_anomaly_pct=soil_anomaly,
                      soil_moisture_status="Below normal" if soil_anomaly < -20 else "Slightly below normal" if soil_anomaly < -10 else "Normal")
    return result, summaries


def apply_observations(polygons, metrics, directory):
    """Overlay one paddock, or explicitly share a v0.2 pilot-zone signal across plans."""
    polygons, metrics = polygons.copy(), metrics.copy()
    metrics["assessment_date"] = DEMO_DATE
    metrics["data_status"] = "DEMO"
    metrics["vegetation_source"] = "DEMO"
    metrics["climate_source"] = "DEMO"
    metrics["soil_source"] = "DEMO"
    metrics["boundary_status"] = "synthetic demo"
    directory = Path(directory)
    if not (directory / "manifest.json").exists():
        return polygons, metrics
    meta, polygon, ndvi, climate = read_bundle(directory)
    values, _ = aggregate_observations(meta, ndvi, climate)
    shared = meta.get("scope") == "shared_pilot_zone"
    target = pd.Series(True, index=metrics.index) if shared else metrics.paddock_id.eq(meta["paddock_id"])
    if not shared and target.sum() != 1:
        raise ValueError("Imported paddock_id does not match one existing paddock.")
    values.update(data_status="MIXED: satellite + reanalysis; soil DEMO",
                  vegetation_source="OBSERVED · Sentinel-2 L2A", climate_source="REANALYSIS · ERA5 via Open-Meteo",
                  boundary_status=meta["boundary_status"], geometry_source=meta["geometry_source"],
                  retrieved_at=meta["retrieved_at"], polygon_sha256=meta["polygon_sha256"],
                  ndvi_source_url=meta["ndvi_source"], climate_source_url=meta["climate_source"])
    if meta.get("schema_version") == 2:
        values.update(data_status="OBSERVED / REANALYSIS · shared pilot zone",
                      vegetation_source="Observed satellite data · Sentinel-2",
                      climate_source="ERA5 reanalysis data", soil_source="ERA5 reanalysis data",
                      observation_scope="Akkum 5 km zone; shared signal, not paddock-specific",
                      common_valid_fraction=meta["common_valid_fraction"], ndvi_method=meta["ndvi_method"],
                      soil_status_method=meta["soil_status_method"], boundary_status="Approximate analysis zone",
                      water_access="Not assessed")
    for key, value in values.items():
        if key not in metrics:
            metrics[key] = None
        # CSV demo anomalies are integers; preserve full observed precision for scoring.
        if isinstance(value, float) and pd.api.types.is_integer_dtype(metrics[key]):
            metrics[key] = metrics[key].astype(float)
        metrics.loc[target, key] = value
    if shared:
        # Four schematic sectors preserve the UI, NOT claimed official paddock locations.
        x0, y0, x1, y1 = polygon.bounds
        x, y = meta["center_longitude"], meta["center_latitude"]
        sectors = [box(x0, y0, x, y), box(x, y0, x1, y), box(x0, y, x, y1), box(x, y, x1, y1)]
        for i, sector in enumerate(sectors, 1):
            polygons.loc[polygons.paddock_id.eq(f"Paddock {i}"), "geometry"] = polygon.intersection(sector)
        polygons.attrs["analysis_geometry"] = mapping(polygon)
    else:
        polygons.loc[polygons.paddock_id.eq(meta["paddock_id"]), "geometry"] = polygon
    return polygons, metrics
