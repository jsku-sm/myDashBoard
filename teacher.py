"""교사전용 관제, 계정, 관찰, 상벌점, 좌석·조, 보관 설정."""
from __future__ import annotations
import copy
import json
from collections import Counter, defaultdict
from datetime import datetime, time as daytime, timezone, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from utils import CLASSES, SUBJECTS, MOODS, DEMO_ROSTER, csv_bytes, parse_roster, point_totals, make_layout, validate_url
from ui import hero, local_time, safe_error, seat_grid


def roster(b, cls):
    return sorted(b.rows("profiles", {"class_id": cls, "role": "student", "active": True}), key=lambda p: p["student_id"])


@st.fragment(run_every="10s")
def class_monitor(b, cls):
    b.require_teacher()
    c = b.rows("classrooms", {"id": cls})[0]
    people = roster(b, cls)
    online = {x["user_id"]: x for x in b.rows("presence", {"class_id": cls, "session_id": c["current_session"]})}
    moods = {x["user_id"]: x for x in b.rows("moods", {"class_id": cls, "session_id": c["current_session"]})}
    now = datetime.now(timezone.utc)
    live = {uid for uid, row in online.items() if row.get("online", True) and now - datetime.fromisoformat(row["last_seen"].replace("Z", "+00:00")) < timedelta(seconds=90)}
    active_ids = {p["id"] for p in people}
    cols = st.columns(4)
    cols[0].metric("명렬", len(people));cols[1].metric("이번 수업 접속", len(set(online)&active_ids))
    cols[2].metric("이번 수업 미접속", len(active_ids-set(online)));cols[3].metric("최근 연결 확인", len(live&active_ids))
    st.caption(f"{c['session_title']} · {local_time(c['started_at'])} 시작 · {'🔒 잠김' if c['locked'] else '🔓 이용 가능'}")
    st.caption("이 표는 10초 간격 갱신, 최근 연결은 90초 기준입니다. 실제 출결·집중도를 확정하는 자료가 아닙니다. 브라우저를 오래 비활성화하거나 연결이 끊기면 표시가 늦을 수 있습니다.")
    table = []
    for p in people:
        event = online.get(p["id"])
        mood = moods.get(p["id"])
        table.append({"학번": p["student_id"], "이름": p["full_name"], "이번 수업": "접속함" if event else "미접속",
          "연결 확인": "최근 연결" if p["id"] in live else "연결 확인 안 됨", "마지막 확인": local_time(event["last_seen"]) if event else "—",
          "마음 날씨": MOODS.get(mood["value"], "미응답") if mood else "미응답"})
    st.dataframe(table, hide_index=True, use_container_width=True)
    count = Counter(m["value"] for uid,m in moods.items() if uid in active_ids)
    st.subheader("마음 날씨 통계 · 교사만 공개")
    stat = [{"감정": MOODS[k], "인원": count[k], "전체 학생 대비 비율": f"{count[k]/len(people)*100:.1f}%" if people else "0%"} for k in MOODS]
    stat.append({"감정": "미응답", "인원": len(people)-sum(count.values()), "전체 학생 대비 비율": f"{(len(people)-sum(count.values()))/len(people)*100:.1f}%" if people else "0%"})
    st.bar_chart(stat, x="감정", y="인원")
    st.dataframe(stat, hide_index=True)
    st.caption("‘말하고 싶지 않아요’와 미응답은 따로 집계합니다. 감정 선택으로 성격·건강상태를 판단하거나 상벌점을 부여하지 않습니다.")


def monitor(b, cls):
    st.subheader(f"{cls} 수업 관제")
    with st.form(f"startclass_{cls}"):
        subject = st.selectbox("진행 과목", SUBJECTS, index=1)
        title = st.text_input("오늘의 수업 제목", placeholder="예: 서로소인 두 집합을 구분하기", max_chars=150)
        if st.form_submit_button("새 수업 시작", type="primary"):
            if title.strip():
                b.rpc("app_start_class", {"target_class": cls, "lesson_title": title.strip(), "lesson_subject": subject})
                st.rerun()
            else:
                st.warning("수업 제목을 입력해 주세요.")
    st.caption("새 수업을 시작하면 이번 수업의 접속·감정 집계가 새로 시작됩니다. 이전 기록은 삭제되지 않습니다.")
    if st.button("수업 종료 · 잠금 해제", key=f"endclass_{cls}"):
        b.teacher_update("classrooms", {"session_open": False, "locked": False}, "id", cls)
        st.rerun()
    class_monitor(b, cls)


