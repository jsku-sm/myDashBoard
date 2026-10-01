"""교과 게시판과 학생 공간. 화면 숨김과 별개로 backend/SQL에서도 권한 검사."""
from __future__ import annotations
from datetime import datetime, timezone
import streamlit as st
from ui import hero, local_time, safe_error, download_file
from utils import CLASSES, SUBJECTS, SUDA_GUIDE, SUDA_URL, point_totals, validate_url


def home(b, p):
    teacher = p["role"] == "teacher"
    hero(f"{p['full_name']} 선생님, 안녕하세요" if teacher else f"{p['full_name']}님, 오늘도 한 걸음",
         "자료 준비부터 배움의 기록까지, 우리 수학 교실" if teacher else "자료를 살펴보고, 생각을 남기고, 다음 질문을 찾아봐요.")
    if teacher:
        cols = st.columns(3)
        cols[0].metric("담당 학급", "7개")
        cols[1].metric("등록 학생", len(b.rows("profiles", {"role": "student", "active": True})))
        cols[2].metric("답변 대기", sum(not q["answer"] for q in b.rows("questions")))
        st.info("왼쪽 ‘교사전용’에서 수업 시작·화면 잠금·마음 날씨·관찰·좌석표를 관리하세요.")
        return
    points = b.rows("points", {"user_id": p["id"]})
    good, bad, net = point_totals(points)
    cols = st.columns(3)
    cols[0].metric("내 상점 누계", f"{good}점")
    cols[1].metric("내 벌점 누계", f"{bad}점")
    cols[2].metric("상점 − 벌점", f"{net}점")
    st.caption("취소된 부과 건은 누계에서 제외합니다. 다른 학생에게는 보이지 않습니다.")
    st.subheader("오늘의 수업 흐름")
    for col, title, body in zip(st.columns(4), ["01 · 자료 받기", "02 · 생각 남기기", "03 · 피드백 보기", "04 · 수다노트"],
                                ["과목과 단원을 찾아 학습지를 받아요.", "활동 결과와 풀이 설명을 제출해요.", "확인할 부분과 다음 질문을 읽어요.", "내가 이해한 것을 내 언어로 정리해요."]):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(body)
    notes = b.rows("notifications", {"user_id": p["id"]}, "created_at", True)
    if notes:
        st.subheader("최근 알림")
        for n in notes[:5]:
            st.write(f"{local_time(n['created_at'])} · {n['body']}")


def info_page(b, page):
    settings = b.settings()
    if page == "구쌤 소개":
        hero("생각이 자라는 수학 교실", "가르치는 사람도, 배우는 사람도 함께 성장합니다.")
        st.subheader("안녕하세요, 구쌤입니다.")
        st.write(settings["intro"])
    else:
        hero("배우고, 연결하고, 나눕니다", "구쌤이 공부하는 분야와 관심 주제")
        for text in settings["interests"].splitlines():
            if text.strip():
                with st.container(border=True):
                    st.markdown(f"### {text.strip()}")


def suda():
    hero("수다노트", "수학을 다시 말하는 시간")
    st.markdown(SUDA_GUIDE)
    st.link_button("✍️ 오늘의 수다노트 작성하기", SUDA_URL, type="primary")
    st.caption("구글폼이 새 탭에서 열립니다. 현재 버전은 링크 연결이며 제출 여부는 자동으로 읽지 않습니다.")


def tools(b):
    hero("수업도구", "필요한 도구를 골라, 생각을 더 멀리")
    settings = b.settings()
    for category in ("수업도구", "퀴즈", "앱 (by 구쌤)"):
        st.subheader(category)
        items = [x for x in settings["tools"] if x.get("category", "수업도구") == category]
        if not items:
            st.info("교사전용 → 소개·도구 설정에서 연결할 이름과 주소를 등록하세요.")
        for i, item in enumerate(items):
            with st.container(border=True):
                left, right = st.columns([4, 1])
                left.markdown(f"**{item['name']}**")
                left.write(item.get("description", ""))
                try:
                    right.link_button("열기 ↗", validate_url(item["url"]), use_container_width=True)
                except ValueError:
                    right.caption("주소 확인 필요")
    st.caption("외부 사이트에는 별도 로그인이 필요할 수 있습니다. 이미 열린 외부 탭은 이 앱의 잠금으로 제어되지 않습니다.")


