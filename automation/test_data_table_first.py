"""Data pages, charts and tools follow academic data-publication norms.

Ryan's rule (Oct. 19, 2026): material that supports the data (methods,
sources, data-through date, definitions, one key-fact line) may sit above or
near the table. News, game schedules, storylines and bullet lists never sit
above a data table, chart or tool; they go below.
A page opts in by putting `data-fcb-data-table` on the element that holds its
table. Pages in REQUIRED must carry that marker.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.git', '__pycache__', 'node_modules'}
REQUIRED = ['news/2026-wnba-finals-ratings-tracker/index.html', 'wnba/owners/index.html']
MARK = re.compile(r'<[a-z]+\b[^>]*\bdata-fcb-data-table\b', re.S)
BYLINE_ROW = re.compile(r'<div class="byline-row[^"]*">.*?</div>', re.S)
BANNED = re.compile(r'<(?:ul|ol|dl|table|figure|svg|canvas|img|picture|iframe|blockquote)\b', re.I)
TAG = re.compile(r'<[^>]+>')
MAX_TEXT = 700  # data-through box + one key-fact line fit under this
# News answer blocks belong below the data.
NEWS_BLOCK = re.compile(r'class="[^"]*\bfcb-direct-answer\b')


def gap_between_byline_and_table(html: str) -> str | None:
    """Return the markup between byline and table, or None if the page has no table marker."""
    mark = MARK.search(html)
    if not mark:
        return None
    rows = [m for m in BYLINE_ROW.finditer(html) if m.end() <= mark.start()]
    if not rows:
        return 'no byline row before the data table'
    between = html[rows[-1].end():mark.start()]
    banned = BANNED.search(between)
    if banned:
        return f'{banned.group(0)} above the table'
    if NEWS_BLOCK.search(between):
        return 'news answer block above the table'
    text = ' '.join(TAG.sub(' ', between).split())
    if len(text) > MAX_TEXT:
        return f'{len(text)} characters of text above the table (max {MAX_TEXT})'
    return ''


def pages():
    for path in ROOT.rglob('index.html'):
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts):
            yield path


class DataTableFirst(unittest.TestCase):
    def test_required_pages_are_marked(self):
        for rel in REQUIRED:
            html = (ROOT / rel).read_text(encoding='utf-8')
            self.assertRegex(html, MARK, f'{rel} lost its data-fcb-data-table marker')

    def test_nothing_between_byline_and_table(self):
        bad = []
        for path in pages():
            html = path.read_text(encoding='utf-8', errors='ignore')
            if 'data-fcb-data-table' not in html:
                continue
            gap = gap_between_byline_and_table(html)
            if gap:
                bad.append(f'{path.relative_to(ROOT)}: {gap}')
        self.assertEqual(bad, [], 'content between byline and data table:\n' + '\n'.join(bad))

    def test_detector(self):
        ok = '<div class="byline-row"><a>x</a></div>\n<span id="a"></span><section data-fcb-data-table>'
        bad = '<div class="byline-row"><a>x</a></div><p><strong>Answer</strong></p><ul><li>a</li></ul><section data-fcb-data-table>'
        intro = '<div class="byline-row"><a>x</a></div><p>Data through: G1. Methods.</p><p>Key fact.</p><section data-fcb-data-table>'
        news = '<div class="byline-row"></div><div class="fcb-direct-answer"><p>Series 1-0</p></div><section data-fcb-data-table>'
        self.assertTrue(gap_between_byline_and_table(news))
        self.assertEqual(gap_between_byline_and_table(intro), '')
        self.assertTrue(gap_between_byline_and_table('<div class="byline-row"></div><p>' + 'x' * 800 + '</p><div data-fcb-data-table>'))
        self.assertEqual(gap_between_byline_and_table(ok), '')
        self.assertTrue(gap_between_byline_and_table(bad))


if __name__ == '__main__':
    unittest.main()
