"""Entry point: streamlit run streamlit_app.py"""
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
from cryptography.fernet import Fernet
from classroom.storage import AppError, EncryptedStore, GitHubBackend, LocalBackend
from classroom.service import Classroom
from classroom.auth import password_hash
from classroom.ui import css, run_ui, setup_screen

st.set_page_config(page_title='구쌤의 수학 교실', page_icon='🌱', layout='wide', initial_sidebar_state='expanded')
ROOT = Path(__file__).resolve().parent


def setting(name: str, default: str = '') -> str:
    if name in os.environ:
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


@st.cache_resource(show_spinner=False)
def build_service(mode, repo, branch, github_token, encryption_key, teacher_id, initial_password, api_key, model, demo_dir):
    if mode == 'demo':
        data_dir = Path(demo_dir or ROOT / '.local_data').resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        key_file = data_dir / '.demo_key'
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
        store = EncryptedStore(LocalBackend(data_dir), key_file.read_text().strip())
        svc = Classroom(store)
        svc.auth.bootstrap('teacher', 'DemoTeacher!2026')
        if len(store.read_json('auth/users.enc', {})) == 1:
            teacher = svc.auth.login('teacher', 'DemoTeacher!2026')
            rows = [{'학번': f'1{c}{n:02}', '이름': f'체험학생{c}-{n}', '학급': f'1-{c}'}
                    for c in range(1, 8) for n in (1, 2)]
            svc.auth.add_students(teacher, rows)
            shared_demo_hash = password_hash('DemoStudent!2026')
            def set_demo_password(users):
                for student in users.values():
                    if student['role'] == 'student':
                        student['password_hash'] = shared_demo_hash
                        student['must_change'] = False
                return users
            store.mutate('auth/users.enc', {}, set_demo_password)
            svc.auth.logout(teacher)
        return svc
    if mode != 'github':
        raise AppError('STORAGE_MODE는 github 또는 demo만 사용할 수 있습니다.')
    if not (repo and github_token and encryption_key):
        raise AppError('GITHUB_REPO, GITHUB_TOKEN, ENCRYPTION_KEY를 Secrets에 입력하세요.')
    backend = GitHubBackend(github_token, repo, branch or 'main')
    svc = Classroom(EncryptedStore(backend, encryption_key), api_key=api_key, model=model)
    svc.auth.bootstrap(teacher_id or 'teacher', initial_password)
    return svc


def main():
    mode = setting('STORAGE_MODE').lower()
    if not mode:
        css()
        setup_screen()
        return
    try:
        svc = build_service(mode, setting('GITHUB_REPO'), setting('GITHUB_BRANCH', 'main'),
                            setting('GITHUB_TOKEN'), setting('ENCRYPTION_KEY'), setting('TEACHER_ID', 'teacher'),
                            setting('TEACHER_INITIAL_PASSWORD'), setting('OPENAI_API_KEY'), setting('OPENAI_MODEL'),
                            setting('DEMO_DATA_DIR'))
        run_ui(svc)
    except AppError as exc:
        css()
        st.error(str(exc))
        st.caption('저장소 설정과 연결을 확인하세요. GitHub 오류가 발생해도 학생 데이터를 임시 로컬 파일로 대신 저장하지 않습니다.')
        if st.button('연결 다시 확인'):
            st.cache_resource.clear()
            st.rerun()


if __name__ == '__main__':
    main()