def material_board(b, teacher: bool, subject: str, unit: str, kinds: list[str], key: str):
    settings = b.settings()
    if teacher:
        with st.expander("➕ 자료 등록"):
            with st.form(f"material_form_{key}", clear_on_submit=True):
                title = st.text_input("자료 제목", max_chars=150)
                unit2 = st.selectbox("단원", settings["units"][subject], key=f"mu_{key}")
                kind = st.selectbox("자료 종류", kinds, key=f"mk_{key}")
                cls = st.selectbox("공개 학급", ["전체 학급"] + CLASSES, key=f"mc_{key}")
                description = st.text_area("설명", max_chars=3000)
                upload = st.file_uploader("PDF·JPG·PNG / 최대 20MB", type=["pdf", "jpg", "jpeg", "png"], key=f"mf_{key}")
                if st.form_submit_button("자료 올리기", type="primary"):
                    try:
                        if not title.strip() or upload is None:
                            raise ValueError("제목과 파일을 확인해 주세요.")
                        b.upload_material({"subject": subject, "unit": unit2, "title": title.strip(),
                                           "kind": kind, "description": description,
                                           "class_id": None if cls == "전체 학급" else cls}, upload.name, upload.getvalue())
                        st.success("자료를 등록했습니다.")
                    except Exception as exc:
                        safe_error(exc)
    items = [m for m in b.rows("materials", {"subject": subject}, "created_at", True)
             if m["kind"] in kinds and (unit == "전체 단원" or m["unit"] == unit)]
    if not items:
        st.info("등록된 자료가 없습니다.")
    for item in items:
        with st.expander(f"{item['kind']} · {item['title']} · {item['unit']}"):
            st.caption(f"{item['class_id'] or '전체 학급'} · {local_time(item['created_at'])}")
            st.write(item["description"])
            download_file(b, item, f"{key}_{item['id']}")
            if teacher:
                confirm = st.checkbox("이 자료 파일을 삭제합니다", key=f"delcheck_{item['id']}")
                if st.button("자료 삭제", disabled=not confirm, key=f"delmat_{item['id']}"):
                    try:
                        b.remove_material(item)
                        st.rerun()
                    except Exception as exc:
                        safe_error(exc)


