"""Sitewide light theme: every published page loads it, and no text renders white (or bold) on white."""
import functools
import http.server
import shutil
import socketserver
import threading
import unittest
from pathlib import Path

import site_nav
from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
MARK = 'Light theme (sitewide)'
SAMPLE = ['/', '/news/finals-game-2-preview-dream-valkyries/', '/wnba/aja-wilson/',
          '/wnba/teams/golden-state-valkyries/', '/news/2026-wnba-finals-ratings-tracker/']

JS = r"""() => {
  const rgb = s => { const m = s.match(/[\d.]+/g); return m ? m.map(Number) : null; };
  const lum = c => { const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); };
                     return 0.2126*f(c[0])+0.7152*f(c[1])+0.0722*f(c[2]); };
  const bgOf = el => { for (let e=el; e; e=e.parentElement) { const cs=getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage!=='none') return null;
      const c=rgb(cs.backgroundColor); if (c && (c.length<4 || c[3]>0.5)) return c; } return [255,255,255]; };
  const bad=[];
  for (const el of document.querySelectorAll('main *, #content *')) {
    const t=[...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
    if (!t) continue; const cs=getComputedStyle(el);
    if (cs.visibility==='hidden' || cs.display==='none' || el.getClientRects().length===0) continue;
    if (cs.webkitTextFillColor && rgb(cs.webkitTextFillColor) && rgb(cs.webkitTextFillColor)[3]===0) continue;
    const fg=rgb(cs.color), bg=bgOf(el); if (!fg || !bg) continue;
    const a=lum(fg), b=lum(bg), ratio=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
    if (b>0.8 && ratio<3) bad.push(el.tagName+' "'+t.slice(0,40)+'" '+cs.color+' on '+bg.join(','));
  }
  return bad.slice(0,20);
}"""


class LightThemeTests(unittest.TestCase):
    def test_shared_css_carries_theme(self):
        self.assertIn(MARK, site_nav.CSS_TEXT)
        self.assertEqual((ROOT / 'assets/site-nav.css').read_text(encoding='utf-8'), site_nav.CSS_TEXT)

    def test_every_page_loads_theme(self):
        missing = []
        for path in iter_html(ROOT):
            html = path.read_text(encoding='utf-8', errors='ignore')
            low = html.lower()
            if 'http-equiv="refresh"' in low or 'location.replace(' in low or 'noindex' in low:
                continue
            if '/assets/site-nav.css' not in html:
                missing.append(str(path.relative_to(ROOT)))
        self.assertEqual(missing, [])

    def test_no_white_or_bold_text_on_white(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright not installed')
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        handler = functools.partial(Quiet, directory=str(ROOT))
        with socketserver.TCPServer(('127.0.0.1', 0), handler) as srv:
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            port = srv.server_address[1]
            with sync_playwright() as p:
                kw = {'args': ['--no-sandbox']}
                if chrome:
                    kw['executable_path'] = chrome
                try:
                    browser = p.chromium.launch(**kw)
                except Exception as exc:  # no browser on this machine
                    self.skipTest(str(exc))
                problems = {}
                for url in SAMPLE:
                    for width in (1280, 390):
                        page = browser.new_page(viewport={'width': width, 'height': 900})
                        page.route('**/*', lambda r: r.abort() if '127.0.0.1' not in r.request.url and 'fonts.' not in r.request.url else r.continue_())
                        page.goto(f'http://127.0.0.1:{port}{url}', wait_until='load')
                        bad = page.evaluate(JS)
                        if bad:
                            problems[f'{url}@{width}'] = bad
                        page.close()
                browser.close()
            srv.shutdown()
        self.assertEqual(problems, {})


if __name__ == '__main__':
    unittest.main()
