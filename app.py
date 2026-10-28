"""SteppeGuard: local observations with explicit provenance and demo fallbacks."""
from datetime import date
import pandas as pd
import folium
import streamlit as st
from src.data_loader import load_data
from src.scoring import calculate_stress
from src.recommendations import recommend, explanation_text
from src.historical import load_history
from src.replay import render_observed_replay
from src.i18n import DEFAULT_LANGUAGE, LANGUAGES, t, display, display_frame

lang = st.session_state.get("language", DEFAULT_LANGUAGE)
st.set_page_config(page_title=display("SteppeGuard · Akkum pilot", lang), page_icon="🌾", layout="wide")
lang = st.sidebar.radio("Язык / Language", options=list(LANGUAGES),
                        format_func=LANGUAGES.get, key="language")
st.markdown("""<style>
.block-container{max-width:1000px;padding-top:4.5rem;padding-bottom:3rem}
h1{letter-spacing:-.04em;font-size:2.4rem!important}
.recommendation{font-size:clamp(1.5rem,4vw,2.1rem);font-weight:700;color:#73501d;background:#fff5e5;border-left:5px solid #dc922b;border-radius:12px;padding:20px;line-height:1.3}
@media(max-width:640px){.block-container{padding-top:3rem} h1{font-size:1.9rem!important}} h2{letter-spacing:-.025em}
[data-testid="stMetricValue"]{font-size:2.5rem;font-weight:650}
[data-testid="stMetric"]{background:#fff;border:1px solid #dfe5da;border-radius:12px;padding:16px}
.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:700;color:#57715d;text-transform:uppercase}
.lead{font-size:21px;color:#526658;margin-top:-12px}
.score{font-size:54px;font-weight:700;line-height:1.15;letter-spacing:-.04em}
.score small{font-size:20px;font-weight:400;color:#758278}
.legend{font-size:13px;color:#53645a;margin:8px 0 16px}
.stTabs [data-baseweb="tab-list"]{gap:28px}.stTabs [data-baseweb="tab"]{font-size:16px}
</style>""", unsafe_allow_html=True)

COLORS = {"LOW": [60, 137, 94], "MODERATE": [220, 146, 43], "HIGH": [196, 68, 54], "REST": [124, 143, 149]}


def prepared_data():
    polygons, metrics, history = load_data()
    scores = pd.DataFrame([calculate_stress(row) for _, row in metrics.iterrows()])
    metrics = pd.concat([metrics, scores], axis=1)
    decisions = pd.DataFrame([recommend(row, date.fromisoformat(row.assessment_date)) for _, row in metrics.iterrows()])
    return polygons, pd.concat([metrics, decisions], axis=1), history


