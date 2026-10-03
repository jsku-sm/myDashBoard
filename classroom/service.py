"""All permissions are enforced here, not just by hiding Streamlit menus."""
from __future__ import annotations
import copy
import re
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlparse
from .auth import Auth, CLASSES, now, today, uid
from .feedback import make_feedback
from .storage import AppError

COURSES = {'math1': '공통수학1', 'math2': '공통수학2'}
MOODS = {'happy': '😊 행복해요', 'calm': '😌 편안해요', 'ready': '🤩 의욕 있어요',
         'tired': '😴 피곤해요', 'worried': '😟 걱정돼요', 'upset': '😤 답답해요', 'skip': '🤐 말하고 싶지 않아요'}
DEFAULT_SETTINGS = {
    'title': '구쌤의 수학 교실',
    'tagline': '생각을 나누고, 나의 언어로 성장하는 수학 시간',
    'about': '안녕하세요, 구쌤입니다. 정답을 찾는 것만큼 왜 그렇게 생각했는지를 소중하게 여깁니다. 우리 함께 일상 속 수학을 발견해 봅시다.',
    'interests': '수학적 사고와 탐구\nAI·디지털 도구를 활용한 수업\n실생활 프로젝트와 학생의 성장 기록',
    'units': {'math1': ['다항식', '방정식과 부등식', '경우의 수', '행렬'],
              'math2': ['도형의 방정식', '집합과 명제', '함수와 그래프']},
    'ai_enabled': False,
    'tools': [
        {'name': '스노클', 'url': 'https://www.snorkl.app/', 'description': '말하고 쓰며 나의 생각 설명하기'},
        {'name': '데스모스', 'url': 'https://www.desmos.com/calculator?lang=ko', 'description': '식과 그래프로 수학 탐구하기'},
        {'name': '데스모스 액티비티', 'url': 'https://classroom.amplify.com/', 'description': 'Amplify Classroom 활동에 참여하기'},
        {'name': '풀리수학', 'url': 'https://pulleymath.com/', 'description': '나에게 맞는 수학 학습하기'},
        {'name': '퀴즈', 'url': '', 'description': '선생님이 등록한 퀴즈에 참여하기'},
        {'name': '앱 (by 구쌤)', 'url': '', 'description': '구쌤이 만든 수학 앱 모음'}]
}
DEFAULT_CONTROL = {'locks': {}, 'points': []}
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'txt', 'md', 'docx', 'pptx', 'xlsx', 'hwp', 'hwpx'}
MAX_UPLOAD = 8 * 1024 * 1024
NOTE_FIELDS = ['이해한 내용', '생각한 과정', '시도·수정한 내용', '아직 어려운 점', '다음 학습 계획']


def text_value(value: str, label: str, max_length: int = 8000, required: bool = True) -> str:
    result = str(value).strip()
    if (required and not result) or len(result) > max_length:
        raise AppError(f'{label}을(를) 확인하세요. 최대 {max_length}자입니다.')
    return result


def checked_class(class_id: str) -> str:
    if class_id not in CLASSES:
        raise AppError('학급을 확인하세요.')
    return class_id


def checked_course(course: str) -> str:
    if course not in COURSES:
        raise AppError('과목을 확인하세요.')
    return course


def valid_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ''
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise AppError('외부 도구 주소는 https://로 시작하는 전체 주소로 입력하세요.')
    return url


