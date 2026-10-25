"""Observed retrospective evaluation; unchanged scoring and seasonal rules."""
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from src.scoring import calculate_stress
from src.recommendations import recommend

PLANS = {"Paddock 1": "Rest", "Paddock 2": "Spring–summer grazing", "Paddock 3": "Summer grazing", "Paddock 4": "Autumn grazing"}


def evaluate_windows(records, climate):
    climate = climate.copy()
    climate["date"] = pd.to_datetime(climate.date)
    if climate.date.duplicated().any():
        raise ValueError("Duplicate climate dates")
    rows = []
    for record in records:
        r = {k: v for k, v in record.items() if k != "scene_records"}
        r.update(conflict=False, baseline_years="", grazing_paddocks="")
        daily = climate.loc[climate.date.between(r["period_start"], r["assessment_date"])]
        cols = ["precipitation_mm", "temperature_mean_c", "soil_moisture_m3m3"]
        if (set(daily.date) != set(pd.date_range(r["period_start"], r["assessment_date"])) or
                not np.isfinite(daily[cols].to_numpy()).all() or (daily.precipitation_mm < 0).any() or
                not daily.soil_moisture_m3m3.between(0, 1).all()):
            r["status"] = "incomplete_climate"
        else:
            r.update(precipitation_mm=float(daily.precipitation_mm.sum()), temperature_mean_c=float(daily.temperature_mean_c.mean()),
                     soil_moisture_m3m3=float(daily.soil_moisture_m3m3.mean()))
        rows.append(r)
    available = [r for r in rows if r["status"] == "ready"]
    for r in available:
        # Baseline eligibility is fixed before scoring, never affected by loop order.
        refs = [other for other in available if other["month"] == r["month"] and other["year"] != r["year"]]
        if len(refs) < 3:
            r["status"] = "insufficient_reference_years"
            continue
        baseline = float(np.mean([other["current_ndvi"] for other in refs]))
        rain = float(np.mean([other["precipitation_mm"] for other in refs]))
        temp = float(np.mean([other["temperature_mean_c"] for other in refs]))
        soil = float(np.mean([other["soil_moisture_m3m3"] for other in refs]))
        if baseline <= 0.05 or rain <= 0.1 or soil <= 0:
            r["status"] = "unstable_reference"
            continue
        soil_anomaly = (r["soil_moisture_m3m3"] / soil - 1) * 100
        r.update(seasonal_ndvi=baseline, baseline_precipitation_mm=rain, baseline_temperature_c=temp,
                 baseline_soil_moisture_m3m3=soil, vegetation_anomaly_pct=(r["current_ndvi"] / baseline - 1) * 100,
                 rainfall_anomaly_pct=(r["precipitation_mm"] / rain - 1) * 100, temperature_anomaly_c=r["temperature_mean_c"] - temp,
                 soil_moisture_anomaly_pct=soil_anomaly,
                 soil_moisture_status="Below normal" if soil_anomaly < -20 else "Slightly below normal" if soil_anomaly < -10 else "Normal",
                 baseline_years=", ".join(str(other["year"]) for other in sorted(refs, key=lambda x: x["year"])))
        r.update(calculate_stress(r))
        grazing = []
        for paddock, plan in PLANS.items():
            decision = recommend({**r, "official_plan": plan}, date.fromisoformat(r["assessment_date"]))
            if decision["plan_now"] == "Graze":
                grazing.append(paddock)
        r.update(grazing_paddocks=", ".join(grazing), conflict=bool(grazing) and r["stress_score"] > 30, status="evaluated")
    return pd.DataFrame(rows)


def load_history(directory=None):
    directory = Path(directory) if directory else Path(__file__).resolve().parents[1] / "data/historical"
    if not (directory / "manifest.json").exists():
        return None, None
    meta = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if meta.get("schema_version") != 1 or meta.get("retrospective_only") is not True:
        raise ValueError("Unsupported historical evaluation")
    for name, digest in meta["artifact_sha256"].items():
        if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Historical artifact checksum mismatch: {name}")
    frame = pd.read_csv(directory / "evaluation.csv")
    return meta, frame
