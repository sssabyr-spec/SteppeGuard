"""Streamlit's own harness checks all tabs and stateful controls."""
import unittest
from unittest.mock import patch
from pathlib import Path
from streamlit.testing.v1 import AppTest
from src.data_loader import load_data
from src.observations import apply_observations


class AppTests(unittest.TestCase):
    def test_tabs_selection_and_replay(self):
        polygons, metrics, history = load_data(include_observed=False)
        polygons, metrics = apply_observations(polygons, metrics, Path(__file__).parent / "no-observation-bundle")
        patched = patch("src.data_loader.load_data", return_value=(polygons, metrics, history))
        patched.start()
        self.addCleanup(patched.stop)
        historical = patch("src.historical.load_history", return_value=(None, None))
        historical.start()
        self.addCleanup(historical.stop)
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
        self.assertFalse(app.exception)
        self.assertEqual([tab.label for tab in app.tabs], ["Pasture dashboard", "Drought Replay", "About the pilot"])
        self.assertEqual([m.value for m in app.metric[:4]], ["4", "1", "1", "2"])
        self.assertEqual(app.selectbox[0].value, "Paddock 2")
        for name, decision in [("Paddock 1", "KEEP RESTING"), ("Paddock 3", "SUITABLE FOR PLANNED GRAZING"),
                               ("Paddock 4", "CONTINUE PLANNED REST"), ("Paddock 2", "DELAY GRAZING")]:
            app.selectbox[0].select(name).run()
            self.assertFalse(app.exception)
            messages = [item.value for kind in (app.success, app.warning, app.error) for item in kind]
            self.assertTrue(any(decision in message for message in messages))
        for value in ["01 Jun 2026", "15 Jun 2026", "01 Jul 2026", "15 Jul 2026"]:
            app.select_slider[0].set_value(value).run()
            self.assertFalse(app.exception)
        self.assertTrue(any("DELAY GRAZING" in item.value for item in app.info))


if __name__ == "__main__":
    unittest.main()
