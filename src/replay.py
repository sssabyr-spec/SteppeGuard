"""Observed replay using the existing Streamlit metrics, chart and table layout."""
from datetime import date
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.historical import PLANS
from src.recommendations import recommend


def render_observed_replay(meta, rows):
    selected = meta.get("selected_date")
    case_month = date.fromisoformat(selected).strftime("%B %Y") if selected else None
    st.subheader(f"Observed Historical Case Study — {case_month}" if selected else "Historical evaluation")
    st.caption("Observed satellite data · Sentinel-2 L2A · ERA5 reanalysis data · Approximate analysis zone: Akkum 5 km buffer.")
    st.caption("Observed conditions compared with the 2026-style seasonal rules. This does not establish predictive accuracy, actual historical grazing decisions or avoided losses.")
    if selected:
        strongest = rows.loc[rows.assessment_date.eq(selected)].iloc[0]
        st.write("**When should planned grazing be adapted?**")
        a, b, c = st.columns(3)
        a.metric("NDVI anomaly", f"{strongest.vegetation_anomaly_pct:+.1f}%")
        b.metric("30-day precipitation", f"{strongest.precipitation_mm:.1f} mm")
        c.metric("Historical precipitation reference", f"{strongest.baseline_precipitation_mm:.1f} mm")
        a, b, c = st.columns(3)
        a.metric("Rainfall anomaly", f"{strongest.rainfall_anomaly_pct:+.1f}%")
        b.metric("Temperature anomaly", f"{strongest.temperature_anomaly_c:+.1f} °C")
        c.metric("Climate stress", f"{int(strongest.stress_score)}/100", strongest.stress_level, delta_color="off")
        for paddock, plan in PLANS.items():
            case_decision = recommend({**strongest.to_dict(), "official_plan": plan}, date.fromisoformat(selected))
            if case_decision["plan_now"] == "Graze":
                wording = "REDUCE GRAZING PRESSURE AND MONITOR" if case_decision["decision"] == "MONITOR / REDUCE PRESSURE" else case_decision["decision"]
                st.info(f"**{paddock} · Official seasonal rule: GRAZE**\n\n**SteppeGuard recommendation: {wording}**")
        st.caption(f"Observed window: {strongest.period_start} to {selected}. Historical reference: same calendar period in {strongest.baseline_years}.")
        st.subheader("Explore observed history")
        options = rows.loc[rows.status.eq("evaluated"), "assessment_date"].tolist()
        replay_date = st.select_slider("Replay through", options=options, value=selected)
        point = rows.loc[rows.assessment_date.eq(replay_date)].iloc[0]
        a, b, c = st.columns(3)
        a.metric("Observed NDVI", f"{point.current_ndvi:.3f}", f"{point.vegetation_anomaly_pct:+.1f}% vs seasonal baseline", delta_color="off")
        b.metric("Climate stress", f"{int(point.stress_score)} / 100", point.stress_level, delta_color="off")
        c.metric("Rainfall anomaly", f"{point.rainfall_anomaly_pct:+.1f}%")
        st.caption(f"Selected window: {point.period_start} to {point.assessment_date}.")
        season = rows.loc[rows.year.eq(point.year)].copy()
        shown = season.loc[season.assessment_date.le(replay_date)].copy()
        shown.loc[shown.status.ne("evaluated"), ["current_ndvi", "seasonal_ndvi"]] = float("nan")
        chart = go.Figure()
        for column, label, color, dash in [("seasonal_ndvi", "Seasonal baseline (observed)", "#9ba897", "dash"),
                                           ("current_ndvi", "NDVI (Sentinel-2)", "#22634a", "solid")]:
            chart.add_trace(go.Scatter(x=shown.assessment_date, y=shown[column], name=label, mode="lines+markers",
                                      connectgaps=False, line=dict(color=color, dash=dash, width=2 if dash == "dash" else 3)))
        chart.update_layout(height=360, margin=dict(l=10, r=20, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.15), yaxis=dict(title="NDVI"),
                            xaxis=dict(title=None, range=[season.assessment_date.min(), season.assessment_date.max()]))
        st.plotly_chart(chart, width="stretch")
        st.caption("Chart shows the selected year up to the slider date. Missing or unscored windows remain gaps; monthly reference footprints can differ.")
        decisions = []
        for paddock, plan in PLANS.items():
            result = recommend({**point.to_dict(), "official_plan": plan}, date.fromisoformat(replay_date))
            decisions.append({"Paddock": paddock, "2026-style rule": plan, "Official Plan": result["plan_now"].upper(),
                              "Observed Climate Stress": point.stress_level, "SteppeGuard": "REDUCE GRAZING PRESSURE AND MONITOR" if result["decision"] == "MONITOR / REDUCE PRESSURE" else result["decision"]})
        for result in decisions:
            if result["Official Plan"] == "GRAZE":
                st.info(f"**{result['Paddock']} · Official Plan = GRAZE · Observed Climate Stress = {point.stress_level} · SteppeGuard = {result['SteppeGuard']}**")
        st.dataframe(pd.DataFrame(decisions), hide_index=True, width="stretch")
        facts = [
            ("NDVI", f"{point.current_ndvi:.3f}", f"{point.seasonal_ndvi:.3f}", f"{point.vegetation_anomaly_pct:+.1f}%", "Sentinel-2 L2A"),
            ("30-day precipitation", f"{point.precipitation_mm:.1f} mm", f"{point.baseline_precipitation_mm:.1f} mm", f"{point.rainfall_anomaly_pct:+.1f}%", "ERA5 reanalysis"),
            ("Mean temperature", f"{point.temperature_mean_c:.1f} °C", f"{point.baseline_temperature_c:.1f} °C", f"{point.temperature_anomaly_c:+.1f} °C", "ERA5 reanalysis"),
            ("Soil moisture (0–7 cm)", f"{point.soil_moisture_m3m3:.3f} m³/m³", f"{point.baseline_soil_moisture_m3m3:.3f} m³/m³", f"{point.soil_moisture_anomaly_pct:+.1f}% · {point.soil_moisture_status}", "ERA5 reanalysis")]
        st.dataframe(pd.DataFrame(facts, columns=["Indicator", "Observed / reanalysis", "Seasonal baseline", "Anomaly / status", "Source"]), hide_index=True, width="stretch")
    else:
        st.info("No meaningful observed grazing conflict was found in the evaluable 2021–2026 windows. No synthetic case is substituted. Gaps remain unassessed.")
    with st.expander("Methodology and details"):
        st.write(f"{meta['evaluated_windows']} of {meta['requested_windows']} monthly windows evaluated; {meta['conflict_windows']} overlap planned grazing with moderate or high stress. Screening: March–November 2021–2025 and March–September 2026.")
        st.write("The highlighted case has the highest unchanged score among evaluable monthly grazing windows; earliest date breaks ties. References exclude the assessed year but can include later years. October–November 2026 were incomplete at acquisition and are excluded.")
        if selected:
            st.write(f"Selected replay window: {point.period_start} to {point.assessment_date} · Reference years: {point.baseline_years} · {int(point.scene_count)} accepted satellite dates · Shared valid land footprint: {point.common_valid_fraction:.1%} of buffer.")
        st.write("Trailing 30-day month-end windows. Scene cloud cover below 60%; SCL vegetation/bare-land mask, at least 70% clear land coverage per accepted scene. Pixelwise median with at least two clear dates per pixel. Same-calendar comparisons share a common land footprint of at least 70% and require at least three other years. Baselines are equal-weight means of available annual windows, not 30-year normals.")
        st.write("ERA5 precipitation includes rain and snow; the existing rainfall score uses its anomaly. Climate is a coarse centroid grid estimate. Soil status uses the unchanged anomaly thresholds: below −20% = Below normal, below −10% = Slightly below normal, otherwise Normal. Score weights and seasonal recommendation rules are unchanged.")
        st.write("Coverage gaps: " + "; ".join(f"{status.replace('_', ' ')}: {count}" for status, count in rows.loc[rows.status.ne("evaluated"), "status"].value_counts().items()))
        display = rows[["assessment_date", "status", "current_ndvi", "seasonal_ndvi", "vegetation_anomaly_pct", "rainfall_anomaly_pct", "temperature_anomaly_c", "soil_moisture_status", "stress_score", "stress_level", "grazing_paddocks"]].copy()
        st.dataframe(display.round({"current_ndvi": 3, "seasonal_ndvi": 3, "vegetation_anomaly_pct": 1, "rainfall_anomaly_pct": 1, "temperature_anomaly_c": 1}), hide_index=True, width="stretch")
        st.caption(f"Retrieved: {meta['retrieved_at']} · Geometry SHA-256: {meta['polygon_sha256']}. Source records, selected-case composites and artifact checksums are archived locally in data/historical.")
        st.markdown("[Sentinel-2 source](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a) · [ERA5 source](https://open-meteo.com/en/docs/historical-weather-api) · [Official Akkum plan](https://old.adilet.zan.kz/kaz/docs/G24LF02818M)")
    export = rows.copy()
    for column in export.columns:
        if column.endswith("_pct"):
            export[column] = export[column].round(1)
    st.download_button("Download historical evaluation · CSV", export.to_csv(index=False).encode("utf-8-sig"), "steppeguard_historical_evaluation.csv", "text/csv")
    st.caption("The September 2026 assessment remains available in its separate tab as a reference. This retrospective case does not validate ecological outcomes or predictive performance.")
