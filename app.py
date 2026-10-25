"""SteppeGuard: local observations with explicit provenance and demo fallbacks."""
from datetime import date, timedelta
import pandas as pd
import plotly.graph_objects as go
import folium
import streamlit as st
from src.data_loader import load_data
from src.scoring import calculate_stress
from src.recommendations import recommend
from src.historical import load_history
from src.replay import render_observed_replay

st.set_page_config(page_title="SteppeGuard · Akkum pilot", page_icon="🌾", layout="wide")
st.markdown("""<style>
.block-container{max-width:1440px;padding-top:4.5rem;padding-bottom:3rem}
h1{letter-spacing:-.05em;font-size:3.4rem!important} h2{letter-spacing:-.025em}
[data-testid="stMetricValue"]{font-size:2.5rem;font-weight:650}
[data-testid="stMetric"]{background:#fff;border:1px solid #dfe5da;border-radius:12px;padding:16px}
.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:700;color:#57715d;text-transform:uppercase}
.lead{font-size:21px;color:#526658;margin-top:-12px}
.score{font-size:54px;font-weight:700;line-height:1.15;letter-spacing:-.04em}
.score small{font-size:20px;font-weight:400;color:#758278}
.legend{font-size:13px;color:#53645a;margin:8px 0 16px}
.stTabs [data-baseweb="tab-list"]{gap:28px}.stTabs [data-baseweb="tab"]{font-size:16px}
</style>""", unsafe_allow_html=True)

ASSESSMENT_DATE = date(2026, 7, 1)
COLORS = {"LOW": [60, 137, 94], "MODERATE": [220, 146, 43], "HIGH": [196, 68, 54], "REST": [124, 143, 149]}


def prepared_data():
    polygons, metrics, history = load_data()
    scores = pd.DataFrame([calculate_stress(row) for _, row in metrics.iterrows()])
    metrics = pd.concat([metrics, scores], axis=1)
    decisions = pd.DataFrame([recommend(row, date.fromisoformat(row.assessment_date)) for _, row in metrics.iterrows()])
    return polygons, pd.concat([metrics, decisions], axis=1), history


try:
    polygons, metrics, history = prepared_data()
except (ValueError, OSError, KeyError) as exc:
    st.error(f"Unable to validate the local datasets: {exc}. Invalid observation bundles are not replaced silently with demo values.")
    st.stop()

left, right = st.columns([3, 1])
with left:
    st.markdown('<div class="eyebrow">Akkum Rural District · Kazakhstan</div>', unsafe_allow_html=True)
    st.title("SteppeGuard")
    st.markdown('<p class="lead">Climate-smart pasture management</p>', unsafe_allow_html=True)
with right:
    st.markdown("**Prototype · v0.2**")
    st.caption("Decision-support demonstration · v0.2")
observed_count = int(metrics.vegetation_source.ne("DEMO").sum())
fully_observed = observed_count == len(metrics) and metrics.soil_source.ne("DEMO").all()
if fully_observed:
    st.caption("Observed satellite data · ERA5 reanalysis data · Approximate analysis zone: 5 km around Akkum (44.916664, 64.712612). All four current paddock schedules use this same environmental signal until official paddock boundaries are georeferenced. Displayed sectors are illustrative, not official boundaries.")
elif observed_count:
    st.warning(f"MIXED DATA · {observed_count} pilot area uses observed Sentinel-2 NDVI and ERA5 reanalysis. Soil moisture, other paddocks and replay remain DEMO. See each assessment's date and provenance.", icon="ℹ️")
else:
    st.warning("DEMO DATA · No observed bundle loaded. Synthetic environmental values and temporary boundaries; assessment: 01 July 2026.", icon="ℹ️")

historical_error = None
try:
    historical_meta, historical_rows = load_history()
except (ValueError, OSError, KeyError) as exc:
    historical_meta, historical_rows = None, None
    historical_error = str(exc)
replay_label = "Observed Historical Replay" if historical_meta and historical_meta.get("selected_date") else "Historical evaluation" if historical_meta or historical_error else "Drought Replay"
if historical_meta and historical_meta.get("selected_date"):
    replay, dashboard, about = st.tabs(["Observed case study", "September 2026 assessment", "About the pilot"])
