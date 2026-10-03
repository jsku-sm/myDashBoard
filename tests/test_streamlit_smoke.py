"""Optional integration test. Requires the installed Streamlit runtime.

No live GitHub or OpenAI access. Run: pytest tests/test_streamlit_smoke.py -q
"""
from pathlib import Path
import pytest
st = pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
ROOT = Path(__file__).resolve().parent.parent


def test_teacher_login_and_home(tmp_path, monkeypatch):
    monkeypatch.setenv('STORAGE_MODE', 'demo')
    monkeypatch.setenv('DEMO_DATA_DIR', str(tmp_path / 'demo'))
    st.cache_resource.clear()
    app = AppTest.from_file(str(ROOT / 'streamlit_app.py'), default_timeout=60).run()
    assert not app.exception
    app.text_input[0].set_value('teacher')
    app.text_input[1].set_value('DemoTeacher!2026')
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state['token']
    for menu in ['📘 공통수학1', '📗 공통수학2', '✍️ 수다노트', '💬 질문 게시판',
                 '🧰 수업도구', '🪑 좌석배치표', '📊 교사 대시보드', '📝 관찰기록·상벌점',
                 '👥 학생 관리', '⚙️ 교실 설정', '🙋 내 정보']:
        app.sidebar.radio[0].set_value(menu).run()
        assert not app.exception, menu
