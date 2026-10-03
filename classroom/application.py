"""Streamlit application bootstrap; persistent storage is GitHub only."""
from __future__ import annotations
import os
import streamlit as st
from .github_connection import connect_github
from .storage import AppError
from .ui import css, run_ui, setup_screen

APP_VERSION = "github-only-r3"


def setting(name: str, default: str = "") -> str:
    """Environment takes precedence over Streamlit Secrets; never print values."""
    if name in os.environ:
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


@st.cache_resource(show_spinner=False)
def build_service(repo: str, branch: str, token: str, encryption_key: str,
                  teacher_id: str, initial_password: str, api_key: str, model: str):
    return connect_github(repo=repo, branch=branch, token=token,
                          encryption_key=encryption_key, teacher_id=teacher_id,
                          initial_password=initial_password, api_key=api_key, model=model)


def render_classroom():
    # This application does not select a database or local demonstration backend.
    mode = setting("STORAGE_MODE", "github").strip().lower() or "github"
    if mode != "github":
        css()
        st.error('이 수정본은 GitHub 저장 전용입니다. Secrets의 STORAGE_MODE를 "github"로 바꾸세요.')
        setup_screen()
        st.caption("실행 버전: " + APP_VERSION)
        return
    repo = setting("GITHUB_REPO").strip()
    token = setting("GITHUB_TOKEN").strip()
    encryption_key = setting("ENCRYPTION_KEY").strip()
    if not (repo and token and encryption_key):
        css()
        setup_screen()
        st.caption("실행 버전: " + APP_VERSION)
        return
    try:
        svc = build_service(repo, setting("GITHUB_BRANCH", "main"), token, encryption_key,
                            setting("TEACHER_ID", "teacher"), setting("TEACHER_INITIAL_PASSWORD"),
                            setting("OPENAI_API_KEY"), setting("OPENAI_MODEL"))
        run_ui(svc)
    except AppError as exc:
        css()
        st.error(str(exc))
        st.caption("GitHub 연결을 확인하세요. 저장 실패를 임시 로컬 저장으로 대체하지 않습니다.")
        if st.button("연결 다시 확인"):
            build_service.clear()
            st.rerun()


def main():
    st.set_page_config(page_title="구쌤의 수학 교실", page_icon="🌱", layout="wide",
                       initial_sidebar_state="expanded")
    # Explicit navigation prevents leftover legacy pages/ files from being
    # automatically registered or executing old database imports.
    page = st.navigation(
        [st.Page(render_classroom, title="구쌤의 수학 교실", default=True)],
        position="hidden",
    )
    page.run()
