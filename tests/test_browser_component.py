"""Browser test for app-local lock and point effect, independent of Streamlit.
Requires Playwright + an installed Chromium. No remote network requests.
"""
import json
import os
from pathlib import Path
import pytest
playwright = pytest.importorskip('playwright.sync_api')
ROOT = Path(__file__).resolve().parent.parent


def test_lock_preserves_draft_and_keyboard_then_unlocks():
    source = (ROOT / 'assets/live.js').read_text()
    def component(payload):
        return '<script>' + source.replace('__PAYLOAD__', json.dumps(payload).replace('<', '\\u003c')) + '</script>'
    with playwright.sync_playwright() as p:
        args = {'headless': True}
        executable = os.getenv('CHROMIUM_PATH')
        if executable:
            args['executable_path'] = executable
        browser = p.chromium.launch(**args)
        page = browser.new_page(viewport={'width': 1280, 'height': 800})
        page.set_content('<div id="root"><textarea id="draft">작성 중인 수다노트</textarea><button id="save">저장</button><iframe id="frame"></iframe></div>')
        draft = page.locator('#draft')
        draft.focus()
        page.locator('#frame').evaluate('(el, html) => el.srcdoc = html', component({'locked': True, 'message': '설명 시간', 'events': []}))
        page.locator('#gussaem-lock-overlay').wait_for()
        assert page.locator('#root').evaluate('(el) => el.inert')
        page.keyboard.type('잘못 입력될 내용')
        assert draft.input_value() == '작성 중인 수다노트'
        page.locator('#frame').evaluate('(el, html) => el.srcdoc = html', component({'locked': False, 'message': '', 'events': [{'id': 'p1', 'score': 2, 'reason': '생각을 잘 설명했어요'}]}))
        page.locator('#gussaem-lock-overlay').wait_for(state='detached')
        assert not page.locator('#root').evaluate('(el) => el.inert')
        assert draft.input_value() == '작성 중인 수다노트'
        assert '상점 +2점' in page.locator('.g-point-toast').inner_text()
        page.wait_for_timeout(100)
        assert page.locator('.g-spark').count() > 0
        draft.fill('계속 작성할 수 있어요')
        assert draft.input_value() == '계속 작성할 수 있어요'
        # A malicious message is rendered as text, never interpreted as HTML.
        page.locator('#frame').evaluate('(el, html) => el.srcdoc = html', component({'locked': True, 'message': '<img src=x onerror=alert(1)>', 'events': []}))
        page.locator('#gussaem-lock-overlay').wait_for()
        assert page.locator('#g-lock-message img').count() == 0
        assert '<img' in page.locator('#g-lock-message').inner_text()
        browser.close()
