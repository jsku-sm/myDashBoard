# Supabase 오류 수정 — GitHub 저장 전용

수정본: **github-only-2026.10.03-r2**

## 무엇을 바꿨나요?

첨부한 오류 화면에는 `app.py`가 기존 `backend.py`를 읽고, 그 안에서 `from supabase import create_client`를 실행하는 것으로 표시되어 있습니다.
이 패키지는 해당 실행 경로를 GitHub 저장 코드로 교체합니다. Supabase를 설치하거나 Supabase URL·키를 입력할 필요가 없습니다.

- `app.py`: 새 GitHub 전용 앱을 실행하는 파일입니다.
- `backend.py`: GitHub 비공개 저장소에 연결하는 코드입니다. 별도 데이터베이스를 불러오지 않습니다.
- `classroom/application.py`: 설정 확인과 실행을 담당합니다. GitHub 모드만 허용합니다.
- `streamlit_app.py`: 이전에 이 파일명으로 배포한 경우에도 같은 앱을 실행합니다.
- `requirements.txt`: 데이터베이스 패키지를 요구하지 않습니다.
- `st.navigation`으로 사용할 화면을 명시해, 기존 `pages/`의 오래된 파일을 자동 실행하지 않습니다.

기존 로그인·감정·수업자료·학생 제출·수다노트·질문·관찰·상벌점·좌석표 코드는 유지했습니다.
실제 GitHub 저장소나 기존 데이터는 이 수정 파일을 만드는 과정에서 변경하지 않았습니다.

## 1. 코드 저장소에 전체 파일 교체

먼저 현재 코드와 설정을 개인적으로 백업하세요. 실제 토큰·키가 들어 있는 설정은 공개 저장소에 백업하지 않습니다.

압축을 푼 뒤 **폴더 안의 파일과 하위 폴더 전체**를 현재 앱의 코드 저장소 `mydashboard` 최상위에 업로드합니다.
동일한 이름의 기존 파일은 수정본으로 교체합니다. `app.py`나 `backend.py` 한 파일만 교체하면 안 됩니다.

```text
mydashboard/
├── app.py                     ← 현재 오류 화면의 실행 파일을 이 파일로 교체
├── backend.py                 ← 기존 Supabase용 파일을 이 파일로 교체
├── streamlit_app.py
├── requirements.txt
├── classroom/
│   ├── application.py
│   ├── storage.py
│   ├── service.py
│   ├── auth.py
│   ├── feedback.py
│   ├── ui.py
│   └── __init__.py
├── assets/
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example    ← 실제 비밀값이 없는 예시
├── examples/
├── scripts/
└── tests/
```

GitHub의 **Add file → Upload files → Commit changes**로 반영하세요.
ZIP 파일 자체만 올리거나, `mydashboard/새폴더/app.py`처럼 실행 파일을 한 단계 아래에 넣지 않습니다.
Mac에서 `.streamlit` 폴더가 보이지 않으면 Finder에서 Command + Shift + .를 누르세요.
**실제 `secrets.toml`은 업로드하지 마세요.**

기존 `uv.lock`, `Pipfile`, `environment.yml` 등 다른 의존성 파일이 있다면, 백업 후 이 앱의 배포 폴더에서 제외하고 동봉한 `requirements.txt`만 사용하세요. Streamlit은 우선순위가 더 높은 의존성 파일이 있으면 `requirements.txt` 대신 그 파일을 사용할 수 있습니다.
다른 앱과 같은 저장소를 공유 중이면 관련 파일을 무작정 삭제하지 말고, 새 코드 저장소에 이 패키지만 올려 배포하는 편이 혼동을 줄입니다.

## 2. 학생 데이터용 GitHub 비공개 저장소 준비

예: `mydashboard-data`

**Private**를 선택하고, **Add a README file**을 켜서 저장소를 생성합니다. `main` 브랜치가 있어야 합니다.
이미 사용 중인 GitHub 데이터 저장소가 있다면 새로 만들 필요가 없습니다. 기존 저장소 이름과 기존 ENCRYPTION_KEY를 그대로 사용하세요.

코드 저장소와 학생 데이터 저장소는 분리합니다. 두 저장소 모두 GitHub이며, 다른 데이터베이스 서비스는 쓰지 않습니다.
이 코드에서는 공개 저장소로 학생 데이터를 저장하려 하면 거절합니다.

## 3. GitHub 토큰 발급

GitHub 프로필 → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token

Repository access에서 **Only select repositories**를 선택하고, `mydashboard-data` 한 개만 지정합니다.
Repository permissions에서 **Contents: Read and write**를 부여합니다.

발급한 토큰은 Streamlit Secrets에 입력합니다. 채팅·앱 코드·README·학생 계정표에 적지 않습니다.
코드만 GitHub에 올려서는 앱이 학생 기록을 저장할 권한을 갖지 못합니다. 데이터를 쓰는 토큰 설정이 별도로 필요합니다.

## 4. Streamlit Secrets 입력

Streamlit 앱 → Manage app → Settings → Secrets에서 설정합니다.
기존 앱용 설정을 먼저 개인적으로 백업하고, 이 앱에서 쓰는 설정은 아래 GitHub 설정으로 바꾸세요. 다른 앱과 공유하는 키는 무작정 삭제하지 않습니다.

```toml
STORAGE_MODE = "github"
GITHUB_REPO = "본인아이디/mydashboard-data"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = "발급한_GitHub_토큰"
ENCRYPTION_KEY = "첫_설정_화면에서_생성한_키"
TEACHER_ID = "teacher"
TEACHER_INITIAL_PASSWORD = "본인이_정한_12자이상_비밀번호"
```