def render_reference():
    try:
        polygons, metrics, history = prepared_data()
    except (ValueError, OSError, KeyError) as exc:
        st.error(t('unable_to_validate_the_local_datasets_p0_invalid', lang, p0=f'{exc}'))
        st.stop()

    observed_count = int(metrics.vegetation_source.ne("DEMO").sum())
    fully_observed = observed_count == len(metrics) and metrics.soil_source.ne("DEMO").all()
    if not fully_observed:
        st.warning(t('mixed_data_p0_pilot_area_uses_observed_sentinel', lang, p0=str(observed_count)) if observed_count else t('demo_data_no_observed_bundle_loaded_synthetic_environmental', lang), icon="ℹ️")
    st.subheader(t('when_should_planned_grazing_be_adapted', lang))
    map_col, detail_col = st.columns([1.45, 1], gap="large")
    with map_col:
        paddock_options = metrics.paddock_id.tolist()
        selected_paddock = st.session_state.get("selected_paddock", paddock_options[1])
        # Streamlit serializes selectbox labels. A language-specific widget key
        # prevents an old translated label from being decoded with the new locale.
        # The independent state value always retains the canonical paddock ID.
        selected = st.selectbox(t('select_a_paddock_to_inspect', lang), paddock_options,
                                index=paddock_options.index(selected_paddock),
                                format_func=lambda value: display(value, lang), key=f"paddock_{lang}")
        st.session_state["selected_paddock"] = selected
        st.info(t('shared_zone', lang))
        st.caption(t('selector_scope', lang))
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
                           tooltip=t('map_tooltip', lang, p0=f"{item['name']}", p1=f"{item['score']}", p2=f"{item['level']}", p3=f"{item['decision']}")).add_to(pasture_map)
            folium.Marker([item["position"][1], item["position"][0]],
                          icon=folium.DivIcon(icon_size=(90, 24), icon_anchor=(45, 12),
                              html=t('map_marker', lang, p0=f"{item['name']}"))).add_to(pasture_map)
        if fully_observed:
            folium.GeoJson(polygons.attrs["analysis_geometry"], name=t('approximate_analysis_zone', lang),
                           style_function=lambda _: {"color": "#20352c", "weight": 2, "fillOpacity": 0, "dashArray": "6 4"},
                           tooltip=t('akkum_5_km_analysis_zone_not_official_paddock', lang)).add_to(pasture_map)
        min_x, min_y, max_x, max_y = polygons.total_bounds
        pasture_map.fit_bounds([[min_y, min_x], [max_y, max_x]])
        st.components.v1.html(pasture_map.get_root().render(), height=420)
        st.markdown(t('low_stress_nbsp_moderate_nbsp_high_nbsp_rest', lang), unsafe_allow_html=True)
        st.caption(t('approximate_analysis_zone_dashed_boundary_is_the_5', lang) if fully_observed else t('schematic_geographic_view_observed_pilot_areas_use_their', lang) if observed_count else t('schematic_geographic_view_temporary_demo_polygons_not_official', lang))
    row = metrics.set_index("paddock_id").loc[selected]
    explanation = explanation_text(row, date.fromisoformat(row.assessment_date), lang)
    with detail_col:
        with st.container(border=True):
            st.markdown(t('paddock_heading', lang, p0=f'{selected}'))
            st.caption(t('assessment_boundary_caption', lang, p0=f'{row.data_status}', p1=f'{row.assessment_date}', p2=f'{row.boundary_status}'))
            st.caption(t('2026_official_plan_akkum_rotation_schedule', lang))
            st.write(t('strong_value', lang, p0=f'{row.official_plan}'))
            color = "#" + "".join(f"{c:02x}" for c in COLORS[row.stress_level])
            st.markdown(t('stress_score_card', lang, p0=f'{color}', p1=f'{row.stress_score}', p2=f'{color}', p3=f'{row.stress_level}'), unsafe_allow_html=True)
            if row.vegetation_source != "DEMO" and row.soil_source == "DEMO":
                st.caption(t('partly_observed_score_soil_moisture_still_uses_the', lang))
            st.divider()
            st.caption(t('steppeguard_recommendation', lang))
            if row.decision == "DELAY GRAZING":
                st.error(t('recommendation_detail', lang, p0=f'{row.decision}', p1=explanation))
            elif row.stress_level == "MODERATE":
                st.warning(t('recommendation_detail', lang, p0=f'{row.decision}', p1=explanation))
            else:
                st.success(t('recommendation_detail', lang, p0=f'{row.decision}', p1=explanation))
        st.markdown(t('vegetation_climate', lang))
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
        st.dataframe(display_frame(facts_table, lang), hide_index=True, width="stretch")
        if row.vegetation_source != "DEMO":
            with st.expander(t('observation_provenance', lang)):
                st.write(t('window_p0_to_p1_historical_reference_same_calendar', lang, p0=f'{row.period_start}', p1=f'{row.assessment_date}', p2=f'{row.baseline_years}'))
                st.write(t('sentinel_2_p0_accepted_dates_latest_scene_p1', lang, p0=f'{int(row.ndvi_scene_count)}', p1=f'{row.latest_scene}'))
                if fully_observed:
                    st.write(t('pixelwise_median_composites_at_20_m_with_at', lang, p0=f'{row.common_valid_fraction:.1%}'))
                    st.write(t('these_are_shared_pilot_area_indicators_not_measurements', lang))
                    st.write(t('soil_classification_p0', lang, p0=f'{row.soil_status_method}'))
                else:
                    st.write(t('current_ndvi_is_the_median_of_polygon_mean', lang))
                st.write(t('precipitation_is_the_period_total_rain_plus_snow', lang))
                st.write(t('geometry_p0_downloaded_p1', lang, p0=f'{row.geometry_source}', p1=f'{row.retrieved_at}'))
                st.caption(t('polygon_sha_256_p0', lang, p0=f'{row.polygon_sha256}'))
                st.markdown(t('sentinel_2_source_p0_climate_source_p1', lang, p0=f'{row.ndvi_source_url}', p1=f'{row.climate_source_url}'))
    st.subheader(t('official_plan_vs_climate_adaptive_plan', lang))
    st.write(t('static_pasture_plans_cannot_anticipate_unusual_drought_or', lang))
    comparison = metrics[["paddock_id", "official_plan", "plan_now", "decision", "stress_score", "stress_level", "changed", "assessment_date", "data_status"]].copy()
    comparison["changed"] = comparison.changed.map({True: "ADAPTED", False: "As planned"})
    comparison.columns = ["Paddock", "Official Plan", "Plan at assessment", "SteppeGuard Decision", "Score / 100", "Stress", "Plan change", "Assessment date", "Data source"]
    def highlight_adaptation(r):
        return ["background-color: #fce9d9; color: #592d17" if comparison.loc[r.name, "Plan change"] == "ADAPTED" else ""] * len(r)
    st.dataframe(display_frame(comparison, lang).style.apply(highlight_adaptation, axis=1), hide_index=True, width="stretch")
    st.caption(t('shaded_rows_change_planned_grazing_season_windows_remain', lang))
    st.markdown(t('official_akkum_pasture_management_plan_2025_2029_adilet', lang))
    with st.expander(t('how_the_score_and_decisions_work', lang)):
        st.write(t('score_50_vegetation_stress_30_rainfall_stress_20', lang))
        st.write(t('vegetation_reaches_100_stress_at_35_rainfall_at', lang))
        st.write(t('0_30_low_planned_grazing_may_proceed_31', lang))
        st.write(t('score_breakdown', lang, p0=f'{selected}', p1=f'{row.vegetation_stress:.1f}', p2=f'{row.rainfall_stress:.1f}', p3=f'{row.moisture_heat_stress:.1f}', p4=f'{row.stress_score}'))
        st.caption(t('the_score_weights_and_recommendation_thresholds_are_unchanged', lang) if fully_observed else t('observed_rows_calculate_anomalies_from_the_imported_period', lang))
    export = metrics.copy()
    for column in export.columns:
        if column.endswith("_pct"):
            export[column] = pd.to_numeric(export[column]).round(1)
    st.download_button(t('download_assessment_csv', lang), export.to_csv(index=False).encode("utf-8-sig"), "steppeguard_assessment.csv", "text/csv")

st.markdown(t('akkum_rural_district_kazakhstan', lang), unsafe_allow_html=True)
st.caption(t('steppeguard', lang))
st.title(t('decision_question', lang))
try:
    historical_meta, historical_rows = load_history()
except (ValueError, OSError, KeyError) as exc:
    st.error(t('history_validation_error', lang, p0=str(exc)))
    historical_meta, historical_rows = None, None
if historical_meta:
    render_observed_replay(historical_meta, historical_rows, lang, render_reference)
else:
    st.info(t('case_unavailable', lang))
    with st.expander(t('explore_other_periods', lang)):
        render_reference()
st.divider()
st.caption(t('this_prototype_is_a_decision_support_demonstration_and', lang))