class Classroom:
    def __init__(self, store, *, api_key: str = '', model: str = ''):
        self.store = store
        self.auth = Auth(store)
        self.api_key = api_key
        self.model = model

    def require(self, token: str, *, teacher: bool = False, action: bool = False,
                allow_password_change: bool = False) -> dict:
        user = self.auth.require(token, teacher=teacher)
        if action and user['role'] == 'student':
            control = self.control(fresh=True)
            lock = self._lock(control, user['class_id'])
            if lock.get('locked'):
                raise AppError('지금은 선생님의 설명 시간입니다. 화면 잠금이 해제된 뒤 다시 시도하세요.')
            if user.get('must_change') and not allow_password_change:
                raise AppError('처음 로그인한 경우 비밀번호를 먼저 변경하세요.')
        return user

    def control(self, fresh: bool = False) -> dict:
        return self.store.read_json('classroom/control.enc', DEFAULT_CONTROL, ttl=0 if fresh else 2.5)

    @staticmethod
    def _lock(control, class_id):
        locks = control.get('locks', {})
        return locks.get('all') if locks.get('all', {}).get('locked') else locks.get(class_id, {})

    def login(self, login_id: str, password: str) -> str:
        token = self.auth.login(login_id, password)
        user = self.auth.require(token)
        if user['role'] == 'student':
            stamp = now()
            def change(records):
                record = records.setdefault(user['uid'], {})
                record.update(login_id=user['login_id'], class_id=user['class_id'], name=user['name'], last_login=stamp)
                record.setdefault('first_login', stamp)
                record['login_count'] = record.get('login_count', 0) + 1
                return records
            try:
                self.store.mutate(f'activity/{today()}.enc', {}, change)
            except AppError:
                self.auth.logout(token)
                raise
        return token

    def monitor(self, token: str) -> dict:
        user = self.require(token)
        if user['role'] == 'teacher':
            return {'locked': False, 'message': '', 'events': []}
        data = self.control()
        lock = self._lock(data, user['class_id'])
        return {'locked': lock.get('locked', False), 'message': lock.get('message', ''),
                'events': [x for x in data['points'] if x['student_uid'] == user['uid']]}

    def set_lock(self, token: str, class_ids: list[str], locked: bool, message: str):
        self.require(token, teacher=True)
        if not class_ids or any(x not in CLASSES + ['all'] for x in class_ids):
            raise AppError('잠글 학급을 선택하세요.')
        entry = {'locked': bool(locked), 'message': text_value(message, '잠금 안내', 200, False), 'updated_at': now()}
        def change(data):
            for cls in class_ids:
                data['locks'][cls] = copy.deepcopy(entry)
            return data
        self.store.mutate('classroom/control.enc', DEFAULT_CONTROL, change)

    def settings(self, token: str) -> dict:
        self.require(token)
        return self.store.read_json('config/settings.enc', DEFAULT_SETTINGS, ttl=60)

    def save_settings(self, token: str, values: dict):
        self.require(token, teacher=True)
        clean = copy.deepcopy(DEFAULT_SETTINGS)
        clean['title'] = text_value(values.get('title', ''), '교실 이름', 60)
        clean['tagline'] = text_value(values.get('tagline', ''), '소개 문구', 150)
        clean['about'] = text_value(values.get('about', ''), '소개', 3000)
        clean['interests'] = text_value(values.get('interests', ''), '관심 분야', 3000, False)
        for course in COURSES:
            units = [text_value(x, '단원명', 80) for x in values['units'][course] if str(x).strip()]
            if not 1 <= len(units) <= 20 or len(set(units)) != len(units):
                raise AppError('과목별 단원을 중복 없이 1~20개 입력하세요.')
            clean['units'][course] = units
        clean['tools'] = [{'name': text_value(x['name'], '도구 이름', 50), 'url': valid_url(x['url']),
                           'description': text_value(x.get('description', ''), '설명', 300, False)}
                          for x in values['tools'] if str(x.get('name', '')).strip()]
        clean['ai_enabled'] = bool(values.get('ai_enabled'))
        if clean['ai_enabled'] and not (self.api_key and self.model):
            raise AppError('AI를 켜려면 먼저 Secrets에 OPENAI_API_KEY와 OPENAI_MODEL을 입력하세요.')
        self.store.mutate('config/settings.enc', DEFAULT_SETTINGS, lambda _: clean)

    def change_password(self, token: str, old: str, new: str):
        self.require(token, action=True, allow_password_change=True)
        self.auth.change_password(token, old, new)

    def save_emotion(self, token: str, mood: str):
        user = self.require(token, action=True)
        if user['role'] != 'student' or mood not in MOODS:
            raise AppError('학생 본인의 감정만 선택할 수 있습니다.')
        stamp = now()
        def change(records):
            record = records.setdefault(user['uid'], {})
            record.update(login_id=user['login_id'], class_id=user['class_id'], name=user['name'], mood=mood, mood_at=stamp)
            return records
        self.store.mutate(f'activity/{today()}.enc', {}, change)

    def dashboard(self, token: str, class_id: str, day: str) -> list[dict]:
        self.require(token, teacher=True)
        checked_class(class_id)
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise AppError('날짜를 확인하세요.') from exc
        records = self.store.read_json(f'activity/{day}.enc', {}, ttl=5)
        active = self.auth.active_ids() if day == today() else set()
        rows = []
        for user in self.auth.users(token, class_id):
            record = records.get(user['uid'], {})
            status = '접속 중' if user['login_id'] in active else ('접속 이력 있음' if record.get('last_login') else '미접속')
            rows.append({'학번': user['login_id'], '이름': user['name'], '계정': '활성' if user['active'] else '중지',
                         '접속 상태': status, '마지막 로그인': record.get('last_login', ''),
                         '감정': MOODS.get(record.get('mood'), '아직 선택하지 않음')})
        return rows

    def _scope(self, token: str, class_id: str) -> dict:
        user = self.require(token)
        checked_class(class_id)
        if user['role'] == 'student' and user['class_id'] != class_id:
            raise AppError('다른 학급의 자료는 열람할 수 없습니다.')
        return user

    def _file(self, attachment: tuple[str, bytes] | None, object_id: str) -> dict | None:
        if attachment is None:
            return None
        original, content = attachment
        filename = PurePosixPath(original.replace('\\', '/')).name
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)[:160]
        extension = filename.rsplit('.', 1)[-1].lower()
        if extension not in ALLOWED_EXTENSIONS or not content or len(content) > MAX_UPLOAD:
            raise AppError('허용된 형식의 파일을 선택하세요. 파일당 최대 8MB입니다.')
        path = f'files/{object_id}.enc'
        # Idempotent upload retry. No personally identifying file names in Git paths.
        existing, _ = self.store.backend.read(path)
        if existing is None:
            self.store.write_bytes(path, content)
        elif self.store._decode(existing) != content:
            raise AppError('이 제출 번호에 다른 파일이 이미 저장되었습니다. 새 제출로 등록하세요.')
        return {'path': path, 'name': filename, 'size': len(content)}

    def materials(self, token: str, course: str) -> list[dict]:
        user = self.require(token)
        checked_course(course)
        rows = self.store.read_json(f'courses/{course}/materials.enc', [], ttl=15)
        return [x for x in rows if not x.get('archived') and
                (user['role'] == 'teacher' or user['class_id'] in x['classes'])]

    def add_material(self, token: str, *, course: str, unit: str, kind: str, title: str, body: str,
                     classes: list[str], attachment=None, event_id: str | None = None):
        self.require(token, teacher=True)
        checked_course(course)
        if kind not in ('평가계획', '학습지', '수업자료') or not classes or any(x not in CLASSES for x in classes):
            raise AppError('자료 종류와 배포 학급을 선택하세요.')
        title = text_value(title, '제목', 150)
        body = text_value(body, '설명', 8000, False)
        if not attachment and not body:
            raise AppError('설명 또는 첨부파일을 입력하세요.')
        record = {'id': event_id or uid(), 'course': course, 'unit': text_value(unit, '단원', 80), 'kind': kind,
                  'title': title, 'body': body, 'classes': classes, 'created_at': now(), 'archived': False}
        record['file'] = self._file(attachment, record['id'])
        return self.store.append(f'courses/{course}/materials.enc', record)

    def archive_material(self, token: str, course: str, material_id: str):
        self.require(token, teacher=True)
        checked_course(course)
        def change(rows):
            found = False
            for row in rows:
                if row['id'] == material_id:
                    row['archived'] = True
                    found = True
            if not found:
                raise AppError('자료를 찾을 수 없습니다.')
            return rows
        self.store.mutate(f'courses/{course}/materials.enc', [], change)

    def material_download(self, token: str, course: str, material_id: str) -> tuple[str, bytes]:
        self.require(token, action=True)
        match = next((x for x in self.materials(token, course) if x['id'] == material_id), None)
        if not match or not match.get('file'):
            raise AppError('다운로드 권한이 없거나 파일이 없습니다.')
        return match['file']['name'], self.store.read_bytes(match['file']['path'])

    def assignments(self, token: str, course: str) -> list[dict]:
        user = self.require(token)
        checked_course(course)
        rows = self.store.read_json(f'courses/{course}/assignments.enc', [], ttl=15)
        return [x for x in rows if user['role'] == 'teacher' or user['class_id'] in x['classes']]

    def add_assignment(self, token: str, *, course: str, unit: str, title: str, description: str,
                       classes: list[str], share: bool, feedback_note: str, event_id: str | None = None):
        self.require(token, teacher=True)
        checked_course(course)
        if not classes or any(x not in CLASSES for x in classes):
            raise AppError('과제 대상 학급을 선택하세요.')
        record = {'id': event_id or uid(), 'course': course, 'unit': text_value(unit, '단원', 80),
                  'title': text_value(title, '과제 제목', 150), 'description': text_value(description, '과제 안내', 5000),
                  'classes': list(classes), 'share': bool(share),
                  'feedback_note': text_value(feedback_note, '공통 피드백', 2000, False), 'created_at': now()}
        return self.store.append(f'courses/{course}/assignments.enc', record)

    def set_assignment_share(self, token: str, course: str, assignment_id: str, share: bool):
        self.require(token, teacher=True)
        checked_course(course)
        def change(rows):
            target = next((x for x in rows if x['id'] == assignment_id), None)
            if not target:
                raise AppError('과제를 찾을 수 없습니다.')
            target['share'] = bool(share)
            return rows
        self.store.mutate(f'courses/{course}/assignments.enc', [], change)

    def submit(self, token: str, *, course: str, assignment_id: str, text: str,
               attachment=None, consent: bool = False, event_id: str | None = None) -> dict:
        user = self.require(token, action=True)
        if user['role'] != 'student':
            raise AppError('학생 계정에서 제출하세요.')
        # Assignment permissions must not rely on a browser-supplied share flag.
        self.store.cache.pop(f'courses/{checked_course(course)}/assignments.enc', None)
        task = next((x for x in self.assignments(token, course) if x['id'] == assignment_id), None)
        if not task:
            raise AppError('이 과제에 제출할 권한이 없습니다.')
        text = text_value(text, '풀이 설명', 8000, False)
        if not text and attachment is None:
            raise AppError('작성 내용이나 첨부파일을 넣어 주세요.')
        record_id = event_id or uid()
        path = f'classes/{user["class_id"]}/submissions.enc'
        previous = next((x for x in self.store.read_json(path, [], ttl=0) if x['id'] == record_id), None)
        if previous:
            if previous['student_uid'] != user['uid']:
                raise AppError('제출 번호 충돌입니다.')
            return previous
        file = self._file(attachment, record_id)
        cfg = self.settings(token)
        feedback = make_feedback(text, task['title'], task['feedback_note'], enabled=cfg['ai_enabled'],
                                 consent=consent, api_key=self.api_key, model=self.model)
        # Recheck after file upload / optional external AI call.
        self.require(token, action=True)
        record = {'id': record_id, 'student_uid': user['uid'], 'student_id': user['login_id'],
                  'name': user['name'], 'class_id': user['class_id'], 'course': course,
                  'assignment_id': assignment_id, 'assignment_title': task['title'], 'unit': task['unit'],
                  'text': text, 'file': file, 'feedback': feedback, 'teacher_feedback': '', 'created_at': now()}
        return self.store.append(path, record)

    def submissions(self, token: str, class_id: str, course: str | None = None) -> list[dict]:
        user = self._scope(token, class_id)
        rows = self.store.read_json(f'classes/{class_id}/submissions.enc', [], ttl=10)
        if course:
            checked_course(course)
            rows = [x for x in rows if x['course'] == course]
        if user['role'] == 'teacher':
            return rows
        allowed_share = {a['id'] for c in COURSES for a in self.assignments(token, c)
                         if a['share'] and class_id in a['classes']}
        visible = []
        for row in rows:
            if row['student_uid'] == user['uid']:
                visible.append(row)
            elif row['assignment_id'] in allowed_share:
                peer = copy.deepcopy(row)
                peer.pop('feedback', None)
                peer.pop('teacher_feedback', None)
                visible.append(peer)
        return visible

    def submission_download(self, token: str, class_id: str, submission_id: str) -> tuple[str, bytes]:
        self.require(token, action=True)
        row = next((x for x in self.submissions(token, class_id) if x['id'] == submission_id), None)
        if not row or not row.get('file'):
            raise AppError('이 제출물을 다운로드할 권한이 없거나 파일이 없습니다.')
        return row['file']['name'], self.store.read_bytes(row['file']['path'])

    def feedback_on_submission(self, token: str, class_id: str, submission_id: str, comment: str):
        self.require(token, teacher=True)
        checked_class(class_id)
        comment = text_value(comment, '교사 피드백', 5000)
        def change(rows):
            target = next((x for x in rows if x['id'] == submission_id), None)
            if target is None:
                raise AppError('제출물을 찾을 수 없습니다.')
            target['teacher_feedback'] = comment
            target['feedback_at'] = now()
            return rows
        self.store.mutate(f'classes/{class_id}/submissions.enc', [], change)

    def _student(self, token: str, student_id: str | None = None) -> dict:
        user = self.require(token)
        if user['role'] == 'student':
            if student_id and student_id != user['login_id']:
                raise AppError('다른 학생의 개인 기록은 열람할 수 없습니다.')
            return user
        target = next((x for x in self.auth.users(token) if x['login_id'] == student_id), None)
        if not target:
            raise AppError('학생을 선택하세요.')
        return target

    def notes(self, token: str, student_id: str | None = None) -> list[dict]:
        student = self._student(token, student_id)
        return self.store.read_json(f'students/{student["uid"]}/notes.enc', [], ttl=15)

    def save_note(self, token: str, *, course: str, unit: str, day: str, topic: str, answers: dict,
                  consent: bool = False, event_id: str | None = None) -> dict:
        student = self.require(token, action=True)
        if student['role'] != 'student':
            raise AppError('수다노트는 학생 계정에서 작성하세요.')
        checked_course(course)
        try:
            parsed = date.fromisoformat(day)
            if parsed > date.fromisoformat(today()):
                raise ValueError('future')
        except ValueError as exc:
            raise AppError('오늘 또는 이전 수업 날짜를 선택하세요.') from exc
        answers = {f: text_value(answers.get(f, ''), f, 2500, False) for f in NOTE_FIELDS}
        if not any(answers.values()):
            raise AppError('한 문항 이상에 자신의 생각을 적어 주세요.')
        topic = text_value(topic, '수업 주제', 150)
        path = f'students/{student["uid"]}/notes.enc'
        record_id = event_id or uid()
        previous = next((x for x in self.store.read_json(path, [], ttl=0) if x['id'] == record_id), None)
        if previous:
            return previous
        cfg = self.settings(token)
        feedback = make_feedback('\n'.join(k + ': ' + v for k, v in answers.items()), topic, '',
                                 enabled=cfg['ai_enabled'], consent=consent, api_key=self.api_key, model=self.model)
        self.require(token, action=True)
        record = {'id': record_id, 'student_id': student['login_id'], 'course': course,
                  'unit': text_value(unit, '단원', 80), 'day': day, 'topic': topic, 'answers': answers,
                  'created_at': now(), 'feedback': feedback, 'teacher_feedback': ''}
        return self.store.append(path, record)

    def feedback_on_note(self, token: str, student_id: str, note_id: str, comment: str):
        self.require(token, teacher=True)
        student = self._student(token, student_id)
        comment = text_value(comment, '교사 피드백', 5000)
        def change(rows):
            target = next((x for x in rows if x['id'] == note_id), None)
            if target is None:
                raise AppError('수다노트를 찾을 수 없습니다.')
            target['teacher_feedback'] = comment
            target['feedback_at'] = now()
            return rows
        self.store.mutate(f'students/{student["uid"]}/notes.enc', [], change)

    def questions(self, token: str, class_id: str) -> list[dict]:
        user = self._scope(token, class_id)
        rows = self.store.read_json(f'classes/{class_id}/questions.enc', [], ttl=10)
        return [x for x in rows if user['role'] == 'teacher' or x['student_uid'] == user['uid'] or x['shared']]

    def ask(self, token: str, *, course: str, title: str, body: str, shared: bool, event_id: str | None = None):
        user = self.require(token, action=True)
        if user['role'] != 'student':
            raise AppError('학생 계정으로 질문을 등록하세요.')
        checked_course(course)
        record = {'id': event_id or uid(), 'student_uid': user['uid'], 'student_id': user['login_id'],
                  'name': user['name'], 'class_id': user['class_id'], 'course': course,
                  'title': text_value(title, '질문 제목', 150), 'body': text_value(body, '질문 내용', 5000),
                  'shared': bool(shared), 'answer': '', 'created_at': now()}
        return self.store.append(f'classes/{user["class_id"]}/questions.enc', record)

    def answer(self, token: str, class_id: str, question_id: str, text: str):
        self.require(token, teacher=True)
        checked_class(class_id)
        text = text_value(text, '답변', 5000)
        def change(rows):
            target = next((x for x in rows if x['id'] == question_id), None)
            if not target:
                raise AppError('질문을 찾을 수 없습니다.')
            target['answer'] = text
            target['answered_at'] = now()
            return rows
        self.store.mutate(f'classes/{class_id}/questions.enc', [], change)

    def observations(self, token: str, class_id: str) -> list[dict]:
        self.require(token, teacher=True)
        checked_class(class_id)
        return self.store.read_json(f'classes/{class_id}/observations.enc', [], ttl=15)

    def add_observation(self, token: str, student_id: str, category: str, content: str, event_id: str | None = None):
        self.require(token, teacher=True)
        student = self._student(token, student_id)
        record = {'id': event_id or uid(), 'student_id': student_id, 'name': student['name'],
                  'class_id': student['class_id'], 'category': text_value(category, '관찰 영역', 100),
                  'content': text_value(content, '관찰 기록', 5000), 'created_at': now()}
        return self.store.append(f'classes/{student["class_id"]}/observations.enc', record)

    def points(self, token: str, class_id: str | None = None) -> list[dict]:
        user = self.require(token)
        rows = self.control()['points']
        if user['role'] == 'student':
            return [x for x in rows if x['student_uid'] == user['uid']]
        if class_id:
            checked_class(class_id)
        return [x for x in rows if class_id is None or x['class_id'] == class_id]

    def award(self, token: str, student_id: str, score: int, reason: str, event_id: str | None = None):
        self.require(token, teacher=True)
        if not isinstance(score, int) or score == 0 or not -20 <= score <= 20:
            raise AppError('상점·벌점은 1~20점으로 입력하세요.')
        student = self._student(token, student_id)
        record = {'id': event_id or uid(), 'student_uid': student['uid'], 'student_id': student_id,
                  'name': student['name'], 'class_id': student['class_id'], 'score': score,
                  'reason': text_value(reason, '부여 사유', 500), 'created_at': now()}
        def change(control):
            if not any(x['id'] == record['id'] for x in control['points']):
                control['points'].append(record)
            return control
        self.store.mutate('classroom/control.enc', DEFAULT_CONTROL, change)
        return record

    def profile(self, token: str, student_id: str | None = None) -> dict:
        student = self._student(token, student_id)
        return self.store.read_json(f'students/{student["uid"]}/profile.enc', {'intro': '', 'interests': ''}, ttl=30)

    def save_profile(self, token: str, intro: str, interests: str):
        user = self.require(token, action=True)
        if user['role'] != 'student':
            raise AppError('학생 계정에서 작성하세요.')
        data = {'intro': text_value(intro, '내 소개', 1500, False),
                'interests': text_value(interests, '관심 분야', 1500, False), 'updated_at': now()}
        self.store.mutate(f'students/{user["uid"]}/profile.enc', {}, lambda _: data)

    def seats(self, token: str, class_id: str) -> dict:
        user = self._scope(token, class_id)
        data = self.store.read_json(f'classes/{class_id}/seats.enc', {}, ttl=15)
        if user['role'] == 'student' and not data.get('published'):
            return {}
        return data

    def save_seats(self, token: str, class_id: str, rows: int, cols: int, seats: list[str], groups: dict, published: bool):
        self.require(token, teacher=True)
        checked_class(class_id)
        if not 1 <= rows <= 8 or not 1 <= cols <= 8 or len(seats) != rows * cols:
            raise AppError('좌석의 행·열 수를 확인하세요.')
        roster = {x['login_id']: x for x in self.auth.users(token, class_id) if x['active']}
        selected = [x for x in seats if x]
        if len(set(selected)) != len(selected):
            raise AppError('같은 학생을 여러 자리에 배치할 수 없습니다.')
        if not set(selected).issubset(roster) or not set(groups).issubset(roster):
            raise AppError('해당 학급의 재학생만 배치할 수 있습니다.')
        if any(not isinstance(v, int) or not 0 <= v <= 10 for v in groups.values()):
            raise AppError('모둠은 0(미배정)~10으로 입력하세요.')
        data = {'rows': rows, 'cols': cols, 'seats': seats, 'groups': groups,
                'names': {sid: roster[sid]['name'] for sid in roster}, 'published': bool(published), 'updated_at': now()}
        self.store.mutate(f'classes/{class_id}/seats.enc', {}, lambda _: data)
