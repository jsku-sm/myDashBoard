from __future__ import annotations
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from cryptography.fernet import Fernet
from classroom import auth as auth_module
from classroom.auth import now, today, password_hash, verify_password
from classroom.feedback import make_feedback
from classroom.service import Classroom, DEFAULT_SETTINGS
from classroom.storage import AppError, Conflict, EncryptedStore, LocalBackend, GitHubBackend, valid_path


@pytest.fixture
def room(tmp_path, monkeypatch):
    # Exercise the same PBKDF2 format with fewer rounds to speed up repeated tests.
    # test_password_production_iterations verifies the shipped 600,000-round default.
    monkeypatch.setattr(auth_module, 'ITERATIONS', 100_000)
    key = Fernet.generate_key().decode()
    store = EncryptedStore(LocalBackend(tmp_path), key)
    svc = Classroom(store)
    svc.auth.bootstrap('teacher', 'TeacherSecret!1234')
    teacher = svc.login('teacher', 'TeacherSecret!1234')
    issued = svc.auth.add_students(teacher, [
        {'학번': '1101', '이름': '가상학생가', '학급': '1-1'},
        {'학번': '1102', '이름': '가상학생나', '학급': '1-1'},
        {'학번': '1201', '이름': '가상학생다', '학급': '1-2'}])
    def approve(users):
        for u in users.values(): u['must_change'] = False
        return users
    store.mutate('auth/users.enc', {}, approve)
    tokens = {row['학번']: svc.login(row['학번'], row['임시비밀번호']) for row in issued}
    return svc, teacher, tokens, issued, tmp_path, key


def task(svc, teacher, share=False):
    return svc.add_assignment(teacher, course='math2', unit='도형의 방정식', title='원 그리기',
        description='중심과 반지름으로 원을 나타내고 이유를 설명하세요.', classes=['1-1'],
        share=share, feedback_note='중심과 반지름을 다시 확인해 보세요.')


def submit(svc, student, assignment):
    return svc.submit(student, course='math2', assignment_id=assignment['id'],
        text='중심과 반지름을 먼저 찾았습니다.', attachment=('내과제.txt', b'example assignment'))


def test_password_production_iterations():
    hashed = password_hash('SafePassword!123')
    assert hashed.startswith('pbkdf2_sha256$600000$')
    assert verify_password('SafePassword!123', hashed)
    assert not verify_password('wrong', hashed)
    assert password_hash('SafePassword!123') != hashed


def test_password_policy():
    with pytest.raises(AppError): password_hash('short')
    assert not verify_password('a', 'broken')


def test_accounts_separate_encrypted_file(room):
    svc, teacher, tokens, issued, root, key = room
    encrypted = (root / 'auth/users.enc').read_bytes()
    assert '가상학생'.encode() not in encrypted
    assert issued[0]['임시비밀번호'].encode() not in encrypted
    decrypted = svc.store.read_json('auth/users.enc', {})
    assert decrypted['1101']['role'] == 'student'
    assert 'password' not in decrypted['1101']
    assert 'password_hash' not in svc.require(tokens['1101'])


def test_initial_password_must_change(room):
    svc, teacher, tokens, *_ = room
    rows = svc.auth.add_students(teacher, [{'학번': '1301', '이름': '신규학생', '학급': '1-3'}])
    token = svc.login('1301', rows[0]['임시비밀번호'])
    with pytest.raises(AppError, match='먼저 변경'): svc.save_emotion(token, 'happy')
    svc.change_password(token, rows[0]['임시비밀번호'], 'NewPassword!123')
    with pytest.raises(AppError): svc.require(token)
    new = svc.login('1301', 'NewPassword!123')
    svc.save_emotion(new, 'happy')


def test_password_change_and_revocation(room):
    svc, teacher, tokens, issued, *_ = room
    old = issued[0]['임시비밀번호']
    second_session = svc.login('1101', old)
    svc.change_password(tokens['1101'], old, 'ChangedPassword!123')
    with pytest.raises(AppError): svc.require(second_session)
    with pytest.raises(AppError): svc.login('1101', old)
    assert svc.require(svc.login('1101', 'ChangedPassword!123'))['login_id'] == '1101'


def test_reset_password_revokes_sessions(room):
    svc, teacher, tokens, *_ = room
    new = svc.auth.reset_password(teacher, '1101')
    with pytest.raises(AppError): svc.require(tokens['1101'])
    assert svc.require(svc.login('1101', new))['must_change']


