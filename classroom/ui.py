"""Streamlit UI. User-provided text is escaped in custom HTML."""
from __future__ import annotations
import base64
import csv
import html
import io
import json
import math
import random
from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from .auth import CLASSES, now, today, uid
from .service import COURSES, MOODS, NOTE_FIELDS, ALLOWED_EXTENSIONS
from .storage import AppError

ROOT = Path(__file__).resolve().parent.parent


def css():
    st.markdown('<style>' + (ROOT / 'assets/style.css').read_text() + '</style>', unsafe_allow_html=True)


def hero(title: str, description: str = '', eyebrow: str = 'GUSSAEM · MATH CLASSROOM'):
    st.markdown(f'<div class="hero"><div class="eyebrow">{html.escape(eyebrow)}</div>'
                f'<h1>{html.escape(title)}</h1><p>{html.escape(description)}</p></div>', unsafe_allow_html=True)


def empty(message: str):
    st.markdown('<div class="empty-card">' + html.escape(message) + '</div>', unsafe_allow_html=True)


def frame(payload: dict):
    # Escape '<' so user messages cannot close a script element.
    data = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    js = (ROOT / 'assets/live.js').read_text().replace('__PAYLOAD__', data)
    components.html('<script>' + js + '</script>', height=0, scrolling=False)


def event_id(name: str) -> str:
    request_ids = st.session_state.setdefault('_request_ids', {})
    key = form_key(name)
    return request_ids.setdefault(key, uid())


def form_key(name: str) -> str:
    return name + ':' + str(st.session_state.get('_revision_' + name, 0))


def done(name: str, message: str):
    st.session_state['_revision_' + name] = st.session_state.get('_revision_' + name, 0) + 1
    st.session_state['_flash'] = message
    st.rerun()


def execute(action, message: str = '', form: str | None = None):
    try:
        with st.spinner('저장 내용을 확인하고 있습니다…'):
            result = action()
        if form:
            done(form, message or '저장했습니다.')
        if message:
            st.success(message)
        return result
    except AppError as exc:
        st.error(str(exc))
        return None


def upload_value(upload):
    return (upload.name, upload.getvalue()) if upload is not None else None


def csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b''
    buf = io.StringIO()
    columns = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        safe = {}
        for key in columns:
            value = row.get(key, '')
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            # Avoid spreadsheet formula injection in exported student text.
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return buf.getvalue().encode('utf-8-sig')


def download_file(key: str, fetch):
    if st.button('첨부파일 준비', key='prepare_' + key):
        try:
            with st.spinner('권한 확인 후 파일을 불러오는 중…'):
                st.session_state['_download_' + key] = fetch()
        except AppError as exc:
            st.error(str(exc))
    cached = st.session_state.get('_download_' + key)
    if cached:
        filename, data = cached
        st.download_button('⬇ ' + filename, data=data, file_name=filename,
                           mime='application/octet-stream', key='download_' + key)


def class_select(user: dict, key: str):
    if user['role'] == 'teacher':
        return st.selectbox('학급', CLASSES, key=key)
    st.caption('우리 반 · ' + user['class_id'])
    return user['class_id']


def student_select(svc, token, class_id, key):
    users = [x for x in svc.auth.users(token, class_id) if x['active']]
    if not users:
        st.info('이 학급에 등록된 학생이 없습니다. 학생 관리에서 명렬을 등록하세요.')
        return None
    mapping = {x['login_id']: x for x in users}
    sid = st.selectbox('학생', list(mapping), format_func=lambda x: x + ' · ' + mapping[x]['name'], key=key)
    return mapping[sid]


def ai_choice(cfg, key):
    if not cfg['ai_enabled']:
        st.caption('자동 피드백: 제출 확인 + 선생님이 설정한 공통 안내. 파일 내용은 자동 분석하지 않습니다.')
        return False
    st.caption('선택 시 아래에 직접 입력한 학습 설명만 OpenAI로 전송됩니다. 파일·감정·관찰 기록은 보내지 않습니다. 이름·연락처를 적지 마세요.')
    return st.checkbox('직접 입력한 설명을 AI로 보내 학습 피드백을 받겠습니다. (선택)', value=False, key=key)


def setup_screen():
    hero('교실을 처음 열 준비를 해요', 'GitHub 데이터 저장소와 관리자 계정을 연결하면 로그인 화면이 열립니다.')
    st.info('아직 운영용 Secrets가 설정되지 않았습니다. 학생 정보가 임시 저장소에 저장되도록 자동 전환하지 않습니다.')
    st.markdown('### 처음 설정할 항목')
    st.code('STORAGE_MODE = "github"\nGITHUB_REPO = "내아이디/비공개-데이터저장소"\nGITHUB_BRANCH = "main"\nGITHUB_TOKEN = "발급한_토큰"\nENCRYPTION_KEY = "아래에서_생성한_키"\nTEACHER_ID = "teacher"\nTEACHER_INITIAL_PASSWORD = "직접정한_12자이상_비밀번호"', language='toml')
    st.caption('README_시작하기.md에 화면별 설정 순서를 적어 두었습니다. Secrets는 GitHub 파일에 올리지 않습니다.')
    if st.button('설정용 새 암호화키 만들기'):
        from cryptography.fernet import Fernet
        st.session_state['_setup_key'] = Fernet.generate_key().decode()
    if st.session_state.get('_setup_key'):
        st.code(st.session_state['_setup_key'])
        st.warning('기존 데이터가 있다면 새 키로 바꾸지 마세요. 이 키를 잃으면 저장된 데이터를 복구할 수 없습니다.')
    st.markdown('### 저장 방식')
    st.write('학생 기록은 GitHub 비공개 데이터 저장소에 암호화된 파일로 저장됩니다.')
    st.caption('이 수정본은 GitHub 전용입니다. 별도 데이터베이스나 임시 로컬 저장을 사용하지 않습니다.')
    st.info('기존 앱을 수정한다면 app.py, backend.py, requirements.txt와 classroom·assets 폴더 전체를 교체하세요. 기존 학생 데이터와 암호화키는 삭제하거나 바꾸지 마세요.')