이 앱은 SUPABASE_URL·SUPABASE_KEY 등의 설정을 읽지 않습니다. STORAGE_MODE가 예전 값이라면 반드시 `github`로 바꾸세요.

### 암호화키를 아직 만들지 않았다면

처음 설치하는 경우, **Secrets를 비워 둔 상태에서 앱을 실행**하세요. 초기 설정 화면의 **설정용 새 암호화키 만들기** 버튼을 눌러 나온 문자열을 ENCRYPTION_KEY에 입력합니다.
터미널을 쓴다면 `python scripts/make_key.py`로 생성해도 됩니다.
키는 비밀번호 관리 도구 등 안전한 곳에도 따로 보관하세요.

**이미 암호화된 데이터가 있으면 새 키를 만들지 말고 원래 키를 사용하세요.** 다른 키를 쓰면 기존 데이터를 읽을 수 없습니다.
TEACHER_INITIAL_PASSWORD는 새 저장소에 첫 교사 계정을 만들 때만 적용됩니다. 기존 계정의 비밀번호를 초기화하지 않습니다.

## 5. 앱 재시작

현재 오류 화면은 `app.py`를 실행 중입니다. 수정본도 `app.py`로 실행하므로 실행 파일명을 바꿀 필요가 없습니다.
새로 배포한다면 Main file path를 **app.py**로 지정하세요. `streamlit_app.py`도 동일한 앱으로 연결됩니다.

업로드와 Secrets 저장을 마친 뒤, 앱의 **Manage app → ⋮ → Reboot app**으로 재시작합니다.
수업 중 사용자가 있는 상태에서 재시작하면 작업이 중단되므로 실제 수업 전에 진행하세요.
로그인 화면 하단에 **GitHub 저장 전용 · 2026.10.03-r2**가 표시되면 수정본이 실행 중인 것입니다.

같은 `from supabase import create_client` 오류가 계속 나오면, 수정 파일이 아니라 다른 저장소·브랜치·기존 파일을 실행 중인지 확인하세요.
현재 앱에 연결된 저장소/브랜치의 `app.py` 내용이 `from classroom.application import main`인지 먼저 확인합니다.

## 6. 어떤 자료가 어디에 저장되나요?

```text
auth/users.enc                      학번·이름·학급·비밀번호 해시
activity/날짜.enc                   날짜별 로그인 이력·마지막 감정
students/학생별ID/notes.enc         학생별 누적 수다노트
students/학생별ID/profile.enc       학생 소개·관심 분야
courses/...                        과목별 자료·과제 목록
classes/1-1/submissions.enc         1-1 제출물 기록
classes/1-1/questions.enc           1-1 질문 게시판
classes/1-1/observations.enc        1-1 교사 관찰기록
classes/1-1/seats.enc               1-1 좌석배치표
classroom/control.enc              학급 잠금·상벌점
files/파일ID.enc                    업로드한 첨부파일
```

다른 학급도 같은 구조입니다. `.enc` 파일은 암호화되어 GitHub 웹페이지에서 바로 읽는 표가 아닙니다. 교사 화면에서 열람하고 지원 메뉴의 CSV 내보내기를 사용합니다.
학생 비밀번호 원문은 보관하지 않습니다. 로그인 검증용 해시를 저장하고 계정 파일도 암호화합니다.
순간 접속 상태·로그인 세션은 실행 중인 앱 서버 메모리에 있으며, 날짜별 로그인 이력은 GitHub에 저장합니다.

## 7. 적용 후 확인과 제한

가상 학생 2명으로 먼저 확인하세요. 교사 로그인 → 학생 등록 → 학생 최초 비밀번호 변경 → 감정 선택 → 과제 제출·수다노트 저장 → 교사의 확인 → 앱 재시작 후 같은 기록 다시 읽기 순서입니다.
비공개 기록이 다른 학생에게 보이지 않는지, 잠금·해제와 상벌점 알림이 대상 학생에게 적용되는지도 확인하세요.

- **기존 Supabase 자료의 자동 이전은 포함하지 않았습니다.** 이 파일을 올린다고 기존 DB의 계정·자료를 옮기거나 삭제하지 않습니다.
- GitHub API 제한과 파일별 쓰기 지연이 있습니다. 최대 25명 실제 동시접속/저장 검증은 아직 수행하지 않았습니다. 저장 중에는 반복 클릭하지 말고 완료 메시지를 확인하세요.
- GitHub 연결 실패 시 성공으로 표시하거나 임시 로컬 저장으로 대체하지 않습니다.
- 파일당 8MB 제한, 수다노트·과제 기본 제출 확인, 앱 내부 화면 잠금 범위 등은 전체 안내서를 확인하세요.
- GitHub는 변경 이력을 보관합니다. 학생 자료 보관 기간과 과거 이력 정리도 학교 운영 기준에 맞게 관리하세요.

이번 수정본의 자동 검사 결과는 TEST_REPORT.md에 구분해 기록했습니다.

## 공식 참고 문서

확인일: 2026-10-03

- Streamlit 의존성 파일: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- Streamlit Secrets: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- Streamlit 앱 재시작: https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app
- Streamlit 명시적 화면 구성: https://docs.streamlit.io/develop/api-reference/navigation/st.navigation
- GitHub 파일 읽기·쓰기 API: https://docs.github.com/en/rest/repos/contents
- GitHub 토큰 권한: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub API 사용 한도: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
