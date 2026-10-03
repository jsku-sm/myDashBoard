"""In-memory HTTP substitute for tests, not a production storage option."""
from __future__ import annotations
import base64
import hashlib
from urllib.parse import unquote

class Response:
    def __init__(self, status, data=None, content=b''):
        self.status_code = status
        self._data = data if data is not None else {}
        self.content = content
        self.headers = {'X-RateLimit-Remaining': '4999'}
    def json(self):
        return self._data

class FakeGitHub:
    def __init__(self):
        self.repo = 'test-owner/private-data'
        self.base = 'https://api.github.com/repos/' + self.repo
        self.private = True
        self.branch_exists = True
        self.files = {}
        self.calls = []
        self.failure = None
        self.reject_status = None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.failure:
            raise self.failure
        if self.reject_status:
            return Response(self.reject_status)
        assert url == self.base or url.startswith(self.base + '/')
        assert kwargs['headers']['Authorization'].startswith('Bearer ')
        if url == self.base:
            return Response(200, {'private': self.private, 'full_name': self.repo})
        if '/branches/' in url:
            return Response(200 if self.branch_exists else 404, {'name': 'main'})
        assert url.startswith(self.base + '/contents/')
        path = unquote(url.split('/contents/', 1)[1])
        if method == 'GET':
            assert kwargs['params']['ref'] == 'main'
            if path not in self.files:
                return Response(404)
            data, sha = self.files[path]
            if kwargs['headers'].get('Accept') == 'application/vnd.github.raw+json':
                return Response(200, content=data)
            if len(data) > 1024 * 1024:
                return Response(200, {'sha': sha, 'encoding': 'none', 'content': ''})
            return Response(200, {'sha': sha, 'encoding': 'base64',
                                  'content': base64.b64encode(data).decode()})
        assert method == 'PUT'
        body = kwargs['json']
        assert body['branch'] == 'main'
        existed = path in self.files
        old_sha = self.files[path][1] if existed else None
        if body.get('sha') != old_sha:
            return Response(409)
        data = base64.b64decode(body['content'])
        sha = hashlib.sha256(data).hexdigest()
        self.files[path] = (data, sha)
        return Response(200 if existed else 201, {'content': {'sha': sha}})
