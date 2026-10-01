"""순수 함수: 개인정보를 출력하지 않는 명렬 파서, 좌석 배치, 파일 검증."""
from __future__ import annotations
import csv
import io
import math
import random
import re
from collections import Counter
from pathlib import PurePath
from urllib.parse import urlparse

CLASSES = [f"1-{i}" for i in range(1, 8)]
SUBJECTS = ["공통수학1", "공통수학2"]
DEMO_ROSTER = [
    {"student_id": "10191", "name": "테스트학생A", "class_id": "1-1"},
    {"student_id": "10192", "name": "테스트학생B", "class_id": "1-1"},
    {"student_id": "10291", "name": "테스트학생C", "class_id": "1-2"},
]
MOODS = {
    "happy": "😄 신나요", "calm": "🙂 편안해요", "neutral": "😐 그저 그래요",
    "tired": "😴 피곤해요", "worried": "😟 걱정돼요", "frustrated": "😣 답답해요",
    "skip": "🤐 지금은 말하고 싶지 않아요",
}
MOOD_MESSAGES = {
    "happy": "좋은 에너지를 오늘의 작은 도전으로 이어가 봐요!",
    "calm": "차분한 마음으로, 내 속도대로 시작해 봐요.",
    "neutral": "괜찮아요. 오늘 한 가지 발견을 함께 찾아봐요.",
    "tired": "많이 피곤하군요. 무리하지 말고 작은 한 걸음부터 시작해요.",
    "worried": "걱정되는 날도 있어요. 도움이 필요하면 선생님께 알려 주세요.",
    "frustrated": "마음이 답답할 수 있어요. 잠시 숨을 고르고 함께 시작해요.",
    "skip": "말하지 않아도 괜찮아요. 오늘도 내 속도로 함께해요.",
}
DEFAULT_SETTINGS = {
    "intro": "학생이 스스로 생각하고, 자신의 언어로 설명하며, 배움의 즐거움을 경험하는 수학 수업을 만들어 갑니다.",
    "interests": "개념기반 탐구수업\nAI·디지털 기반 수업과 평가\n학생의 사고와 성장 기록\n데이터 분석·교육용 웹앱 개발",
    "units": {"공통수학1": ["다항식", "방정식과 부등식", "경우의 수", "행렬"],
              "공통수학2": ["도형의 방정식", "집합과 명제", "함수와 그래프"]},
    "tools": [
        {"name": "스노클", "category": "수업도구", "description": "생각을 말과 글로 설명해요.", "url": "https://student.snorkl.app"},
        {"name": "데스모스", "category": "수업도구", "description": "식을 그래프로 확인해요.", "url": "https://www.desmos.com/calculator?lang=ko"},
        {"name": "데스모스 액티비티", "category": "수업도구", "description": "Amplify Classroom에서 함께 탐구해요.", "url": "https://classroom.amplify.com"},
    ],
    "retention_note": "학교의 보관·삭제 기준 확인 전입니다. 실제 학생 자료를 등록하기 전에 담당자와 확인하세요.",
}
SUDA_URL = "https://forms.gle/v1vNNTZ9bjD85AWy9"
SUDA_GUIDE = """### 오늘의 수업, 나의 언어로 정리하기
이 기록은 정답을 잘 쓰는 시간이 아닙니다.

오늘 수업에서 **내가 무엇을 이해했고, 어떻게 생각했으며, 무엇이 아직 어려운지**를 자신의 말로 기록하는 시간입니다.

짧게 써도 괜찮지만, “재미있었다”, “어려웠다”, “알게 되었다”로 끝내지 말고 **무엇이, 왜, 어떻게** 그랬는지를 함께 적어 주세요."""


def class_from_id(student_id: str) -> str:
    if not re.fullmatch(r"10[1-7][0-9]{2}", student_id):
        raise ValueError("학번은 10102처럼 1학년 1~7반의 5자리 숫자여야 합니다.")
    return f"1-{int(student_id[1:3])}"