def login_page(svc):
    frame({'locked': False, 'watchdog': False, 'events': [], 'reset': True})
    images = []
    for i in range(1, 4):
        encoded = base64.b64encode((ROOT / f'assets/login_{i}.svg').read_bytes()).decode()
        images.append(f'<img src="data:image/svg+xml;base64,{encoded}" alt=""/>')
    st.markdown('''<style>
      .stApp{background:#173a32;}[data-testid="stHeader"]{background:transparent;}
      .login-backdrops{position:fixed;inset:0;z-index:0;pointer-events:none;background:#173a32;}
      .login-backdrops img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;animation:backdrop 21s infinite;}
      .login-backdrops img:nth-child(2){animation-delay:7s;}.login-backdrops img:nth-child(3){animation-delay:14s;}
      @keyframes backdrop{0%,29%{opacity:1;}34%,95%{opacity:0;}100%{opacity:1;}}
      [data-testid="stMain"] .block-container{position:relative;z-index:1;padding-top:12vh;max-width:1180px;}
      .login-copy{color:#fff;padding:32px 30px 35px 0;}.login-copy .login-label{font-size:11px;letter-spacing:.22em;color:#c5d6be;font-weight:700;}
      .login-copy h1{color:#fff;font-size:clamp(38px,4.2vw,64px)!important;line-height:1.28;letter-spacing:-.055em;margin:30px 0 24px;}
      .login-copy p{color:#d9e4d8;font-size:17px;line-height:1.9;}.login-copy .login-foot{margin-top:70px;font-size:12px;color:#b2c9b6;}
      .st-key-login_card{background:rgba(255,255,255,.96);border:1px solid #ffffffaa;border-radius:26px;
        padding:30px 32px;box-shadow:0 28px 90px #0003;}
      .st-key-login_card [data-testid="stForm"]{border:0;padding:0;background:transparent;}
      .st-key-login_card h2{font-size:26px!important;}
      @media(max-width:700px){[data-testid="stMain"] .block-container{padding-top:3rem;}.login-copy{padding:0;}.login-copy .login-foot{margin:18px 0;}.st-key-login_card{padding:25px;}}
      @media(prefers-reduced-motion:reduce){.login-backdrops img{animation:none;}.login-backdrops img:first-child{opacity:1;}}
    </style><div class="login-backdrops">''' + ''.join(images) + '</div>', unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap='large')
    with left:
        st.markdown('''<div class="login-copy"><div class="login-label">G / GUSSAEM'S MATH CLASSROOM</div>
          <h1>생각이 자라는 곳,<br>우리의 수학 교실.</h1>
          <p>틀려도 괜찮아요. 질문해도 괜찮아요.<br>오늘의 배움을 나의 언어로 쌓아가요.</p>
          <div class="login-foot">공통수학1 · 공통수학2 &nbsp; / &nbsp; 1학년 1반—7반</div></div>''', unsafe_allow_html=True)
    with right:
        with st.container(key='login_card'):
            st.markdown('<div class="small-label">WELCOME BACK</div>', unsafe_allow_html=True)
            st.subheader('오늘도 반가워요 🌱')
            st.caption('학번과 비밀번호로 우리 교실에 들어오세요.')
            with st.form('login_form'):
                login_id = st.text_input('학번 / 교사 아이디', placeholder='예: 1101', max_chars=30)
                password = st.text_input('비밀번호', type='password', max_chars=128)
                submitted = st.form_submit_button('우리 교실 입장하기 →', use_container_width=True, type='primary')
            if submitted:
                try:
                    token = svc.login(login_id, password)
                    user = svc.require(token)
                    st.session_state.clear()
                    st.session_state['token'] = token
                    st.session_state['_needs_mood'] = user['role'] == 'student'
                    st.session_state['_login_at'] = now()
                    st.rerun()
                except AppError as exc:
                    st.error(str(exc))
            st.divider()
            st.caption('GitHub 저장 전용 · GITHUB_ONLY_R3')
            st.caption('처음에는 선생님이 발급한 임시 비밀번호를 사용하세요. 비밀번호를 잊었다면 선생님에게 초기화를 요청하세요.')



@st.fragment(run_every=3)
def live_monitor(svc, token):
    try:
        data = svc.monitor(token)
        user = svc.require(token)
        shown = st.session_state.setdefault('_shown_events', set())
        login_at = st.session_state.get('_login_at', now())
        events = [x for x in data['events'] if x['id'] not in shown and x['created_at'] >= login_at]
        for event in events:
            shown.add(event['id'])
        st.session_state['_locked'] = data['locked']
        frame({'locked': data['locked'], 'message': data['message'], 'events': events,
               'watchdog': user['role'] == 'student'})
        if events:
            for item in events:
                label = ('상점 +' + str(item['score'])) if item['score'] > 0 else ('벌점 ' + str(abs(item['score'])))
                st.toast(label + '점 · ' + item['reason'], icon='🎉' if item['score'] > 0 else '📌')
    except AppError as exc:
        if token not in svc.auth.sessions:
            st.session_state.clear()
            st.session_state['_flash'] = '로그인이 만료되었습니다. 다시 로그인하세요.'
            st.rerun()
        st.session_state['_locked'] = True
        frame({'locked': True, 'message': str(exc), 'events': [], 'watchdog': True})


@st.dialog('오늘의 마음 날씨는?', width='small', dismissible=False)
def mood_dialog(svc, token):
    st.markdown('### 수학 여행을 떠나기 전, 마음 체크인 🌤️')
    st.write('오늘 내 마음과 가장 가까운 표정을 눌러 주세요.')
    st.caption('선택한 감정은 선생님만 볼 수 있어요. 친구들에게 공개되지 않아요. 말하고 싶지 않아도 괜찮아요.')
    pairs = list(MOODS.items())
    for start in range(0, 6, 2):
        columns = st.columns(2)
        for col, (code, label) in zip(columns, pairs[start:start + 2]):
            if col.button(label, key='mood_' + code, use_container_width=True):
                try:
                    svc.save_emotion(token, code)
                    st.session_state['_needs_mood'] = False
                    st.session_state['_flash'] = '마음을 알려줘서 고마워요. 오늘도 한 걸음씩 시작해 봐요!'
                    st.rerun()
                except AppError as exc:
                    st.error(str(exc))
    if st.button(MOODS['skip'], key='mood_skip', use_container_width=True):
        try:
            svc.save_emotion(token, 'skip')
            st.session_state['_needs_mood'] = False
            st.rerun()
        except AppError as exc:
            st.error(str(exc))


def sidebar(svc, token, user, cfg):
    with st.sidebar:
        st.markdown('<div class="brand">🌱 ' + html.escape(cfg['title']) + '</div>', unsafe_allow_html=True)
        st.caption(cfg['tagline'])
        st.divider()
        st.write('**' + user['name'] + '** 님')
        st.caption('교사 계정' if user['role'] == 'teacher' else user['class_id'] + ' · ' + user['login_id'])
        student_menus = ['🏡 우리 교실', '📘 공통수학1', '📗 공통수학2', '✍️ 수다노트', '💬 질문 게시판',
                         '🧰 수업도구', '🪑 좌석배치표', '🙋 내 정보']
        menus = student_menus if user['role'] == 'student' else student_menus[:-1] + [
            '📊 교사 대시보드', '📝 관찰기록·상벌점', '👥 학생 관리', '⚙️ 교실 설정', '🙋 내 정보']
        if user.get('must_change'):
            menu = '🙋 내 정보'
            st.info('임시 비밀번호를 먼저 변경하세요.')
        else:
            if st.session_state.get('_nav_pending'):
                st.session_state['nav'] = st.session_state.pop('_nav_pending')
            menu = st.radio('교실 메뉴', menus, key='nav', label_visibility='collapsed')
        st.divider()
        if svc.store.backend.mode == 'demo':
            st.warning('로컬 데모 · GitHub 미연결')
        else:
            st.caption('🔐 GitHub 비공개·암호화 저장')
        if st.button('로그아웃', use_container_width=True):
            svc.require(token, action=True, allow_password_change=True)
            svc.auth.logout(token)
            st.session_state.clear()
            st.rerun()
    return menu


