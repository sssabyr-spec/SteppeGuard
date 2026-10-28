"""Observed replay using the existing Streamlit metrics, chart and table layout."""
from datetime import date
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.historical import PLANS
from src.recommendations import recommend
from src.i18n import DEFAULT_LANGUAGE, t, display, display_frame, localize_chart


def render_observed_replay(meta, rows, lang=DEFAULT_LANGUAGE, reference_renderer=None):
    # Presentation stays pinned to this archived case, independently of exploration state.
    selected = "2025-10-31"
    case = rows.loc[rows.assessment_date.eq(selected) & rows.status.eq("evaluated")]
    if not case.empty:
        strongest = case.iloc[0]
        result = recommend({**strongest.to_dict(), "official_plan": PLANS["Paddock 4"]}, date.fromisoformat(selected))
        st.caption(t('fixed_case', lang))
        st.write(t('case_official_plan', lang))
        st.caption(t('steppeguard_recommendation', lang))
        wording = "REDUCE GRAZING PRESSURE AND MONITOR" if result["decision"] == "MONITOR / REDUCE PRESSURE" else result["decision"]
        st.markdown(f'<div class="recommendation">{display(wording, lang)}</div>', unsafe_allow_html=True)
        st.markdown(t('case_reasons', lang, vegetation=f'{strongest.vegetation_anomaly_pct:+.1f}', rainfall=f'{strongest.rainfall_anomaly_pct:+.1f}', score=f'{int(strongest.stress_score)}'))
        st.caption(t('case_plan_scope', lang))
        st.subheader(t('territory_conditions', lang))
        st.write(t('shared_zone', lang))
        a, b, c = st.columns(3)
        a.metric(t('term_vegetation_anomaly', lang), t('percentage', lang, p0=f'{strongest.vegetation_anomaly_pct:+.1f}'))
        b.metric(t('rainfall_anomaly', lang), t('percentage', lang, p0=f'{strongest.rainfall_anomaly_pct:+.1f}'))
        c.metric(t('climate_stress', lang), t('stress_score_compact', lang, p0=f'{int(strongest.stress_score)}'))
        with st.expander(t('why_recommendation', lang)):
            point = strongest
            facts = [
                ("NDVI", f"{point.current_ndvi:.3f}", f"{point.seasonal_ndvi:.3f}", f"{point.vegetation_anomaly_pct:+.1f}%", "Sentinel-2 L2A"),
                ("30-day precipitation", f"{point.precipitation_mm:.1f} mm", f"{point.baseline_precipitation_mm:.1f} mm", f"{point.rainfall_anomaly_pct:+.1f}%", "ERA5 reanalysis"),
                ("Mean temperature", f"{point.temperature_mean_c:.1f} °C", f"{point.baseline_temperature_c:.1f} °C", f"{point.temperature_anomaly_c:+.1f} °C", "ERA5 reanalysis"),
                ("Soil moisture (0–7 cm)", f"{point.soil_moisture_m3m3:.3f} m³/m³", f"{point.baseline_soil_moisture_m3m3:.3f} m³/m³", f"{point.soil_moisture_anomaly_pct:+.1f}% · {point.soil_moisture_status}", "ERA5 reanalysis")]
            st.dataframe(display_frame(pd.DataFrame(facts, columns=["Indicator", "Observed / reanalysis", "Seasonal baseline", "Anomaly / status", "Source"]), lang), hide_index=True, width="stretch")
            st.write(t('observed_window_p0_to_p1_historical_reference_same', lang, p0=strongest.period_start, p1=selected, p2=strongest.baseline_years))
    else:
        st.info(t('case_unavailable', lang))
    with st.expander(t('explore_other_periods', lang)):
        options = rows.loc[rows.status.eq("evaluated"), "assessment_date"].tolist()
        if options:
            replay_date = st.select_slider(t('replay_through', lang), options=options, value=selected if selected in options else options[-1],
                                          format_func=lambda value: display(value, lang), key="observed_replay_date")
            point = rows.loc[rows.assessment_date.eq(replay_date)].iloc[0]
            a, b, c = st.columns(3)
            a.metric(t('observed_ndvi', lang), t('formatted_value', lang, p0=f'{point.current_ndvi:.3f}'), t('baseline_percent_comparison', lang, p0=f'{point.vegetation_anomaly_pct:+.1f}'), delta_color="off")
            b.metric(t('climate_stress', lang), t('stress_score_spaced', lang, p0=f'{int(point.stress_score)}'), display(point.stress_level, lang), delta_color="off")
            c.metric(t('rainfall_anomaly', lang), t('percentage', lang, p0=f'{point.rainfall_anomaly_pct:+.1f}'))
            st.caption(t('selected_window_p0_to_p1', lang, p0=f'{point.period_start}', p1=f'{point.assessment_date}'))
            st.subheader(t('territory_conditions', lang))
            st.write(t('shared_zone', lang))
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
        if reference_renderer is not None:
            with st.expander(t('september_2026_assessment', lang)):
                reference_renderer()
    with st.expander(t('methodology_sources', lang)):
        st.write(t('ai_disclosure', lang))
        st.write(t('satellite_ndvi_and_era5_precipitation_temperature_and_surface', lang))
        st.write(t('score_50_vegetation_stress_30_rainfall_stress_20', lang))
        st.write(t('vegetation_reaches_100_stress_at_35_rainfall_at', lang))
        st.write(t('0_30_low_planned_grazing_may_proceed_31', lang))
        st.write(t('screening_summary', lang, p0=f"{meta['evaluated_windows']}", p1=f"{meta['requested_windows']}", p2=f"{meta['conflict_windows']}"))
        st.write(t('the_highlighted_case_has_the_highest_unchanged_score', lang))
        if not case.empty:
            st.write(t('selected_replay_window_p0_to_p1_reference_years', lang, p0=f'{strongest.period_start}', p1=f'{strongest.assessment_date}', p2=f'{strongest.baseline_years}', p3=f'{int(strongest.scene_count)}', p4=f'{strongest.common_valid_fraction:.1%}'))
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
