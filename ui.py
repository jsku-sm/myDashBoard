from __future__ import annotations
import html
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import streamlit.components.v1 as components

SEOUL = ZoneInfo("Asia/Seoul")


def local_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(SEOUL).strftime("%m/%d %H:%M")
    except ValueError:
        return value


def apply_style():
    st.markdown("""<style>
    .block-container{max-width:1180px;padding-top:2rem;padding-bottom:3rem}
    h1{letter-spacing:-.045em!important;font-weight:800!important}
    h2,h3{letter-spacing:-.025em!important}
    [data-testid="stSidebar"]{background:#EDF0F9;border-right:1px solid #E2E6F2}
    div[data-testid="stMetric"]{background:white;border:1px solid #E3E8F2;border-radius:16px;padding:18px}
    .hero{padding:32px 36px;background:linear-gradient(135deg,#273F8B,#5874CF);color:white;border-radius:22px;margin:8px 0 24px}
    .hero h1{color:white!important;margin:0}.hero p{color:#E7EDFF;line-height:1.8;margin-bottom:0}
    .eyebrow{font-size:12px;letter-spacing:.18em;font-weight:700;margin-bottom:12px;color:#BCCAFF}
    .seat{background:#fff;border:1px solid #DDE3F2;border-radius:12px;text-align:center;padding:12px 6px;min-height:84px;margin-bottom:10px}
    .seat small{display:block;color:#69778E}.seat strong{display:block;color:#233659}
    .board{background:#273A56;color:white;text-align:center;padding:13px;border-radius:9px;margin-bottom:22px;letter-spacing:.25em}
    button[kind="primary"]{border-radius:10px}
    @media(max-width:700px){.block-container{padding:1rem}.hero{padding:24px}}
    </style>""", unsafe_allow_html=True)


def hero(title: str, subtitle: str, eyebrow="GU SSAEM · MATH STUDIO"):
    st.markdown(f'<div class="hero"><div class="eyebrow">{html.escape(eyebrow)}</div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>', unsafe_allow_html=True)


def safe_error(exc: Exception):
    if isinstance(exc, (ValueError, PermissionError)):
        st.error(str(exc)[:300])
    else:
        st.error("처리를 완료하지 못했습니다. 연결 상태와 Supabase 설정을 확인한 뒤 다시 시도하세요. 학생 자료나 비밀키가 포함된 오류 전문은 공개하지 마세요.")


def download_file(b, item: dict, key: str):
    st.caption(f"첨부: {item['filename']}")
    if st.button("📥 다운로드 준비", key=f"prepare_{key}"):
        try:
            data = b.download(item["path"])
            st.download_button("파일 내려받기", data, file_name=item["filename"], mime=item["mime"], key=f"download_{key}")
        except Exception as exc:
            safe_error(exc)


def fireworks():
    # Local canvas only: no analytics/CDN or injected student text. Reduced-motion respected.
    components.html('''<div style="font:600 18px system-ui;text-align:center;color:#4056A1">🎉 오늘의 좋은 시도를 응원해요!</div>
    <canvas id="sky" style="width:100%;height:180px"></canvas>
    <script>
    const c=document.getElementById('sky'),x=c.getContext('2d');
    c.width=800;c.height=180;
    if(!matchMedia('(prefers-reduced-motion: reduce)').matches){
      const a=[];for(let burst=0;burst<5;burst++)for(let i=0;i<50;i++){
        const t=Math.random()*Math.PI*2,s=1+Math.random()*3;
        a.push({x:90+Math.random()*620,y:40+Math.random()*70,dx:Math.cos(t)*s,dy:Math.sin(t)*s,
          life:50+Math.random()*35,wait:burst*9,h:Math.random()*360});}
      let frame=0;function draw(){x.clearRect(0,0,800,180);for(const p of a){
        if(frame<p.wait||p.life<=0)continue;p.x+=p.dx;p.y+=p.dy;p.dy+=.032;p.life--;
        x.globalAlpha=Math.min(1,p.life/20);x.fillStyle=`hsl(${p.h},78%,55%)`;
        x.beginPath();x.arc(p.x,p.y,2.5,0,7);x.fill();}
        if(frame++<130)requestAnimationFrame(draw);}draw();
    }</script>''', height=220)


def seat_grid(entries: list[dict], rows: int, cols: int):
    by_seat = {(int(e["행"]), int(e["열"])): e for e in entries}
    st.markdown('<div class="board">칠판 · 선생님</div>', unsafe_allow_html=True)
    for r in range(1, rows + 1):
        columns = st.columns(cols)
        for c, col in enumerate(columns, 1):
            e = by_seat.get((r, c))
            with col:
                if e:
                    st.markdown(f'<div class="seat"><small>{html.escape(str(e["학번"]))}</small><strong>{html.escape(str(e["이름"]))}</strong><small>{html.escape(str(e.get("조", "")))}</small></div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="seat"><small>빈자리</small><strong>—</strong></div>', unsafe_allow_html=True)
