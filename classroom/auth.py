"""PBKDF2 passwords, server-side sessions, revocation, and login throttling."""
from __future__ import annotations
import copy
import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from .storage import AppError

KST = ZoneInfo('Asia/Seoul')
CLASSES = [f'1-{n}' for n in range(1, 8)]
ITERATIONS = 600_000


def now() -> str:
    return datetime.now(KST).isoformat(timespec='seconds')


def today() -> str:
    return datetime.now(KST).date().isoformat()


def uid() -> str:
    return secrets.token_hex(16)


def password_hash(password: str) -> str:
    if not isinstance(password, str) or not 10 <= len(password) <= 128:
        raise AppError('비밀번호는 10~128자로 입력하세요.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        alg, rounds, salt, expected = encoded.split('$')
        if alg != 'pbkdf2_sha256' or not 100_000 <= int(rounds) <= 2_000_000 or len(password) > 128:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def safe_user(user: dict) -> dict:
    return {k: v for k, v in user.items() if k not in ('password_hash', 'auth_version')}


class Auth:
    def __init__(self, store):
        self.store = store
        self.sessions: dict[str, dict] = {}
        self.failures: dict[str, list[float]] = {}
        self.lock = threading.RLock()
        self.dummy = password_hash(secrets.token_urlsafe(20))

    def bootstrap(self, login_id: str, password: str):
        if self.store.read_json('auth/users.enc', {}, ttl=0):
            return
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,30}', login_id):
            raise AppError('교사 아이디는 영문·숫자·밑줄·하이픈 3~30자로 설정하세요.')
        if len(password) < 12:
            raise AppError('최초 교사 비밀번호는 12자 이상으로 설정하세요.')
        record = {'uid': uid(), 'login_id': login_id, 'name': '구쌤', 'class_id': '', 'role': 'teacher',
                  'password_hash': password_hash(password), 'auth_version': 1, 'active': True,
                  'must_change': False, 'created_at': now()}
        self.store.mutate('auth/users.enc', {}, lambda users: users or {login_id: record})

    def login(self, login_id: str, password: str) -> str:
        login_id = login_id.strip()
        with self.lock:
            t = time.monotonic()
            self.failures = {k: [x for x in v if t - x < 300] for k, v in self.failures.items() if any(t - x < 300 for x in v)}
            attempts = self.failures.setdefault(login_id, [])
            if len(attempts) >= 5:
                raise AppError('로그인 시도가 반복되었습니다. 5분 후 다시 시도하세요.')
            users = self.store.read_json('auth/users.enc', {}, ttl=20)
            user = users.get(login_id)
            good = verify_password(password, user['password_hash'] if user else self.dummy)
            if not user or not user.get('active') or not good:
                attempts.append(t)
                raise AppError('학번(교사 아이디) 또는 비밀번호를 확인하세요.')
            self.failures.pop(login_id, None)
            self.sessions = {k: v for k, v in self.sessions.items() if time.time() - v['created'] < 8 * 3600}
            token = secrets.token_urlsafe(32)
            self.sessions[token] = {'login_id': login_id, 'version': user['auth_version'],
                                    'created': time.time(), 'last_seen': time.time(), 'login_at': now()}
            return token

    def require(self, token: str, teacher: bool = False) -> dict:
        with self.lock:
            session = self.sessions.get(token)
            if not session or time.time() - session['created'] > 8 * 3600:
                self.sessions.pop(token, None)
                raise AppError('로그인이 만료되었습니다. 다시 로그인하세요.')
            user = self.store.read_json('auth/users.enc', {}, ttl=20).get(session['login_id'])
            if not user or not user.get('active') or session['version'] != user['auth_version']:
                self.sessions.pop(token, None)
                raise AppError('계정 정보가 변경되었습니다. 다시 로그인하세요.')
            if teacher and user['role'] != 'teacher':
                raise AppError('교사만 사용할 수 있는 기능입니다.')
            session['last_seen'] = time.time()
            return safe_user(user)

    def logout(self, token: str):
        with self.lock:
            self.sessions.pop(token, None)

    def users(self, token: str, class_id: str | None = None) -> list[dict]:
        self.require(token, teacher=True)
        users = self.store.read_json('auth/users.enc', {}, ttl=20)
        return sorted([safe_user(u) for u in users.values() if u['role'] == 'student' and
                       (class_id is None or u['class_id'] == class_id)], key=lambda u: u['login_id'])

    def active_ids(self) -> set[str]:
        with self.lock:
            return {s['login_id'] for s in self.sessions.values() if time.time() - s['last_seen'] < 20}

    def add_students(self, token: str, rows: list[dict]) -> list[dict]:
        self.require(token, teacher=True)
        if not rows or len(rows) > 250:
            raise AppError('한 번에 1~250명을 등록하세요.')
        records = {}
        issued = []
        for row in rows:
            sid = str(row.get('학번', '')).strip()
            name = str(row.get('이름', '')).strip()
            cls = str(row.get('학급', '')).strip()
            if not re.fullmatch(r'\d{4,12}', sid) or not name or len(name) > 30 or cls not in CLASSES:
                raise AppError('학번(4~12자리 숫자), 이름, 학급(1-1~1-7)을 확인하세요.')
            if sid in records:
                raise AppError(f'명렬에 중복 학번이 있습니다: {sid}')
            password = 'Gs!' + secrets.token_urlsafe(9)
            records[sid] = {'uid': uid(), 'login_id': sid, 'name': name, 'class_id': cls, 'role': 'student',
                            'password_hash': password_hash(password), 'auth_version': 1, 'active': True,
                            'must_change': True, 'created_at': now()}
            issued.append({'학번': sid, '이름': name, '학급': cls, '임시비밀번호': password})
        def change(users):
            overlap = set(users) & set(records)
            if overlap:
                raise AppError('이미 등록된 학번이 있습니다: ' + ', '.join(sorted(overlap)[:8]) + '. 기존 계정은 덮어쓰지 않았습니다.')
            users.update(records)
            return users
        self.store.mutate('auth/users.enc', {}, change)
        return issued

    def change_password(self, token: str, old: str, new: str):
        user = self.require(token)
        new_hash = password_hash(new)
        if new == old:
            raise AppError('현재 비밀번호와 다른 비밀번호를 입력하세요.')
        def change(users):
            target = users[user['login_id']]
            if not verify_password(old, target['password_hash']):
                raise AppError('현재 비밀번호가 올바르지 않습니다.')
            target['password_hash'] = new_hash
            target['must_change'] = False
            target['auth_version'] += 1
            return users
        self.store.mutate('auth/users.enc', {}, change)
        self.logout(token)

    def reset_password(self, token: str, student_id: str) -> str:
        self.require(token, teacher=True)
        password = 'Gs!' + secrets.token_urlsafe(9)
        new_hash = password_hash(password)
        def change(users):
            target = users.get(student_id)
            if not target or target['role'] != 'student':
                raise AppError('학생 계정을 선택하세요.')
            target.update(password_hash=new_hash, must_change=True, auth_version=target['auth_version'] + 1)
            return users
        self.store.mutate('auth/users.enc', {}, change)
        return password

    def set_active(self, token: str, student_id: str, active: bool):
        self.require(token, teacher=True)
        def change(users):
            target = users.get(student_id)
            if not target or target['role'] != 'student':
                raise AppError('학생 계정을 선택하세요.')
            target['active'] = bool(active)
            target['auth_version'] += 1
            return users
        self.store.mutate('auth/users.enc', {}, change)