def parse_roster(data: bytes) -> list[dict]:
    """첨부와 같은 가로형 명렬 또는 student_id,name,class_id 세로형 CSV 지원."""
    text = None
    for encoding in ("utf-8-sig", "cp949", "utf-16"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeError:
            continue
    if text is None:
        raise ValueError("CSV 인코딩을 확인해 주세요. UTF-8 형식을 권합니다.")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("빈 파일입니다.")
    aliases = {"student_id": "student_id", "학번": "student_id", "신학번": "student_id",
               "name": "name", "이름": "name", "성명": "name", "class_id": "class_id", "학급": "class_id"}
    headers = [aliases.get(x.strip(), x.strip()) for x in rows[0]]
    result = []
    if "student_id" in headers and "name" in headers:
        for row in rows[1:]:
            values = dict(zip(headers, [x.strip() for x in row]))
            sid, name = values.get("student_id", ""), values.get("name", "")
            if not sid and not name:
                continue
            cls = class_from_id(sid)
            if not name or len(name) > 40:
                raise ValueError("이름이 비어 있거나 너무 깁니다.")
            if values.get("class_id") and values["class_id"] != cls:
                raise ValueError("학번과 학급이 일치하지 않는 행이 있습니다.")
            result.append({"student_id": sid, "name": name, "class_id": cls})
    else:
        for row in rows:
            for col, value in enumerate(row[:-1]):
                sid, name = value.strip(), row[col + 1].strip()
                if re.fullmatch(r"10[1-7][0-9]{2}", sid) and name:
                    result.append({"student_id": sid, "name": name, "class_id": class_from_id(sid)})
    if not result:
        raise ValueError("학생 행을 찾지 못했습니다. 학번·이름·학급 열을 확인하세요.")
    if len({r['student_id'] for r in result}) != len(result):
        raise ValueError("중복 학번이 있습니다. 등록 전에 확인해 주세요.")
    return sorted(result, key=lambda r: r["student_id"])


def csv_bytes(rows: list[dict], fields: list[str] | None = None) -> bytes:
    fields = fields or (list(rows[0]) if rows else [])
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        safe = {}
        for key in fields:
            v = "" if row.get(key) is None else str(row.get(key))
            # 스프레드시트 프로그램에서 수식으로 실행되지 않도록 방지.
            safe[key] = "'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v
        writer.writerow(safe)
    return out.getvalue().encode("utf-8-sig")


def validate_url(url: str) -> str:
    u = url.strip()
    p = urlparse(u)
    if p.scheme != "https" or not p.netloc or p.username or p.password:
        raise ValueError("로그인 정보가 포함되지 않은 https:// 주소를 입력하세요.")
    return u


def validate_password(password: str) -> None:
    if len(password) < 10 or len(password.encode("utf-8")) > 72:
        raise ValueError("비밀번호는 10자 이상, UTF-8 기준 72바이트 이하여야 합니다.")


def validate_file(name: str, data: bytes, max_mb: int = 20) -> tuple[bytes, str, str]:
    """이름/확장자/실제 형식을 검사. 이미지 메타데이터는 제거. 악성코드 검사기는 아님."""
    if not data or len(data) > max_mb * 1024 * 1024:
        raise ValueError(f"빈 파일은 제출할 수 없습니다. 파일은 {max_mb}MB 이하여야 합니다.")
    ext = PurePath(name).suffix.lower()
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise ValueError("PDF 파일 형식을 확인해 주세요.")
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ValueError("암호가 걸린 PDF는 업로드할 수 없습니다.")
        if not 1 <= len(reader.pages) <= 100:
            raise ValueError("PDF는 1~100쪽으로 나누어 제출해 주세요.")
        return data, "application/pdf", ".pdf"
    if ext not in {".jpg", ".jpeg", ".png"}:
        raise ValueError("PDF, JPG, PNG만 지원합니다. 다른 문서는 PDF로 내보내 주세요.")
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in {"JPEG", "PNG"} or im.width * im.height > 25_000_000:
            raise ValueError("JPG·PNG 이미지, 2,500만 화소 이하로 제출해 주세요.")
        im.load()
        converted = im.convert("RGBA" if ext == ".png" else "RGB")
        clean = Image.new(converted.mode, converted.size)
        clean.paste(converted)
        target = io.BytesIO()
        clean.save(target, format="PNG" if ext == ".png" else "JPEG")
        raw = target.getvalue()
        if len(raw) > max_mb * 1024 * 1024:
            raise ValueError("이미지 처리 후 용량이 큽니다. 해상도를 줄여 주세요.")
        return raw, "image/png" if ext == ".png" else "image/jpeg", ".png" if ext == ".png" else ".jpg"


def point_totals(rows: list[dict]) -> tuple[int, int, int]:
    good = sum(int(r["delta"]) for r in rows if not r.get("cancelled") and int(r["delta"]) > 0)
    bad = -sum(int(r["delta"]) for r in rows if not r.get("cancelled") and int(r["delta"]) < 0)
    return good, bad, good - bad


def make_layout(students: list[dict], rows: int, cols: int, shuffle=False, group_count=0) -> list[dict]:
    if rows * cols < len(students):
        raise ValueError("좌석 수가 학생 수보다 적습니다.")
    members = list(students)
    if shuffle:
        random.SystemRandom().shuffle(members)
    return [{"user_id": p["id"], "학번": p["student_id"], "이름": p["full_name"],
             "행": i // cols + 1, "열": i % cols + 1,
             "조": f"{i % group_count + 1}조" if group_count else "미배정"}
            for i, p in enumerate(members)]


def validate_layout(entries: list[dict], rows: int, cols: int, allowed_ids: set[str]) -> None:
    seen, seats = set(), set()
    for e in entries:
        uid = str(e["user_id"])
        if uid not in allowed_ids or uid in seen:
            raise ValueError("다른 반 학생 또는 중복 학생이 포함되어 있습니다.")
        if int(e["행"]) != float(e["행"]) or int(e["열"]) != float(e["열"]):
            raise ValueError("행·열은 정수로 입력하세요.")
        seat = (int(e["행"]), int(e["열"]))
        if not (1 <= seat[0] <= rows and 1 <= seat[1] <= cols) or seat in seats:
            raise ValueError("좌석이 겹치거나 교실 범위를 벗어났습니다.")
        seen.add(uid)
        seats.add(seat)
    if seen != allowed_ids:
        raise ValueError("배치에서 빠진 학생이 있습니다. 명렬을 다시 불러오세요.")