def nav_button(label, destination, key):
    if st.button(label, key=key, use_container_width=True):
        st.session_state['_nav_pending'] = destination
        st.rerun()


def home_page(svc, token, user, cfg):
    hero(user['name'] + ' 님, 오늘도 한 걸음 🌿', cfg['tagline'])
    if user['role'] == 'teacher':
        users = svc.auth.users(token)
        c = st.columns(3)
        c[0].metric('등록 학생', len(users))
        c[1].metric('수업 학급', '7개')
        c[2].metric('개설 과목', '2개')
    else:
        points = svc.points(token)
        c = st.columns(3)
        c[0].metric('나의 수다노트', len(svc.notes(token)))
        c[1].metric('나의 상점', sum(x['score'] for x in points if x['score'] > 0))
        c[2].metric('나의 벌점', -sum(x['score'] for x in points if x['score'] < 0))
    st.write('')
    left, right = st.columns([1.5, 1])
    with left:
        with st.container(border=True):
            st.subheader('안녕하세요, 구쌤입니다')
            st.text(cfg['about'])
        with st.container(border=True):
            st.subheader('함께 탐구하는 분야')
            st.text(cfg['interests'])
    with right:
        with st.container(border=True):
            st.subheader('오늘의 교실 바로가기')
            nav_button('📘 공통수학1 수업 열기', '📘 공통수학1', 'home_math1')
            nav_button('📗 공통수학2 수업 열기', '📗 공통수학2', 'home_math2')
            nav_button('✍️ 오늘의 수다노트', '✍️ 수다노트', 'home_note')
            if user['role'] == 'teacher':
                nav_button('📊 감정·접속 현황 확인', '📊 교사 대시보드', 'home_dash')
            elif st.button('🌤️ 지금의 마음 다시 선택하기', use_container_width=True):
                st.session_state['_needs_mood'] = True
                st.rerun()
    if user['role'] == 'student':
        st.subheader('나에게 도착한 피드백')
        works = [x for x in svc.submissions(token, user['class_id']) if x['student_uid'] == user['uid']]
        notifications = []
        for x in works[-8:]:
            notifications.append((x.get('feedback_at', x['created_at']), '📎 ' + x['assignment_title'],
                                  x['teacher_feedback'] or x['feedback']['text']))
        for x in svc.notes(token)[-5:]:
            notifications.append((x.get('feedback_at', x['created_at']), '✍️ ' + x['topic'],
                                  x['teacher_feedback'] or x['feedback']['text']))
        for x in points[-5:]:
            notifications.append((x['created_at'], '🎉 상점' if x['score'] > 0 else '📌 벌점 안내',
                                  str(abs(x['score'])) + '점 · ' + x['reason']))
        if not notifications:
            empty('첫 기록을 남기면 이곳에 나의 피드백이 모여요.')
        for stamp, title, content in sorted(notifications, reverse=True)[:6]:
            with st.expander(title + ' · ' + stamp[:16].replace('T', ' ')):
                st.text(content)
        st.caption('제출·수다노트 저장 직후 자동 확인이 표시됩니다. 새 교사 피드백은 메뉴를 다시 열거나 새로고침하면 확인할 수 있습니다.')


def render_materials(svc, token, user, course, rows):
    if not rows:
        empty('등록된 자료가 아직 없습니다.')
    for material in reversed(rows):
        with st.expander('[' + material['unit'] + '] ' + material['title']):
            st.caption(material['kind'] + ' · ' + material['created_at'][:10] + ' · ' + ', '.join(material['classes']))
            if material['body']:
                st.text(material['body'])
            if material.get('file'):
                download_file('mat_' + material['id'], lambda m=material: svc.material_download(token, course, m['id']))
            if user['role'] == 'teacher':
                st.caption('보관하면 학생 화면에서 숨겨집니다. Git 이력에서는 삭제되지 않습니다.')
                if st.button('이 자료 보관하기', key='archive_' + material['id']):
                    execute(lambda m=material: svc.archive_material(token, course, m['id']), form='archive', message='자료를 보관했습니다.')


def material_form(svc, token, course, cfg):
    name = 'new_material_' + course
    with st.expander('➕ 평가계획·학습지·수업자료 올리기'):
        with st.form(form_key(name)):
            c = st.columns(2)
            kind = c[0].selectbox('자료 종류', ['평가계획', '학습지', '수업자료'])
            unit = c[1].selectbox('단원', ['공통'] + cfg['units'][course])
            classes = st.multiselect('배포할 학급', CLASSES, default=CLASSES)
            title = st.text_input('자료 제목', max_chars=150)
            body = st.text_area('자료 안내', max_chars=8000)
            file = st.file_uploader('첨부파일 · 최대 8MB', type=sorted(ALLOWED_EXTENSIONS))
            saved = st.form_submit_button('자료 게시하기', type='primary')
        if saved:
            execute(lambda: svc.add_material(token, course=course, unit=unit, kind=kind, title=title,
                    body=body, classes=classes, attachment=upload_value(file), event_id=event_id(name)),
                    form=name, message='수업자료를 게시했습니다.')


def assignment_form(svc, token, course, cfg):
    name = 'new_assignment_' + course
    with st.expander('➕ 학생 제출 과제 만들기'):
        with st.form(form_key(name)):
            title = st.text_input('과제 제목', max_chars=150)
            unit = st.selectbox('과제 단원', cfg['units'][course])
            classes = st.multiselect('제출 대상 학급', CLASSES, default=CLASSES)
            description = st.text_area('할 일·제출 안내', max_chars=5000)
            note = st.text_area('제출 즉시 보낼 공통 피드백', value='풀이에서 사용한 개념과 그렇게 생각한 이유를 함께 확인해 보세요.', max_chars=2000)
            shared = st.checkbox('이 과제의 제출물을 같은 반 친구들과 공유합니다.', value=False)
            st.caption('기본은 본인·교사만 열람입니다. 공유해도 개인 피드백은 친구에게 공개하지 않습니다.')
            saved = st.form_submit_button('과제 만들기', type='primary')
        if saved:
            execute(lambda: svc.add_assignment(token, course=course, unit=unit, title=title,
                    description=description, classes=classes, share=shared, feedback_note=note,
                    event_id=event_id(name)), form=name, message='제출 과제를 만들었습니다.')


