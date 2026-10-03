"""Checks imports and versions after installing requirements.txt."""
import sys
import streamlit, pandas, requests, cryptography
print('Python:', sys.version.split()[0])
for module in (streamlit, pandas, requests, cryptography):
    print(module.__name__ + ':', module.__version__)
print('기본 라이브러리 확인 완료. 실행: streamlit run streamlit_app.py')
