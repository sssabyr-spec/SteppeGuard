"""Observed replay using the existing Streamlit metrics, chart and table layout."""
from datetime import date
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.historical import PLANS
from src.recommendations import recommend
from src.i18n import DEFAULT_LANGUAGE, t, display, display_frame, localize_chart


def render_observed_replay(meta, rows, lang=DEFAULT_LANGUAGE):
    selected = meta.get("selected_date")
    case_month = date.fromisoformat(selected).strftime("%B %Y") if selected else None
    st.subheader(t('observed_historical_case_study_p0', lang, p0=f'{case_month}') if selected else t('historical_evaluation', lang))
    st.caption(t('observed_satellite_data_sentinel_2_l2a_era5_reanalysis', lang))
    st.caption(t('observed_conditions_compared_with_the_2026_style_seasonal', lang))
    if selected:
        strongest = rows.loc[rows.assessment_date.eq(selected)].iloc[0]
        st.write(t('when_should_planned_grazing_be_adapted_2', lang))
        a, b, c = st.columns(3)
        a.metric(t('ndvi_anomaly', lang), t('percentage', lang, p0=f'{strongest.vegetation_anomaly_pct:+.1f}'))
        b.metric(t('30_day_precipitation', lang), t('precipitation_value', lang, p0=f'{strongest.precipitation_mm:.1f}'))
        c.metric(t('historical_precipitation_reference', lang), t('precipitation_value', lang, p0=f'{strongest.baseline_precipitation_mm:.1f}'))
        a, b, c = st.columns(3)
        a.metric(t('rainfall_anomaly', lang), t('percentage', lang, p0=f'{strongest.rainfall_anomaly_pct:+.1f}'))
        b.metric(t('temperature_anomaly', lang), t('temperature_value', lang, p0=f'{strongest.temperature_anomaly_c:+.1f}'))
        c.metric(t('climate_stress', lang), t('stress_score_compact', lang, p0=f'{int(strongest.stress_score)}'), display(strongest.stress_level, lang), delta_color="off")
        for paddock, plan in PLANS.items():
            case_decision = recommend({**strongest.to_dict(), "official_plan": plan}, date.fromisoformat(selected))
            if case_decision["plan_now"] == "Graze":
                wording = "REDUCE GRAZING PRESSURE AND MONITOR" if case_decision["decision"] == "MONITOR / REDUCE PRESSURE" else case_decision["decision"]
                st.info(t('seasonal_rule_recommendation', lang, p0=f'{paddock}', p1=f'{wording}'))
        st.caption(t('observed_window_p0_to_p1_historical_reference_same', lang, p0=f'{strongest.period_start}', p1=f'{selected}', p2=f'{strongest.baseline_years}'))
        st.subheader(t('explore_observed_history', lang))
        options = rows.loc[rows.status.eq("evaluated"), "assessment_date"].tolist()
        replay_date = st.select_slider(t('replay_through', lang), options=options, value=selected,
                                      format_func=lambda value: display(value, lang), key="observed_replay_date")
        point = rows.loc[rows.assessment_date.eq(replay_date)].iloc[0]
        a, b, c = st.columns(3)
        a.metric(t('observed_ndvi', lang), t('formatted_value', lang, p0=f'{point.current_ndvi:.3f}'), t('baseline_percent_comparison', lang, p0=f'{point.vegetation_anomaly_pct:+.1f}'), delta_color="off")
        b.metric(t('climate_stress', lang), t('stress_score_spaced', lang, p0=f'{int(point.stress_score)}'), display(point.stress_level, lang), delta_color="off")
        c.metric(t('rainfall_anomaly', lang), t('percentage', lang, p0=f'{point.rainfall_anomaly_pct:+.1f}'))
        st.caption(t('selected_window_p0_to_p1', lang, p0=f'{point.period_start}', p1=f'{point.assessment_date}'))
        season = rows.loc[rows.year.eq(point.year)].copy()
        shown = season.loc[season.assessment_date.le(replay_date)].copy()
        shown.loc[shown.status.ne("evaluated"), ["current_ndvi", "seasonal_ndvi"]] = float("nan")
        chart = go.Figure()
        for column, label, color, dash in [("seasonal_ndvi", "Seasonal baseline (observed)", "#9ba897", "dash"),
                                           ("current_ndvi", "NDVI (Sentinel-2)", "#22634a", "solid")]:
            chart.add_trace(go.Scatter(x=shown.assessment_date, y=shown[column], name=display(label, lang), mode="lines+markers",
                                      connectgaps=False, line=dict(color=color, dash=dash, width=2 if dash == "dash" else 3)))
        chart.update_layout(height=360, margin=dict(l=10, r=20, t=20, b=10), paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.15), yaxis=dict(title="NDVI"),
                            xaxis=dict(title=None, range=[season.assessment_date.min(), season.assessment_date.max()]))
        st.plotly_chart(localize_chart(chart, season.assessment_date.tolist(), lang), width="stretch")
        st.caption(t('chart_shows_the_selected_year_up_to_the', lang))
        decisions = []
        for paddock, plan in PLANS.items():
            result = recommend({**point.to_dict(), "official_plan": plan}, date.fromisoformat(replay_date))
            decisions.append({"Paddock": paddock, "2026-style rule": plan, "Official Plan": result["plan_now"].upper(),
                              "Observed Climate Stress": point.stress_level, "SteppeGuard": "REDUCE GRAZING PRESSURE AND MONITOR" if result["decision"] == "MONITOR / REDUCE PRESSURE" else result["decision"]})
        for result in decisions:
            if result["Official Plan"] == "GRAZE":
                st.info(t('observed_plan_recommendation', lang, p0=f"{result['Paddock']}", p1=f'{point.stress_level}', p2=f"{result['SteppeGuard']}"))
        st.dataframe(display_frame(pd.DataFrame(decisions), lang), hide_index=True, width="stretch")
        facts = [
            ("NDVI", f"{point.current_ndvi:.3f}", f"{point.seasonal_ndvi:.3f}", f"{point.vegetation_anomaly_pct:+.1f}%", "Sentinel-2 L2A"),
            ("30-day precipitation", f"{point.precipitation_mm:.1f} mm", f"{point.baseline_precipitation_mm:.1f} mm", f"{point.rainfall_anomaly_pct:+.1f}%", "ERA5 reanalysis"),
            ("Mean temperature", f"{point.temperature_mean_c:.1f} °C", f"{point.baseline_temperature_c:.1f} °C", f"{point.temperature_anomaly_c:+.1f} °C", "ERA5 reanalysis"),
            ("Soil moisture (0–7 cm)", f"{point.soil_moisture_m3m3:.3f} m³/m³", f"{point.baseline_soil_moisture_m3m3:.3f} m³/m³", f"{point.soil_moisture_anomaly_pct:+.1f}% · {point.soil_moisture_status}", "ERA5 reanalysis")]
        st.dataframe(display_frame(pd.DataFrame(facts, columns=["Indicator", "Observed / reanalysis", "Seasonal baseline", "Anomaly / status", "Source"]), lang), hide_index=True, width="stretch")
    else:
        st.info(t('no_meaningful_observed_grazing_conflict_was_found_in', lang))
    with st.expander(t('methodology_and_details', lang)):
        st.write(t('screening_summary', lang, p0=f"{meta['evaluated_windows']}", p1=f"{meta['requested_windows']}", p2=f"{meta['conflict_windows']}"))
        st.write(t('the_highlighted_case_has_the_highest_unchanged_score', lang))
        if selected:
            st.write(t('selected_replay_window_p0_to_p1_reference_years', lang, p0=f'{point.period_start}', p1=f'{point.assessment_date}', p2=f'{point.baseline_years}', p3=f'{int(point.scene_count)}', p4=f'{point.common_valid_fraction:.1%}'))
        st.write(t('trailing_30_day_month_end_windows_scene_cloud', lang))
        st.write(t('era5_precipitation_includes_rain_and_snow_the_existing', lang))
        gaps = "; ".join(f"{display(status, lang) if lang == 'ru' else status.replace('_', ' ')}: {count}"
                         for status, count in rows.loc[rows.status.ne("evaluated"), "status"].value_counts().items())
        st.write(t('coverage_gaps', lang, gaps=gaps))
        history_table = rows[["assessment_date", "status", "current_ndvi", "seasonal_ndvi", "vegetation_anomaly_pct", "rainfall_anomaly_pct", "temperature_anomaly_c", "soil_moisture_status", "stress_score", "stress_level", "grazing_paddocks"]].copy()
        st.dataframe(display_frame(history_table.round({"current_ndvi": 3, "seasonal_ndvi": 3, "vegetation_anomaly_pct": 1, "rainfall_anomaly_pct": 1, "temperature_anomaly_c": 1}), lang), hide_index=True, width="stretch")
        st.caption(t('retrieved_p0_geometry_sha_256_p1_source_records', lang, p0=f"{meta['retrieved_at']}", p1=f"{meta['polygon_sha256']}"))
        st.markdown(t('sentinel_2_source_https_planetarycomputer_microsoft_com_dataset', lang))
    export = rows.copy()
    for column in export.columns:
        if column.endswith("_pct"):
            export[column] = export[column].round(1)
    st.download_button(t('download_historical_evaluation_csv', lang), export.to_csv(index=False).encode("utf-8-sig"), "steppeguard_historical_evaluation.csv", "text/csv")
    st.caption(t('the_september_2026_assessment_remains_available_in_its', lang))
