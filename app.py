"""GitHub / Streamlit Community Cloud 진입 파일: streamlit run app.py"""
from __future__ import annotations
from pathlib import Path
import streamlit as st

from backend import sign_in, bootstrap
from utils import CLASSES, MOODS, MOOD_MESSAGES
from ui import apply_style, hero, safe_error, fireworks
import views
from teacher import teacher_page

st.set_page_config(page_title="구쌤의 수학 교실",page_icon="📘",layout="wide")
apply_style()


def load_config():
    try:
        return st.secrets.to_dict()
    except (FileNotFoundError,KeyError):
        return {}


def configuration_ready(config):
    db=config.get("supabase",{})
    return all(
        isinstance(db.get(k), str) and db[k].strip()
        and not any(word in db[k] for word in ("YOUR_PROJECT", "REPLACE_ME"))
        for k in ("url", "publishable_key", "secret_key")
    )


def setup_page():
    # This setup panel is a Streamlit component, not an HTML document.
    st.subheader("Supabase 연결 설정")
    st.info("실제 학생 정보는 아직 연결되지 않았습니다. GitHub 코드에는 학생 명단과 비밀번호를 넣지 마세요.")
    st.markdown("""### 처음 실행하는 순서
1. Supabase에서 새 프로젝트를 만듭니다.
2. SQL Editor에서 `supabase/schema.sql` 전체를 실행합니다.
3. Streamlit의 Settings → Secrets에 아래 예시를 붙여넣고 실제 연결 값으로 바꿉니다.
4. 앱을 다시 열고 ‘처음 교사 계정 만들기’를 진행합니다.

자세한 설명은 프로젝트의 `docs/처음시작.md`를 읽어 주세요.""")
    example=Path(__file__).parent/".streamlit"/"secrets.toml.example"
    st.code(example.read_text(encoding="utf-8"),language="toml")


def login_page(config):
    ready = configuration_ready(config)
    left,right=st.columns([1.15,1],gap="large")
    with left:
        hero("생각을 꺼내는 수학 교실", "틀려도 괜찮아요. 내 생각을 설명하는 순간, 배움이 시작됩니다.")
        st.markdown("### 오늘의 작은 발견을 함께 기록해요")
        st.write("📚 자료 받기　→　✍️ 활동 제출　→　💬 피드백　→　🌱 수다노트")
        st.caption("학번·비밀번호로 로그인합니다. 교사 아이디는 teacher입니다.")
    with right:
        with st.container(border=True):
            st.subheader("우리 교실 로그인")
            if not ready:
                st.info("Supabase를 연결하면 학번 로그인을 사용할 수 있습니다. 선생님은 아래의 연결 설정을 진행해 주세요.")
            with st.form("login",clear_on_submit=True):
                login_id=st.text_input("학번 / 교사 아이디",placeholder="예: 10102 또는 teacher",max_chars=30,disabled=not ready)
                password=st.text_input("비밀번호",type="password",max_chars=100,disabled=not ready)
                if st.form_submit_button("로그인",type="primary",use_container_width=True,disabled=not ready):
                    try:
                        if not login_id.strip() or not password:raise ValueError("학번과 비밀번호를 입력하세요.")
                        b=sign_in(config,login_id.strip(),password)
                        # Backend and Auth session are private to this Streamlit browser session.
                        st.session_state.clear()
                        st.session_state["backend"]=b
                        st.session_state["need_mood"]=True
                        st.rerun()
                    except Exception as exc:safe_error(exc)
            st.caption("비밀번호를 잊었나요? 선생님께 임시 비밀번호 재발급을 요청하세요.")
    if not ready:
        with st.expander("교사용 · Supabase 연결 설정", expanded=False):
            setup_page()
        return
    with st.expander("교사용 · 처음 교사 계정 만들기 (최초 1회)"):
        st.caption("Supabase SQL과 Secrets 설정을 마친 뒤 사용하세요. setup_token은 학생에게 알려 주지 마세요.")
        with st.form("bootstrap",clear_on_submit=True):
            token=st.text_input("Secrets에 저장한 초기 설정 코드",type="password")
            pw=st.text_input("교사 비밀번호 (10자 이상)",type="password")
            again=st.text_input("교사 비밀번호 확인",type="password")
            if st.form_submit_button("교사 계정 생성"):
                try:
                    if pw!=again:raise ValueError("비밀번호 두 칸이 일치하지 않습니다.")
                    bootstrap(config,token,pw)
                    st.success("교사 계정을 만들었습니다. 위에서 teacher로 로그인하세요. 이후 Secrets의 setup_token을 빈 문자열로 지우세요.")
                except Exception as exc:safe_error(exc)


def preserve_drafts():
    drafts=st.session_state.setdefault("draft_notes",{})
    for key in list(st.session_state):
        if str(key).startswith("draft_note_"):
            drafts[str(key).removeprefix("draft_note_")]=st.session_state[key]