def submissions_page(svc, token, user, course, cfg):
    class_id = class_select(user, 'sub_class_' + course)
    tasks = [x for x in svc.assignments(token, course) if class_id in x['classes']]
    if not tasks:
        empty('이 학급에 열린 제출 과제가 없습니다. 선생님이 과제를 만들면 제출할 수 있어요.')
    else:
        task_map = {x['id']: x for x in tasks}
        selected = st.selectbox('과제', list(task_map), format_func=lambda x: '[' + task_map[x]['unit'] + '] ' + task_map[x]['title'], key='task_pick_' + course)
        task = task_map[selected]
        st.text(task['description'])
        st.info('같은 반에 공유되는 과제입니다. 개인 정보는 포함하지 마세요.' if task['share'] else '비공개 과제 · 본인과 선생님만 볼 수 있습니다.')
        if user['role'] == 'teacher':
            share = st.checkbox('같은 반 제출물 공개', value=task['share'], key='share_' + selected)
            if st.button('공개 범위 저장', key='save_share_' + selected):
                execute(lambda: svc.set_assignment_share(token, course, selected, share), form='share', message='공개 범위를 저장했습니다.')
        else:
            name = 'submission_' + selected
            with st.form(form_key(name)):
                text = st.text_area('나의 풀이·생각 설명', height=160, max_chars=8000,
                                    placeholder='내가 사용한 개념과 생각한 순서를 적어 주세요.')
                file = st.file_uploader('수업 중 작성한 파일 · 최대 8MB', type=sorted(ALLOWED_EXTENSIONS))
                consent = ai_choice(cfg, 'ai_' + form_key(name))
                saved = st.form_submit_button('과제 제출하고 피드백 받기', type='primary')
            if saved:
                execute(lambda: svc.submit(token, course=course, assignment_id=selected, text=text,
                        attachment=upload_value(file), consent=consent, event_id=event_id(name)),
                        form=name, message='과제를 제출했습니다. 아래 내 제출물에서 피드백을 확인하세요.')
        st.divider()
        st.subheader('학급 제출 게시판')
        rows = [x for x in svc.submissions(token, class_id, course) if x['assignment_id'] == selected]
        if not rows:
            empty('아직 볼 수 있는 제출물이 없습니다.')
        for row in reversed(rows):
            mine = row['student_uid'] == user['uid']
            label = ('나의 제출' if mine else row['student_id'] + ' ' + row['name']) + ' · ' + row['created_at'][:16].replace('T', ' ')
            with st.expander(label, expanded=mine and row is rows[-1]):
                if row['text']:
                    st.text(row['text'])
                if row.get('file'):
                    download_file('sub_' + row['id'], lambda r=row: svc.submission_download(token, class_id, r['id']))
                if 'feedback' in row:
                    st.caption(row['feedback']['mode'])
                    st.info(row['feedback']['text'])
                if row.get('teacher_feedback'):
                    st.success('선생님의 피드백\n\n' + row['teacher_feedback'])
                if user['role'] == 'teacher':
                    name = 'feedback_' + row['id']
                    with st.form(form_key(name)):
                        comment = st.text_area('개별 피드백', value=row['teacher_feedback'], max_chars=5000)
                        saved = st.form_submit_button('학생에게 피드백 보내기')
                    if saved:
                        execute(lambda r=row, c=comment: svc.feedback_on_submission(token, class_id, r['id'], c),
                                form=name, message='학생에게 피드백을 보냈습니다.')
        if user['role'] == 'teacher' and rows:
            st.download_button('제출 기록 CSV', csv_bytes(rows), file_name=class_id + '_제출기록.csv', mime='text/csv', key='export_sub_' + course)


def course_page(svc, token, user, course, cfg):
    hero(COURSES[course], '개념을 만나고, 생각을 표현하고, 배움을 기록해요.', 'COURSE / ' + course.upper())
    if user['role'] == 'teacher':
        material_form(svc, token, course, cfg)
        assignment_form(svc, token, course, cfg)
    materials = svc.materials(token, course)
    plans, resources, submissions = st.tabs(['평가계획', '단원별 수업자료', '학급별 제출 게시판'])
    with plans:
        render_materials(svc, token, user, course, [x for x in materials if x['kind'] == '평가계획'])
    with resources:
        # Include legacy units when a teacher later renames a unit.
        units = list(dict.fromkeys(cfg['units'][course] + [x['unit'] for x in materials]))
        unit = st.selectbox('단원별로 보기', ['전체'] + units, key='material_unit_' + course)
        rows = [x for x in materials if x['kind'] != '평가계획' and (unit == '전체' or x['unit'] == unit)]
        render_materials(svc, token, user, course, rows)
    with submissions:
        submissions_page(svc, token, user, course, cfg)


NOTE_GUIDE = '''이 기록은 정답을 잘 쓰는 시간이 아닙니다.

오늘 수업에서 **내가 무엇을 이해했고, 어떻게 생각했으며, 무엇이 아직 어려운지**를 자신의 말로 기록하는 시간입니다.

짧게 써도 괜찮지만, “재미있었다”, “어려웠다”, “알게 되었다”로 끝내지 말고 **무엇이, 왜, 어떻게** 그랬는지를 함께 적어 주세요.'''
NOTE_QUESTIONS = {
    '이해한 내용': ('1. 오늘 무엇을 이해했나요?', '배운 개념 하나를 골라 친구에게 설명하듯 써 보세요.'),
    '생각한 과정': ('2. 어떤 순서로 생각했나요? 왜 그렇게 생각했나요?', '내가 사용한 방법과 그 방법을 선택한 이유를 적어 보세요.'),
    '시도·수정한 내용': ('3. 시도하거나 고친 부분은 무엇인가요?', '처음 생각 → 확인한 것 → 바꾼 생각의 순서로 적어도 좋아요.'),
    '아직 어려운 점': ('4. 아직 어려운 점은 무엇인가요?', '어느 부분에서 막혔는지, 무엇이 궁금한지 구체적으로 적어 보세요.'),
    '다음 학습 계획': ('5. 다음에는 무엇을 해 볼까요?', '복습할 개념이나 새롭게 해 볼 작은 행동 하나를 적어 보세요.')}


