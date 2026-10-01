"""python scripts_check.py: 외부 DB를 건드리지 않는 로컬 점검."""
from pathlib import Path
import compileall
import subprocess
import sys
root=Path(__file__).parent
if not compileall.compile_dir(str(root),quiet=1):
    raise SystemExit(1)
raise SystemExit(subprocess.call([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=root))