def accounts(b, cls):
    st.subheader("학생 명렬과 계정")
    st.info("학번·이름·학급만 등록합니다. 비밀번호 원문은 보관하거나 조회하지 않습니다. 임시 비밀번호 파일은 발급 직후 개별 전달용으로만 사용하고 안전하게 삭제하세요.")
    with st.expander("실제 학생 등록 전 · 가상 학생 3명으로 시험하기"):
        st.write("10191·10192(1-1), 10291(1-2) 가상 계정을 만듭니다. 학교 데이터 승인 전에도 가상 계정만 시험할 수 있습니다.")
        if st.button("가상 학생 3명 생성"):
            credentials, result = b.import_students(DEMO_ROSTER)
            st.session_state["issued_credentials"] = credentials
            st.session_state["import_result"] = result
            st.rerun()
        if st.button("가상 학생 3명 비활성화"):
            for row in b.rows("profiles", {"role": "student"}):
                if any(row["student_id"] == d["student_id"] and row["full_name"] == d["name"] for d in DEMO_ROSTER):
                    b.teacher_update("profiles", {"active": False}, "id", row["id"])
            st.success("가상 학생 계정을 비활성화했습니다. 테스트 과제는 과목 화면에서 별도로 삭제하세요.")
    upload = st.file_uploader("명렬 CSV 업로드 · 원본 가로형 / 정리된 세로형 모두 지원", type=["csv"], key="roster_import")
    if upload:
        try:
            rows = parse_roster(upload.getvalue())
            counts = Counter(r["class_id"] for r in rows)
            st.write({c: counts[c] for c in CLASSES})
            target_classes = st.multiselect("이번에 등록할 학급", [c for c in CLASSES if counts[c]], default=[cls] if counts[cls] else [])
            chosen = [r for r in rows if r["class_id"] in target_classes]
            st.dataframe(chosen, hide_index=True)
            checked = st.checkbox("학교의 학생 데이터 이용 기준을 확인했고, 위 명단의 계정을 생성합니다.")
            if st.button("선택한 학생 계정 생성", type="primary", disabled=not checked or not chosen):
                progress = st.progress(0.0)
                credentials, result = b.import_students(chosen, lambda n,total: progress.progress(n/total))
                st.session_state["issued_credentials"] = credentials
                st.session_state["import_result"] = result
                st.success(f"새 계정 {len(credentials)}개를 생성했습니다. 기존 계정과 실패 건은 아래 결과를 확인하세요.")
        except Exception as exc:
            safe_error(exc)
    if "import_result" in st.session_state:
        st.dataframe(st.session_state["import_result"], hide_index=True)
    issued = st.session_state.get("issued_credentials", [])
    if issued:
        st.download_button("🔐 이번 발급 임시 비밀번호 CSV 받기 (공유 금지)", csv_bytes(issued), file_name="임시비밀번호_개별전달후삭제.csv", mime="text/csv")
        st.warning("전체 파일을 학급에 배포하지 마세요. 각 학생에게 본인의 비밀번호만 전달하세요. 이 파일은 현재 교사 세션에서만 내려받을 수 있습니다.")
        if st.button("발급 파일을 이 화면에서 지우기"):
            st.session_state.pop("issued_credentials", None);st.rerun()
    people = sorted(b.rows("profiles", {"class_id": cls, "role": "student"}), key=lambda p:p["student_id"])
    st.subheader(f"{cls} 등록 현황")
    table = [{"학번": p["student_id"], "이름": p["full_name"], "학급": p["class_id"], "활성": p["active"], "첫 비밀번호 변경 필요": p["must_change_password"]} for p in people]
    st.dataframe(table, hide_index=True)
    st.download_button("학생 계정명단 CSV (비밀번호 없음)", csv_bytes(table), file_name=f"{cls}_학생명단.csv", mime="text/csv")
    if people:
        p = st.selectbox("관리할 학생", people, format_func=lambda p:f"{p['student_id']} {p['full_name']}")
        if st.button("이 학생에게 새 임시 비밀번호 발급"):
            password = b.reset_password(p["id"])
            st.session_state["issued_credentials"] = [{"학급": p["class_id"], "학번": p["student_id"], "이름": p["full_name"], "임시비밀번호": password}]
            st.rerun()
        with st.form(f"profileedit_{p['id']}"):
            name = st.text_input("학생 이름 수정", value=p["full_name"], max_chars=40)
            active = st.checkbox("로그인 가능한 활성 계정", value=p["active"])
            if st.form_submit_button("계정 상태 저장"):
                if name.strip():
                    b.teacher_update("profiles", {"full_name": name.strip(), "active": active}, "id", p["id"])
                    st.rerun()

        with st.expander("학생 1명 계정·자료 완전 삭제 · 복구 불가"):
            st.warning("이 학생의 계정, 제출파일, 피드백, 감정·접속, 질문, 관찰, 상벌점, 좌석 배치를 앱의 운영 저장소에서 삭제합니다. 학교 보존 의무와 백업 파일을 먼저 확인하세요. 제공자의 별도 백업 보존·삭제는 별도로 관리해야 합니다.")
            agreed = st.checkbox("학교에서 보존해야 할 자료를 확인했고 삭제를 승인합니다", key=f"purge_agree_{p['id']}")
            typed = st.text_input("삭제할 학생 학번을 그대로 입력", key=f"purge_type_{p['id']}")
            if st.button("이 학생의 계정과 앱 자료 삭제", key=f"purge_user_{p['id']}", disabled=not agreed or typed != p["student_id"]):
                b.delete_student_account(p["id"], typed)
                st.session_state.pop("issued_credentials", None)
                st.session_state.pop(f"layoutdraft_{cls}", None)
                st.rerun()


