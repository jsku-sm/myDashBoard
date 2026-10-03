"""Optional real Streamlit AppTest; HTTP is mocked, never real student data."""
from pathlib import Path
import pytest
st = pytest.importorskip('streamlit', reason='Streamlit runtime not installed in this environment')
from streamlit.testing.v1 import AppTest
from cryptography.fernet import Fernet
from classroom import auth, storage
from fake_github import FakeGitHub
ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture
def github_env(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(storage.requests, 'request', fake.request)
    monkeypatch.setattr(storage.time, 'sleep', lambda _: None)
    monkeypatch.setattr(auth, 'ITERATIONS', 100_000)
    env = dict(STORAGE_MODE='github', GITHUB_REPO=fake.repo, GITHUB_TOKEN='TEST-TOKEN',
               GITHUB_BRANCH='main', ENCRYPTION_KEY=Fernet.generate_key().decode(),
               TEACHER_ID='teacher', TEACHER_INITIAL_PASSWORD='TeacherSecret!1234',
               OPENAI_API_KEY='', OPENAI_MODEL='')
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    st.cache_resource.clear()
    yield fake
    st.cache_resource.clear()

@pytest.mark.parametrize('entry', ['app.py', 'streamlit_app.py'])
def test_teacher_login_and_all_menus(github_env, entry):
    app = AppTest.from_file(str(ROOT / entry), default_timeout=60).run()
    assert not app.exception
    app.text_input[0].set_value('teacher')
    app.text_input[1].set_value('TeacherSecret!1234')
    next(b for b in app.button if b.label.startswith('우리 교실 입장')).click().run()
    assert not app.exception
    assert app.session_state['token']
    for menu in ['📘 공통수학1', '📗 공통수학2', '✍️ 수다노트', '💬 질문 게시판',
                 '🧰 수업도구', '🪑 좌석배치표', '📊 교사 대시보드', '📝 관찰기록·상벌점',
                 '👥 학생 관리', '⚙️ 교실 설정', '🙋 내 정보']:
        app.sidebar.radio[0].set_value(menu).run()
        assert not app.exception, menu


def test_missing_secrets_shows_setup_without_network(github_env, monkeypatch):
    monkeypatch.setenv('GITHUB_TOKEN', '')
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=60).run()
    assert not app.exception
    assert any(b.label == '설정용 새 암호화키 만들기' for b in app.button)
    assert not github_env.calls


def test_legacy_storage_mode_is_rejected_without_import(github_env, monkeypatch):
    monkeypatch.setenv('STORAGE_MODE', 'supabase')
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=60).run()
    assert not app.exception
    assert any('GitHub 저장 전용' in e.value for e in app.error)
    assert not github_env.calls
