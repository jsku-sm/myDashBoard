# 📘 구쌤의 수학 교실

**Streamlit + Supabase / 공통수학1·공통수학2 / 1-1 ~ 1-7**

학생의 자료 내려받기 → 활동 제출 → 피드백 → 수다노트와 교사의 수업 관제를 연결하는 웹앱입니다.

> 코드 구현본입니다. 실제 Supabase 프로젝트·GitHub 저장소·Streamlit 앱은 자동 생성되지 않습니다. 아래 안내에 따라 연결해야 합니다. 이 제작 환경에서는 Python 구문과 30개 단위·정적 점검을 수행했으며, 실제 Streamlit 실행, Supabase 권한 동작, 25명 동시 접속, AI API 실연결은 검증하지 않았습니다. 실제 학생 등록 전 가상 계정으로 시험하세요.

## 시작하기

**[처음 시작하기](docs/처음시작.md)** → **[학생 자료 보관 기준](docs/학생자료_운영기준.md)** → **[배포 후 점검](docs/배포후_점검표.md)** 순서로 읽으세요.

### 바로 실행하기

이 프로젝트는 HTML 문서가 아니라 **Streamlit Python 웹앱**입니다.
압축을 푼 폴더를 VS Code에서 열고 터미널에서 다음을 실행하세요.

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

**실행 파일은 `app.py`입니다.** 이 파일만 따로 실행하지 말고, `backend.py`,
`views.py`, `teacher.py`, `ui.py`, `utils.py`, `.streamlit`, `supabase`가 같은 프로젝트에 있도록 유지하세요.
Supabase 설정 전에도 로그인 화면이 먼저 표시됩니다. 이때 로그인 버튼은 비활성 상태이며,
화면 아래의 ‘교사용 · Supabase 연결 설정’에서 연결 방법을 확인할 수 있습니다.
실제 로그인·제출물 저장·교사 대시보드는 Supabase 연결과 교사 계정 생성 후 사용합니다.

### GitHub 업로드 / Streamlit 배포

이 폴더 **안의 파일 전체**를 저장소에 업로드합니다. 저장소 최상위에 `app.py`가 있도록 하세요.
Streamlit Community Cloud의 실행 파일(Main file path)은 `app.py`입니다.
실제 학생 명렬과 실제 연결키가 들어 있는 `.streamlit/secrets.toml`은 업로드하지 마세요.
이 패키지에는 HTML 안내 파일과 실제 학생 명렬이 포함되어 있지 않습니다.

## 포함 기능

| 영역 | 구현 내용 |
|---|---|
| 로그인 | 학생 학번 / 교사 `teacher`, 임시 비밀번호 발급, 최초 변경, 분실 시 재발급, 학생별 반복 로그인 제한 |
| 개인정보 분리 | 학생 본인 데이터, 같은 반의 교사 지정 공유 과제, 교사전용 데이터에 다른 RLS 적용 |
| 마음 날씨 | 로그인·새 수업 시작 시 감정 선택 창, 응답 거절 선택지, 교사용 인원·비율 통계 |
| 접속 확인 | 수업별 접속·미접속, 마지막 연결 시각, 최근 연결 확인; 실제 출석 판정 기능 아님 |
| 수업 공간 | 과목·단원별 평가계획/학습자료, 학급별 과제, 학생 제출·재제출 이력, 다운로드 |
| 학습 피드백 | AI 미연결 시 제출 확인, 연결·승인·신청이 있을 때 자동 AI 피드백, 교사 보완 피드백 |
| 질문 | 개인 질문 또는 같은 반 공유 질문, 교사 답변·알림 |
| 수다노트 | 사용자 제공 구글폼 안내와 링크; 응답 자동 수집은 미포함 |
| 수업도구 | 스노클, 데스모스, Amplify Classroom, 외부 퀴즈, ‘앱 (by 구쌤)’ 링크 관리 |
| 화면 잠금 | 학급별/전체 7개 반 잠금, 학생 화면 5초 간격 상태 조회, DB·파일 권한에서 잠금 검사 |
| 관찰·상벌점 | 학생별 교사 관찰기록, 상점/벌점 부여·취소 이력, 학생 자신의 누계, 상점 폭죽·벌점 알림 |
| 좌석·조 | 학번순/무작위 편성, 행·열·조 직접 수정, 중복·누락 검사, 좌석표·조별 명단·CSV |
| 운영 | 계정 비활성화·명시적 개별 완전 삭제, 학급 기록 JSON/CSV 내보내기, 자료 삭제, 보관기준 기록 |