def observations_points(b, p, cls):
    people = roster(b, cls)
    if not people:
        st.info("먼저 이 반의 학생 계정을 등록하세요.")
        return
    selected = st.selectbox("학생 선택", people, format_func=lambda x:f"{x['student_id']} {x['full_name']}")
    uid = selected["id"]
    top = b.rows("points", {"user_id": uid}, "created_at", True)
    good,bad,net = point_totals(top)
    a,c,d=st.columns(3);a.metric("상점 누계",good);c.metric("벌점 누계",bad);d.metric("상점 − 벌점",net)
    tab1,tab2 = st.tabs(["📝 관찰기록", "✨ 상점·벌점"])
    with tab1:
        with st.form("observeform", clear_on_submit=True):
            day = st.date_input("관찰 날짜", datetime.now(ZoneInfo("Asia/Seoul")).date())
            subject = st.selectbox("관찰 과목", SUBJECTS, index=1)
            category = st.selectbox("관찰 영역", ["개념 이해", "문제해결", "사고·성장", "질문·의사소통", "협력", "기타"])
            body = st.text_area("직접 관찰한 말·풀이·행동과 다음 확인 사항", max_chars=10000,
                                placeholder="학생이 한 일 → 변화 과정 → 교사가 제공한 지원 → 다음 확인할 점")
            if st.form_submit_button("관찰기록 저장", type="primary"):
                if body.strip():
                    b.insert("observations", {"user_id": uid, "class_id": cls, "observed_on": day.isoformat(),
                             "subject": subject, "category": category, "body": body.strip(), "teacher_id": p["id"]})
                    st.success("교사전용 기록으로 저장했습니다.")
        rows = b.rows("observations", {"user_id": uid}, "observed_on", True)
        for r in rows:
            with st.expander(f"{r['observed_on']} · {r['category']} · {r['body'][:35]}"):
                text = st.text_area("기록 내용", value=r["body"], key=f"obsbody_{r['id']}")
                a1,a2=st.columns(2)
                if a1.button("수정", key=f"obsedit_{r['id']}") and text.strip():
                    b.teacher_update("observations", {"body": text.strip()}, "id", r["id"]);st.rerun()
                check=st.checkbox("이 기록 삭제 확인", key=f"obscheck_{r['id']}")
                if a2.button("삭제",key=f"obsdelete_{r['id']}",disabled=not check):
                    b.teacher_delete("observations","id",r["id"]);st.rerun()
        st.download_button("이 학생 관찰기록 CSV",csv_bytes(rows),file_name=f"{selected['student_id']}_관찰기록.csv",mime="text/csv")
    with tab2:
        with st.form("pointsform", clear_on_submit=True):
            kind = st.radio("부여할 점수", ["상점", "벌점"], horizontal=True)
            amount = st.number_input("점수", 1, 100, 1)
            reason = st.text_input("부여 사유", max_chars=500, placeholder="예: 두 풀이를 비교하여 차이점을 설명함")
            if st.form_submit_button("이 학생에게 부여", type="primary"):
                if reason.strip():
                    b.rpc("app_award_points", {"target_user": uid, "amount": int(amount) if kind=="상점" else -int(amount), "why": reason.strip()})
                    st.rerun()
                else:
                    st.warning("부여 사유를 입력하세요.")
        st.caption("학생이 접속 중이면 상태 갱신 후 알림을 봅니다. 미접속·잠금 중에는 다음 접속·잠금 해제 후 표시됩니다. 소리는 재생하지 않습니다.")
        for r in top:
            with st.expander(f"{'[취소] ' if r['cancelled'] else ''}{'상점' if r['delta']>0 else '벌점'} {abs(r['delta'])}점 · {r['reason']} · {local_time(r['created_at'])}"):
                if r["cancelled"]:
                    st.write(r["cancel_reason"])
                else:
                    why=st.text_input("정정·취소 사유",key=f"cancelwhy_{r['id']}",max_chars=500)
                    if st.button("부과 취소 (이력 유지)",key=f"cancelpoint_{r['id']}",disabled=not why.strip()):
                        b.rpc("app_cancel_points",{"point_id":r["id"],"why":why.strip()});st.rerun()
        st.download_button("이 학생 상벌점 CSV",csv_bytes(top),file_name=f"{selected['student_id']}_상벌점.csv",mime="text/csv")