def notes_page(svc, token, user, cfg):
    hero('수다노트', '오늘의 수업, 나의 언어로 정리하기', 'REFLECT / THINK / GROW')
    st.markdown(NOTE_GUIDE)
    target = None
    if user['role'] == 'teacher':
        class_id = class_select(user, 'note_class')
        target = student_select(svc, token, class_id, 'note_student')
        if target is None:
            return
        records = svc.notes(token, target['login_id'])
        st.caption('교사 전용 · 선택한 학생의 누적 기록입니다.')
    else:
        course = st.selectbox('수업 과목', list(COURSES), format_func=lambda x: COURSES[x], key='note_course')
        name = 'note_write'
        with st.form(form_key(name)):
            c = st.columns(2)
            day = c[0].date_input('수업 날짜', value=date.fromisoformat(today()), max_value=date.fromisoformat(today()))
            unit = c[1].selectbox('수업 단원', cfg['units'][course])
            topic = st.text_input('오늘의 수업 주제', max_chars=150, placeholder='예: 원의 중심과 반지름으로 원의 방정식 나타내기')
            answers = {}
            for field in NOTE_FIELDS:
                question, hint = NOTE_QUESTIONS[field]
                answers[field] = st.text_area(question, placeholder=hint, max_chars=2500, height=110)
            consent = ai_choice(cfg, 'note_ai_' + form_key(name))
            saved = st.form_submit_button('오늘의 배움 저장하기', type='primary')
        if saved:
            execute(lambda: svc.save_note(token, course=course, unit=unit, day=day.isoformat(), topic=topic,
                    answers=answers, consent=consent, event_id=event_id(name)), form=name,
                    message='수다노트를 학생별 파일에 저장했습니다. 아래 기록에서 확인하세요.')
        records = svc.notes(token)
    st.divider()
    st.subheader('차곡차곡 쌓인 배움')
    if not records:
        empty('아직 기록이 없습니다. 짧은 한 문장부터 시작해도 괜찮아요.')
    for record in reversed(records):
        with st.expander(record['day'] + ' · ' + COURSES[record['course']] + ' · ' + record['topic']):
            st.caption(record['unit'])
            for field in NOTE_FIELDS:
                if record['answers'].get(field):
                    st.markdown('**' + field + '**')
                    st.text(record['answers'][field])
            st.caption(record['feedback']['mode'])
            st.info(record['feedback']['text'])
            if record.get('teacher_feedback'):
                st.success('선생님의 피드백\n\n' + record['teacher_feedback'])
            if user['role'] == 'teacher':
                name = 'note_comment_' + record['id']
                with st.form(form_key(name)):
                    comment = st.text_area('선생님의 한마디', value=record.get('teacher_feedback', ''), max_chars=5000)
                    saved = st.form_submit_button('피드백 저장')
                if saved:
                    execute(lambda r=record, c=comment: svc.feedback_on_note(token, target['login_id'], r['id'], c),
                            form=name, message='수다노트 피드백을 보냈습니다.')
    if records:
        export = [{'날짜': r['day'], '과목': COURSES[r['course']], '단원': r['unit'], '주제': r['topic'],
                   **r['answers'], '교사 피드백': r.get('teacher_feedback', '')} for r in records]
        sid = target['login_id'] if target else user['login_id']
        st.download_button('누적 수다노트 CSV 내려받기', csv_bytes(export), file_name=sid + '_수다노트.csv', mime='text/csv')


def questions_page(svc, token, user):
    hero('질문 게시판', '질문은 배움이 시작되는 순간이에요.')
    class_id = class_select(user, 'question_class')
    if user['role'] == 'student':
        name = 'new_question'
        with st.form(form_key(name)):
            course = st.selectbox('질문 과목', list(COURSES), format_func=lambda x: COURSES[x])
            title = st.text_input('질문 제목', max_chars=150)
            body = st.text_area('어디까지 이해했고, 무엇이 궁금한가요?', max_chars=5000, height=180)
            shared = st.checkbox('같은 반 친구들도 질문과 답변을 볼 수 있게 합니다.', value=False)
            saved = st.form_submit_button('질문 남기기', type='primary')
        if saved:
            execute(lambda: svc.ask(token, course=course, title=title, body=body, shared=shared, event_id=event_id(name)),
                    form=name, message='질문을 남겼습니다.')
    rows = svc.questions(token, class_id)
    if not rows:
        empty('아직 볼 수 있는 질문이 없습니다.')
    for row in reversed(rows):
        status = '답변 완료' if row['answer'] else '답변 기다리는 중'
        with st.expander('[' + status + '] ' + row['title']):
            st.caption(row['name'] + ' · ' + COURSES[row['course']] + ' · ' + ('우리 반 공개' if row['shared'] else '본인·교사만'))
            st.text(row['body'])
            if row['answer']:
                st.success('선생님의 답변\n\n' + row['answer'])
            if user['role'] == 'teacher':
                name = 'answer_' + row['id']
                with st.form(form_key(name)):
                    answer = st.text_area('답변 작성', value=row['answer'], max_chars=5000)
                    saved = st.form_submit_button('답변 보내기')
                if saved:
                    execute(lambda r=row, a=answer: svc.answer(token, class_id, r['id'], a), form=name, message='답변을 보냈습니다.')


def tools_page(svc, token, user, cfg):
    hero('수업도구', '도구를 활용해 생각을 더 선명하게 표현해요.')
    st.caption('외부 사이트는 새 탭에서 열립니다. 교실 화면 잠금은 이미 열린 외부 탭이나 다른 앱까지 잠그지는 않습니다.')
    for start in range(0, len(cfg['tools']), 2):
        for col, tool in zip(st.columns(2), cfg['tools'][start:start + 2]):
            with col, st.container(border=True):
                st.subheader(tool['name'])
                st.text(tool['description'])
                if tool['url']:
                    st.link_button(tool['name'] + ' 열기 ↗', tool['url'], use_container_width=True)
                else:
                    st.info('선생님이 교실 설정에서 연결 주소를 등록하면 열립니다.')
    st.divider()
    with st.expander('데스모스 그래프를 교실 안에서 사용하기'):
        if st.button('교실 안 그래프 계산기 열기'):
            svc.require(token, action=True)
            st.session_state['_desmos_embed'] = True
        if st.session_state.get('_desmos_embed'):
            components.iframe('https://www.desmos.com/calculator?lang=ko', height=650, scrolling=True)
            st.caption('이 영역은 교실 화면 잠금과 함께 가려집니다. 외부 사이트 접속 정책에 따라 표시되지 않을 수 있습니다.')


@st.fragment(run_every=6)
def dashboard_table(svc, token, class_id, day):
    rows = svc.dashboard(token, class_id, day)
    active = sum(x['접속 상태'] == '접속 중' for x in rows)
    visited = sum(x['접속 상태'] != '미접속' for x in rows)
    c = st.columns(4)
    c[0].metric('등록 학생', len(rows))
    c[1].metric('지금 접속', active)
    c[2].metric('선택일 접속 이력', visited)
    c[3].metric('선택일 미접속', len(rows) - visited)
    st.caption('현재 접속은 이 앱 서버에서 최근 20초 이내에 신호가 확인된 상태입니다. 브라우저 절전·네트워크 지연·서버 재시작 시 실제 접속과 다를 수 있습니다.')
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.subheader('감정별 통계')
    counts = {label: sum(x['감정'] == label for x in rows) for label in MOODS.values()}
    st.bar_chart(pd.DataFrame({'학생 수': counts}))
    st.caption('선택일에 마지막으로 선택한 감정을 학생당 한 번 집계합니다. “아직 선택하지 않음”은 그래프에서 제외합니다. 감정은 평가·성적 산정에 사용하지 않습니다.')
    if rows:
        st.download_button('접속·감정 현황 CSV', csv_bytes(rows), file_name=f'{class_id}_{day}_현황.csv', mime='text/csv', key='dash_csv')


