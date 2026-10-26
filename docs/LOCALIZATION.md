# Interface languages

SteppeGuard opens in Russian. The sidebar selector (`Язык / Language`) switches the same application between Russian and English, retaining the selected paddock and replay date within the session.

`src/i18n.py` loads the two dictionaries in `src/locales/ru.json` and `src/locales/en.json` as `TRANSLATIONS`. Use stable message keys with `t(key, lang, **parameters)` for interface text. Both catalogs must contain the same keys and format placeholders. Source names, links, hashes and archived provenance remain intact.

`display(value, lang)` translates known canonical labels at the presentation boundary. `display_frame` creates a translated table copy and preserves numeric values and dtypes. Do not use translated labels for filters, decisions, scoring, or exports. Recommendation explanations are rendered by `explanation_text`; `recommend` continues to return its original canonical values and English explanation.

Dates and formatted decimal strings use Russian presentation conventions. English retains the original content and formatting. The explicit CSV download buttons retain the existing canonical export schema and data in both languages. Streamlit's own menus and built-in widget toolbars are supplied by Streamlit, outside the application message catalogs.

Run `python -m unittest discover -s tests -v`. The localization regressions check default language, round-trip switching, selection persistence, translated explanations and errors, catalog placeholders and links, identical numeric table/chart values, and identical CSV download contents.