def layouts(b, cls):
    people = roster(b, cls)
    st.subheader(f"{cls} 좌석표 · 조별 명단")
    st.caption("교사전용입니다. 좌석과 조는 직접 수정하거나 무작위로 편성한 뒤 저장할 수 있습니다. 학생의 감정·상벌점은 배치에 사용하지 않습니다.")
    if not people:
        st.info("학생 명렬을 먼저 등록하세요.");return
    saved=b.rows("layouts",{"class_id":cls})
    row_default=saved[0]["rows"] if saved else 5
    col_default=saved[0]["cols"] if saved else 5
    a,c,d=st.columns(3)
    rows=int(a.number_input("가로줄 수 (행)",1,10,row_default,key=f"lr_{cls}"))
    cols=int(c.number_input("한 줄의 좌석 수 (열)",1,10,col_default,key=f"lc_{cls}"))
    groups=int(d.number_input("무작위 편성 조 수",1,10,5,key=f"lg_{cls}"))
    statekey=f"layoutdraft_{cls}"
    versionkey=f"layoutversion_{cls}"
    if statekey not in st.session_state:
        st.session_state[statekey]=copy.deepcopy(saved[0]["entries"]) if saved else make_layout(people,rows,cols)
    a1,a2=st.columns(2)
    if a1.button("학번순 좌석 배치 준비"):
        st.session_state[statekey]=make_layout(people,rows,cols)
        st.session_state[versionkey]=st.session_state.get(versionkey,0)+1;st.rerun()
    if a2.button("무작위 좌석·조 편성 준비"):
        st.session_state[statekey]=make_layout(people,rows,cols,shuffle=True,group_count=groups)
        st.session_state[versionkey]=st.session_state.get(versionkey,0)+1;st.rerun()
    with st.form(f"layoutform_{cls}"):
        edited=st.data_editor(st.session_state[statekey], hide_index=True, use_container_width=True,
             column_order=["학번","이름","행","열","조"], disabled=["user_id","학번","이름"],
             column_config={"행":st.column_config.NumberColumn(min_value=1,max_value=10,step=1),
                            "열":st.column_config.NumberColumn(min_value=1,max_value=10,step=1)},
             key=f"layouteditor_{cls}_{st.session_state.get(versionkey,0)}")
        if st.form_submit_button("좌석표·조별 명단 저장",type="primary"):
            try:
                b.save_layout(cls,rows,cols,edited)
                st.session_state[statekey]=edited
                st.success("저장했습니다.")
            except Exception as exc:safe_error(exc)
    st.caption("수정한 표는 저장 버튼을 눌러야 보관됩니다. 같은 좌석 중복이나 누락된 학생은 저장할 수 없습니다.")
    current=b.rows("layouts",{"class_id":cls})
    if current:
        layout=current[0]
        st.markdown("#### 저장된 좌석표")
        seat_grid(layout["entries"],layout["rows"],layout["cols"])
        groupdict=defaultdict(list)
        for e in layout["entries"]:groupdict[e.get("조") or "미배정"].append(e)
        st.markdown("#### 저장된 조별 명단")
        for label,members in sorted(groupdict.items()):
            with st.container(border=True):
                st.markdown(f"**{label} · {len(members)}명**")
                st.write(" / ".join(f"{e['학번']} {e['이름']}" for e in members))
        st.download_button("좌석·조별 명단 CSV",csv_bytes(layout["entries"],["학번","이름","행","열","조"]),file_name=f"{cls}_좌석조별_학생명단.csv",mime="text/csv")