def dashboard_page(svc, token, user):
    svc.require(token, teacher=True)
    hero('교사 대시보드', '감정과 접속 현황은 선생님만 확인할 수 있습니다.', 'TEACHER ONLY')
    class_id = st.selectbox('확인할 학급', CLASSES, key='dash_class')
    day = st.date_input('확인할 날짜', value=date.fromisoformat(today()), max_value=date.fromisoformat(today()), key='dash_day')
    with st.container(border=True):
        st.subheader('🔒 설명 시간 · 학생 화면 제어')
        c = st.columns([2, 3])
        targets = c[0].multiselect('대상 학급', CLASSES, default=[class_id], key='lock_targets_' + class_id)
        message = c[1].text_input('학생에게 표시할 안내', value='잠시 화면에서 손을 떼고 선생님의 설명에 집중해 주세요.', max_chars=200)
        buttons = st.columns(4)
        for col, label, locked, scope in [
            (buttons[0], '선택 학급 잠금', True, targets), (buttons[1], '선택 학급 해제', False, targets),
            (buttons[2], '전체 학급 잠금', True, ['all']), (buttons[3], '전체 잠금 해제', False, ['all'] + CLASSES)]:
            if col.button(label, use_container_width=True):
                execute(lambda l=locked, s=scope: svc.set_lock(token, s, l, message), message='화면 제어 설정을 저장했습니다.')
        locks = svc.control()['locks']
        if locks.get('all', {}).get('locked'):
            st.warning('전체 잠금이 켜져 있습니다. 학급별 해제보다 전체 잠금이 우선하므로, 전체 잠금 해제를 눌러야 합니다.')
        st.caption('학생 화면은 약 3초 간격으로 확인합니다. 통신 지연이 추가될 수 있습니다. 잠금 중에는 화면·키보드 조작을 막고, 서버에서도 새로운 저장·파일 요청을 거절합니다.')
    dashboard_table(svc, token, class_id, day.isoformat())


def observations_page(svc, token, user):
    svc.require(token, teacher=True)
    hero('관찰기록 · 상점 · 벌점', '학생의 변화는 구체적인 장면과 행동으로 기록합니다.', 'TEACHER ONLY')
    class_id = st.selectbox('학급', CLASSES, key='obs_class')
    student = student_select(svc, token, class_id, 'obs_student')
    if student is None:
        return
    observations, points_tab = st.tabs(['학생 관찰기록', '상점·벌점'])
    with observations:
        name = 'observation_' + student['login_id']
        with st.form(form_key(name)):
            category = st.selectbox('관찰 영역', ['개념 이해', '수학적 사고', '문제 해결', '의사소통·협력', '학습 태도', '성장·변화', '기타'])
            content = st.text_area('실제로 관찰한 장면과 행동', max_chars=5000, height=180,
                                   placeholder='예: 원의 방정식에서 중심 좌표의 부호를 혼동했으나, 그래프와 비교해 스스로 수정함.')
            saved = st.form_submit_button('교사 전용 기록 저장', type='primary')
        if saved:
            execute(lambda: svc.add_observation(token, student['login_id'], category, content, event_id(name)),
                    form=name, message='교사 전용 관찰기록을 저장했습니다.')
        rows = [x for x in svc.observations(token, class_id) if x['student_id'] == student['login_id']]
        for row in reversed(rows):
            with st.expander(row['created_at'][:16].replace('T', ' ') + ' · ' + row['category']):
                st.text(row['content'])
        if rows:
            st.download_button('이 학생의 관찰기록 CSV', csv_bytes(rows), file_name=student['login_id'] + '_관찰기록.csv', mime='text/csv')
    with points_tab:
        name = 'points_' + student['login_id']
        with st.form(form_key(name)):
            c = st.columns(2)
            kind = c[0].radio('구분', ['상점', '벌점'], horizontal=True)
            score = int(c[1].number_input('점수', min_value=1, max_value=20, value=1))
            reason = st.text_input('사유 · 해당 학생에게 표시됩니다.', max_chars=500)
            saved = st.form_submit_button('점수 부여하고 학생에게 알리기', type='primary')
        if saved:
            execute(lambda: svc.award(token, student['login_id'], score if kind == '상점' else -score,
                    reason, event_id(name)), form=name, message='점수를 저장했습니다. 접속 중인 학생에게 알림이 표시됩니다.')
        rows = [x for x in svc.points(token, class_id) if x['student_id'] == student['login_id']]
        c = st.columns(3)
        plus = sum(x['score'] for x in rows if x['score'] > 0)
        minus = -sum(x['score'] for x in rows if x['score'] < 0)
        c[0].metric('상점 합계', plus);c[1].metric('벌점 합계', minus);c[2].metric('상점 − 벌점', plus - minus)
        st.caption('상점은 해당 학생 화면에 폭죽 효과, 벌점은 개인 안내로 표시됩니다. 미접속 중 부여한 점수는 다음 로그인 후 내 정보·알림에서 확인합니다.')
        st.dataframe(pd.DataFrame([{'일시': x['created_at'], '점수': x['score'], '사유': x['reason']} for x in rows]), hide_index=True, use_container_width=True)
        st.caption('잘못 부여한 점수는 사유를 적고 반대 점수로 조정하여 기록을 남기세요. 합계에는 각 부여·조정 내역이 모두 포함됩니다.')


def parse_roster(data: bytes) -> list[dict]:
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = data.decode('cp949')
        except UnicodeDecodeError as exc:
            raise AppError('CSV 파일을 UTF-8 또는 CP949로 저장해 주세요.') from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {'학번', '이름', '학급'}.issubset(reader.fieldnames):
        raise AppError('CSV 첫 행에 학번,이름,학급 열이 필요합니다. 샘플 양식을 사용하세요.')
    return [{k: str(row.get(k, '')).strip() for k in ('학번', '이름', '학급')} for row in reader if any(row.values())]


