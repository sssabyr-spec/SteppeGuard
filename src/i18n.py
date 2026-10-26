"""Presentation-only translations. Canonical data, exports and decisions stay unchanged."""
from datetime import date, datetime
import json
from pathlib import Path
import re

DEFAULT_LANGUAGE = "ru"
LANGUAGES = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}
TRANSLATIONS = {
    lang: json.loads((Path(__file__).parent / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
    for lang in LANGUAGES
}
_ENGLISH_KEYS = {text: key for key, text in TRANSLATIONS["en"].items() if "{" not in text}
_ERROR_PATTERNS = [
    (re.compile(re.escape(text).replace(re.escape("{detail}"), "(.+)")), key)
    for key, text in TRANSLATIONS["en"].items() if key.startswith("error_") and "{detail}" in text
]
_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря")
_MONTH_NAMES = ("январь", "февраль", "март", "апрель", "май", "июнь",
                "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")


def t(key, lang=DEFAULT_LANGUAGE, **values):
    """Resolve a stable message key; format only display copies of its parameters."""
    return TRANSLATIONS[lang][key].format(**{name: display(value, lang) for name, value in values.items()})


def date_text(value, lang=DEFAULT_LANGUAGE, english_format=None, month_only=False, year=True):
    """Use explicit Russian month names, independent of the server's locale."""
    if not isinstance(value, (str, date)):
        # Plotly stores datetime series as numpy.datetime64 rather than datetime.
        value = str(value)[:10]
    if isinstance(value, str):
        parsed = None
        for pattern in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%B %Y", "%d %B"):
            try:
                parsed = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue
        if parsed is None:
            return value
    else:
        parsed = value
    if lang == "en":
        return parsed.strftime(english_format) if english_format else str(value)
    if month_only:
        return f"{_MONTH_NAMES[parsed.month - 1]} {parsed.year} года"
    return f"{parsed.day} {_MONTHS[parsed.month - 1]}" + (f" {parsed.year} года" if year else "")


def display(value, lang=DEFAULT_LANGUAGE):
    """Translate known canonical labels and formatted values without mutating input."""
    if lang == "en" or not isinstance(value, str):
        return value
    if value in _ENGLISH_KEYS:
        return TRANSLATIONS[lang][_ENGLISH_KEYS[value]]
    for pattern, key in _ERROR_PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            return TRANSLATIONS[lang][key].format(detail=match.group(1))
    if value.startswith(("https://", "http://", "#")) or re.fullmatch(r"[a-f0-9]{64}", value):
        return value
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date_text(value, lang)
    if re.fullmatch(r"\d{2} [A-Za-z]+(?: \d{4})?", value):
        return date_text(value, lang, year=bool(re.search(r"\d{4}$", value)))
    if re.fullmatch(r"[A-Za-z]+ \d{4}", value):
        return date_text(value, lang, month_only=True)
    # These delimiters occur in display cells, never in the calculation data.
    if " · " in value:
        return " · ".join(display(part, lang) for part in value.split(" · "))
    if re.fullmatch(r"Paddock [1-4](, Paddock [1-4])*", value):
        return ", ".join(display(part, lang) for part in value.split(", "))
    if re.fullmatch(r"[+−-]?\d+(?:\.\d+)?(?:%| mm| °C| m³/m³)?", value):
        return value.replace(".", ",").replace(" mm", " мм").replace(" m³/m³", " м³/м³")
    return value


def display_frame(frame, lang=DEFAULT_LANGUAGE):
    """Translate a table copy, retaining numeric dtypes and canonical source frames."""
    result = frame.copy(deep=True)
    for column in result:
        if result[column].dtype == object or str(result[column].dtype).startswith("str"):
            result[column] = result[column].map(lambda value: display(value, lang)).astype(frame[column].dtype)
    result.columns = [display(column, lang) for column in result.columns]
    return result


def localize_chart(chart, dates, lang=DEFAULT_LANGUAGE):
    """Keep chart coordinates intact; localize only date ticks and hover labels."""
    if lang == "ru":
        labels = [date_text(value, lang) for value in dates]
        chart.update_xaxes(tickmode="array", tickvals=list(dates), ticktext=labels)
        for trace in chart.data:
            trace.customdata = [date_text(value, lang) for value in trace.x]
            trace.hovertemplate = "%{customdata}<br>%{y}<extra>%{fullData.name}</extra>"
        chart.update_layout(separators=", ")
    return chart
