"""Homepage lead card: 16:9 photo with no empty bands around it (Ryan, Oct 19, 2026).

Renders / at 1280 and 390 and fails if the lead card has more than 24px of
empty vertical space above/below the photo or below the text.
"""
import functools
import http.server
import shutil
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = """()=>{const c=document.querySelector('.feature-grid>.article-card');if(!c)return null;
const C=c.getBoundingClientRect(),V=c.querySelector('.article-visual').getBoundingClientRect(),
I=c.querySelector('.article-visual img').getBoundingClientRect(),T=c.querySelector('.article-copy').getBoundingClientRect();
return {above:I.top-C.top,visGap:V.height-I.height,below:C.bottom-Math.max(T.bottom,I.bottom),ratio:I.width/I.height}}"""


class HomeLeadCardTests(unittest.TestCase):
    def test_lead_card_has_no_empty_bands(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright not installed')
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome:
            self.skipTest('no chrome')
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
        handler.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=chrome)
                for w in (1280, 390):
                    pg = b.new_page(viewport={'width': w, 'height': 1000})
                    pg.goto(f'http://127.0.0.1:{srv.server_address[1]}/', wait_until='load')
                    m = pg.evaluate(JS)
                    self.assertIsNotNone(m, 'no homepage lead card')
                    for k in ('above', 'visGap', 'below'):
                        if m[k] > 24:
                            bad.append(f'@{w}: {k} {m[k]:.0f}px')
                    if not 1.70 <= m['ratio'] <= 1.85:
                        bad.append(f'@{w}: photo {m["ratio"]:.2f}:1')
                b.close()
        finally:
            srv.shutdown()
        self.assertEqual(bad, [], 'Lead card empty space:\n' + '\n'.join(bad))


if __name__ == '__main__':
    unittest.main()