def test_disabled_student_cannot_continue(room):
    svc, teacher, tokens, *_ = room
    svc.auth.set_active(teacher, '1101', False)
    with pytest.raises(AppError): svc.require(tokens['1101'])


def test_login_throttle(room):
    svc, *_ = room
    for _ in range(5):
        with pytest.raises(AppError): svc.login('invalid-user', 'bad')
    with pytest.raises(AppError, match='5분'): svc.login('invalid-user', 'bad')


def test_duplicate_roster_does_not_overwrite(room):
    svc, teacher, tokens, *_ = room
    before = svc.store.read_json('auth/users.enc', {})['1101']
    with pytest.raises(AppError):
        svc.auth.add_students(teacher, [{'학번': '1101', '이름': '덮어쓰기', '학급': '1-2'}])
    assert svc.store.read_json('auth/users.enc', {})['1101'] == before


def test_teacher_features_denied_to_student(room):
    svc, teacher, t, *_ = room
    for call in [lambda: svc.dashboard(t['1101'], '1-1', today()),
                 lambda: svc.auth.users(t['1101']), lambda: svc.observations(t['1101'], '1-1'),
                 lambda: svc.set_lock(t['1101'], ['all'], True, '잠금'),
                 lambda: svc.award(t['1101'], '1102', 1, '사유'),
                 lambda: svc.save_settings(t['1101'], DEFAULT_SETTINGS)]:
        with pytest.raises(AppError): call()


def test_mood_and_login_stats(room):
    svc, teacher, t, *_ = room
    svc.save_emotion(t['1101'], 'happy')
    svc.save_emotion(t['1101'], 'calm')
    rows = svc.dashboard(teacher, '1-1', today())
    assert len(rows) == 2
    first = next(x for x in rows if x['학번'] == '1101')
    assert first['감정'] == '😌 편안해요'
    assert first['접속 상태'] == '접속 중'
    svc.auth.logout(t['1101'])
    assert svc.dashboard(teacher, '1-1', today())[0]['접속 상태'] == '접속 이력 있음'


def test_lock_blocks_mutations_and_unlock_restores(room):
    svc, teacher, t, *_ = room
    svc.set_lock(teacher, ['1-1'], True, '설명 시간')
    assert svc.monitor(t['1101'])['locked']
    assert not svc.monitor(t['1201'])['locked']
    with pytest.raises(AppError, match='설명 시간'): svc.save_emotion(t['1101'], 'happy')
    with pytest.raises(AppError): svc.save_profile(t['1101'], '소개', '관심')
    svc.set_lock(teacher, ['1-1'], False, '')
    svc.save_emotion(t['1101'], 'happy')


def test_global_lock_wins_over_class_unlock(room):
    svc, teacher, t, *_ = room
    svc.set_lock(teacher, ['all'], True, '전체 설명')
    svc.set_lock(teacher, ['1-1'], False, '')
    assert svc.monitor(t['1101'])['locked']
    svc.set_lock(teacher, ['all'], False, '')
    assert not svc.monitor(t['1101'])['locked']


def test_material_permissions_and_encrypted_attachment(room):
    svc, teacher, t, issued, root, key = room
    material = svc.add_material(teacher, course='math1', unit='다항식', kind='학습지',
        title='연습', body='', classes=['1-1'], attachment=('학습지.txt', b'PRIVATE DOCUMENT'))
    assert len(svc.materials(t['1101'], 'math1')) == 1
    assert not svc.materials(t['1201'], 'math1')
    filename, data = svc.material_download(t['1101'], 'math1', material['id'])
    assert data == b'PRIVATE DOCUMENT'
    assert b'PRIVATE DOCUMENT' not in (root / material['file']['path']).read_bytes()
    with pytest.raises(AppError): svc.material_download(t['1201'], 'math1', material['id'])
    svc.set_lock(teacher, ['1-1'], True, '')
    with pytest.raises(AppError): svc.material_download(t['1101'], 'math1', material['id'])


def test_archived_material_not_visible(room):
    svc, teacher, t, *_ = room
    material = svc.add_material(teacher, course='math1', unit='공통', kind='평가계획',
        title='평가', body='계획', classes=['1-1'])
    svc.archive_material(teacher, 'math1', material['id'])
    assert not svc.materials(t['1101'], 'math1')