def settings(b):
    data=b.settings()
    st.subheader("소개·관심 분야·단원·수업도구")
    with st.form("infosettings"):
        intro=st.text_area("구쌤 소개",value=data["intro"],max_chars=3000)
        interests=st.text_area("공부·관심 분야 (한 줄에 하나)",value=data["interests"],max_chars=3000)
        units={}
        for subject in SUBJECTS:
            units[subject]=st.text_area(f"{subject} 단원 (한 줄에 하나)",value="\n".join(data["units"][subject]))
        if st.form_submit_button("소개·단원 저장"):
            parsed={s:list(dict.fromkeys(x.strip() for x in text.splitlines() if x.strip())) for s,text in units.items()}
            if all(parsed.values()):
                b.save_settings({**data,"intro":intro,"interests":interests,"units":parsed});st.rerun()
            else:st.warning("각 과목에 한 개 이상의 단원이 필요합니다.")
    st.caption("단원명을 바꾸어도 기존 자료의 단원명까지 자동 변경되지는 않습니다. 기존 자료는 ‘전체 단원’에서 볼 수 있습니다.")
    with st.form("newtool",clear_on_submit=True):
        name=st.text_input("도구·앱 이름",max_chars=100)
        category=st.selectbox("분류",["수업도구","퀴즈","앱 (by 구쌤)"])
        description=st.text_input("간단한 설명",max_chars=300)
        url=st.text_input("연결 주소",placeholder="https://...")
        if st.form_submit_button("도구 추가"):
            if not name.strip():st.warning("이름을 입력하세요.")
            else:
                url=validate_url(url)
                data["tools"].append({"name":name.strip(),"category":category,"description":description,"url":url})
                b.save_settings(data);st.rerun()
    for i,item in enumerate(data["tools"]):
        with st.expander(f"{item.get('category','수업도구')} · {item['name']}"):
            title=st.text_input("이름",value=item["name"],key=f"toolname{i}")
            url=st.text_input("주소",value=item["url"],key=f"toolurl{i}")
            desc=st.text_input("설명",value=item.get("description",""),key=f"tooldesc{i}")
            cat=st.selectbox("분류",["수업도구","퀴즈","앱 (by 구쌤)"],index=["수업도구","퀴즈","앱 (by 구쌤)"].index(item.get("category","수업도구")),key=f"toolcat{i}")
            a,c=st.columns(2)
            if a.button("변경 저장",key=f"toolsave{i}"):
                data["tools"][i]={"name":title,"url":validate_url(url),"description":desc,"category":cat};b.save_settings(data);st.rerun()
            if c.button("목록에서 삭제",key=f"tooldel{i}"):
                data["tools"].pop(i);b.save_settings(data);st.rerun()


