# Observed pilot data without a production API

> **Legacy v0.1 single-paddock import guide.** The active v0.2 bundle uses Microsoft Planetary Computer, a 5 km buffer, pixelwise median composites and ERA5 soil moisture. Real data are already delivered. See [v0.2 data and validation](V02_REAL_DATA.md); it supersedes the demo-soil, location-pending and scene-mean assumptions below for the active dashboard.

The UI and scoring/recommendation rules are retained. One optional local bundle supplies Sentinel-2 NDVI and ERA5 precipitation/temperature for one pilot polygon. The Streamlit process makes **no environmental API calls**. No account, Google Earth Engine authentication or scheduled service is required.

## Fastest acquisition

1. Provide a verified WGS84 polygon, or latitude/longitude for a **provisional approximately 1 km square**. The script has no default location and never uses a synthetic demo polygon as an actual Akkum boundary.
2. Run the downloader once. It reads small windows of public Sentinel-2 Level-2A cloud-optimized GeoTIFFs through [Earth Search](https://github.com/Element84/earth-search), and downloads daily ERA5 through [Open-Meteo Historical Weather](https://open-meteo.com/en/docs/historical-weather-api).
3. Keep the output files with the app. A normal app reload recalculates indicators from those files; no restart or API connection is required. The app reads `data/observed/manifest.json` if present.

ERA5 is **reanalysis**, combining observations and a model. It is not a direct weather-station observation at the pasture. Explicit `models=era5` avoids Open-Meteo's changing default model mixture. Precipitation includes rain and snowfall water equivalent, and feeds the existing rainfall-anomaly score field. We choose ERA5 for both temperature and precipitation to keep one consistent source; ERA5-Land is not implemented in this importer.

### Install and download

From the repository root, with the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
# Replace LATITUDE and LONGITUDE with the user's chosen coordinates:
.\.venv\Scripts\python.exe -m scripts.fetch_observations --latitude LATITUDE --longitude LONGITUDE
```

The default target is **Paddock 2**. Its geometry becomes the supplied observation area, clearly labeled provisional unless a verified polygon is supplied. The other paddocks remain synthetic. A provisional 1 km area measures that sample area only; it does not establish a real paddock's extent or represent all of Akkum.

For a user-supplied GeoJSON Feature containing one Polygon:

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_observations --polygon path\to\pilot.geojson --paddock "Paddock 2" --end 2026-07-01 --years 2019 2020 2021 2022 2023 2024 2025
```

Include `properties.geometry_source` and `properties.boundary_status` (`provisional` or `verified`) in the input. Use `verified` only with a verified boundary; absent status defaults to provisional. The MVP intentionally accepts only one Polygon, not a multipolygon or an entire FeatureCollection. Large areas and pilots crossing tile boundaries require a future mosaicking workflow.

The downloader never overwrites an existing bundle. For a new acquisition, choose `--output data/observed-new`, inspect it, then explicitly replace the app's `data/observed` directory with that validated bundle. Incomplete attempts remain in an `observations-*` staging directory for inspection and are never loaded by the app. Network errors fail the run; they are not replaced with invented values.

### Default assessment and reference

To preserve the existing demonstration's assessment, the default period is **2 June–1 July 2026 inclusive** (30 days). “Current” means this stated assessment window, not the wall-clock date. You can change it with `--end YYYY-MM-DD`; choose a date at least seven days old to allow reanalysis availability. Recommendations use each row's own assessment date. Other paddocks remain dated 1 July 2026.

Historical windows have the **same month/day boundaries** in 2019–2025. This seven-year comparison is a **short historical reference, not a 30-year climatological normal**. At least three distinct prior years are required; every declared year must have sufficient valid data. A window containing February 29 that cannot be mapped to all requested years is rejected rather than silently shifted.

## NDVI calculations and quality

- Source: Earth Search v1 `sentinel-2-l2a`, red B04 and NIR B08, 10 m. Every selected tile must cover the whole polygon; partial tiles are excluded. No mosaicking or interpolation is attempted.
- Apply each asset's explicit `raster:bands` scale and offset **before** computing NDVI. Missing metadata fails the run. This handles processing-baseline offsets across dates; see [Earth Search's offset notes](https://github.com/Element84/earth-search/blob/main/docs/collections/sentinel-2-l2a.md#gainoffset-in-items-after-jan-25-2022).
- Align NIR and SCL to the red-band grid. SCL uses nearest-neighbor resampling. Retain only SCL 4 (vegetation) and 5 (bare soil); exclude clouds, shadows, snow, water, unclassified and nodata. Also reject negative reflectances and nonpositive NDVI denominators.
- Pixel NDVI = `(NIR - red) / (NIR + red)`. Scene NDVI is its mean over valid pixel centers inside the polygon. Coverage is valid pixels divided by all polygon pixel centers. Require at least **70%** valid coverage per accepted scene.
- For overlapping scenes on the same date, select the one with best valid coverage. Require at least two distinct accepted dates in each current/reference window. The current NDVI is the median of those per-date means. Each historical year contributes one such median; the seasonal baseline is their equal-weight mean.
- Vegetation anomaly = `(current NDVI / seasonal baseline - 1) × 100`, computed automatically. NDVI baseline ≤0.05 is rejected because relative anomalies become unstable.

This simple SCL mask is not perfect. Cloud-edge contamination, varying valid footprints, remaining atmospheric/processing differences, mixed land use and a short baseline limit interpretation. Source scene IDs and full STAC metadata are retained for audit. There is no claim that one provisional sample represents the whole district.

## Climate calculations and quality

The downloader queries the polygon centroid in `Asia/Qyzylorda`, with explicit millimeters and Celsius units. Open-Meteo returns a grid estimate; the returned grid coordinates and request URL are preserved in the raw response. ERA5's grid is much coarser than the pilot, about 0.25°, and is **not a polygon zonal mean**.

- Current precipitation: sum of every daily precipitation value in the period.
- Historical precipitation: equal-weight mean of historical period sums.
- Precipitation anomaly: `(current sum / reference sum - 1) × 100`.
- Current temperature: mean of all daily mean temperatures in the period.
- Historical temperature: equal-weight mean of historical period means.
- Temperature anomaly: current period mean minus historical reference mean, in °C.
- Require complete dates, no duplicates, no null/nonfinite values and nonnegative precipitation. Reference precipitation ≤0.1 mm is rejected rather than producing an extreme percentage.

Percentages are displayed/exported to at most one decimal place. Internal calculations retain precision so rounding does not change the scoring thresholds.

## Local import contract

The downloader produces this folder; externally prepared exports can use the same contract:

```text
data/observed/
  manifest.json
  pilot.geojson
  ndvi_observations.csv
  climate_daily.csv
  source_records.json
  aggregation.json
```

`ndvi_observations.csv` columns:

```text
date,ndvi,valid_fraction,scene_id,polygon_sha256
```

`climate_daily.csv` columns:

```text
date,precipitation_mm,temperature_mean_c,polygon_sha256
```

Dates are ISO `YYYY-MM-DD`; fractions are 0–1. The polygon hash must be generated by `src.observations.geometry_hash` from the GeoJSON geometry object. All current and historical rows must refer to this identical geometry. External NDVI exports must follow the documented radiometric and masking method; a CSV alone cannot prove that upstream processing was correct.

Required manifest fields: `schema_version: 1`, `paddock_id`, `period_start`, `period_end`, `baseline_years` (integer array), `polygon_sha256`, `boundary_status`, `geometry_source`, `retrieved_at`, `ndvi_source`, `ndvi_collection: "sentinel-2-l2a"`, `climate_source`, `climate_model: "era5"`. See the downloader's manifest construction for a complete example without invented environmental values.

`source_records.json` retains full provider replies and scene metadata, including rejected scenes. `aggregation.json` is an audit summary; the app recomputes indicators from the CSVs rather than trusting precomputed anomalies. The importer checks structure, coverage and consistency, but cannot authenticate a manually edited file's scientific provenance.

## Mixed data and existing engine

The score formula and recommendation thresholds are unchanged. Only current NDVI, baseline NDVI, vegetation anomaly, rainfall anomaly and temperature anomaly are replaced for the imported paddock. Soil moisture remains the existing **DEMO category**, so the resulting score is explicitly labeled **PARTLY OBSERVED**, not fully observed. Official plan labels and water access also remain the supplied demo scenario.

Per-indicator source labels, assessment date, baseline years, last Sentinel acquisition, acquisition count, polygon status and retrieval time appear without changing the page layout. The comparison table and CSV preserve mixed-data provenance. Drought Replay remains the original synthetic scenario; it does not claim to be an observed historical replay.

Without a manifest the application explicitly stays in demo mode. An invalid manifest or incomplete observation bundle stops the assessment with an error; it never silently substitutes demo values for a failed real import. After a successful import, the UI continues working offline except for Folium's JavaScript/CSS assets.

## Attribution and use

- Sentinel-2: Copernicus Sentinel data, accessed via Element 84 Earth Search / AWS public COGs.
- Climate: ECMWF ERA5 reanalysis, supplied through Open-Meteo; retain [Open-Meteo attribution and usage terms](https://open-meteo.com/en/terms). Check the service's terms before commercial or large-scale use; this script is for a small prototype acquisition.

This prototype is a decision-support demonstration and should not yet be used for operational livestock or land-management decisions.
