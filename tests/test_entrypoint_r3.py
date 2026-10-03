"""Launcher and import isolation tests. These are not Streamlit runtime tests."""
import ast
import runpy
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_application_uses_package_local_github_connection():
    tree = ast.parse((ROOT / 'classroom/application.py').read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert any(node.module == 'github_connection' and node.level == 1 for node in imports)
    assert not any(node.module == 'backend' and node.level == 0 for node in imports)


def test_github_connection_ignores_poisoned_legacy_backend():
    result = subprocess.run(
        [sys.executable, '-c', '''
import sys
class NeverLoadLegacy:
    def __getattr__(self, name):
        raise AssertionError("legacy backend was accessed")
sys.modules['backend'] = NeverLoadLegacy()
from classroom.github_connection import connect_github
assert callable(connect_github)
print("package-local import passed")
'''], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'package-local import passed' in result.stdout


@pytest.mark.parametrize('filename', ['app.py', 'streamlit_app.py'])
def test_missing_files_shows_upload_instructions_before_app_import(tmp_path, monkeypatch, filename):
    path = tmp_path / filename
    path.write_text((ROOT / filename).read_text())
    calls = []
    fake_st = types.ModuleType('streamlit')
    class StopExecution(Exception):
        pass
    for name in ('set_page_config', 'title', 'error', 'code', 'info', 'caption'):
        setattr(fake_st, name, lambda *a, _name=name, **kw: calls.append((_name, a, kw)))
    def stop():
        raise StopExecution()
    fake_st.stop = stop
    monkeypatch.setitem(sys.modules, 'streamlit', fake_st)
    with pytest.raises(StopExecution):
        runpy.run_path(str(path), run_name='__main__')
    texts = '\n'.join(str(args) for _, args, _ in calls)
    assert 'classroom/github_connection.py' in texts
    assert 'Secrets나 토큰 문제가 아닙니다' in texts
    assert 'GITHUB_ONLY_R3' in texts
