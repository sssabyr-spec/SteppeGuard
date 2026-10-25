"""Transparent heuristic, NOT an agronomically validated model.

Original bundled inputs are DEMO DATA. Optional imports supply Sentinel-2
vegetation and ERA5 climate anomalies; the same formula applies to both.
The v0.2 pilot also supplies a soil category derived from ERA5 reanalysis;
legacy demo/partial bundles retain their explicit per-indicator labels.
Vegetation: 0% to -35% anomaly maps linearly to 0–100 stress.
Rainfall: 0% to -50% anomaly maps linearly to 0–100 stress.
Soil: Normal=0, Slightly below normal=40, Below normal=100.
Heat: 0 to +4 °C maps linearly to 0–100 stress.
Combined soil/heat stress = their arithmetic mean.
Final score = 50% vegetation + 30% rainfall + 20% soil/heat.
Every component is clipped to [0,100]. Positive vegetation/rainfall
anomalies and negative temperature anomalies add no stress.
The final integer (rounded half up) is used consistently for decisions:
0–30 LOW, 31–60 MODERATE, 61–100 HIGH. Thresholds are illustrative.
"""
import math

SOIL_STRESS = {"Normal": 0, "Slightly below normal": 40, "Below normal": 100}


def clip(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Stress inputs must be finite numbers.")
    return max(0.0, min(100.0, value))


def calculate_stress(metrics):
    vegetation = clip(-float(metrics["vegetation_anomaly_pct"]) / 35 * 100)
    rainfall = clip(-float(metrics["rainfall_anomaly_pct"]) / 50 * 100)
    soil = SOIL_STRESS[metrics["soil_moisture_status"]]
    heat = clip(float(metrics["temperature_anomaly_c"]) / 4 * 100)
    moisture_heat = (soil + heat) / 2
    score = int(math.floor(0.5 * vegetation + 0.3 * rainfall + 0.2 * moisture_heat + 0.5))
    return {"stress_score": score, "stress_level": stress_level(score),
            "vegetation_stress": vegetation, "rainfall_stress": rainfall,
            "moisture_heat_stress": moisture_heat}


def stress_level(score):
    if not 0 <= score <= 100:
        raise ValueError("Score must be between 0 and 100.")
    return "LOW" if score <= 30 else "MODERATE" if score <= 60 else "HIGH"
