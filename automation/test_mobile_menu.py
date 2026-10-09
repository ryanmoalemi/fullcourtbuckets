"""Mobile menu must open on every published page, including the news hub.

The open panel is position:absolute against the header. A header with no
position drops that panel below the viewport, so the button looks dead.
"""
import re
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITEMAPS = ('sitemap.xml', 'pages-sitemap.xml', 'player-sitemap.xml')
VIEWPORT = {'width': 390, 'height': 844}
THIRD_PARTY = (
    'googlesyndication', 'doubleclick', 'googletagmanager', 'google-analytics',
    'googleadservices', 'gstatic', 'fundingchoices', 'googleapis',
)

MEASURE = """(section) => {
  const nav = document.querySelector('nav.site-nav');
  const menu = document.getElementById('site-nav-menu');
  const header = nav.closest('header, .site-header');
  const box = menu.getBoundingClientRect();
  const headerBox = header.getBoundingClientRect();
  const branch = (name) => {
    const control = nav.querySelector('.site-nav-subtoggle[data-section="' + name + '"]');
    const item = control.parentElement;
    const sub = document.getElementById(control.getAttribute('aria-controls'));
    return {
      open: item.classList.contains('is-open'),
      expanded: control.getAttribute('aria-expanded'),
      height: sub.offsetHeight,
    };
  };
  return {
    ready: document.documentElement.classList.contains('site-nav-ready'),
    open: nav.classList.contains('is-open'),
    expanded: nav.querySelector('.site-nav-toggle').getAttribute('aria-expanded'),
    display: getComputedStyle(menu).display,
    top: box.top,
    height: box.height,
    width: box.width,
    headerBottom: headerBox.bottom,
    headerPosition: getComputedStyle(header).position,
    viewport: window.innerHeight,
    branch: section ? branch(section) : null,
  };
}"""


def published_paths():
    paths = []
    seen = set()
    for name in SITEMAPS:
        text = (ROOT / name).read_text(encoding='utf-8')
        for loc in re.findall(r'<loc>\s*([^<]+?)\s*</loc>', text):
            path = urlsplit(loc).path or '/'
            if path.endswith('.xml'):
                continue
            if not path.endswith('/'):
                path += '/'
            if path not in seen:
                seen.add(path)
                paths.append(path)
    if '/404.html' not in seen:
        paths.append('/404.html')
    return paths


def _ignored_console(text, url):
    blob = f'{text} {url}'.casefold()
    if any(host in blob for host in THIRD_PARTY):
        return True
    # Aborted third-party scripts and the headless GA skip are not page bugs.
    if 'failed to load resource' in blob and not url.startswith('http://127.0.0.1'):
        return True
    return False


class MobileMenuTests(unittest.TestCase):
    def test_menu_opens_on_every_sitemap_page(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('Playwright is not installed')

        paths = published_paths()
        self.assertGreater(len(paths), 100)
        server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_address[1]}'
        failures = []
        try:
            with sync_playwright() as playwright:
                browser = _launch(playwright)
                context = browser.new_context(
                    viewport=VIEWPORT,
                    device_scale_factor=2,
                    is_mobile=True,
                    has_touch=True,
                )
                page = context.new_page()
                page.set_default_timeout(15000)

                def allow(route):
                    host = urlsplit(route.request.url).hostname
                    if host in (None, '127.0.0.1', 'localhost'):
                        route.continue_()
                    else:
                        route.abort()

                page.route('**/*', allow)
                for path in paths:
                    failures.extend(_audit(page, origin, path))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(failures, [])


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        return


def _launch(playwright):
    args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    try:
        return playwright.chromium.launch(args=args)
    except Exception:
        return playwright.chromium.launch(channel='chrome', args=args)


def _audit(page, origin, path):
    problems = []

    def on_pageerror(error):
        problems.append(f'pageerror: {error}')

    def on_console(message):
        if message.type != 'error':
            return
        url = (message.location or {}).get('url') or ''
        text = message.text or ''
        if _ignored_console(text, url):
            return
        if text.startswith('Failed to load resource') and not url.startswith(origin):
            return
        problems.append(f'console: {text}')

    page.on('pageerror', on_pageerror)
    page.on('console', on_console)
    try:
        response = page.goto(origin + path, wait_until='domcontentloaded')
        if response is None or response.status != 200:
            status = None if response is None else response.status
            return [f'{path} HTTP {status}']
        page.wait_for_function("() => document.documentElement.classList.contains('site-nav-ready')")
        toggle = page.locator('nav.site-nav .site-nav-toggle')
        toggle.tap()
        opened = page.evaluate(MEASURE, None)
        problems.extend(_expect_open(path, opened))
        for section in ('Players', 'Teams', 'About'):
            page.evaluate(
                """(section) => {
                  const menu = document.getElementById('site-nav-menu');
                  const control = document.querySelector('.site-nav-subtoggle[data-section="' + section + '"]');
                  menu.scrollTop += control.getBoundingClientRect().top - menu.getBoundingClientRect().top;
                }""",
                section,
            )
            page.locator(f'.site-nav-subtoggle[data-section="{section}"]').tap()
            state = page.evaluate(MEASURE, section)
            branch = state['branch']
            if not branch['open'] or branch['expanded'] != 'true' or branch['height'] < 20:
                problems.append(f'{path} {section} submenu did not expand: {branch}')
            if not state['open']:
                problems.append(f'{path} menu closed while opening {section}')
        toggle.tap()
        closed = page.evaluate(MEASURE, None)
        if closed['open'] or closed['expanded'] != 'false' or closed['display'] != 'none':
            problems.append(f'{path} menu did not close: {closed}')
    except Exception as error:
        problems.append(f'{path} {type(error).__name__}: {error}')
    finally:
        page.remove_listener('pageerror', on_pageerror)
        page.remove_listener('console', on_console)
    return [f'{path} {item}' if not str(item).startswith(path) else item for item in problems]


def _expect_open(path, state):
    if not state['ready'] or not state['open'] or state['expanded'] != 'true':
        return [f'{path} menu did not open: {state}']
    if state['display'] == 'none' or state['height'] < 80 or state['width'] < 300:
        return [f'{path} menu is not visible: {state}']
    if state['top'] < 0 or state['top'] > state['viewport'] - 40:
        return [f'{path} menu is outside the viewport: {state}']
    if abs(state['top'] - state['headerBottom']) > 4:
        return [f'{path} menu is not anchored to the header: {state}']
    if state['headerPosition'] == 'static':
        return [f'{path} header is not a positioning context: {state}']
    return []


if __name__ == '__main__':
    unittest.main()