def test_upload_rejects_html_and_oversize(room):
    svc, teacher, t, *_ = room
    a = task(svc, teacher)
    with pytest.raises(AppError): svc.submit(t['1101'], course='math2', assignment_id=a['id'], text='', attachment=('x.html', b'<script>1</script>'))
    with pytest.raises(AppError): svc.submit(t['1101'], course='math2', assignment_id=a['id'], text='', attachment=('x.txt', b'x' * (8 * 1024 * 1024 + 1)))


def test_private_submission_and_feedback_receipt(room):
    svc, teacher, t, *_ = room
    a = task(svc, teacher)
    entry = submit(svc, t['1101'], a)
    assert entry['feedback']['mode'] == '제출 확인'
    assert '중심과 반지름' in entry['feedback']['text']
    assert not svc.submissions(t['1102'], '1-1')
    assert len(svc.submissions(teacher, '1-1')) == 1
    with pytest.raises(AppError): svc.submission_download(t['1102'], '1-1', entry['id'])
    with pytest.raises(AppError): svc.submissions(t['1201'], '1-1')


def test_shared_submission_does_not_share_personal_feedback(room):
    svc, teacher, t, *_ = room
    a = task(svc, teacher, share=True)
    entry = submit(svc, t['1101'], a)
    svc.feedback_on_submission(teacher, '1-1', entry['id'], '개인 피드백')
    peer = svc.submissions(t['1102'], '1-1')[0]
    assert 'teacher_feedback' not in peer and 'feedback' not in peer
    assert svc.submission_download(t['1102'], '1-1', entry['id'])[1] == b'example assignment'
    svc.set_assignment_share(teacher, 'math2', a['id'], False)
    assert not svc.submissions(t['1102'], '1-1')


def test_submission_idempotency(room):
    svc, teacher, t, *_ = room
    a = task(svc, teacher)
    for _ in range(2):
        svc.submit(t['1101'], course='math2', assignment_id=a['id'], text='같은 제출', event_id='request001')
    assert len(svc.submissions(t['1101'], '1-1')) == 1


def test_student_cannot_submit_other_class_assignment(room):
    svc, teacher, t, *_ = room
    a = task(svc, teacher)
    with pytest.raises(AppError): svc.submit(t['1201'], course='math2', assignment_id=a['id'], text='무단 제출')


def test_notes_are_student_specific_and_teacher_can_reply(room):
    svc, teacher, t, issued, root, key = room
    note = svc.save_note(t['1101'], course='math2', unit='집합과 명제', day=today(), topic='집합 연산',
                        answers={'이해한 내용': '합집합은 두 집합의 원소를 모은 것입니다.'})
    student_uid = svc.require(t['1101'])['uid']
    assert (root / f'students/{student_uid}/notes.enc').exists()
    assert not svc.notes(t['1102'])
    with pytest.raises(AppError): svc.notes(t['1102'], '1101')
    svc.feedback_on_note(teacher, '1101', note['id'], '중복되는 원소를 어떻게 처리하는지도 생각해 봅시다.')
    assert '중복' in svc.notes(t['1101'])[0]['teacher_feedback']


def test_observations_are_teacher_only(room):
    svc, teacher, t, *_ = room
    svc.add_observation(teacher, '1101', '성장', '스스로 식을 수정함')
    assert svc.observations(teacher, '1-1')[0]['content'] == '스스로 식을 수정함'
    with pytest.raises(AppError): svc.observations(t['1101'], '1-1')


def test_points_and_live_events_only_for_target(room):
    svc, teacher, t, *_ = room
    svc.award(teacher, '1101', 2, '생각을 자세히 설명함', event_id='award1')
    svc.award(teacher, '1101', 2, '생각을 자세히 설명함', event_id='award1')
    svc.award(teacher, '1101', -1, '사전 안내한 수업 규칙', event_id='award2')
    assert sum(x['score'] for x in svc.points(t['1101'])) == 1
    assert len(svc.monitor(t['1101'])['events']) == 2
    assert not svc.monitor(t['1102'])['events']
    assert not svc.points(t['1102'])


def test_private_and_shared_questions(room):
    svc, teacher, t, *_ = room
    q = svc.ask(t['1101'], course='math1', title='질문', body='왜 그런가요?', shared=False)
    assert not svc.questions(t['1102'], '1-1')
    svc.answer(teacher, '1-1', q['id'], '조건을 확인해 보세요.')
    assert svc.questions(t['1101'], '1-1')[0]['answer']
    svc.ask(t['1101'], course='math1', title='공개 질문', body='함께 생각해 볼까요?', shared=True)
    assert len(svc.questions(t['1102'], '1-1')) == 1