def students_page(svc, token, user):
    svc.require(token, teacher=True)
    hero('학생 관리', '계정 등록과 비밀번호 초기화를 관리합니다.', 'TEACHER ONLY')
    st.caption('계정은 auth/users.enc 별도 파일에 저장됩니다. 현재 비밀번호 원문은 누구도 조회할 수 없습니다.')
    st.download_button('학생 명렬 CSV 양식', (ROOT / 'examples/학생명렬_양식.csv').read_bytes(), file_name='학생명렬_양식.csv', mime='text/csv')
    single, batch, manage = st.tabs(['학생 한 명 등록', 'CSV 명렬 일괄 등록', '기존 학생 관리'])
    with single:
        name = 'single_student'
        with st.form(form_key(name)):
            c = st.columns(3)
            sid = c[0].text_input('학번 · 4~12자리', max_chars=12)
            sname = c[1].text_input('이름', max_chars=30)
            cls = c[2].selectbox('학급', CLASSES)
            saved = st.form_submit_button('학생 계정 만들기', type='primary')
        if saved:
            issued = execute(lambda: svc.auth.add_students(token, [{'학번': sid, '이름': sname, '학급': cls}]))
            if issued:
                st.session_state['_issued'] = issued
                done(name, '학생 계정을 등록했습니다. 아래 임시 비밀번호를 전달하세요.')
    with batch:
        file = st.file_uploader('명렬 CSV 올리기', type=['csv'], key='roster_upload')
        if file:
            try:
                rows = parse_roster(file.getvalue())
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                confirmed = st.checkbox('위 명렬을 확인했습니다. 실제 수업에서 사용할 학생 계정으로 등록합니다.')
                if st.button('명렬의 학생 계정 생성', disabled=not confirmed, type='primary'):
                    issued = execute(lambda: svc.auth.add_students(token, rows))
                    if issued:
                        st.session_state['_issued'] = issued
                        st.success('등록했습니다. 아래에서 임시 비밀번호를 내려받으세요.')
            except AppError as exc:
                st.error(str(exc))
    with manage:
        cls = st.selectbox('확인할 학급', CLASSES, key='manage_class')
        users = svc.auth.users(token, cls)
        st.dataframe(pd.DataFrame([{'학번': x['login_id'], '이름': x['name'], '학급': x['class_id'],
                                   '계정': '활성' if x['active'] else '중지', '첫 비밀번호 변경': '필요' if x['must_change'] else '완료'} for x in users]),
                     hide_index=True, use_container_width=True)
        if users:
            mapping = {x['login_id']: x for x in users}
            sid = st.selectbox('관리할 학생', list(mapping), format_func=lambda x: x + ' ' + mapping[x]['name'])
            with st.expander('선택 학생의 소개·관심 분야'):
                profile = svc.profile(token, sid)
                st.text(profile.get('intro') or '아직 작성한 소개가 없습니다.')
                st.text(profile.get('interests') or '아직 작성한 관심 분야가 없습니다.')
            c = st.columns(2)
            if c[0].button('선택 학생 비밀번호 초기화'):
                pw = execute(lambda: svc.auth.reset_password(token, sid))
                if pw:
                    st.session_state['_issued'] = [{'학번': sid, '이름': mapping[sid]['name'], '학급': cls, '임시비밀번호': pw}]
                    st.success('초기화했습니다. 기존 로그인은 만료됩니다.')
            target_active = not mapping[sid]['active']
            if c[1].button('선택 학생 계정 ' + ('활성화' if target_active else '중지')):
                execute(lambda: svc.auth.set_active(token, sid, target_active), form='active', message='계정 상태를 변경했습니다.')
    if st.session_state.get('_issued'):
        st.divider()
        st.warning('임시 비밀번호 · 학생 본인에게 개별 전달하세요. 내려받은 파일은 안전하게 보관한 뒤 배부 후 삭제하세요.')
        st.dataframe(pd.DataFrame(st.session_state['_issued']), use_container_width=True, hide_index=True)
        st.download_button('이번 발급 계정표 내려받기', csv_bytes(st.session_state['_issued']), file_name='임시계정_개별배부용.csv', mime='text/csv')
        if st.button('발급표를 화면과 세션에서 지우기'):
            st.session_state.pop('_issued', None)
            st.rerun()


def seats_page(svc, token, user):
    hero('좌석배치표', '우리 반 자리와 모둠을 확인해요.')
    cls = class_select(user, 'seats_class')
    saved = svc.seats(token, cls)
    if user['role'] == 'teacher':
        roster = [x for x in svc.auth.users(token, cls) if x['active']]
        if not roster:
            empty('학생 관리에서 이 학급의 명렬을 먼저 등록하세요.')
            return
        c = st.columns(2)
        rows = int(c[0].number_input('행 · 앞에서 뒤로', 1, 8, value=int(saved.get('rows', 5)), key='seat_rows_' + cls))
        cols = int(c[1].number_input('열 · 왼쪽에서 오른쪽으로', 1, 8, value=int(saved.get('cols', 5)), key='seat_cols_' + cls))
        slots = rows * cols
        labels = {'': '빈자리', **{x['login_id']: x['login_id'] + ' · ' + x['name'] for x in roster}}
        reverse_labels = {v: k for k, v in labels.items()}
        draft_key = f'_seatdraft_{cls}_{rows}_{cols}'
        if draft_key not in st.session_state:
            previous = saved.get('seats', [])
            st.session_state[draft_key] = (previous + [''] * slots)[:slots]
        if st.button('🎲 무작위 자리 배치', key='shuffle_' + cls):
            if len(roster) > slots:
                st.error('전체 학생을 배치할 좌석이 부족합니다. 행 또는 열을 늘려 주세요.')
            else:
                candidates = [x['login_id'] for x in roster] + [''] * (slots - len(roster))
                random.SystemRandom().shuffle(candidates)
                st.session_state[draft_key] = candidates
                st.session_state['_seat_editor_rev'] = st.session_state.get('_seat_editor_rev', 0) + 1
                st.rerun()
        grid = {f'{col + 1}열': [labels.get(st.session_state[draft_key][r * cols + col], '빈자리') for r in range(rows)] for col in range(cols)}
        st.markdown('<div class="seat-front">칠판 · 선생님 자리</div>', unsafe_allow_html=True)
        st.caption('표의 각 칸을 눌러 학생을 직접 바꿀 수 있습니다. 같은 학생의 중복 배치는 저장되지 않습니다.')
        with st.form('seats_form_' + cls + '_' + str(rows) + '_' + str(cols)):
            edited = st.data_editor(pd.DataFrame(grid), hide_index=False, use_container_width=True,
                column_config={k: st.column_config.SelectboxColumn(k, options=list(labels.values()), required=True) for k in grid},
                key=f'seat_editor_{cls}_{rows}_{cols}_{st.session_state.get("_seat_editor_rev", 0)}')
            group_rows = [{'학번': x['login_id'], '이름': x['name'], '모둠': saved.get('groups', {}).get(x['login_id'], 0)} for x in roster]
            st.markdown('**모둠 배정 · 0은 미배정입니다.**')
            groups = st.data_editor(pd.DataFrame(group_rows), hide_index=True, disabled=['학번', '이름'],
                column_config={'모둠': st.column_config.NumberColumn('모둠', min_value=0, max_value=10, step=1, required=True)},
                key='group_editor_' + cls)
            published = st.checkbox('이 좌석표와 모둠을 해당 학급 학생들에게 공개합니다.', value=saved.get('published', False))
            submit = st.form_submit_button('좌석표·모둠 저장', type='primary')
        if submit:
            seat_values = [reverse_labels.get(str(edited.iloc[r, col]), '') for r in range(rows) for col in range(cols)]
            group_values = {str(x['학번']): int(x['모둠']) for x in groups.to_dict('records')}
            try:
                svc.save_seats(token, cls, rows, cols, seat_values, group_values, published)
                st.session_state[draft_key] = seat_values
                st.success('좌석표와 모둠을 저장했습니다.')
                saved = svc.seats(token, cls)
            except AppError as exc:
                st.error(str(exc))
    if not saved:
        empty('아직 공개된 좌석배치표가 없습니다.')
        return
    st.subheader('저장된 좌석표')
    if user['role'] == 'teacher':
        st.caption('학생에게 공개 중' if saved['published'] else '교사만 확인 · 아직 학생에게 공개하지 않았습니다.')
    st.markdown('<div class="seat-front">칠판 · 선생님 자리</div>', unsafe_allow_html=True)
    for r in range(saved['rows']):
        columns = st.columns(saved['cols'])
        for c, col in enumerate(columns):
            sid = saved['seats'][r * saved['cols'] + c]
            mine = sid and sid == user['login_id']
            name = saved['names'].get(sid, '빈자리')
            col.markdown('<div class="seat' + (' mine' if mine else '') + '"><small>' + html.escape(sid or '—') +
                         '</small><strong>' + html.escape(name) + (' 👋' if mine else '') + '</strong></div>', unsafe_allow_html=True)
    groups = saved.get('groups', {})
    if any(groups.values()):
        st.subheader('우리 반 모둠')
        for group in sorted(set(groups.values()) - {0}):
            names = [saved['names'].get(sid, sid) for sid, value in groups.items() if value == group]
            st.write(str(group) + '모둠 · ' + ', '.join(names))
    if user['role'] == 'teacher':
        export = [{'행': i // saved['cols'] + 1, '열': i % saved['cols'] + 1, '학번': sid,
                   '이름': saved['names'].get(sid, ''), '모둠': groups.get(sid, 0)} for i, sid in enumerate(saved['seats'])]
        st.download_button('좌석표 CSV', csv_bytes(export), file_name=cls + '_좌석배치.csv', mime='text/csv')