else:
    dashboard, replay, about = st.tabs(["Pasture dashboard", replay_label, "About the pilot"])

with dashboard:
    counters = st.columns(4)
    counters[0].metric("Total paddocks", len(metrics))
    for col, level, label in zip(counters[1:], ["HIGH", "MODERATE", "LOW"], ["High stress paddocks", "Moderate stress paddocks", "Low stress paddocks"]):
        col.metric(label, int((metrics.stress_level == level).sum()))
    st.caption("All four schedules use the same observed 5 km pilot-zone signal; these are not four independent paddock measurements. Rest remains a separate management status." if fully_observed else "Stress counts include resting paddocks. Rest is a management status, independent of climate stress.")
    st.subheader("When should planned grazing be adapted?")
    map_col, detail_col = st.columns([1.45, 1], gap="large")
    with map_col:
        selected = st.selectbox("Select a paddock to inspect", metrics.paddock_id.tolist(), index=1)
        st.caption("Use this selector to update the map highlight and detail panel. Hover over a polygon for a summary.")
        map_rows = []
        for _, geom_row in polygons.iterrows():
            row = metrics.set_index("paddock_id").loc[geom_row.paddock_id]
            # Only year-round Rest gets gray; seasonal paddocks retain stress colors.
            color = COLORS["REST" if row.official_plan == "Rest" else row.stress_level]
            center = geom_row.geometry.centroid
            map_rows.append({"name": geom_row.paddock_id, "polygon": list(geom_row.geometry.exterior.coords),
                             "color": color + [175], "line": [25, 48, 38] if geom_row.paddock_id == selected else [255, 255, 255],
                             "width": 4 if geom_row.paddock_id == selected else 1,
                             "position": [center.x, center.y], "score": int(row.stress_score),
                             "level": row.stress_level, "decision": row.decision})
        pasture_map = folium.Map(location=[45.143, 64.54], zoom_start=11, tiles=None,
                                 control_scale=True, prefer_canvas=False)
        for item in map_rows:
            fill = "#" + "".join(f"{c:02x}" for c in item["color"][:3])
            folium.Polygon(locations=[(lat, lon) for lon, lat in item["polygon"]],
                           color="#20352c" if item["name"] == selected else "#ffffff",
                           weight=item["width"], fill=True, fill_color=fill, fill_opacity=0.65,
                           tooltip=f"{item['name']} · {item['score']}/100 · {item['level']} · {item['decision']}").add_to(pasture_map)
            folium.Marker([item["position"][1], item["position"][0]],
                          icon=folium.DivIcon(icon_size=(90, 24), icon_anchor=(45, 12),
                              html=f'<div style="text-align:center;font:600 13px sans-serif;color:#182e24">{item["name"]}</div>')).add_to(pasture_map)
        if fully_observed:
            folium.GeoJson(polygons.attrs["analysis_geometry"], name="Approximate analysis zone",
                           style_function=lambda _: {"color": "#20352c", "weight": 2, "fillOpacity": 0, "dashArray": "6 4"},
                           tooltip="Akkum 5 km analysis zone · not official paddock boundaries").add_to(pasture_map)
        min_x, min_y, max_x, max_y = polygons.total_bounds
        pasture_map.fit_bounds([[min_y, min_x], [max_y, max_x]])
        st.components.v1.html(pasture_map.get_root().render(), height=420)
        st.markdown('<div class="legend">🟢 Low stress &nbsp; 🟠 Moderate &nbsp; 🔴 High &nbsp; ⚪ Rest</div>', unsafe_allow_html=True)
        st.caption("Approximate analysis zone · Dashed boundary is the 5 km buffer. Four sectors are an illustrative rotation layout, not georeferenced paddock boundaries. Every sector uses the same zone-level data." if fully_observed else "Schematic geographic view · Observed pilot areas use their imported geometry; remaining polygons are synthetic. A provisional pilot area is not an official paddock boundary." if observed_count else "Schematic geographic view · Temporary demo polygons, not official boundaries. No basemap service or API key is required.")
    row = metrics.set_index("paddock_id").loc[selected]
    with detail_col:
        with st.container(border=True):
            st.markdown(f"### {selected}")
            st.caption(f"{row.data_status} · Assessment: {row.assessment_date} · Boundary: {row.boundary_status}")
            st.caption("2026 OFFICIAL PLAN · AKKUM ROTATION SCHEDULE")
            st.write(f"**{row.official_plan}**")
            color = "#" + "".join(f"{c:02x}" for c in COLORS[row.stress_level])
            st.markdown(f'<div class="eyebrow">Climate Stress Score</div><div class="score" style="color:{color}">{row.stress_score} <small>/ 100</small></div><strong style="color:{color}">{row.stress_level}</strong>', unsafe_allow_html=True)
            if row.vegetation_source != "DEMO" and row.soil_source == "DEMO":
                st.caption("PARTLY OBSERVED SCORE · Soil moisture still uses the demo category; this is not a fully observed assessment.")
            st.divider()
            st.caption("STEPPEGUARD RECOMMENDATION")
            if row.decision == "DELAY GRAZING":
                st.error(f"**{row.decision}**\n\n{row.explanation}")
            elif row.stress_level == "MODERATE":
                st.warning(f"**{row.decision}**\n\n{row.explanation}")
            else:
                st.success(f"**{row.decision}**\n\n{row.explanation}")
        st.markdown("**Vegetation & climate**")
        facts = {"Current NDVI": f"{row.current_ndvi:.3f}", "Seasonal baseline NDVI": f"{row.seasonal_ndvi:.3f}",
                 "Vegetation anomaly": f"{row.vegetation_anomaly_pct:+.1f}%", "Rainfall anomaly": f"{row.rainfall_anomaly_pct:+.1f}%",
                 "Soil moisture": row.soil_moisture_status, "Temperature anomaly": f"{row.temperature_anomaly_c:+.1f} °C",
                 "Water access": row.water_access}
        if row.vegetation_source != "DEMO":
            facts.update({"Period precipitation": f"{row.precipitation_mm:.1f} mm", "Reference precipitation": f"{row.baseline_precipitation_mm:.1f} mm",
                          "Period mean temperature": f"{row.temperature_mean_c:.1f} °C", "Reference mean temperature": f"{row.baseline_temperature_c:.1f} °C"})
        sources = [row.vegetation_source] * 3 + [row.climate_source, row.soil_source, row.climate_source, "Not assessed" if fully_observed else "DEMO"]
        if len(facts) > 7:
            sources += [row.climate_source] * 4
        if row.soil_source != "DEMO":
            facts.update({"Soil moisture (0–7 cm)": f"{row.soil_moisture_m3m3:.3f} m³/m³",
                          "Reference soil moisture": f"{row.baseline_soil_moisture_m3m3:.3f} m³/m³",
                          "Soil moisture anomaly": f"{row.soil_moisture_anomaly_pct:+.1f}%"})
            sources += [row.soil_source] * 3
        facts_table = pd.DataFrame(facts.items(), columns=["Indicator", "Value"])
        facts_table["Source"] = sources
        st.dataframe(facts_table, hide_index=True, width="stretch")
        if row.vegetation_source != "DEMO":
            with st.expander("Observation provenance"):
                st.write(f"Window: {row.period_start} to {row.assessment_date}. Historical reference: same calendar dates in {row.baseline_years} (short reference, not a 30-year normal).")
                st.write(f"Sentinel-2: {int(row.ndvi_scene_count)} accepted dates; latest scene {row.latest_scene}. SCL cloud/shadow/snow/water masking; at least 70% valid land coverage.")
                if fully_observed:
                    st.write(f"Pixelwise median composites at 20 m, with at least two clear observations per pixel. Current and historical means use exactly the same valid land footprint ({row.common_valid_fraction:.1%} of the buffer). The baseline is the equal-weight mean of five historical composites. Water and other excluded pixels are not represented.")
                    st.write("These are shared pilot-area indicators, not measurements of the individual illustrated paddocks. The buffer includes land around the village and has not been restricted to legally designated pasture.")
                    st.write(f"Soil classification: {row.soil_status_method}")
                else:
                    st.write("Current NDVI is the median of polygon-mean scene NDVI; baseline is the equal-weight mean of historical annual medians.")
                st.write("Precipitation is the period total (rain plus snow); temperature is the daily-mean average. ERA5 is a coarse grid reanalysis at the pilot centroid, not a pasture weather-station measurement. The existing rainfall score input uses the precipitation anomaly.")
                st.write(f"Geometry: {row.geometry_source}. Downloaded: {row.retrieved_at}.")
                st.caption(f"Polygon SHA-256: {row.polygon_sha256}")
                st.markdown(f"[Sentinel-2 source]({row.ndvi_source_url}) · [Climate source]({row.climate_source_url})")
    st.subheader("Official Plan vs Climate-Adaptive Plan")
    st.write("Static pasture plans cannot anticipate unusual drought or delayed vegetation recovery. SteppeGuard uses environmental observations to identify when planned grazing should be adapted.")
    comparison = metrics[["paddock_id", "official_plan", "plan_now", "decision", "stress_score", "stress_level", "changed", "assessment_date", "data_status"]].copy()
    comparison["changed"] = comparison.changed.map({True: "ADAPTED", False: "As planned"})
    comparison.columns = ["Paddock", "Official Plan", "Plan at assessment", "SteppeGuard Decision", "Score / 100", "Stress", "Plan change", "Assessment date", "Data source"]
    def highlight_adaptation(r):
        return ["background-color: #fce9d9; color: #592d17" if r["Plan change"] == "ADAPTED" else ""] * len(r)
    st.dataframe(comparison.style.apply(highlight_adaptation, axis=1), hide_index=True, width="stretch")
    st.caption("Shaded rows change planned grazing. Season windows remain illustrative: spring–summer Mar–Aug, summer Jun–Aug, autumn Sep–Nov. Decisions use each row's assessment date and the retained 2026 official-plan baseline.")
    st.markdown("[Official Akkum pasture-management plan, 2025–2029 · Adilet](https://old.adilet.zan.kz/kaz/docs/G24LF02818M)")
    with st.expander("How the score and decisions work"):
        st.write("Score = 50% vegetation stress + 30% rainfall stress + 20% soil moisture / heat stress.")
        st.write("Vegetation reaches 100 stress at −35%; rainfall at −50%. Normal / slightly below normal / below normal soil moisture maps to 0 / 40 / 100. Heat reaches 100 at +4°C. Soil and heat are averaged. Components are capped at 0–100, then the final score is rounded to an integer.")
        st.write("0–30 LOW: planned grazing may proceed. 31–60 MODERATE: monitor / reduce pressure. 61–100 HIGH: delay grazing. Scheduled rest always takes precedence. These are illustrative thresholds, not validated agronomic limits.")
        st.write(f"{selected}: vegetation {row.vegetation_stress:.1f} × 0.5 + rainfall {row.rainfall_stress:.1f} × 0.3 + soil/heat {row.moisture_heat_stress:.1f} × 0.2 → **{row.stress_score}/100**.")
        st.caption("The score weights and recommendation thresholds are unchanged. Imported NDVI, precipitation, temperature and soil moisture use the stated current/reference periods. Soil categories are a provisional interpretation of reanalysis anomalies. Water access does not affect the score." if fully_observed else "Observed rows calculate anomalies from the imported period and historical reference; demo rows retain synthetic expectations. Soil moisture remains DEMO where labeled. Water access does not affect the score.")
    export = metrics.copy()
    for column in export.columns:
        if column.endswith("_pct"):
            export[column] = pd.to_numeric(export[column]).round(1)
    st.download_button("Download assessment · CSV", export.to_csv(index=False).encode("utf-8-sig"), "steppeguard_assessment.csv", "text/csv")

