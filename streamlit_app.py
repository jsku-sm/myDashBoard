# GITHUB_ONLY_R3 — 기존 app.py의 내용을 모두 지우고 이 파일로 교체하세요.
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = (
    "classroom/__init__.py",
    "classroom/application.py",
    "classroom/github_connection.py",
    "classroom/storage.py",
    "classroom/auth.py",
    "classroom/service.py",
    "classroom/feedback.py",
    "classroom/ui.py",
    "assets/style.css",
    "assets/live.js",
    "assets/login_1.svg",
    "assets/login_2.svg",
    "assets/login_3.svg",
)
missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
if missing:
    st.set_page_config(page_title="수정본 업로드 확인", page_icon="🛠️")
    st.title("실행 파일은 교체되었습니다. 나머지 파일을 올려 주세요.")
    st.error("아래 파일이 없습니다. Secrets나 토큰 문제가 아닙니다.")
    st.code("\n".join(missing), language="text")
    st.info("전체 수정본 ZIP을 풀고, classroom과 assets 폴더를 app.py와 같은 위치에 올려 주세요.")
    st.caption("실행 버전: GITHUB_ONLY_R3")
    st.stop()

from classroom.application import main

if __name__ == "__main__":
    main()
