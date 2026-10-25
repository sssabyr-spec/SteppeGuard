"""Load and validate bundled DEMO DATA; paths are independent of the caller's cwd."""
from pathlib import Path
import json
import geopandas as gpd
import pandas as pd
from .scoring import SOIL_STRESS
from .recommendations import GRAZING_MONTHS
from .observations import apply_observations

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def load_data(data_dir=DATA_DIR, include_observed=True):
    metrics = pd.read_csv(data_dir / "pasture_metrics.csv")
    # Standard JSON + GeoPandas avoids requiring a system GDAL DLL on Windows.
    with (data_dir / "pastures.geojson").open(encoding="utf-8") as file:
        geojson = json.load(file)
    # GeoJSON coordinates are WGS84 longitude/latitude. This schematic never
    # reprojects or computes areas; omit a CRS object to avoid a native PROJ
    # dependency at runtime. Assign/validate a CRS before future spatial analysis.
    pastures = gpd.GeoDataFrame.from_features(geojson["features"])
    history = pd.read_csv(data_dir / "climate_history.csv", parse_dates=["date"])
    expected = {f"Paddock {n}" for n in range(1, 5)}
    for frame in (metrics, pastures):
        if frame.paddock_id.duplicated().any() or set(frame.paddock_id) != expected:
            raise ValueError("Exactly four unique, matching paddock IDs are required.")
    if not pastures.geometry.is_valid.all() or pastures.geometry.is_empty.any():
        raise ValueError("Pasture geometries must be nonempty and valid.")
    if metrics.isna().any().any() or history.isna().any().any():
        raise ValueError("Demo datasets contain missing values.")
    for frame in (metrics, history):
        if not frame.soil_moisture_status.isin(SOIL_STRESS).all():
            raise ValueError("Unsupported soil moisture status.")
        if not frame.current_ndvi.between(-1, 1).all() or not frame.seasonal_ndvi.between(0.001, 1).all():
            raise ValueError("NDVI values or seasonal baselines are invalid.")
    if not metrics.official_plan.isin(GRAZING_MONTHS).all():
        raise ValueError("Unsupported management plan.")
    calculated = (metrics.current_ndvi / metrics.seasonal_ndvi - 1) * 100
    if ((calculated - metrics.vegetation_anomaly_pct).abs() > 0.1).any():
        raise ValueError("Vegetation anomalies disagree with NDVI values.")
    history["vegetation_anomaly_pct"] = (history.current_ndvi / history.seasonal_ndvi - 1) * 100
    if include_observed:
        pastures, metrics = apply_observations(pastures, metrics, data_dir / "observed")
    return pastures, metrics, history.sort_values("date")
