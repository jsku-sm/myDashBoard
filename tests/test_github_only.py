"""GitHub HTTP adapter regression tests. These do NOT contact GitHub."""
from __future__ import annotations
import ast
from pathlib import Path
import pytest
import requests
from cryptography.fernet import Fernet
from backend import connect_github
from classroom import auth as auth_module, storage as storage_module
from classroom.auth import today
from classroom.storage import AppError
from fake_github import FakeGitHub

ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(storage_module.requests, 'request', fake.request)
    monkeypatch.setattr(storage_module.time, 'sleep', lambda _: None)
    monkeypatch.setattr(auth_module, 'ITERATIONS', 100_000)
    settings = dict(repo=fake.repo, token='TEST-TOKEN-NOT-A-REAL-SECRET',
                    encryption_key=Fernet.generate_key().decode(),
                    initial_password='TeacherSecret!1234')
    return fake, settings


def test_initial_teacher_written_as_encrypted_github_file(github):
    fake, args = github
    room = connect_github(**args)
    assert room.store.backend.mode == 'github'
    assert 'auth/users.enc' in fake.files
    encrypted = fake.files['auth/users.enc'][0]
    assert args['initial_password'].encode() not in encrypted
    assert b'teacher' not in encrypted
    teacher = room.login('teacher', args['initial_password'])
    assert room.require(teacher)['role'] == 'teacher'
    assert any(m == 'PUT' for m, _, _ in fake.calls)


def test_restart_reads_same_github_teacher_without_overwrite(github):
    fake, args = github
    first = connect_github(**args)
    first.login('teacher', args['initial_password'])
    before = dict(fake.files)
    second = connect_github(**{**args, 'initial_password': 'DifferentInitial!1234'})
    assert fake.files == before
    assert second.require(second.login('teacher', args['initial_password']))['role'] == 'teacher'
    with pytest.raises(AppError):
        second.login('teacher', 'DifferentInitial!1234')


def test_github_student_records_roundtrip_after_service_restart(github):
    fake, args = github
    room = connect_github(**args)
    teacher = room.login('teacher', args['initial_password'])
    issued = room.auth.add_students(teacher, [{'학번':'1101', '이름':'가상학생', '학급':'1-1'}])
    student = room.login('1101', issued[0]['임시비밀번호'])
    room.change_password(student, issued[0]['임시비밀번호'], 'StudentChanged!123')
    student = room.login('1101', 'StudentChanged!123')
    room.save_emotion(student, 'ready')
    note = room.save_note(student, course='math2', unit='도형의 방정식', day=today(),
                         topic='원의 중심', answers={'이해한 내용': '원의 중심을 좌표로 설명했다.'})
    room.add_observation(teacher, '1101', '수학적 설명', '원의 중심을 말로 설명함')
    room.award(teacher, '1101', 2, '생각을 설명했어요')
    room.save_seats(teacher, '1-1', 1, 1, ['1101'], {'1101': 1}, True)
    room.ask(student, course='math2', title='원 질문', body='원의 중심은 왜 이동하나요?', shared=False)
    room.save_profile(student, '내 소개', '수학 디자인')
    task = room.add_assignment(teacher, course='math2', unit='도형의 방정식', title='원 그리기',
                               description='원의 중심과 반지름을 설명하세요.', classes=['1-1'],
                               share=False, feedback_note='잘 제출했어요.')
    submission = room.submit(student, course='math2', assignment_id=task['id'], text='중심을 찾았어요.',
                             attachment=('test.txt', b'fictional homework'))
    room.set_lock(teacher, ['1-1'], True, '설명 시간')
    with pytest.raises(AppError, match='설명 시간'):
        room.save_profile(student, '잠금 중 저장', '실패해야 함')
    room.set_lock(teacher, ['1-1'], False, '')
    after = connect_github(**args)
    teacher2 = after.login('teacher', args['initial_password'])
    student2 = after.login('1101', 'StudentChanged!123')
    assert after.notes(student2)[0]['id'] == note['id']
    assert after.points(student2)[0]['score'] == 2
    assert after.seats(student2, '1-1')['seats'] == ['1101']
    assert after.observations(teacher2, '1-1')[0]['content'] == '원의 중심을 말로 설명함'
    assert after.profile(student2)['interests'] == '수학 디자인'
    assert after.questions(student2, '1-1')[0]['title'] == '원 질문'
    assert after.submission_download(student2, '1-1', submission['id'])[1] == b'fictional homework'
    assert after.dashboard(teacher2, '1-1', today())[0]['감정'] == '🤩 의욕 있어요'
    assert all(path.endswith('.enc') for path in fake.files)
    assert any(path.startswith('students/') and path.endswith('/notes.enc') for path in fake.files)
    assert all(b'fictional homework' not in item[0] for item in fake.files.values())


