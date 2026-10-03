"""Starts an explicit local-only demo, containing fictional students."""
import os
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent
env = dict(os.environ, STORAGE_MODE='demo')
print('로컬 데모: 실제 학생 정보 입력 금지')
print('교사 teacher / DemoTeacher!2026')
print('학생 1101 / DemoStudent!2026 (1201~1701도 가능)')
raise SystemExit(subprocess.call([sys.executable, '-m', 'streamlit', 'run', str(root / 'streamlit_app.py')], cwd=root, env=env))