@st.fragment(run_every="5s")
def pulse():
    b=st.session_state["backend"]
    try:
        current=b.rpc("app_poll")
    except Exception:
        if not st.session_state.get("connection_lost"):
            st.session_state["connection_lost"]=True
            preserve_drafts();st.rerun()
        st.caption("연결 확인 중입니다. 연결이 복구되기 전에는 학습 기능이 차단됩니다.")
        return
    if st.session_state.pop("connection_lost",False):st.rerun()
    old=st.session_state.get("status",{})
    if any(old.get(k)!=current.get(k) for k in ("locked","session_id","must_change_password")):
        if old.get("session_id")!=current.get("session_id"):
            st.session_state["need_mood"]=True
        preserve_drafts()
        st.session_state["status"]=current
        st.rerun()
    st.session_state["status"]=current
    if current.get("locked") or current.get("must_change_password"):
        return
    if current.get("pending",0):
        try:
            notes=b.rows("notifications",{"user_id":b.user_id,"seen_at":None},"created_at")
            burst=False
            for n in notes[:5]:
                if not b.rpc("app_mark_notice",{"notice":n["id"]}):
                    continue
                if n["kind"]=="merit":
                    st.success(n["body"]);burst=True
                elif n["kind"]=="demerit":st.warning(n["body"])
                else:st.info(n["body"])
            if burst and not st.session_state.get("reduce_motion",False):fireworks()
        except Exception:
            st.caption("알림은 내 계정·내 제출물에서 다시 확인할 수 있습니다.")


@st.dialog("오늘, 나의 마음 날씨는?",dismissible=False)
def mood_dialog():
    st.write("지금 내 상태와 가까운 것을 골라 주세요. 정답은 없어요. 선택은 선생님만 확인할 수 있어요.")
    b=st.session_state["backend"]
    for i,(key,label) in enumerate(MOODS.items()):
        if st.button(label,key=f"mood_{key}",use_container_width=True):
            try:
                b.rpc("app_set_mood",{"mood":key})
                st.session_state["need_mood"]=False
                st.session_state["flash"]=MOOD_MESSAGES[key]
                st.rerun()
            except Exception as exc:
                safe_error(exc)
                # A lock can arrive while the modal is open. Refresh to the lock screen.
                try:
                    if b.rpc("app_poll").get("locked"):st.rerun()
                except Exception:pass


def main():
    config=load_config()
    if not configuration_ready(config):
        # Keep the requested login screen as the initial app screen.
        # Never allow unconfigured or mock credentials to access student data.
        login_page(config)
        return
    if "backend" not in st.session_state:login_page(config);return
    b=st.session_state["backend"]
    # Reflect changed Secrets without keeping obsolete approval flags in a long-lived session.
    b.config=config
    try:p=b.profile()
    except Exception:
        st.session_state.clear()
        st.warning("인증 또는 연결 상태를 확인하지 못했습니다. 다시 로그인하세요.")
        if st.button("로그인 화면으로"):st.rerun()
        return
    teacher=p["role"]=="teacher"
    with st.sidebar:
        st.markdown("## 📘 구쌤의 수학 교실")
        st.caption("THINK · EXPLAIN · GROW")
        st.write(f"**{p['full_name']}** · {'교사' if teacher else p['class_id']}")
        if st.button("로그아웃",use_container_width=True):
            try:b.logout()
            except Exception:pass
            st.session_state.clear();st.rerun()
    if p["must_change_password"]:
        views.account(b,p,force=True);return
    if not teacher:
        try:
            previous=st.session_state.get("status",{})
            status=b.rpc("app_poll")
            if previous.get("session_id")!=status.get("session_id"):st.session_state["need_mood"]=True
            st.session_state["status"]=status
        except Exception:
            st.session_state["connection_lost"]=True
        pulse()
        status=st.session_state.get("status",{})
        if st.session_state.get("connection_lost"):
            hero("연결을 확인하고 있어요", "안전하게 연결이 복구되면 수업을 이어갈 수 있어요.")
            return
        if status.get("locked"):
            preserve_drafts()
            hero("🔒 지금은 선생님의 설명을 듣는 시간", "화면에서 잠시 눈을 떼고 함께 생각해 봅시다.","PAUSE · LISTEN · THINK")
            st.info("선생님이 잠금을 해제하면 다시 사용할 수 있어요. 로그인은 유지됩니다.")
            st.caption("이미 저장된 제출물은 안전합니다. 아직 제출하지 않은 파일은 해제 후 다시 선택해야 할 수 있습니다.")
            return
    with st.sidebar:
        if teacher:
            cls=st.selectbox("관리 학급",CLASSES,key="teacher_class")
            all_classes=st.checkbox("잠금을 전체 7개 반에 적용",value=False)
            targets=CLASSES if all_classes else [cls]
            a,c=st.columns(2)
            if a.button("🔒 잠금",use_container_width=True):
                b.require_teacher();b.client.table("classrooms").update({"locked":True}).in_("id",targets).execute();st.rerun()
            if c.button("🔓 해제",use_container_width=True):
                b.require_teacher();b.client.table("classrooms").update({"locked":False}).in_("id",targets).execute();st.rerun()
            st.caption("앱 안의 학습 기능만 제어합니다.")
        pages=["홈","구쌤 소개","공부·관심 분야","공통수학1","공통수학2","수다노트","수업도구","내 계정"]
        if teacher:pages.append("교사전용")
        last=st.session_state.get("last_page","홈")
        page=st.radio("메뉴",pages,index=pages.index(last) if last in pages else 0,key="navigation")
        st.session_state["last_page"]=page
    flash=st.session_state.pop("flash",None)
    if flash:st.success(flash)
    if not teacher and st.session_state.get("need_mood"):
        mood_dialog()
    try:
        if page=="홈":views.home(b,p)
        elif page in ("구쌤 소개","공부·관심 분야"):views.info_page(b,page)
        elif page in ("공통수학1","공통수학2"):views.course(b,p,page)
        elif page=="수다노트":views.suda()
        elif page=="수업도구":views.tools(b)
        elif page=="내 계정":views.account(b,p)
        elif page=="교사전용":teacher_page(b,p,st.session_state.get("teacher_class","1-1"))
    except Exception as exc:safe_error(exc)


if __name__=="__main__":main()