def assignment_board(b, p, subject: str, unit: str):
    teacher = p["role"] == "teacher"
    units = b.settings()["units"][subject]
    cls = st.selectbox("학급별 제출 게시판", CLASSES, key=f"aclass_{subject}") if teacher else p["class_id"]
    if not teacher:
        st.caption(f"{cls} 활동 제출 게시판 · 내 제출물과 교사가 지정한 우리 반 공유 과제만 볼 수 있어요.")
    if teacher:
        with st.expander("➕ 활동 과제 만들기"):
            with st.form(f"newassignment_{subject}", clear_on_submit=True):
                title = st.text_input("과제 제목", max_chars=150)
                u = st.selectbox("과제 단원", units)
                targets = st.multiselect("대상 학급", CLASSES, default=[cls])
                instructions = st.text_area("활동 안내·학습 목표", max_chars=6000)
                rubric = st.text_area("AI와 교사가 확인할 기준", placeholder="예: 교집합의 의미를 설명하는가? 공통 원소를 중복 없이 찾는가?", max_chars=4000)
                shared = st.checkbox("같은 반에 제출물을 공유하는 과제입니다", value=False)
                ai = st.checkbox("이 과제에서 AI 학습 피드백을 사용합니다", value=False)
                st.caption("공유 과제라도 AI·교사 피드백은 본인·교사만 열람합니다. AI는 Secrets 연결과 학생의 분석 신청이 모두 필요합니다.")
                if st.form_submit_button("과제 등록", type="primary"):
                    try:
                        if not title.strip() or not targets:
                            raise ValueError("과제 제목과 대상 학급이 필요합니다.")
                        for target in targets:
                            b.insert("assignments", {"subject": subject, "unit": u, "class_id": target,
                                      "title": title.strip(), "instructions": instructions, "rubric": rubric,
                                      "shared": shared, "ai_enabled": ai})
                        st.success(f"{len(targets)}개 반에 과제를 등록했습니다.")
                    except Exception as exc:
                        safe_error(exc)
    assignments = [a for a in b.rows("assignments", {"subject": subject, "class_id": cls}, "created_at", True)
                   if unit == "전체 단원" or a["unit"] == unit]
    if not assignments:
        st.info("등록된 활동 과제가 없습니다.")
        return
    selected = st.selectbox("활동 과제", assignments, format_func=lambda a: f"{'[마감] ' if a['closed'] else ''}{a['unit']} · {a['title']}", key=f"pickassign_{subject}")
    aid = selected["id"]
    st.write(selected["instructions"])
    st.info("우리 반 공유 과제입니다. 파일 안에 공개할 수 없는 개인정보를 넣지 마세요." if selected["shared"] else "개별 제출 과제입니다. 학생 본인과 교사만 열람합니다.")
    if teacher:
        a1, a2 = st.columns(2)
        with a1:
            if st.button("제출 다시 열기" if selected["closed"] else "제출 마감하기", key=f"close_{aid}"):
                b.teacher_update("assignments", {"closed": not selected["closed"]}, "id", aid)
                st.rerun()
        with a2:
            new_shared = st.toggle("우리 반 공유", value=selected["shared"], key=f"shared_{aid}")
            if new_shared != selected["shared"]:
                b.teacher_update("assignments", {"shared": new_shared}, "id", aid)
                st.rerun()
        with st.expander("과제 안내·피드백 기준 수정"):
            with st.form(f"editassignment_{aid}"):
                e_title = st.text_input("제목", value=selected["title"], max_chars=150)
                e_note = st.text_area("안내", value=selected["instructions"], max_chars=6000)
                e_rubric = st.text_area("피드백 기준", value=selected["rubric"], max_chars=4000)
                e_ai = st.checkbox("AI 사용", value=selected["ai_enabled"])
                if st.form_submit_button("수정 저장"):
                    if e_title.strip():
                        b.teacher_update("assignments", {"title": e_title.strip(), "instructions": e_note,
                                         "rubric": e_rubric, "ai_enabled": e_ai}, "id", aid)
                        st.rerun()
        with st.expander("과제·제출파일 삭제 (복구 불가)"):
            confirmation = st.text_input("삭제하려면 과제 제목을 그대로 입력", key=f"delete_a_{aid}")
            if st.button("이 과제와 모든 제출물 삭제", key=f"delete_ab_{aid}", disabled=confirmation != selected["title"]):
                b.delete_assignment(selected)
                st.rerun()
    elif not selected["closed"]:
        st.subheader("내 활동 제출")
        upload = st.file_uploader("필기 PDF 또는 사진 / 최대 20MB", type=["pdf", "jpg", "jpeg", "png"], key=f"student_upload_{aid}")
        draft = st.session_state.setdefault("draft_notes", {})
        note = st.text_area("풀이를 어떻게 생각했나요?", value=draft.get(aid, ""), max_chars=5000, key=f"draft_note_{aid}",
                            placeholder="처음 생각 → 확인한 방법 → 지금 이해한 내용을 적어 보세요.")
        draft[aid] = note
        consent = False
        ai = b.config.get("ai", {})
        if selected["ai_enabled"] and ai.get("approved") and ai.get("openai_api_key"):
            consent = st.checkbox("제출파일과 풀이 설명을 외부 AI에 전달하여 학습 피드백을 받겠습니다.", key=f"consent_{aid}")
            st.caption("OpenAI API로 전달됩니다. 파일 본문에 쓴 이름도 전달될 수 있어요. 선택하지 않아도 제출할 수 있습니다. AI 피드백은 교사 검토 전 참고 의견입니다.")
        else:
            st.caption("AI 미연결 또는 미사용 과제입니다. 제출 확인만 제공됩니다.")
        if st.button("활동 결과 제출", type="primary", disabled=upload is None, key=f"submit_{aid}"):
            try:
                with st.spinner("제출물을 저장하고 있습니다. AI를 신청한 경우 분석도 진행합니다."):
                    _, status = b.submit(selected, upload.name, upload.getvalue(), note, consent)
                st.success(status)
            except Exception as exc:
                safe_error(exc)
    submissions = b.rows("submissions", {"assignment_id": aid}, "created_at", True)
    profiles = {x["id"]: x for x in b.rows("profiles", {"class_id": cls, "role": "student", "active": True})} if teacher else {p["id"]: p}
    if teacher:
        submitted = {s["user_id"] for s in submissions}
        cols = st.columns(3)
        cols[0].metric("대상", len(profiles)); cols[1].metric("제출", len(set(profiles) & submitted)); cols[2].metric("미제출", len(set(profiles)-submitted))
        with st.expander("미제출 학생"):
            st.dataframe([{"학번": x["student_id"], "이름": x["full_name"]} for uid, x in profiles.items() if uid not in submitted], hide_index=True)
    own = submissions if teacher else [s for s in submissions if s["user_id"] == p["id"]]
    st.subheader("제출물·피드백" if teacher else "내 제출물·피드백")
    if own:
        def label(s):
            owner = profiles.get(s["user_id"], {})
            return f"{owner.get('student_id', '')} {owner.get('full_name', '')} · {local_time(s['created_at'])} · {s['filename']}"
        s = st.selectbox("열람할 제출물 (재제출 이력 포함)", own, format_func=label, key=f"submission_pick_{aid}")
        st.write(s["note"] or "풀이 설명 없음")
        download_file(b, s, f"submission_{s['id']}")
        for f in b.rows("feedback", {"submission_id": s["id"]}, "created_at"):
            with st.container(border=True):
                st.markdown(f"**{'선생님' if f['source']=='teacher' else 'AI · 교사 검토 전 참고 의견' if f['source']=='ai' else '안내'}** · {local_time(f['created_at'])}")
                st.write(f["body"])
        if teacher:
            text = st.text_area("교사 피드백 또는 AI 피드백 보완", key=f"feedback_{s['id']}", max_chars=5000)
            if st.button("교사 피드백 보내기", key=f"sendfb_{s['id']}", disabled=not text.strip()):
                b.add_teacher_feedback(s, text.strip())
                st.rerun()
            if st.button("AI 피드백 재시도 (미생성 건만)", key=f"retryai_{s['id']}"):
                with st.spinner("분석 중입니다."):
                    st.info(b.generate_feedback(s, selected))
    else:
        st.caption("아직 제출물이 없습니다.")
    if not teacher and selected["shared"]:
        st.subheader("우리 반이 공유한 생각")
        others = [s for s in submissions if s["user_id"] != p["id"]]
        if others:
            item = st.selectbox("공유 제출물", others, format_func=lambda s: f"{local_time(s['created_at'])} · {s['filename']}", key=f"peer_{aid}")
            st.write(item["note"])
            download_file(b, item, f"peer_{item['id']}")
        else:
            st.caption("아직 다른 공유 제출물이 없습니다.")


