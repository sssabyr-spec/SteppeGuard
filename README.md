# SteppeGuard

**Climate-smart pasture management · Akkum, Kazakhstan**

A small, working Streamlit decision-support prototype for an MIT Solve 2027 application and demo video. It compares a supplied 2026 grazing-plan scenario with vegetation and climate indicators, then explains when planned grazing should be adapted. This is not a production system or an MIT endorsement.

**v0.2 real data are loaded:** Sentinel-2 L2A from Microsoft Planetary Computer and ERA5 precipitation, temperature and surface soil moisture for a **5 km buffer around 44.916664, 64.712612**. The active window is **1–30 September 2026**, with the same calendar period in 2021–2025 as reference. NDVI **0.3343**, vegetation anomaly **−0.2%**, precipitation **0.8 mm**, rainfall anomaly **−64.6%**, climate stress **34/100**. See [methods, provenance and validation](docs/V02_REAL_DATA.md).

The UI layout and scoring engine are retained. Four schedules use one shared pilot-zone signal; the displayed map sectors are illustrative until the official plan map is georeferenced. Environmental inputs are real satellite/reanalysis values. Water access is not assessed. No credentials are required to run the delivered app.

**Observed Historical Replay is now loaded:** 38 of 52 monthly windows were evaluable across 2021–2026; 13 overlap grazing rules with moderate stress. The strongest case is **2–31 October 2025**, score **54/100**: NDVI anomaly **−15.3%**, precipitation anomaly **−95.7%**, temperature anomaly **+0.9°C**, soil moisture Normal. The autumn rule says GRAZE; SteppeGuard says **MONITOR / REDUCE PRESSURE**. No evaluated window reached HIGH stress. See the [case, coverage gaps and reproduction method](docs/OBSERVED_HISTORICAL_CASE.md). This retrospective comparison does not establish actual past grazing or predictive skill.

## Pilot and demonstration

Akkum Rural District, Zhalagash District, Kyzylorda Region, Kazakhstan.

The bundled demo uses a **1 July 2026** assessment, independent of today's date. Imported rows use their own assessment date. With no observed bundle, four paddocks demonstrate the complete decision flow:

| Paddock | Supplied 2026 plan | Demo score | July decision |
|---|---|---:|---|
| Paddock 1 | Rest | 15 · Low | Keep resting |
| Paddock 2 | Spring–summer grazing | 76 · High | Delay grazing |
| Paddock 3 | Summer grazing | 22 · Low | Suitable for planned grazing |
| Paddock 4 | Autumn grazing | 46 · Moderate | Continue planned rest |

Select a paddock to update its map highlight, metrics and explanation. Hover over map polygons for summaries. The comparison table highlights adapted decisions. Download the assessment with data provenance. The Observed Historical Replay tab lets you inspect evaluated monthly observations and download all intervals, including unscored gaps; About the pilot explains the concept and future integrations.

## Local setup

Use Python **3.12** (tested). From this repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Open http://localhost:8501. No credentials, Google Earth Engine authentication, API keys, database, or basemap service are needed. The Folium map deliberately uses a schematic geographic view; all polygons and chart inputs load from local files. Package installation and the map's Leaflet JavaScript/CSS assets require internet access. No environmental data is fetched remotely.

Run the checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover dataset joins and consistency, score limits and thresholds, rest precedence, seasonal rules, replay deterioration, all tabs, all paddock selections and all replay positions using Streamlit AppTest.

## Data provenance — DEMO DATA