def retention(b, cls):
    st.subheader("자료 보관 기준 · 백업 · 정리")
    st.write("보관 기준은 ‘무엇을 왜 모으는지, 누가 볼 수 있는지, 언제까지 보관하고 어떻게 지울지’를 정하는 것입니다. 자동으로 정해지는 법정 기간을 뜻하지 않습니다.")
    st.info("학교 개인정보 담당자와 클라우드 이용, 처리·보관 장소, AI 전송, 보관·삭제 시점을 먼저 확인하세요. Supabase 서울 리전을 선택해도 Streamlit·외부 AI 처리까지 모두 국내로 한정되는 것은 아닙니다.")
    data=b.settings()
    note=st.text_area("학교에서 확인한 운영 기준",value=data["retention_note"],height=180,
                      placeholder="예: 감정·접속 기록의 이용 목적 / 열람자 / 삭제 시점 / 과제·평가자료 보관 기준 / 외부 AI 이용 기준")
    if st.button("운영 기준 저장"):
        b.save_settings({**data,"retention_note":note});st.success("기준을 기록했습니다. 자동 삭제 일정은 생성하지 않습니다.")
    st.markdown("#### 선택 학급 기록 백업")
    st.caption("JSON 백업은 명단·게시글·감정·관찰·상벌점·좌석·제출파일 경로를 포함합니다. 비밀번호, Auth 백업, 실제 첨부파일은 포함하지 않습니다. 실제 파일은 각 자료·과제에서 별도 내려받으세요. 원클릭 전체 복원 기능은 없습니다.")
    if st.button(f"{cls} 교사전용 기록 백업 만들기"):
        b.require_teacher()
        people=b.rows("profiles",{"class_id":cls,"role":"student"})
        ids={p["id"] for p in people}
        dump={"schema_version":"1.0","class_id":cls,"exported_at":datetime.now(timezone.utc).isoformat(),"profiles":people}
        for table in ("assignments","moods","presence","observations","points","questions","layouts"):
            dump[table]=b.rows(table,{"class_id":cls})
        assignment_ids={a["id"] for a in dump["assignments"]}
        dump["submissions"]=[s for s in b.rows("submissions") if s["assignment_id"] in assignment_ids]
        subids={s["id"] for s in dump["submissions"]}
        dump["feedback"]=[f for f in b.rows("feedback") if f["submission_id"] in subids]
        raw=json.dumps(dump,ensure_ascii=False,indent=2).encode()
        st.download_button("개인정보 포함 백업 내려받기",raw,file_name=f"private_roster_{cls}_records.json",mime="application/json")
    st.markdown("#### 오래된 감정·접속 기록 정리")
    st.warning("현재 수업 기록은 제외합니다. 선택 날짜 이전 감정·접속 기록과 읽은 알림을 삭제합니다. 학생 계정·관찰·상벌점·과제는 이 버튼으로 삭제하지 않습니다.")
    cutoff=st.date_input("이 날짜 이전 기록",datetime.now(ZoneInfo("Asia/Seoul")).date()-timedelta(days=30))
    typed=st.text_input("실행 확인 문구",placeholder=f"{cls} 기록삭제")
    if st.button("선택 학급의 오래된 기록 삭제",disabled=typed!=f"{cls} 기록삭제"):
        stamp=datetime.combine(cutoff,daytime.min,tzinfo=ZoneInfo("Asia/Seoul")).isoformat()
        b.rpc("app_purge_transient",{"target_class":cls,"cutoff":stamp});st.success("대상 기록을 삭제했습니다.")
    st.caption("학습자료는 각 자료의 삭제 버튼, 과제·첨부파일은 과제 삭제 버튼, 관찰기록은 해당 기록의 삭제 버튼으로 정리합니다. 상벌점은 수정 이력을 보존하는 취소 방식을 사용합니다. 학생 계정과 해당 학생의 앱 자료를 삭제하려면 학생·계정 메뉴의 명시적 삭제 절차를 사용하세요. 제공자 백업과 내려받은 파일의 파기는 별도로 관리해야 합니다.")


def teacher_page(b,p,cls):
    b.require_teacher()
    hero("교사전용",f"{cls} · 배움의 과정을 살피고 수업을 운영합니다.")
    menu=st.radio("관리 메뉴",["수업 관제","학생·계정","관찰·상벌점","좌석표·조별 명단","소개·도구 설정","자료 보관·백업"],horizontal=True)
    if menu=="수업 관제":monitor(b,cls)
    elif menu=="학생·계정":accounts(b,cls)
    elif menu=="관찰·상벌점":observations_points(b,p,cls)
    elif menu=="좌석표·조별 명단":layouts(b,cls)
    elif menu=="소개·도구 설정":settings(b)
    else:retention(b,cls)