def questions_board(b, p, subject: str, unit: str):
    teacher = p["role"] == "teacher"
    cls = st.selectbox("질문 학급", CLASSES, key=f"qclass_{subject}") if teacher else p["class_id"]
    if not teacher:
        with st.form(f"questionform_{subject}", clear_on_submit=True):
            u = st.selectbox("질문 단원", b.settings()["units"][subject])
            text = st.text_area("어디까지 이해했고, 어느 부분이 궁금한가요?", max_chars=5000)
            shared = st.checkbox("질문과 교사 답변을 우리 반에도 공개합니다", value=False)
            if st.form_submit_button("질문 남기기", type="primary"):
                try:
                    if not text.strip():
                        raise ValueError("질문을 입력해 주세요.")
                    b.insert("questions", {"user_id": p["id"], "class_id": cls, "subject": subject,
                                           "unit": u, "body": text.strip(), "shared": shared})
                    st.success("질문을 남겼습니다.")
                except Exception as exc:
                    safe_error(exc)
    people = {x["id"]: x for x in b.rows("profiles", {"class_id": cls})} if teacher else {}
    qs = [q for q in b.rows("questions", {"subject": subject, "class_id": cls}, "created_at", True)
          if unit == "전체 단원" or q["unit"] == unit]
    if not qs:
        st.info("등록된 질문이 없습니다.")
    for q in qs:
        person = people.get(q["user_id"], {}).get("full_name", "내 질문" if q["user_id"]==p["id"] else "우리 반 질문")
        with st.expander(f"{'✅' if q['answer'] else '💬'} {person} · {q['body'][:40]} · {local_time(q['created_at'])}"):
            st.caption("우리 반 공개" if q["shared"] else "본인·교사만 공개")
            st.write(q["body"])
            if q["answer"]:
                st.success(q["answer"])
            if teacher:
                answer = st.text_area("답변", value=q["answer"], key=f"answer_{q['id']}", max_chars=5000)
                if st.button("답변 저장", key=f"answerbtn_{q['id']}", disabled=not answer.strip()):
                    b.teacher_update("questions", {"answer": answer, "answered_at": datetime.now(timezone.utc).isoformat()}, "id", q["id"])
                    b.insert("notifications", {"user_id": q["user_id"], "kind": "info", "body": "질문 게시판에 선생님의 답변이 도착했습니다."})
                    st.rerun()


