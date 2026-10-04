"""The built site must share one main menu. A missing or drifted nav fails."""
import json
import re
import unittest
from pathlib import Path

import site_nav
from link_graph import iter_html, page_url

ROOT = Path(__file__).resolve().parents[1]


def _current_hrefs(nav_html: str) -> list[str]:
    import re
    return re.findall(r'<a href="([^"]+)" aria-current="page">', nav_html)


class SiteNavTests(unittest.TestCase):
    def test_menu_uses_real_pages_and_stays_small(self):
        menu = site_nav.build_menu(ROOT)
        hrefs = list(site_nav.iter_hrefs(menu))
        labels = ' '.join(site_nav.iter_labels(menu))
        self.assertGreaterEqual(len(hrefs), 29)
        self.assertLessEqual(len(hrefs), 40)
        self.assertNotIn('\u2014', labels)
        self.assertNotIn('adu', labels.casefold())
        self.assertNotIn('accessory dwelling', labels.casefold())
        for href in hrefs:
            target = site_nav.page_path(href)
            self.assertIsNotNone(site_nav.file_for_url(ROOT, target), href)
        text = site_nav.render(menu, '/__none__')
        self.assertIn('<nav class="site-nav" aria-label="Main">', text)
        self.assertIn('<ul id="site-nav-menu">', text)
        self.assertIn('<li class="site-nav-branch"><a href="/wnba/">Players</a>', text)
        self.assertIn('<li class="site-nav-branch"><a href="/wnba/teams/">Teams</a>', text)
        self.assertNotIn('href="/wnba/#teams"', text)
        self.assertIn('aria-controls="site-nav-sub-players"', text)
        self.assertIn('aria-controls="site-nav-sub-teams"', text)
        self.assertIn('aria-controls="site-nav-sub-about"', text)
        self.assertNotIn('site-nav-sub-news', text)
        self.assertNotIn('Show News menu', text)
        self.assertIn('<li><a href="/news/">News</a></li>', text)
        self.assertNotIn('/wnba/couples/', text)
        self.assertNotIn('>Couples</a>', text)
        self.assertIn('<li><a href="/standings/">Standings</a></li>', text)
        news = next(item for item in menu if item['label'] == 'News')
        self.assertEqual(news, {'label': 'News', 'href': '/news/'})
        self.assertNotIn('Couples', [item['label'] for item in menu])
        self.assertNotIn('/wnba/couples/', hrefs)
        players = next(item for item in menu if item['label'] == 'Players')
        self.assertNotIn('/wnba/couples/', [child['href'] for child in players['children']])
        players_sub = text.split('id="site-nav-sub-players"', 1)[1].split('</ul>', 1)[0]
        self.assertNotIn('/wnba/couples/', players_sub)
        self.assertTrue(any(item['label'] == 'Players' and item.get('children') for item in menu))
        self.assertTrue(any(item['label'] == 'Teams' and item.get('children') for item in menu))
        self.assertTrue(any(item['label'] == 'About' and item.get('children') for item in menu))
        self.assertIn('>Show Players menu</span>', text)
        for article in json.loads((ROOT / 'articles.json').read_text(encoding='utf-8')):
            self.assertNotIn(article['title'], text)
        self.assertIn('<ul id="site-nav-sub-teams">', text)
        self.assertIn('class="site-nav-subtoggle" aria-expanded="false"', text)
        self.assertIn('Player index, A to Z', text)
        self.assertIn('href="/standings/"', text)
        self.assertIn('href="/about/"', text)
        self.assertIn('href="/contact/"', text)
        self.assertGreaterEqual(text.count('href="/wnba/teams/'), 15)
        self.assertIn('href="/wnba/teams/portland-fire/">Portland Fire</a>', text)
        self.assertIn('href="/wnba/teams/toronto-tempo/">Toronto Tempo</a>', text)
        self.assertNotIn('href="/wnba/teams/fire/"', text)
        self.assertNotIn('href="/wnba/teams/tempo/"', text)
        self.assertNotIn('>Fire</a>', text)
        self.assertNotIn('>Tempo</a>', text)
        self.assertNotIn('<script', text)
        self.assertNotIn('createElement', site_nav.JS_TEXT)
        self.assertNotIn('innerHTML', site_nav.JS_TEXT)
        self.assertIn("menu.style.maxHeight", site_nav.JS_TEXT)
        js_path = ROOT / 'assets' / 'site-nav.js'
        self.assertEqual(js_path.read_text(encoding='utf-8'), site_nav.JS_TEXT)

    def test_every_built_page_has_the_same_nav(self):
        menu = site_nav.build_menu(ROOT)
        expected = site_nav.normalize(site_nav.render(menu, '/__none__'))
        pages = list(iter_html(ROOT))
        self.assertGreater(len(pages), 100)
        for path in pages:
            html = path.read_text(encoding='utf-8')
            if 'http-equiv="refresh"' in html.lower():
                continue
            found = site_nav.extract_main_nav(html)
            self.assertEqual(len(found), 1, path)
            self.assertEqual(site_nav.normalize(found[0]), expected, path)
            self.assertIn('/assets/site-nav.css', html, path)
            self.assertIn('/assets/site-nav.js', html, path)
            footers = site_nav.FOOTER_RE.findall(html)
            self.assertEqual(footers, [site_nav.FOOTER_HTML], path)
            current = page_url(path.relative_to(ROOT))
            marked = _current_hrefs(found[0])
            for href in site_nav.iter_hrefs(menu):
                if site_nav.is_current(href, current):
                    self.assertIn(href, marked, path)
                else:
                    self.assertNotIn(href, marked, path)

    def test_checker_rejects_a_missing_or_different_nav(self):
        menu = site_nav.build_menu(ROOT)
        expected = site_nav.normalize(site_nav.render(menu, '/__none__'))
        missing = '<html><head></head><body><p>No menu</p></body></html>'
        self.assertEqual(site_nav.extract_main_nav(missing), [])
        drifted = expected.replace('href="/standings/"', 'href="/standings/extra/"', 1)
        self.assertNotEqual(site_nav.normalize(drifted), expected)
        sample = site_nav.install('<header><nav><a href="/">Old</a></nav></header><footer class="site-footer"><p>Different</p></footer></body>', '/', menu)
        self.assertEqual(site_nav.normalize(site_nav.extract_main_nav(sample)[0]), expected)
        self.assertEqual(site_nav.FOOTER_RE.findall(sample), [site_nav.FOOTER_HTML])
        bare = '<html><body><p>No footer</p></body></html>'
        self.assertEqual(site_nav.FOOTER_RE.findall(bare), [])
        self.assertIn(site_nav.FOOTER_HTML, site_nav.install_footer(bare))

    def test_footer_uses_shared_css_and_chrome_links_stay_in_page(self):
        css_path = ROOT / 'assets' / 'site-nav.css'
        css = css_path.read_text(encoding='utf-8')
        self.assertEqual(css, site_nav.CSS_TEXT)
        self.assertIn(':where(header,.site-header){position:relative}', css)
        self.assertIn('.site-footer .footer-links{display:flex;flex-wrap:wrap', css)
        self.assertIn('column-gap:16px', css)
        self.assertIn('color:#d4d0ca', css)
        self.assertIn('display:inline-block', css)
        self.assertIn('min-height:44px', css)
        self.assertIn('.site-footer .footer-links a:hover{color:#ff9800}', css)
        menu = site_nav.render(site_nav.build_menu(ROOT), '/news/')
        self.assertNotIn('target="_blank"', menu)
        self.assertEqual(_blank_internal_anchors(site_nav.FOOTER_HTML), [])
        self.assertEqual(_blank_internal_anchors(site_nav.footer_html(False)), [])
        self.assertIn(
            'href="https://www.tiktok.com/@fullcourtbuckets" target="_blank" rel="noopener me"',
            site_nav.FOOTER_HTML,
        )
        self.assertIn('>Follow us</a>', site_nav.FOOTER_HTML)
        self.assertIn('<svg', site_nav.FOOTER_HTML)
        self.assertIn(site_nav.links.TIKTOK_FOOTER_LINK, site_nav.footer_html(False))
        pages = [path for path in iter_html(ROOT) if 'http-equiv="refresh"' not in path.read_text(encoding='utf-8').lower()]
        self.assertGreater(len(pages), 100)
        offenders = []
        for path in pages:
            html = path.read_text(encoding='utf-8')
            rel = path.relative_to(ROOT).as_posix()
            if 'class="footer-links"' in html and 'href="/assets/site-nav.css"' not in html:
                offenders.append(rel + ' missing /assets/site-nav.css')
            for match in site_nav._CHROME_REGION_RE.finditer(html):
                for tag in site_nav._ANCHOR_RE.findall(match.group(0)):
                    href = re.search(r'\bhref\s*=\s*(["\'])([^"\']*)\1', tag, re.I)
                    if href and not site_nav._is_internal_href(href.group(2)):
                        continue
                    if re.search(r'\btarget\s*=\s*(["\']?)_blank\1', tag, re.I):
                        offenders.append(f'{rel} {tag[:160]}')
        self.assertEqual(offenders, [])

    def test_on_site_links_outside_article_prose_stay_in_page(self):
        """Hubs, indexes, cards, and profiles stay in this tab. Story prose does not."""
        offenders = []
        for path in iter_html(ROOT):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding='utf-8')
            parts = rel.split('/')
            if len(parts) == 3 and parts[0] == 'news' and parts[2] == 'index.html':
                continue
            if 'http-equiv="refresh"' in text.lower():
                continue
            for block in site_nav._SCRIPT_OR_STYLE_RE.findall(text):
                if not block[:7].casefold().startswith('<script'):
                    continue
                if '_blank' in block:
                    offenders.append(rel + ' script still opens a new tab')
                    break
            visible = site_nav._SCRIPT_OR_STYLE_RE.sub('', text)
            for tag in site_nav._ANCHOR_RE.findall(visible):
                href = re.search(r'\bhref\s*=\s*(["\'])([^"\']*)\1', tag, re.I)
                if href and not site_nav._is_internal_href(href.group(2)):
                    continue
                if re.search(r'\btarget\s*=\s*(["\']?)_blank\1', tag, re.I):
                    offenders.append(f'{rel} {tag[:180]}')
        self.assertEqual(offenders, [])
        hub = (ROOT / 'news' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('class="news-item"', hub)
        # Story cards stay in this tab. The footer TikTok profile is the external exception.
        self.assertNotIn('target="_blank"', hub.split('<footer', 1)[0])
        story = (ROOT / 'news' / 'liberty-lynx-game-2-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('href="/wnba/breanna-stewart/" target="_blank" rel="noopener"', story)

    def test_footer_tiktok_link_exists_on_every_built_page(self):
        pages = list(iter_html(ROOT))
        self.assertGreater(len(pages), 100)
        missing = []
        for path in pages:
            html = path.read_text(encoding='utf-8')
            if 'http-equiv="refresh"' in html.lower():
                continue
            footers = site_nav.FOOTER_RE.findall(html)
            if footers != [site_nav.FOOTER_HTML]:
                missing.append(path.relative_to(ROOT).as_posix())
                continue
            footer = footers[0]
            if 'href="https://www.tiktok.com/@fullcourtbuckets" target="_blank" rel="noopener me"' not in footer:
                missing.append(path.relative_to(ROOT).as_posix())
            elif '>Follow us</a>' not in footer or '<svg' not in footer:
                missing.append(path.relative_to(ROOT).as_posix() + ' missing icon or label')
        self.assertEqual(missing, [])


def _blank_internal_anchors(html: str) -> list[str]:
    bad = []
    for tag in site_nav._ANCHOR_RE.findall(html):
        href = re.search(r'\bhref\s*=\s*(["\'])([^"\']*)\1', tag, re.I)
        if href and not site_nav._is_internal_href(href.group(2)):
            continue
        if re.search(r'\btarget\s*=\s*(["\']?)_blank\1', tag, re.I):
            bad.append(tag)
    return bad
