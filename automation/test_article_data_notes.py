"""Article tables and charts get a natural lead-in above and a muted data note below.

Ryan (Oct. 27, 2026): "Data through / Methods / Source / Download (CC0)" blocks
must not sit between a heading and its table or chart, there is no "Key finding:"
label, and wide tables show a visible scroll cue on phones.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import publish_articles  # noqa: E402

TAG = re.compile(r'<[^>]+>')
NOTE_START = re.compile(r'^\s*(?:Data through|Methods(?: and sources)?:|Sources?:|Download\b)', re.I)
BEFORE_DATA = re.compile(
    r'<p\b[^>]*>((?:(?!</p>).)*)</p>(?:<!--/fcb-dynamic-->)?\s*'
    r'(?=<(?:div class="(?:fcb-)?table-wrap|figure class="chart|section class="fcb-data-table|svg)\b)', re.S)
LABEL = re.compile(r'\bKey (?:finding|fact):', re.I)


def article_pages():
    for path in sorted((ROOT / 'news').glob('*/index.html')):
        html = path.read_text(encoding='utf-8')
        if 'http-equiv="refresh"' in html:
            continue
        match = re.search(r'<article\b.*?</article>', html, re.S)
        if match:
            yield path, match.group(0)


class ArticleDataNotes(unittest.TestCase):
    def test_no_note_above_a_table_or_chart(self):
        bad = []
        for path, html in article_pages():
            for match in BEFORE_DATA.finditer(html):
                if 'class="table-note"' in match.group(0)[:80] and re.search(r'</(?:table></div|figure)>\s*$', html[:match.start()]):
                    continue  # the caption of the table or chart just above
                if NOTE_START.match(TAG.sub('', match.group(1))):
                    bad.append(f'{path.relative_to(ROOT)}: {TAG.sub("", match.group(1))[:70]}')
        self.assertEqual(bad, [], 'move data notes below the table as <p class="table-note">')

    def test_no_key_finding_label(self):
        bad = [str(p.relative_to(ROOT)) for p, html in article_pages() if LABEL.search(TAG.sub(' ', html))]
        bad += [str(p.relative_to(ROOT)) for p in (ROOT / 'content' / 'articles').glob('*/article.md')
                if LABEL.search(p.read_text(encoding='utf-8'))]
        self.assertEqual(bad, [], 'write a natural lead-in sentence instead of "Key finding:"')

    def test_builder_moves_note_below_table(self):
        md = ('Lead line.\n\n## Section\n\nIntro sentence. Here is the table:\n\n'
              'Data through Oct. 26, 2026. Methods: m. Source: WNBA.com box scores. '
              'Download (CC0): [x.csv](/x.csv)\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n'
              '**Key finding:** Words after.\n')
        html = publish_articles.body_html(md)
        self.assertLess(html.index('Intro sentence'), html.index('<table>'))
        note = re.search(r'</table></div>\s*<p class="table-note" data-fcb-dynamic="data-note"[^>]*>(.*?)</p>', html, re.S)
        self.assertIsNotNone(note, html)
        text = TAG.sub('', note.group(1))
        self.assertTrue(text.startswith('Source: WNBA.com box scores.'), text)
        self.assertIn('Data through Oct. 26, 2026.', text)
        self.assertIn('Download CSV (CC0)', text)
        self.assertNotIn('Key finding', html)

    def test_note_after_table_stays_below_it(self):
        md = '## S\n\nIntro:\n\n| A |\n| --- |\n| 1 |\n\nPara.\n\nMethods and sources: x.\n'
        html = publish_articles.body_html(md)
        self.assertRegex(html, r'</table></div>\s*<p class="table-note"')

    def test_wide_tables_have_scroll_cue(self):
        css = (ROOT / 'assets' / 'site-nav.css').read_text(encoding='utf-8')
        js = (ROOT / 'assets' / 'site-nav.js').read_text(encoding='utf-8')
        self.assertIn('.article .table-wrap', css)
        self.assertIn('overflow-x:auto', css)
        self.assertIn('.table-scroll-hint', css)
        self.assertIn('table-scroll-hint', js)
        self.assertIn('.article .table-note', css)


if __name__ == '__main__':
    unittest.main()
