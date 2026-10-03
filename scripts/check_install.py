"""Run after installing requirements.txt to check direct dependencies."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import streamlit, pandas, requests, cryptography
from backend import connect_github
print("Python:", sys.version.split()[0])
for module in (streamlit, pandas, requests, cryptography):
    print(module.__name__ + ":", module.__version__)
print("GitHub 저장 코드 import 확인 완료. 실제 GitHub 연결 검사는 아닙니다.")
print("실행: python -m streamlit run app.py")