## 중요 경계

- **GitHub에 학생 명렬, 임시 비밀번호, 실제 Secrets를 올리지 마세요.** 이 저장소에는 가상 예시 명렬만 있습니다. 별도로 제공된 `private_roster_136.csv`는 교사 화면에서 업로드하는 파일입니다.
- 학생 비밀번호는 Supabase Auth에서 보호된 해시로 관리합니다. 변경된 비밀번호를 교사가 읽거나 CSV로 내려받는 기능은 없습니다.
- 잠금은 **이 앱 안의 학습 기능**에 적용됩니다. 이미 열린 외부 사이트/구글폼/아이패드 앱이나 이미 다운로드된 파일을 제어하지 않습니다. 계정 인증·로그아웃·연결 상태 확인은 잠금 중에도 필요합니다.
- 5초 주기 조회는 엄밀한 5초 이내 반영 보장이 아닙니다. 네트워크, 비활성 탭, 진행 중인 업로드·AI 요청에 따라 지연될 수 있습니다. 잠금 직전에 시작된 외부 요청은 완료될 수 있습니다.
- 잠금 해제 시 메뉴·서버에 전달된 풀이 메모를 가능한 범위에서 복원합니다. 선택만 하고 제출하지 않은 파일, 서버에 전송되기 전 입력은 보존을 보장하지 않습니다.
- 동시에 최대 25명이 사용하는 수업을 대상으로 설계했지만 **25명 부하 시험은 수행하지 않았습니다.** Free 요금제의 무중단·용량·성능을 보장하지 않습니다.
- AI는 성적이나 세특을 자동 확정하지 않습니다. 학생 파일에 이름이 적혀 있으면 그 이름도 외부 AI에 전달될 수 있습니다. 자동 익명화 기능이 아닙니다.
- JSON 백업은 앱 기록과 파일 경로만 포함합니다. 실제 첨부파일·Auth 비밀번호 해시·서비스 제공자 백업은 포함하지 않으며, 원클릭 복원 기능도 없습니다.
- 파일 형식/크기를 검사하지만 전문 악성코드 검사 서비스를 포함하지는 않습니다.

## 구조

```text
app.py                         # Streamlit 진입점
backend.py                     # 인증·데이터·파일·AI 처리
views.py                       # 학생/교과 화면
teacher.py                     # 교사 관제·좌석·관리 화면
ui.py                          # 공통 화면·폭죽
utils.py                       # 명렬·좌석·누계·파일 검증
requirements.txt
.streamlit/config.toml
.streamlit/secrets.toml.example # 실제 값은 절대 커밋 금지
supabase/schema.sql            # 새 프로젝트 DB·RLS·비공개 Storage
supabase/verify_schema.sql      # 설치 구조 확인
examples/roster_template.csv    # 가상 학생만 포함
scripts_check.py               # 로컬 구문·단위 점검 실행
상세_구현현황.md
docs/
```

## 로컬 실행 (Python 3.12 권장)

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
# secrets.toml.example을 복사해 .streamlit/secrets.toml을 만들고 실제 연결 값 입력
streamlit run app.py
```

## 단위 점검

```bash
python -m unittest discover -s tests -v
```

시험용 계정 생성: 교사전용 → 학생·계정 → 가상 학생 3명 생성. 실제 데이터 승인 설정이 꺼져 있어도 고정된 가상 명렬만 허용됩니다.

## 참고한 공식 문서

- Supabase 새 프로젝트/SQL Editor: https://supabase.com/docs/guides/getting-started/tutorials/with-react
- 지역: https://supabase.com/docs/guides/platform/regions
- API keys: https://supabase.com/docs/guides/getting-started/api-keys
- RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- 비밀번호 저장: https://supabase.com/docs/guides/auth/password-security
- Streamlit 배포: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- Secrets: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- Fragments: https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- OpenAI 파일 입력: https://developers.openai.com/api/docs/guides/file-inputs
