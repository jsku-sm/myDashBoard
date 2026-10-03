"""Encrypted file persistence. No SQL, Firebase, or Supabase.

GitHub mode never falls back to a temporary local disk. Writes use optimistic
SHA checks and a process-wide lock; JSON mutations are retried on conflicts.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
import requests
from cryptography.fernet import Fernet, InvalidToken


class AppError(Exception):
    """A safe, user-displayable error."""


class Conflict(AppError):
    pass


def valid_path(path: str) -> str:
    if not path or path.startswith('/') or '\\' in path or any(p in ('', '.', '..') for p in path.split('/')):
        raise AppError('저장 경로가 올바르지 않습니다.')
    return path


class LocalBackend:
    """Explicit local demonstration only. Not production persistence."""
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.mode = 'demo'

    def read(self, path: str) -> tuple[bytes | None, str | None]:
        p = self.root / valid_path(path)
        with self.lock:
            if not p.exists():
                return None, None
            data = p.read_bytes()
            return data, hashlib.sha256(data).hexdigest()

    def write(self, path: str, data: bytes, sha: str | None) -> str:
        p = self.root / valid_path(path)
        with self.lock:
            _, current_sha = self.read(path)
            if sha != current_sha:
                raise Conflict('동시 저장 충돌')
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.with_suffix('.tmp')
            temp.write_bytes(data)
            os.replace(temp, p)
            return hashlib.sha256(data).hexdigest()


class GitHubBackend:
    def __init__(self, token: str, repo: str, branch: str = 'main'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
            raise AppError('GITHUB_REPO는 아이디/저장소이름 형식이어야 합니다.')
        if not token or not branch:
            raise AppError('GitHub 토큰과 브랜치를 확인해 주세요.')
        self.base = f'https://api.github.com/repos/{repo}'
        self.branch = branch
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28'}
        self.lock = threading.RLock()
        self.mode = 'github'
        self.repo = repo
        self.last_write = 0.0
        self.private_checked = 0.0
        self.remaining = None
        self.check_private()

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = dict(self.headers)
        headers.update(kwargs.pop('headers', {}))
        # Deliberately do not retry a PUT on a timeout: it may already be committed.
        try:
            response = requests.request(method, url, headers=headers, timeout=(8, 35), **kwargs)
        except requests.RequestException as exc:
            raise AppError('GitHub 연결이 끊겼습니다. 저장 완료 여부를 다시 확인한 뒤 재시도하세요. 임시 저장으로 대체하지 않았습니다.') from exc
        self.remaining = response.headers.get('X-RateLimit-Remaining', self.remaining)
        if response.status_code in (403, 429):
            raise AppError('GitHub 접근 권한 또는 API 사용 한도에 문제가 있습니다. 토큰 권한·만료일·사용량을 확인하세요.')
        if response.status_code == 401:
            raise AppError('GitHub 토큰이 유효하지 않거나 만료되었습니다.')
        if response.status_code >= 500:
            raise AppError('GitHub 서버 오류입니다. 작성 내용을 보관하고 다시 시도하세요.')
        return response

    def check_private(self):
        if self.private_checked and time.monotonic() - self.private_checked < 60:
            return
        r = self.request('GET', self.base)
        if r.status_code != 200:
            raise AppError('데이터 저장소를 찾을 수 없습니다. 저장소 이름과 토큰 접근 범위를 확인하세요.')
        if not r.json().get('private'):
            raise AppError('학생 정보 보호를 위해 데이터 저장소는 반드시 Private이어야 합니다. 공개 저장소에는 저장하지 않습니다.')
        self.private_checked = time.monotonic()

    def read(self, path: str) -> tuple[bytes | None, str | None]:
        url = self.base + '/contents/' + quote(valid_path(path), safe='/')
        r = self.request('GET', url, params={'ref': self.branch})
        if r.status_code == 404:
            # A missing file is normal; a missing repository/branch is not.
            self.check_private()
            b = self.request('GET', self.base + '/branches/' + quote(self.branch, safe=''))
            if b.status_code != 200:
                raise AppError('데이터 저장소에 지정한 브랜치가 없습니다. README를 추가해 main 브랜치를 먼저 생성하세요.')
            return None, None
        if r.status_code != 200 or not isinstance(r.json(), dict):
            raise AppError('GitHub 파일을 읽을 수 없습니다.')
        obj = r.json()
        sha = obj.get('sha')
        if obj.get('encoding') == 'base64':
            return base64.b64decode(obj['content']), sha
        # The contents endpoint omits base64 for files larger than 1 MB.
        raw = self.request('GET', url, params={'ref': self.branch}, headers={'Accept': 'application/vnd.github.raw+json'})
        if raw.status_code != 200:
            raise AppError('첨부파일을 읽지 못했습니다.')
        return raw.content, sha

    def write(self, path: str, data: bytes, sha: str | None) -> str:
        with self.lock:
            self.check_private()
            # GitHub recommends serial content writes. Leave >= 1 second between PUTs.
            gap = 1.05 - (time.monotonic() - self.last_write)
            if gap > 0:
                time.sleep(gap)
            body = {'message': 'Classroom encrypted data update', 'branch': self.branch,
                    'content': base64.b64encode(data).decode('ascii')}
            if sha:
                body['sha'] = sha
            r = self.request('PUT', self.base + '/contents/' + quote(valid_path(path), safe='/'), json=body)
            self.last_write = time.monotonic()
            if r.status_code in (409, 422):
                raise Conflict('동시 저장 충돌 또는 저장소 쓰기 제한입니다.')
            if r.status_code not in (200, 201):
                raise AppError('GitHub에 저장하지 못했습니다. 토큰의 Contents 쓰기 권한과 브랜치 보호 규칙을 확인하세요.')
            return r.json()['content']['sha']


class EncryptedStore:
    def __init__(self, backend, key: str):
        self.backend = backend
        try:
            self.cipher = Fernet(key.encode('ascii'))
        except (ValueError, UnicodeError) as exc:
            raise AppError('ENCRYPTION_KEY가 올바르지 않습니다. scripts/make_key.py로 생성하세요.') from exc
        self.cache: dict[str, tuple[float, Any]] = {}
        self.lock = threading.RLock()

    def _decode(self, data: bytes) -> bytes:
        try:
            return self.cipher.decrypt(data)
        except InvalidToken as exc:
            raise AppError('암호화키가 기존 데이터와 다릅니다. 원래 ENCRYPTION_KEY를 복구하세요. 데이터를 덮어쓰지 않았습니다.') from exc

    def read_json(self, path: str, default: Any = None, ttl: float = 15) -> Any:
        # Single-flight cache: 25 student sessions share one cached control read.
        with self.lock:
            cached = self.cache.get(path)
            if ttl > 0 and cached and time.monotonic() - cached[0] < ttl:
                return copy.deepcopy(cached[1])
            data, _ = self.backend.read(path)
            if data is None:
                value = copy.deepcopy(default)
            else:
                try:
                    value = json.loads(self._decode(data))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise AppError('저장 파일 형식이 손상되었습니다. 관리자 확인이 필요합니다.') from exc
            self.cache[path] = (time.monotonic(), copy.deepcopy(value))
            return value

    def mutate(self, path: str, default: Any, change: Callable[[Any], Any]) -> Any:
        """change must be repeatable; generate event IDs before calling mutate."""
        with self.lock:
            for attempt in range(5):
                data, sha = self.backend.read(path)
                value = copy.deepcopy(default) if data is None else json.loads(self._decode(data))
                result = change(value)
                payload = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                # Refuse silent overwrites on any failure.
                try:
                    self.backend.write(path, self.cipher.encrypt(payload), sha)
                except Conflict:
                    self.cache.pop(path, None)
                    if attempt == 4:
                        raise AppError('여러 사용자가 동시에 저장 중입니다. 작성 내용은 화면에 남아 있으니 잠시 후 다시 저장하세요.')
                    time.sleep(0.15 * (attempt + 1))
                    continue
                self.cache[path] = (time.monotonic(), copy.deepcopy(result))
                return copy.deepcopy(result)
        raise AppError('저장에 실패했습니다.')

    def append(self, path: str, event: dict) -> dict:
        def change(items):
            if not any(x.get('id') == event['id'] for x in items):
                items.append(copy.deepcopy(event))
            return items
        self.mutate(path, [], change)
        return event

    def write_bytes(self, path: str, data: bytes):
        with self.lock:
            self.backend.write(path, self.cipher.encrypt(data), None)

    def read_bytes(self, path: str) -> bytes:
        data, _ = self.backend.read(path)
        if data is None:
            raise AppError('첨부파일이 없습니다.')
        return self._decode(data)
