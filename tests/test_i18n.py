"""Localization must affect presentation only, including stateful reruns."""
import ast
from datetime import date
import json
from pathlib import Path
import re
from string import Formatter
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.data_loader import load_data
from src.historical import load_history
from src.i18n import TRANSLATIONS, display, display_frame, date_text
from src.observations import apply_observations
from src.recommendations import recommend, explanation_text
from src.scoring import calculate_stress

ROOT = Path(__file__).resolve().parents[1]


class LocalizationTests(unittest.TestCase):
    def test_catalog_keys_placeholders_and_source_links_match(self):
        en, ru = TRANSLATIONS['en'], TRANSLATIONS['ru']
        self.assertEqual(en.keys(), ru.keys())
        for key in en:
            fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field is not None}
            self.assertEqual(fields(en[key]), fields(ru[key]), key)
            links = lambda text: re.findall(r'https?://[^\s)]+', text)
            self.assertEqual(links(en[key]), links(ru[key]), key)
            self.assertTrue(ru[key], key)
        for filename in ['app.py', 'src/replay.py']:
            for node in ast.walk(ast.parse((ROOT / filename).read_text(encoding='utf-8'))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 't':
                    self.assertIn(node.args[0].value, en)

    def test_presentation_keeps_canonical_data_and_numeric_values(self):
        _, metrics, _ = load_data()
        _, history = load_history()
        for frame in [metrics, history]:
            before = frame.copy(deep=True)
            for lang in ['ru', 'en']:
                rendered = display_frame(frame, lang)
                pd.testing.assert_frame_equal(frame, before)
                pd.testing.assert_frame_equal(rendered.select_dtypes('number').set_axis(range(len(rendered.select_dtypes('number').columns)), axis=1),
                                              before.select_dtypes('number').set_axis(range(len(before.select_dtypes('number').columns)), axis=1))
        self.assertEqual(display('MODERATE', 'ru'), 'УМЕРЕННЫЙ')
        self.assertEqual(display('-15.3%', 'ru'), '-15,3%')
        self.assertEqual(display('https://example.org/v0.2', 'ru'), 'https://example.org/v0.2')
        self.assertEqual(date_text('2025-10-31', 'ru'), '31 октября 2025 года')

    def test_explanations_cover_directions_and_every_decision(self):
        cases = [('Rest', 70), ('Autumn grazing', 70), ('Summer grazing', 70),
                 ('Summer grazing', 50), ('Summer grazing', 10)]
        for plan, score in cases:
            for anomaly in [-15.3, 0, 15.3]:
                metrics = dict(official_plan=plan, stress_score=score,
                               vegetation_anomaly_pct=anomaly, rainfall_anomaly_pct=-95.7)
                result = recommend(metrics, date(2026, 7, 1))
                before = dict(result)
                russian = explanation_text(metrics, date(2026, 7, 1), 'ru', result)
                self.assertIn('95,7%', russian)
                self.assertNotIn('Vegetation', russian)
                self.assertEqual(explanation_text(metrics, date(2026, 7, 1), 'en', result), result['explanation'])
                self.assertEqual(result, before)
                if result['decision'] == 'DELAY GRAZING':
                    self.assertIn('15 июля 2026 года', russian)

    def test_russian_default_switch_and_preserved_selections(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=45).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key='language').value, 'ru')
        self.assertEqual([tab.label for tab in app.tabs], ['Наблюдаемый исторический пример', 'Оценка за сентябрь 2026 года', 'О пилотном проекте'])
        self.assertEqual(app.metric[0].value, '-15,3%')
        self.assertTrue(any('54/100' == m.value for m in app.metric))
        self.assertTrue(any('октябрь 2025 года' in h.value for h in app.subheader))
        app.selectbox[0].select('Paddock 4').run()
        app.select_slider(key='observed_replay_date').set_value('2021-05-31').run()
        self.assertFalse(app.exception)
        ru_tables = [element.value.copy() for element in app.dataframe]
        ru_charts = [json.loads(element.proto.spec) for element in app.get('plotly_chart')]
        downloads = [element.proto.url for element in app.get('download_button')]
        app.radio(key='language').set_value('en').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value, 'Paddock 4')
        self.assertEqual(app.selectbox[0].key, 'paddock_en')
        self.assertEqual(app.select_slider(key='observed_replay_date').value, '2021-05-31')
        self.assertEqual(app.tabs[0].label, 'Observed case study')
        self.assertTrue(any('50 / 100' == m.value for m in app.metric))
        self.assertEqual(downloads, [element.proto.url for element in app.get('download_button')])
        for translated, original in zip(ru_tables, app.dataframe):
            pd.testing.assert_frame_equal(translated, display_frame(original.value, 'ru'))
        for ru_chart, en_chart in zip(ru_charts, [json.loads(element.proto.spec) for element in app.get('plotly_chart')]):
            for ru_trace, en_trace in zip(ru_chart['data'], en_chart['data']):
                self.assertEqual(ru_trace['x'], en_trace['x'])
                self.assertEqual(ru_trace['y'], en_trace['y'])
                self.assertEqual(ru_trace['line'], en_trace['line'])
        app.radio(key='language').set_value('ru').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox[0].value, 'Paddock 4')
        self.assertEqual(app.selectbox[0].key, 'paddock_ru')
        self.assertEqual(app.select_slider(key='observed_replay_date').value, '2021-05-31')
        self.assertTrue(any('СНИЗИТЬ ПАСТБИЩНУЮ НАГРУЗКУ' in e.value for e in app.warning))

    def test_demo_and_validation_messages_in_russian(self):
        polygons, metrics, history = load_data(include_observed=False)
        polygons, metrics = apply_observations(polygons, metrics, ROOT / 'tests/no-observation-bundle')
        with patch('src.data_loader.load_data', return_value=(polygons, metrics, history)), patch('src.historical.load_history', return_value=(None, None)):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=45).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.tabs[0].label, 'Мониторинг пастбищ')
            self.assertEqual(app.tabs[1].label, 'Динамика засухи')
            self.assertTrue(any('ОТЛОЖИТЬ ВЫПАС' in e.value for e in app.error))
            for day in ['01 Jun 2026', '15 Jun 2026', '01 Jul 2026', '15 Jul 2026']:
                app.select_slider(key='demo_replay_date').set_value(day).run()
                self.assertFalse(app.exception)
        with patch('src.historical.load_history', side_effect=ValueError('Historical artifact checksum mismatch: evaluation.csv')):
            app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=45).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Не совпадает контрольная сумма' in e.value for e in app.error))
            app.radio(key='language').set_value('en').run()
            self.assertTrue(any('Historical artifact checksum mismatch' in e.value for e in app.error))


if __name__ == '__main__':
    unittest.main()