def render_demo_replay():
    st.subheader("Drought Replay")
    st.write("Paddock 2 · A synthetic deterioration scenario, June–July 2026")
    st.caption("DEMO DATA · This includes simulated dates after the dashboard assessment. It is not a validated historical forecast or evidence of predictive performance.")
    dates = history.date.dt.strftime("%d %b %Y").tolist()
    replay_date = st.select_slider("Replay through", options=dates, value=dates[-1])
    end = dates.index(replay_date)
    shown = history.iloc[:end + 1]
    point = shown.iloc[-1].to_dict()
    point.update(calculate_stress(point))
    point["official_plan"] = "Spring–summer grazing"
    replay_decision = recommend(point, point["date"].date())
    a, b, c = st.columns(3)
    a.metric("Demo NDVI", f"{point['current_ndvi']:.3f}")
    b.metric("Climate stress", f"{point['stress_score']} / 100", point["stress_level"], delta_color="off")
    c.metric("Rainfall anomaly", f"{point['rainfall_anomaly_pct']:+.0f}%")
    chart = go.Figure()
    chart.add_trace(go.Scatter(x=shown.date, y=shown.seasonal_ndvi, name="Seasonal baseline (demo)", mode="lines+markers", line=dict(color="#9ba897", dash="dash", width=2)))
    chart.add_trace(go.Scatter(x=shown.date, y=shown.current_ndvi, name="NDVI (demo)", mode="lines+markers", line=dict(color="#22634a", width=3), marker=dict(size=9)))
    chart.update_layout(height=360, margin=dict(l=10, r=20, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        legend=dict(orientation="h", y=1.15), yaxis=dict(title="NDVI", range=[0.1, 0.38]),
                        xaxis=dict(title=None, range=[history.date.min().to_pydatetime() - timedelta(days=2), history.date.max().to_pydatetime() + timedelta(days=2)]))
    st.plotly_chart(chart, width="stretch")
    st.info(f"**{replay_decision['decision']}** · {replay_decision['explanation']}")
    for col, (_, event) in zip(st.columns(4), history.iterrows()):
        with col:
            st.markdown(f"**{event.date:%d %B}**")
            st.write(event.event)
            st.caption(f"{calculate_stress(event)['stress_score']}/100 stress · synthetic")
    st.write("This synthetic replay illustrates how recommendations change as environmental inputs change.")
    st.caption("This demo illustrates the intended workflow. Demonstrating real lead time requires observed satellite/climate histories and independent validation.")

with replay:
    if historical_error:
        st.error(f"Historical evidence failed validation: {historical_error}. The September reference dashboard remains available.")
    elif historical_meta:
        render_observed_replay(historical_meta, historical_rows)
    else:
        render_demo_replay()

with about:
    st.subheader("About the pilot")
    a, b = st.columns([1, 2], gap="large")
    with a:
        st.markdown("**PILOT LOCATION**\n\nAkkum Rural District  \nZhalagash District  \nKyzylorda Region  \nKazakhstan")
    with b:
        st.write("SteppeGuard combines Earth observation, climate information and existing pasture management plans to help pastoral communities adapt grazing decisions to changing environmental conditions.")
        st.markdown("### From static pasture planning\n### To climate-responsive pasture management")
        st.write("The app reads local CSV and GeoJSON files, with transparent scoring and seasonal rules. The v0.2 acquisition script imports Sentinel-2 observations from Microsoft Planetary Computer and ERA5 reanalysis from Open-Meteo. Streamlit does not call data providers during use.")
    st.divider()
    st.markdown("**Future integrations — not yet implemented**")
    st.write("Georeferenced official paddock boundaries · Paddock-specific environmental summaries · Livestock numbers · Pasture carrying capacity · Watering points")
    st.markdown("**Data provenance**")
    st.write("Satellite NDVI and ERA5 precipitation, temperature and surface soil moisture are summarized for a 5 km analysis zone around 44.916664, 64.712612. All four paddock schedules use this shared signal until the official plan map is georeferenced. The four displayed sectors are illustrative, not official boundaries. The 2026 rotation schedule is retained as the official-plan baseline; exact seasonal dates remain assumptions. Water access is not assessed. The historical evaluation applies these seasonal rules retrospectively to observed conditions; it does not establish actual past grazing, predictive skill or field outcomes.")
    st.markdown("Sources: [Microsoft Planetary Computer / Copernicus Sentinel-2](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a) · [Open-Meteo / ECMWF ERA5](https://open-meteo.com/en/docs/historical-weather-api) · [Official plan](https://old.adilet.zan.kz/kaz/docs/G24LF02818M)")
st.divider()
st.caption("This prototype is a decision-support demonstration and should not yet be used for operational livestock or land-management decisions.")
