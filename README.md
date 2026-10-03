> **R3 오류 수정:** 먼저 `오류수정_먼저읽기.md`를 읽어 주세요. 현재 실행 파일은 `app.py`입니다.

# 🌱 구쌤의 수학 교실 — GitHub 저장 전용 수정본

기존 `app.py → backend.py → 데이터베이스 클라이언트` 실행 경로를 교체하는 전체 패키지입니다.
**실행 파일은 `app.py`입니다.** `streamlit_app.py`로 실행해도 같은 앱을 엽니다.

1. [오류 수정·업로드 순서](UPDATE_GITHUB_ONLY.md)
2. [전체 설치·운영 안내서](README_시작하기.md)
3. [검증 결과 및 미검증 범위](TEST_REPORT.md)

코드 저장소에 폴더 내용 전체를 올리세요. ZIP 자체나 app.py 하나만 올리면 안 됩니다.
운영 기록은 별도의 **GitHub Private 데이터 저장소**에 암호화한 파일로 저장합니다.
학생 비밀번호 원문, 토큰, 암호화키는 코드 저장소에 올리지 마세요.

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Secrets가 없으면 초기 설정 화면을 표시하며 실제 학생 데이터를 저장하지 않습니다.
이 수정본에는 로컬 데모 실행 모드가 없습니다. `LocalBackend`는 테스트 전용입니다.
별도의 데이터베이스 계정, 테이블 생성, 데이터베이스용 키가 필요하지 않습니다.