def test_public_repository_rejected_before_any_write(github):
    fake, args = github
    fake.private = False
    with pytest.raises(AppError, match='Private'):
        connect_github(**args)
    assert not fake.files
    assert not any(m == 'PUT' for m, _, _ in fake.calls)


@pytest.mark.parametrize('name', ['repo', 'token', 'encryption_key'])
def test_missing_settings_do_not_contact_github(github, name):
    fake, args = github
    args[name] = ''
    with pytest.raises(AppError, match='Secrets'):
        connect_github(**args)
    assert not fake.calls


def test_invalid_key_checked_before_network(github):
    fake, args = github
    args['encryption_key'] = 'not-an-encryption-key'
    with pytest.raises(AppError, match='ENCRYPTION_KEY'):
        connect_github(**args)
    assert not fake.calls


def test_wrong_key_cannot_overwrite_existing_data(github):
    fake, args = github
    connect_github(**args)
    before = dict(fake.files)
    with pytest.raises(AppError, match='암호화키'):
        connect_github(**{**args, 'encryption_key': Fernet.generate_key().decode()})
    assert fake.files == before


def test_expired_token_is_not_replaced_with_local_storage(github):
    fake, args = github
    fake.reject_status = 401
    with pytest.raises(AppError, match='토큰'):
        connect_github(**args)
    assert not fake.files


def test_network_error_is_not_replaced_with_local_storage(github):
    fake, args = github
    fake.failure = requests.ConnectionError('simulated network failure')
    with pytest.raises(AppError, match='임시 저장으로 대체하지 않았습니다'):
        connect_github(**args)
    assert not fake.files


def test_missing_branch_reported_without_creating_wrong_branch(github):
    fake, args = github
    fake.branch_exists = False
    with pytest.raises(AppError, match='브랜치'):
        connect_github(**args)
    assert not fake.files


def test_raw_download_for_large_encrypted_file(github):
    _, args = github
    room = connect_github(**args)
    data = b'A' * (1024 * 1024 + 1)
    room.store.write_bytes('files/large-test.enc', data)
    assert room.store.read_bytes('files/large-test.enc') == data


def test_no_database_import_or_dependency_in_release():
    banned = {'supabase','gotrue','postgrest','firebase','firebase_admin','sqlalchemy'}
    for path in ROOT.rglob('*.py'):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else (
                [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
            assert not any(name.split('.')[0] in banned for name in names), str(path)
    deps = (ROOT/'requirements.txt').read_text().lower()
    assert all(name not in deps for name in banned)


def test_both_entrypoints_route_to_same_github_application():
    for name in ('app.py', 'streamlit_app.py'):
        source = (ROOT/name).read_text()
        assert 'from classroom.application import main' in source
        assert 'main()' in source
        assert 'from backend import sign_in' not in source
    source = (ROOT/'classroom/application.py').read_text()
    assert 'st.navigation(' in source
    assert 'LocalBackend' not in source
    assert 'LocalBackend' not in (ROOT/'backend.py').read_text()
