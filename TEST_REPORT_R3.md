# R3 검증 결과

## 실제 실행

- Python 소스 전체 구문 검사: 통과.
- `python -m pytest -q tests/test_core.py tests/test_github_only.py tests/test_entrypoint_r3.py tests/test_streamlit_smoke.py`
- 결과: **58 passed, 1 skipped in 9.86s**.

이번 실행에는 기존 핵심 기능·권한·암호화 저장 검사와 GitHub HTTP 모의 서버 검사,
새 실행 진입점의 파일 누락 안내 검사, 기존 root backend 모듈과의 분리 검사가 포함됩니다.
실제 GitHub 토큰이나 학생 데이터는 사용하지 않았습니다.

## 새 회귀 검사

1. application.py가 root backend.py 대신 package-local github_connection을 불러오는지 검사.
2. backend 모듈을 의도적으로 접근 실패하게 해도 새 GitHub 연결 모듈이 로드되는지 검사.
3. app.py만 업로드했을 때 누락 파일 안내 후 중단하는지 검사.
4. streamlit_app.py만 업로드했을 때 동일하게 안전하게 안내하는지 검사.

3, 4는 Streamlit 표시 함수를 모의 객체로 대체한 단위 검사이며, 실제 화면 실행 검사가 아닙니다.

## 실행하지 못한 범위

Streamlit 패키지가 이 환경에 없고 설치 시 패키지를 찾지 못하여
실제 Streamlit AppTest 모듈 1개를 건너뛰었습니다. 실제 Streamlit 전체 앱 실행,
사용자 GitHub 저장소 연결, Streamlit Community Cloud 배포, 학생 여러 명의 동시 접속,
iPad Safari 동작은 이번에 검증하지 않았습니다. 브라우저 구성요소 시험도 이번 R3에서는
다시 실행하지 않았습니다. 이전 보고서는 이전 버전의 검사 결과입니다.

연결된 GitHub 검색에서는 mydashboard 저장소가 반환되지 않아 원격 파일을 수정하지 않았습니다.
이 결과는 다운로드한 패키지와 모의 환경에 한정됩니다.

## 적용 후 확인

GitHub에서 배포 브랜치의 app.py 첫 줄이 GITHUB_ONLY_R3인지 확인합니다.
앱 재시작 후 로그인/설정 화면에서 R3를 확인합니다. 테스트 계정으로 제출 후
앱을 재시작해 기록이 다시 조회되는지 확인하고 실제 학생 운영 전에 권한을 점검하세요.
