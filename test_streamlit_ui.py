"""Optional UI smoke test; requires Streamlit and Supabase packages.
Run: python -m unittest discover -s tests -v
No live Supabase connection is used by this test.
"""
from pathlib import Path
import sys
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HAS_RUNTIME = all(importlib.util.find_spec(x) is not None for x in ("streamlit", "supabase"))

@unittest.skipUnless(HAS_RUNTIME, "Streamlit/Supabase runtime dependencies not installed")
class StreamlitUI(unittest.TestCase):
    def test_initial_screen_is_login_before_configuration(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15)
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any(x.value == "우리 교실 로그인" for x in app.subheader))
        button = next(x for x in app.button if x.label == "로그인")
        self.assertTrue(button.disabled)
        self.assertTrue(any(x.label == "교사용 · Supabase 연결 설정" for x in app.expander))

if __name__ == "__main__":
    unittest.main()
