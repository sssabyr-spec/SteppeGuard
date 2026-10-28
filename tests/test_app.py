"""Streamlit's own harness checks all tabs and stateful controls."""
import unittest
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.data_loader import load_data
from src.observations import apply_observations


class AppTests(unittest.TestCase):
    def test_reference_selection_without_historical_bundle(self):
        polygons, metrics, history = load_data(include_observed=False)
        polygons, metrics = apply_observations(polygons, metrics, Path(__file__).parent / "no-observation-bundle")
        patched = patch("src.data_loader.load_data", return_value=(polygons, metrics, history))
        patched.start()
        self.addCleanup(patched.stop)
        historical = patch("src.historical.load_history", return_value=(None, None))
        historical.start()
        self.addCleanup(historical.stop)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45)
        app.session_state["language"] = "en"
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.tabs)
        self.assertTrue(any("unavailable" in item.value for item in app.info))
        self.assertEqual(app.selectbox[0].value, "Paddock 2")
        for name, decision in [("Paddock 1", "KEEP RESTING"), ("Paddock 3", "SUITABLE FOR PLANNED GRAZING"),
                               ("Paddock 4", "CONTINUE PLANNED REST"), ("Paddock 2", "DELAY GRAZING")]:
            app.selectbox[0].select(name).run()
            self.assertFalse(app.exception)
            messages = [item.value for kind in (app.success, app.warning, app.error) for item in kind]
            self.assertTrue(any(decision in message for message in messages))
        self.assertFalse(app.select_slider)

    def test_fixed_case_is_independent_of_exploration(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Нужно ли корректировать запланированный выпас?")
        before = [m.value for m in app.metric[:3]]
        self.assertEqual(before, ["-15,3%", "-95,7%", "54/100"])
        self.assertEqual([e.label for e in app.expander[:2]], ["Почему такая рекомендация?", "Посмотреть другие исторические периоды"])
        self.assertTrue(all(not e.proto.expanded for e in app.expander))
        app.select_slider(key="observed_replay_date").set_value("2021-05-31").run()
        app.selectbox[0].select("Paddock 1").run()
        self.assertFalse(app.exception)
        self.assertEqual([m.value for m in app.metric[:3]], before)
        self.assertTrue(any("2–31 октября 2025" in c.value for c in app.caption))
        self.assertTrue(any("генеративный ИИ" in m.value for m in app.markdown))


if __name__ == "__main__":
    unittest.main()