**The original fallback environmental files are synthetic.** The active bundle under `data/observed` overrides all dashboard NDVI, precipitation, temperature and soil-moisture inputs with shared pilot-zone observations/reanalysis. `data/historical` replaces the synthetic replay with an observed case. The fallback files remain for regression tests and legacy mode only when observation bundles are absent. The [official plan](https://old.adilet.zan.kz/kaz/docs/G24LF02818M) is linked; its map has not been georeferenced.

- `data/pastures.geojson`: four **temporary demo geometries**, placed in an approximate pilot-region setting. They are not official boundaries and do not establish actual Akkum paddock locations or areas. Replace them with digitized official Akkum pasture polygons. A GeoJSON foreign member named `_comment` documents this; JSON syntax does not support comments.
- `data/pasture_metrics.csv`: snapshot at 1 July 2026. NDVI is unitless, its baseline is a synthetic seasonal expectation, and vegetation anomaly is `(current / baseline - 1) × 100`. Rainfall anomaly represents an illustrative trailing 30-day period relative to normal. Soil moisture is a categorical proxy; temperature anomaly is in °C. No real climatological reference period is defined.
- `data/climate_history.csv`: four synthetic Paddock 2 observations from 1 June to 15 July 2026. Later points intentionally extend beyond the dashboard date to illustrate a replay, not a forecast. They do not demonstrate validated warning lead time.

## Transparent scoring and rules

No machine learning and no LLM. See `src/scoring.py`:

```text
vegetation = clip(-vegetation_anomaly_pct / 35 × 100, 0, 100)
rainfall   = clip(-rainfall_anomaly_pct / 50 × 100, 0, 100)
soil       = Normal: 0; Slightly below normal: 40; Below normal: 100
heat       = clip(temperature_anomaly_c / 4 × 100, 0, 100)
soil_heat  = (soil + heat) / 2
score      = round_half_up(0.50 × vegetation + 0.30 × rainfall + 0.20 × soil_heat)
```

The final integer score drives both displayed categories and decisions: **0–30 Low**, **31–60 Moderate**, **61–100 High**. Favorable anomalies cannot yield negative stress; extreme adverse anomalies cannot exceed 100. These normalizations and thresholds are illustrative and require local agronomic calibration.

Rest overrides grazing recommendations. For demonstration only, spring–summer means March–August, summer June–August, and autumn September–November. Outside its grazing window, a paddock continues planned rest. During planned grazing, Low means suitable, Moderate means monitor/reduce pressure, and High means delay and reassess in 14 days. Reassessment dates are suggestions, not scheduled notifications. Water access is displayed as context and is not part of scoring. Stress counters include resting paddocks; only year-round Rest is colored gray, while seasonal paddocks retain their stress color.

## Repository

```text
SteppeGuard/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/config.toml
├── data/
│   ├── pastures.geojson
│   ├── pasture_metrics.csv
│   └── climate_history.csv
├── requirements-data.txt
├── docs/OBSERVED_DATA.md
├── docs/V02_REAL_DATA.md
├── scripts/
│   ├── __init__.py
│   ├── fetch_observations.py
│   └── fetch_pilot.py
├── src/
│   ├── __init__.py
│   ├── data_loader.py
│   ├── scoring.py
│   ├── observations.py
│   └── recommendations.py
└── tests/
    ├── test_core.py
    ├── test_app.py
    ├── test_observations.py
    ├── test_acquisition.py
    └── test_real_pilot.py
```

## Streamlit Community Cloud

Follow the [exact GitHub upload and deployment steps](docs/GITHUB_DEPLOYMENT.md), including PowerShell commands and deployment settings.

Deploy `app.py` from branch `main`, using **Python 3.12** and `requirements.txt`. No secrets or new observation downloads are needed. Include **all files in `data/observed` and `data/historical`**; the app checks their hashes. `.gitattributes` protects data line endings and `.gitignore` excludes acquisition caches and local files. GitHub hosts the repository; Streamlit Community Cloud provides the shareable running demo, not GitHub Pages.

This repository is prepared for deployment, but no GitHub repository or public deployment is created by the implementation itself.

## Demo video walkthrough

1. Open the default **Observed case study** tab: **Observed Historical Case Study — October 2025**, score 54/100 MODERATE.
2. Show the seasonal rule GRAZE beside **REDUCE GRAZING PRESSURE AND MONITOR**, supported by the displayed observations.
3. Explore other observed dates; open **Methodology and details** for screening coverage and limitations.
4. Open the secondary **September 2026 assessment**, score 34/100. All four schedules share the same 5 km environmental signal until official paddock boundaries are georeferenced.
5. Show that Paddock 1 stays resting; finish on About the pilot. Do not claim predictive accuracy, actual historical grazing decisions or avoided losses.

## Limitations and next five improvements

This is an English-language demonstration with four paddock schedules and one observed pilot-zone signal. Acquisition is manual, not a live feed. It has no user accounts, persistent UI edits, livestock optimization, field validation or production infrastructure. Selection uses the dropdown; map hover provides summaries. Seasonal windows and score thresholds are assumptions. Historical references exclude the assessed year but can include later years; results are retrospective, not evidence of predictive performance.

1. Digitize and verify official Akkum boundaries and dated grazing-plan windows with local authorities.
2. Extend Sentinel-2 validation and coverage to verified individual paddocks.
3. Validate surface soil-moisture reanalysis against local conditions and extend the climate reference period.
4. Validate thresholds and warning lead time with pastoralists, agronomists and independent field observations.
5. Incorporate livestock demand, carrying capacity and verified watering points into practical grazing alternatives.

Sentinel-2 and ERA5 acquisition is complete for the supplied Akkum coordinates. Paddock-specific measurements await georeferencing of the official plan map. See [v0.2 limitations and provenance](docs/V02_REAL_DATA.md).

> This prototype is a decision-support demonstration and should not yet be used for operational livestock or land-management decisions.
