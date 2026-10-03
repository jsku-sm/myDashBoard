// Same-origin Streamlit HTML frame. UI lock is reinforced by server checks.
// Does not try to control other browser tabs, other apps or the operating system.
(function () {
  const payload = __PAYLOAD__;
  let win, doc;
  try { win = window.parent; doc = win.document; } catch (e) { return; }
  const id = 'gussaem-lock-overlay';
  const root = doc.getElementById('root');
  if (!win.__gussaemLive) {
    win.__gussaemLive = {seen: new Set(), timer: null, lastFocus: null, locked: false};
    const css = doc.createElement('style');
    css.textContent = `
      #gussaem-lock-overlay { position:fixed; inset:0; z-index:2147483600;
        display:flex; align-items:center; justify-content:center;
        background:rgba(14,34,35,.97); color:white; font-family:system-ui,sans-serif;
        overscroll-behavior:contain; text-align:center; padding:24px; }
      #gussaem-lock-overlay .g-lock-card {max-width:600px; padding:50px 35px;
        border:1px solid #45625e; border-radius:28px; background:#172e30;}
      #gussaem-lock-overlay h1 {color:white;font-size:32px;margin:22px 0 14px;}
      #gussaem-lock-overlay p {font-size:18px;line-height:1.8;color:#dce6e0;white-space:pre-wrap;}
      #gussaem-lock-overlay small {color:#b0c7be;}
      .g-point-toast {position:fixed;top:25px;left:50%;transform:translateX(-50%);
        z-index:2147483640;background:white;color:#173631;border:2px solid #478778;
        box-shadow:0 14px 60px #0004;padding:18px 26px;border-radius:20px;font:600 18px system-ui;
        max-width:80vw;text-align:center;white-space:pre-wrap;pointer-events:none;}
      .g-spark {position:fixed;width:8px;height:8px;border-radius:50%;z-index:2147483645;
        pointer-events:none;animation:g-burst 1.5s cubic-bezier(.15,.6,.4,1) forwards;}
      @keyframes g-burst {from {opacity:1;transform:translate(0,0) scale(1);}
        to {opacity:0;transform:translate(var(--x),var(--y)) scale(.1);}}
    `;
    doc.head.appendChild(css);
    // Capture keyboard too; an overlay alone does not stop focus in a text field.
    ['keydown','pointerdown','click','touchstart','wheel'].forEach(type => {
      doc.addEventListener(type, event => {
        if (win.__gussaemLive.locked) {
          event.preventDefault(); event.stopImmediatePropagation();
        }
      }, {capture:true, passive:false});
    });
  }
  const state = win.__gussaemLive;
  const setLock = (locked, message) => {
    state.locked = locked;
    let overlay = doc.getElementById(id);
    if (locked) {
      if (!overlay) {
        state.lastFocus = doc.activeElement;
        if (doc.activeElement && doc.activeElement.blur) doc.activeElement.blur();
        overlay = doc.createElement('div'); overlay.id = id;
        overlay.setAttribute('role','alertdialog'); overlay.setAttribute('aria-modal','true');
        overlay.setAttribute('aria-label','선생님 설명 시간'); overlay.tabIndex = -1;
        const card = doc.createElement('div');card.className = 'g-lock-card';
        const icon = doc.createElement('div');icon.textContent='🔒';icon.style.fontSize='58px';
        const title = doc.createElement('h1');title.textContent='잠깐, 선생님께 집중해요';
        const p = doc.createElement('p');p.id='g-lock-message';
        const small = doc.createElement('small');small.textContent='작성 중인 내용은 그대로 두었어요. 잠금이 풀리면 이어서 할 수 있어요.';
        card.append(icon,title,p,small);overlay.append(card);doc.body.append(overlay);
      }
      doc.getElementById('g-lock-message').textContent = message || '설명이 끝나면 화면이 다시 열립니다.';
      if (root) root.inert = true;
      overlay.focus({preventScroll:true});
    } else {
      if (root) root.inert = false;
      if (overlay) overlay.remove();
      if (state.lastFocus && state.lastFocus.isConnected && state.lastFocus.focus) {
        state.lastFocus.focus({preventScroll:true}); state.lastFocus = null;
      }
    }
  };
  clearTimeout(state.timer);
  setLock(!!payload.locked, payload.message);
  // If a student loses connection, stop normal interaction until polling resumes.
  if (payload.watchdog) state.timer = setTimeout(() => setLock(true,
    '서버 연결을 확인하고 있어요. 네트워크가 복구되면 자동으로 다시 확인합니다. 계속되면 페이지를 새로고침하세요.'), 45000);
  if (payload.reset) state.seen.clear();
  (payload.events || []).forEach(event => {
    if (state.seen.has(event.id)) return;
    state.seen.add(event.id);
    const toast = doc.createElement('div');toast.className='g-point-toast';
    toast.textContent = (event.score > 0 ? '🎉 상점 +' + event.score + '점!\n' : '📌 벌점 ' + Math.abs(event.score) + '점 안내\n') + event.reason;
    if (event.score < 0) toast.style.borderColor='#bd6657';
    doc.body.append(toast);setTimeout(() => toast.remove(), 7000);
    if (event.score > 0 && !win.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      [0,300,650].forEach((delay,burst) => setTimeout(() => {
        const x = win.innerWidth * (.25 + burst*.25), y = win.innerHeight * (.28 + (burst%2)*.2);
        for (let i=0;i<42;i++) {
          const spark=doc.createElement('span');spark.className='g-spark';
          const angle=Math.PI*2*i/42, radius=90+Math.random()*160;
          spark.style.left=x+'px';spark.style.top=y+'px';
          spark.style.background=['#FFD166','#65D6AD','#98A7FF','#FF9DA9','#F9FAFB'][i%5];
          spark.style.setProperty('--x',Math.cos(angle)*radius+'px');
          spark.style.setProperty('--y',Math.sin(angle)*radius+'px');
          doc.body.append(spark);setTimeout(() => spark.remove(),1600);
        }
      },delay));
    }
  });
})();