def course(b, p, subject):
    hero(subject, "개념을 이해하고, 생각을 설명하고, 배움을 기록합니다.")
    unit = st.selectbox("단원별로 보기", ["전체 단원"] + b.settings()["units"][subject], key=f"unit_{subject}")
    tabs = st.tabs(["📋 평가계획", "📚 학습자료", "📤 활동 제출", "💬 질문"])
    with tabs[0]: material_board(b, p["role"]=="teacher", subject, "전체 단원", ["평가계획"], f"plan_{subject}")
    with tabs[1]: material_board(b, p["role"]=="teacher", subject, unit, ["학습지", "보충자료"], f"handout_{subject}")
    with tabs[2]: assignment_board(b, p, subject, unit)
    with tabs[3]: questions_board(b, p, subject, unit)


def account(b, p, force=False):
    st.header("처음 비밀번호 바꾸기" if force else "내 계정")
    st.caption(f"{p['class_id'] or '교사'} · {p['student_id']} · {p['full_name']}")
    if force:
        st.info("임시 비밀번호를 자신만 아는 비밀번호로 바꾼 뒤 수업을 시작해 주세요.")
    with st.form("passwordchange", clear_on_submit=True):
        current = st.text_input("현재 비밀번호", type="password")
        new = st.text_input("새 비밀번호 (10자 이상)", type="password")
        again = st.text_input("새 비밀번호 다시 입력", type="password")
        if st.form_submit_button("비밀번호 변경", type="primary"):
            try:
                if new != again:
                    raise ValueError("새 비밀번호 두 칸이 일치하지 않습니다.")
                if new == current:
                    raise ValueError("현재와 다른 비밀번호를 사용하세요.")
                b.change_password(current, new)
                st.session_state["flash"] = "비밀번호가 변경되었습니다."
                st.rerun()
            except Exception as exc:
                safe_error(exc)
    if not force and p["role"] == "student":
        st.subheader("내 상벌점 누계와 이력")
        rows = b.rows("points", {"user_id": p["id"]}, "created_at", True)
        good, bad, net = point_totals(rows)
        a, c, d = st.columns(3)
        a.metric("상점", good);c.metric("벌점", bad);d.metric("차이", net)
        st.dataframe([{"일시": local_time(r["created_at"]), "구분": "상점" if r["delta"]>0 else "벌점", "점수": abs(r["delta"]),
                       "사유": r["reason"], "취소": r["cancelled"], "취소 사유": r["cancel_reason"] or ""} for r in rows], hide_index=True)
        st.toggle("상점 애니메이션 줄이기", key="reduce_motion", value=False)
        st.subheader("내 알림함")
        for n in b.rows("notifications", {"user_id": p["id"]}, "created_at", True)[:100]:
            st.write(f"{local_time(n['created_at'])} · {n['body']}")