def settings_page(svc, token, user, cfg):
    svc.require(token, teacher=True)
    hero('교실 설정', '소개, 관심 분야, 단원과 수업도구 주소를 바꿀 수 있습니다.', 'TEACHER ONLY')
    name = 'settings'
    with st.form(form_key(name)):
        title = st.text_input('교실 이름', value=cfg['title'], max_chars=60)
        tagline = st.text_input('한 줄 소개', value=cfg['tagline'], max_chars=150)
        about = st.text_area('간단한 내 소개', value=cfg['about'], max_chars=3000)
        interests = st.text_area('내가 공부하는 분야·관심 분야', value=cfg['interests'], max_chars=3000)
        c = st.columns(2)
        units = {}
        for col, course in zip(c, COURSES):
            value = col.text_area(COURSES[course] + ' 단원 · 한 줄에 하나', value='\n'.join(cfg['units'][course]))
            units[course] = value.splitlines()
        st.markdown('**수업도구 · https 주소를 입력하세요.**')
        tools = st.data_editor(pd.DataFrame(cfg['tools']), num_rows='dynamic', hide_index=True, use_container_width=True,
                              column_config={'name': '도구 이름', 'url': '연결 주소', 'description': '설명'})
        ai_enabled = st.checkbox('학생 선택 동의가 있을 때 AI 텍스트 피드백을 사용합니다.', value=cfg['ai_enabled'])
        st.caption('기본은 꺼짐입니다. API 키와 모델 설정이 있어야 켜집니다. 비용 및 학교의 외부 서비스 이용 기준을 확인하세요. 학생이 동의하지 않으면 제출 확인만 제공합니다.')
        saved = st.form_submit_button('교실 설정 저장', type='primary')
    if saved:
        rows = tools.fillna('').to_dict('records')
        execute(lambda: svc.save_settings(token, {'title': title, 'tagline': tagline, 'about': about,
                'interests': interests, 'units': units, 'tools': rows, 'ai_enabled': ai_enabled}),
                form=name, message='교실 설정을 저장했습니다.')
    st.divider()
    st.subheader('저장 상태')
    st.write('운영 모드: ' + svc.store.backend.mode)
    if svc.store.backend.mode == 'github':
        st.code(svc.store.backend.repo)
        st.caption('데이터 저장소는 앱 코드 저장소와 분리하세요. 암호화키는 GitHub가 아닌 Secrets와 안전한 별도 장소에 보관하세요.')



def profile_page(svc, token, user):
    hero('내 정보', user['name'] + ' · ' + (user['class_id'] if user['role'] == 'student' else '교사'))
    if user.get('must_change'):
        st.warning('처음 발급받은 임시 비밀번호를 본인만 아는 새 비밀번호로 변경하세요. 변경 후 다시 로그인합니다.')
    name = 'password'
    with st.form(form_key(name)):
        st.subheader('비밀번호 변경')
        old = st.text_input('현재 비밀번호', type='password', max_chars=128)
        new = st.text_input('새 비밀번호 · 10자 이상', type='password', max_chars=128)
        confirm = st.text_input('새 비밀번호 확인', type='password', max_chars=128)
        saved = st.form_submit_button('비밀번호 변경 후 다시 로그인', type='primary')
    if saved:
        if new != confirm:
            st.error('새 비밀번호 확인이 일치하지 않습니다.')
        else:
            try:
                svc.change_password(token, old, new)
                st.session_state.clear()
                st.session_state['_flash'] = '비밀번호를 변경했습니다. 새 비밀번호로 로그인하세요.'
                st.rerun()
            except AppError as exc:
                st.error(str(exc))
    if user['role'] == 'student' and not user.get('must_change'):
        data = svc.profile(token)
        name = 'profile'
        with st.form(form_key(name)):
            st.subheader('간단한 내 소개')
            st.caption('본인과 교사만 볼 수 있는 개인 기록입니다.')
            intro = st.text_area('나는 이런 사람이에요.', value=data['intro'], max_chars=1500)
            interests = st.text_area('내가 공부하는 분야·관심 있는 분야', value=data['interests'], max_chars=1500)
            saved = st.form_submit_button('소개 저장')
        if saved:
            execute(lambda: svc.save_profile(token, intro, interests), form=name, message='내 소개를 저장했습니다.')
        st.subheader('나의 상점·벌점 기록')
        rows = svc.points(token)
        st.dataframe(pd.DataFrame([{'일시': x['created_at'], '점수': x['score'], '사유': x['reason']} for x in rows]), hide_index=True, use_container_width=True)


def run_ui(svc):
    css()
    if st.session_state.get('_flash'):
        st.toast(st.session_state.pop('_flash'))
    token = st.session_state.get('token')
    if not token:
        login_page(svc)
        return
    try:
        user = svc.require(token)
    except AppError as exc:
        frame({'locked': False, 'watchdog': False, 'events': []})
        if token not in svc.auth.sessions:
            st.session_state.clear()
        st.error(str(exc))
        if st.button('로그인 화면으로'):
            st.session_state.clear()
            st.rerun()
        return
    cfg = svc.settings(token)
    live_monitor(svc, token)
    menu = sidebar(svc, token, user, cfg)
    try:
        if user.get('must_change'):
            profile_page(svc, token, user)
            return
        if menu == '🏡 우리 교실': home_page(svc, token, user, cfg)
        elif menu == '📘 공통수학1': course_page(svc, token, user, 'math1', cfg)
        elif menu == '📗 공통수학2': course_page(svc, token, user, 'math2', cfg)
        elif menu == '✍️ 수다노트': notes_page(svc, token, user, cfg)
        elif menu == '💬 질문 게시판': questions_page(svc, token, user)
        elif menu == '🧰 수업도구': tools_page(svc, token, user, cfg)
        elif menu == '🪑 좌석배치표': seats_page(svc, token, user)
        elif menu == '📊 교사 대시보드': dashboard_page(svc, token, user)
        elif menu == '📝 관찰기록·상벌점': observations_page(svc, token, user)
        elif menu == '👥 학생 관리': students_page(svc, token, user)
        elif menu == '⚙️ 교실 설정': settings_page(svc, token, user, cfg)
        elif menu == '🙋 내 정보': profile_page(svc, token, user)
    except AppError as exc:
        st.error(str(exc))
    if user['role'] == 'student' and st.session_state.get('_needs_mood') and not st.session_state.get('_locked'):
        mood_dialog(svc, token)
