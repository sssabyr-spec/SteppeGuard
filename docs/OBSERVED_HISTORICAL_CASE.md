# Observed historical case: Akkum, October 2025

The historical scan identifies **2–31 October 2025** as the strongest stress period among the evaluated monthly grazing windows. It supports **MODERATE stress and MONITOR / REDUCE PRESSURE**, not a high-stress delay recommendation. No environmental values or scoring thresholds were altered to create a conflict.

| Indicator | Observed / reanalysis | Seasonal reference | Anomaly |
|---|---:|---:|---:|
| Sentinel-2 NDVI | 0.2245 | 0.2650 | −15.3% |
| 30-day precipitation | 0.4 mm | 9.3 mm | −95.7% |
| Mean temperature | 10.9°C | 10.1°C | +0.9°C |
| ERA5 soil moisture, 0–7 cm | 0.272 m³/m³ | 0.260 m³/m³ | +4.6%, Normal |
| Climate Stress Score | **54/100 · MODERATE** | | |

Reference: **2–31 October in 2021, 2022, 2023 and 2024**, excluding the assessed year. Four accepted Sentinel-2 dates contribute to October 2025. Comparisons use the same valid land footprint, covering **84.6%** of the 5 km buffer.

Under the retained **2026-style** rules, Paddock 4 is scheduled for autumn grazing: **Official Plan = GRAZE → Observed Climate Stress = MODERATE → SteppeGuard = MONITOR / REDUCE PRESSURE**. Paddock 1 stays resting; Paddocks 2 and 3 are outside their grazing seasons. This is a retrospective application of the supplied schedule, not a claim that these paddocks actually followed that rotation in 2025.

## Search coverage and selection

- 52 trailing 30-day windows ending at month-end: March–November 2021–2025 and March–September 2026. October and November 2026 are incomplete as of the acquisition date, 10 October 2026.
- **38 evaluated**, including **13 moderate-stress windows** overlapping a grazing rule. No evaluated window reached HIGH stress under the unchanged engine.
- 14 unscored: 5 with insufficient accepted satellite dates, 1 with insufficient composite coverage, 6 with insufficient common spatial coverage, and 2 without at least three reference years. Unscored windows are not evidence of low stress.
- Selection uses the highest existing integer stress score among evaluated grazing windows; the earliest date breaks ties. This identifies the strongest *sampled, evaluable monthly* case, not a daily extreme or a complete history of drought.

The complete interval table is available in the replay and its CSV download, including unscored rows and reasons. The slider includes only evaluated windows; chart gaps retain missing intervals. The September 2026 Pasture dashboard and its original reference bundle remain available, with score **34/100**.

## Methods and provenance

The analysis zone is a 5 km geodesic-style buffer constructed in a local azimuthal equidistant projection around **44.916664, 64.712612**. It includes the village surroundings and is not a verified pasture-only mask. Illustrative paddock sectors are not official boundaries. Every seasonal rule receives the same zone-level environmental signal.

Satellite search uses the public [Microsoft Planetary Computer STAC API](https://planetarycomputer.microsoft.com/api/stac/v1/search), collection `sentinel-2-l2a`. One full-zone scene per acquisition date is selected by lowest tile cloud cover below 60%. Red B04 and NIR B08 are converted using product quantification and radiometric offsets. Extraction uses the existing 20 m UTM grid. SCL vegetation and bare-land classes (4/5) exclude clouds, shadows, snow, water and other classes. A scene requires at least 70% valid buffer coverage. Each monthly composite is a pixelwise temporal median requiring at least two valid dates per pixel; composites and the shared same-month footprint also require at least 70% coverage. Reference and assessed means use that identical monthly footprint. Different calendar months may have different footprints.

Climate uses the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) with explicit `models=era5`, timezone `Asia/Qyzylorda`: daily precipitation total, mean 2 m temperature and mean 0–7 cm soil moisture. The returned centroid grid is approximately 45.0°N, 64.75°E. This is coarse reanalysis, not local station measurement. Precipitation includes rain and snow. Each evaluated climate window must contain every daily record with finite values.

For each calendar month, baseline values are equal-weight means of at least three other available years; the assessed year is always excluded. NDVI, precipitation and soil anomalies are `(current / reference − 1) × 100`; temperature anomaly is a difference. Baselines too close to zero are not scored. References are short seasonal comparisons, not 30-year climatological normals. All display/export percentages have at most one decimal; archived calculation inputs retain full precision to reproduce scores.

Soil status uses the existing thresholds: below −20% = Below normal; below −10% = Slightly below normal; otherwise Normal. `src/scoring.py` and `src/recommendations.py` remain unchanged. Score components for the selected case are vegetation 43.6, rainfall 100, soil/heat 10.9, giving a rounded weighted score of 54.

This is **retrospective evaluation**, not a predictive hindcast: some evaluated years use later years in their references, and the strongest case is selected after scanning the period. It does not validate warning lead time, actual livestock pressure, carrying capacity or ecological outcomes. The exact month assignments remain prototype assumptions applied to the [official Akkum plan](https://old.adilet.zan.kz/kaz/docs/G24LF02818M).

## Reproduce and audit

Run the app without provider credentials or network data calls:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open **Observed Historical Replay**. The strongest supported case is the default slider position. **Pasture dashboard** remains September 2026.

The delivered `data/historical/` contains a checksum manifest, all 52 interval results, daily climate values, raw climate responses, Sentinel-2 scene metadata with acceptance decisions, and five October case/reference GeoTIFF composites. The Streamlit loader checks artifact integrity. Invalid historical evidence produces an error in its tab without replacing it with synthetic evidence or disabling the current dashboard.

To repeat acquisition, install `requirements-data.txt`, then run:

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate_history
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On this workspace the shared acquisition cache is already populated; the historical command reuses it and `data/history_cache/`. On a fresh checkout it initializes the scene cache and retrieves the required data. Both caches are excluded from version control. The historical command writes only its historical output and acquisition caches; the delivered `data/observed` current bundle remains unchanged. Network failures are recorded as gaps and retried on a subsequent history run. Streamlit itself only reads the archived bundles.

Tests reproduce all interval calculations from archived records, verify reference exclusion and order independence, check raster means and common masks, exercise absent/invalid/no-conflict histories, and retain the current September metrics and recommendations.
