# SteppeGuard v0.2 — delivered real-data pilot

## Active analysis

- Center: **44.916664 N, 64.712612 E**, Akkum village, Akkum Rural District, Zhalagash District, Kyzylorda Region, Kazakhstan.
- Geometry: **5,000 m radius**, constructed in a local azimuthal-equidistant projection and transformed to WGS84. Approximately 78.5 km². This is an **approximate analysis zone**, not an administrative boundary or official pasture boundary.
- Current assessment: **1–30 September 2026**, inclusive. “Current” means this dated snapshot; the app is not a live feed.
- Seasonal reference: the same calendar dates in **2021–2025**. Five-year reference, not a 30-year climate normal.
- Satellite source: Copernicus Sentinel-2 L2A via [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a).
- Climate source: [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api), explicitly selecting **ECMWF ERA5** for precipitation, temperature and 0–7 cm soil moisture. The returned climate grid location is **45.0 N, 64.75 E**. These are reanalysis estimates, not direct local weather-station measurements or a polygon average.

| Indicator | Current window | Historical reference | Anomaly |
|---|---:|---:|---:|
| NDVI | 0.3343 | 0.3350 | −0.2% |
| Total precipitation | 0.80 mm | 2.26 mm | −64.6% |
| Mean temperature | 19.87 °C | 18.43 °C | +1.44 °C |
| Surface soil moisture | 0.2856 m³/m³ | 0.2730 m³/m³ | +4.6% |

The unchanged scoring engine produces **34/100, MODERATE**. Soil moisture maps to **Normal**. The rainfall anomaly is large relative to a low reference total; both absolute totals are displayed to retain context. NDVI shows little change, so these data do not establish a large vegetation decline.

## Sentinel-2 processing

1. Search the public Planetary Computer STAC collection `sentinel-2-l2a` for each September window. Require whole-scene cloud cover below 60% and a tile footprint covering the entire zone.
2. Select one fully covering tile per acquisition date, preferring the lowest scene cloud fraction. Dates rejected by local quality checks are retained in the audit record.
3. Access public assets using temporary SAS signatures from `planetary-computer`; no user account is required. Signed URLs are not saved in the delivered records.
4. Read **BOA_QUANTIFICATION_VALUE** and **BOA_ADD_OFFSET** from each product's ESA XML metadata. Apply offsets before NDVI; no fixed post-2022 adjustment is assumed. Raw XML and pixel arrays are retained in the ignored acquisition cache for local audit/re-runs.
5. Align red B04 and NIR B08 to a common **20 m EPSG:32641** grid using average resampling. Align scene classification (SCL) using nearest-neighbor sampling.
6. Retain SCL 4/5 (vegetation/bare soil), removing clouds, shadows, snow, water, unclassified and nodata pixels. Reject negative reflectances or nonpositive denominators. Calculate `(NIR − red) / (NIR + red)` per valid pixel.
7. Accept only scenes with at least 70% valid land coverage of the zone. Form a **pixelwise temporal median NDVI composite**, requiring at least two clear observations per pixel.
8. Use the **same common valid pixel footprint in all six annual composites**. Calculate a zone mean from each composite. The historical baseline is the equal-weight mean of the five historical zone means. The app exposes the common valid coverage fraction and accepted scene count.

The 2026 composite uses **four accepted dates**; latest acquisition **26 September 2026**. Water and other excluded areas do not contribute. The buffer contains land around the village and is not restricted to legally designated pasture. Mixed land use and cloud-mask imperfections remain limitations.

## ERA5 and soil interpretation

Download daily precipitation totals, daily mean 2 m temperature and daily mean volumetric 0–7 cm soil moisture in `Asia/Qyzylorda`, with mm/°C/m³/m³ units. Every window must contain every calendar day. Precipitation includes rain and snowfall water equivalent; it feeds the existing `rainfall_anomaly_pct` field.

Current precipitation is the 30-day sum. Its baseline is the equal-weight mean of the five historical sums. Temperature and soil moisture use period means and equal-weight historical means. Relative anomalies are calculated for vegetation, precipitation and soil moisture; temperature uses an absolute °C difference. All displayed/exported percentages have at most one decimal, while the engine retains precision.

Soil moisture is mapped into the existing score categories using **provisional, explicit thresholds**: anomaly below −20% → Below normal; below −10% → Slightly below normal; otherwise Normal. This interpretation requires local calibration. It changes the input category, not the existing score weights or recommendation rules.

## Official plan and four-paddock display

The baseline remains:

| Paddock | 2026 official-plan baseline | Decision at 30 September 2026 |
|---|---|---|
| 1 | Rest | Keep resting |
| 2 | Spring–summer grazing | Continue planned rest |
| 3 | Summer grazing | Continue planned rest |
| 4 | Autumn grazing | Monitor / reduce pressure |

The [Adilet decision and Akkum annex](https://old.adilet.zan.kz/kaz/docs/G24LF02818M) provide the official planning reference. The exact season month ranges in the MVP remain illustrative.

Until the official plan map is georeferenced, **all four schedules use the same measured pilot-zone signal**. The four map sectors are schematic subdivisions used to preserve the existing selection workflow, not claimed paddock locations. Stress counters count schedules exposed to the same zone signal, not independent environmental samples. The dashed outline is the actual 5 km analysis buffer.

There is no global DEMO banner on the observed dashboard. A small geometry disclaimer and per-indicator provenance labels remain. Water access is **not assessed**. The separate **Observed Historical Replay** now uses the archived 2021–2026 scan and opens on October 2025 (54/100, moderate stress). See [historical methods and case](OBSERVED_HISTORICAL_CASE.md). The September 2026 dashboard is retained unchanged; retrospective replay is not validation of predictive skill.

## Delivered files and reproducibility

`data/observed/` contains:

- `manifest.json`: sources, dates, geometry hash, method, scope, retrieval timestamp and artifact checksums.
- `pilot.geojson`: full 5 km buffer.
- `ndvi_observations.csv`: accepted acquisition dates, IDs, clear fractions and per-scene NDVI summaries.
- `window_ndvi.csv`: zone means of the pixelwise median composites. These, not the medians of per-scene means, feed the v0.2 score.
- `ndvi_median_2021.tif` through `ndvi_median_2026.tif`: common-support median NDVI rasters, with CRS, grid transform and nodata.
- `climate_daily.csv`: 180 daily rows covering all six September windows.
- `source_records.json`: unsigned STAC metadata, including rejected candidate scenes.
- `climate_source_records.json`: original weather responses, grid coordinates, units and request URLs.

Run the app normally; the delivered bundle is loaded without network calls to data providers. The Folium frontend still needs its JavaScript/CSS assets.

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To reproduce acquisition, install `requirements-data.txt` and run `python -m scripts.fetch_pilot` from the repository root in the virtual environment. The script protects an existing validated bundle; preserve it before rerunning. It is deliberately a fixed v0.2 acquisition, not a scheduler. Interrupted acquisition uses `data/acquisition_cache/` and can resume; do not reuse that cache for changed coordinates, periods, grid settings or processing rules.

Tests cover the 5 km radius, identical raster support, saved-raster means, climate aggregation, retained plans, actual score/decisions, source labels, missing-data rejection and the absence of the global demo warning. The legacy one-paddock schema remains supported; [the older import guide](OBSERVED_DATA.md) describes that separate workflow.

This prototype is a decision-support demonstration and should not yet be used for operational livestock or land-management decisions.