def test_seats_publish_and_duplicates(room):
    svc, teacher, t, *_ = room
    svc.save_seats(teacher, '1-1', 1, 2, ['1101', '1102'], {'1101': 1, '1102': 1}, False)
    assert not svc.seats(t['1101'], '1-1')
    with pytest.raises(AppError): svc.save_seats(teacher, '1-1', 1, 2, ['1101', '1101'], {}, True)
    svc.save_seats(teacher, '1-1', 1, 2, ['1101', '1102'], {}, True)
    assert svc.seats(t['1101'], '1-1')['seats'] == ['1101', '1102']
    with pytest.raises(AppError): svc.seats(t['1201'], '1-1')


def test_profile_privacy(room):
    svc, teacher, t, *_ = room
    svc.save_profile(t['1101'], '내 소개', '수학')
    assert svc.profile(teacher, '1101')['interests'] == '수학'
    with pytest.raises(AppError): svc.profile(t['1102'], '1101')


def test_settings_reject_script_urls_and_ai_without_key(room):
    svc, teacher, t, *_ = room
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings['tools'][0]['url'] = 'javascript:alert(1)'
    with pytest.raises(AppError): svc.save_settings(teacher, settings)
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings['ai_enabled'] = True
    with pytest.raises(AppError): svc.save_settings(teacher, settings)


def test_ai_off_never_calls_network(monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('No network allowed')
    monkeypatch.setattr('classroom.feedback.requests.post', forbidden)
    for enabled, consent in [(False, True), (True, False)]:
        result = make_feedback('내용', '주제', '', enabled=enabled, consent=consent, api_key='key', model='model')
        assert result['mode'] == '제출 확인'


def test_ai_failure_preserves_receipt(monkeypatch):
    import requests
    def failure(*args, **kwargs): raise requests.Timeout('timeout')
    monkeypatch.setattr('classroom.feedback.requests.post', failure)
    result = make_feedback('내용', '주제', '', enabled=True, consent=True, api_key='key', model='model')
    assert result['mode'] == '제출 확인'
    assert '연결이 원활하지' in result['text']


def test_store_25_simultaneous_appends_no_loss(tmp_path):
    store = EncryptedStore(LocalBackend(tmp_path), Fernet.generate_key().decode())
    with ThreadPoolExecutor(max_workers=25) as pool:
        list(pool.map(lambda n: store.append('data.enc', {'id': str(n), 'value': n}), range(25)))
    assert len(store.read_json('data.enc', [])) == 25
    assert sum(x['value'] for x in store.read_json('data.enc', [])) == sum(range(25))


def test_store_retries_sha_conflict(tmp_path):
    class ConflictingBackend(LocalBackend):
        failures = 0
        def write(self, path, data, sha):
            self.failures += 1
            if self.failures <= 2: raise Conflict('simulated')
            return super().write(path, data, sha)
    backend = ConflictingBackend(tmp_path)
    store = EncryptedStore(backend, Fernet.generate_key().decode())
    store.append('test.enc', {'id': 'one'})
    assert backend.failures == 3
    assert store.read_json('test.enc') == [{'id': 'one'}]


def test_wrong_key_does_not_overwrite(tmp_path):
    backend = LocalBackend(tmp_path)
    first = EncryptedStore(backend, Fernet.generate_key().decode())
    first.append('test.enc', {'id': 'secret'})
    original = (tmp_path / 'test.enc').read_bytes()
    wrong = EncryptedStore(backend, Fernet.generate_key().decode())
    with pytest.raises(AppError, match='암호화키'): wrong.append('test.enc', {'id': 'overwrite'})
    assert (tmp_path / 'test.enc').read_bytes() == original


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', 'a/../b', 'a//b', 'a\\b'])
def test_reject_path_traversal(path):
    with pytest.raises(AppError): valid_path(path)


def test_github_requires_private_repository(monkeypatch):
    class Response:
        status_code = 200
        headers = {}
        def json(self): return {'private': False}
    monkeypatch.setattr('classroom.storage.requests.request', lambda *args, **kwargs: Response())
    with pytest.raises(AppError, match='Private'): GitHubBackend('token', 'owner/repo')


def test_github_network_error_has_no_local_fallback(monkeypatch):
    import requests
    def down(*args, **kwargs): raise requests.Timeout('offline')
    monkeypatch.setattr('classroom.storage.requests.request', down)
    with pytest.raises(AppError, match='임시 저장으로 대체하지 않았습니다'): GitHubBackend('token', 'owner/repo')
