"""Season-aware demonstration rules. No LLM or machine learning."""
from datetime import timedelta

# Illustrative season windows, not verified official dates.
GRAZING_MONTHS = {"Rest": (), "Spring–summer grazing": (3, 4, 5, 6, 7, 8),
                  "Summer grazing": (6, 7, 8), "Autumn grazing": (9, 10, 11)}


def anomaly_text(value, baseline):
    direction = "below" if value < 0 else "above" if value > 0 else "at"
    return f"{abs(value):.1f}% {direction} {baseline}" if value else f"at {baseline}"


def recommend(metrics, assessment_date):
    plan = metrics["official_plan"]
    if plan not in GRAZING_MONTHS:
        raise ValueError(f"Unknown plan: {plan}")
    scheduled = assessment_date.month in GRAZING_MONTHS[plan]
    score = int(metrics["stress_score"])
    evidence = (f"Vegetation is {anomaly_text(metrics['vegetation_anomaly_pct'], 'its seasonal baseline')} "
                f"and rainfall is {anomaly_text(metrics['rainfall_anomaly_pct'], 'normal')}.")
    if plan == "Rest":
        decision, reason = "KEEP RESTING", "Preserve the rest period specified in the 2026 plan."
    elif not scheduled:
        decision, reason = "CONTINUE PLANNED REST", "Outside the illustrative grazing season; reassess before grazing begins."
    elif score > 60:
        decision = "DELAY GRAZING"
        reason = f"Delay grazing and reassess in 14 days ({assessment_date + timedelta(days=14):%d %b %Y})."
    elif score > 30:
        decision, reason = "MONITOR / REDUCE PRESSURE", "Monitor recovery and reduce grazing pressure; reassess in 14 days."
    else:
        decision, reason = "SUITABLE FOR PLANNED GRAZING", "Climate indicators support the planned grazing window; confirm conditions in the field."
    return {"decision": decision, "explanation": f"{evidence} {reason}",
            "plan_now": "Graze" if scheduled else "Rest",
            "changed": scheduled and score > 30}


def explanation_text(metrics, assessment_date, lang="ru", result=None):
    """Render an existing canonical decision; never change its thresholds or data."""
    from src.i18n import t, display, date_text

    result = result if result is not None else metrics
    if lang == "en":
        return result["explanation"]

    def evidence_part(field, prefix):
        value = metrics[field]
        direction = "below" if value < 0 else "above" if value > 0 else "at"
        return t(f"{prefix}_{direction}", lang, amount=f"{abs(value):.1f}")

    evidence = t("recommendation_evidence", lang,
                 vegetation=evidence_part("vegetation_anomaly_pct", "vegetation"),
                 rainfall=evidence_part("rainfall_anomaly_pct", "rainfall"))
    # Reason wording follows the already-computed decision, not new scoring rules.
    reasons = {
        "KEEP RESTING": "Preserve the rest period specified in the 2026 plan.",
        "CONTINUE PLANNED REST": "Outside the illustrative grazing season; reassess before grazing begins.",
        "MONITOR / REDUCE PRESSURE": "Monitor recovery and reduce grazing pressure; reassess in 14 days.",
        "SUITABLE FOR PLANNED GRAZING": "Climate indicators support the planned grazing window; confirm conditions in the field.",
    }
    if result["decision"] == "DELAY GRAZING":
        reason = t("delay_reason", lang, day=date_text(assessment_date + timedelta(days=14), lang))
    else:
        reason = display(reasons[result["decision"]], lang)
    return f"{evidence} {reason}"
