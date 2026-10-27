"""Data pages, charts and tools follow academic data-publication norms.

Ryan's rule (Oct. 19, 2026): material that supports the data (methods,
sources, data-through date, definitions, one key-fact line) may sit above or
near the table. News, game schedules, storylines and bullet lists never sit
above a data table, chart or tool; they go below.
A page opts in by putting `data-fcb-data-table` on the element that holds its
table. Pages in REQUIRED must carry that marker.

News exception (Ryan, Oct. 27, 2026): a news article (under news/) may run
headline, byline, an optional top link, one 16:9 lead photo, a one-line
opening paragraph (p.lead), then the marked table, with only a section title,
key finding and methods/data-through lines in between. Data pages and tools
keep the strict rule: nothing but supporting material above the table.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.git', '__pycache__', 'node_modules'}
REQUIRED = ['news/2026-wnba-finals-ratings-tracker/index.html', 'wnba/owners/index.html', 'wnba/where-to-watch/index.html']
MARK = re.compile(r'<[a-z]+\b[^>]*\bdata-fcb-data-table\b', re.S)
BYLINE_ROW = re.compile(r'<div class="byline-row[^"]*">.*?</div>', re.S)
BANNED = re.compile(r'<(?:ul|ol|dl|table|figure|svg|canvas|img|picture|iframe|blockquote)\b', re.I)
TAG = re.compile(r'<[^>]+>')
MAX_TEXT = 700
MAX_LEAD = 400  # one-line opening
TOP_LINK = re.compile(r'^\s*<p class="top-link">.*?</p>', re.S)
LEAD_PHOTO = re.compile(r'^\s*<figure class="lead-photo">.*?</figure>', re.S)
LEAD_P = re.compile(r'^\s*<p class="lead">(.*?)</p>', re.S)
WH = re.compile(r'<img\b[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"')


def strip_news_opening(between: str) -> str | None:
    """Drop the allowed news opening; return the rest, or an error string prefixed with '!'."""
    rest = TOP_LINK.sub('', between, count=1)
    photo = LEAD_PHOTO.match(rest)
    if not photo:
        return None
    size = WH.search(photo.group(0))
    if not size or abs(int(size.group(1)) * 9 - int(size.group(2)) * 16) > 16:
        return '!lead photo above the table is not 16:9'
    rest = rest[photo.end():]
    lead = LEAD_P.match(rest)
    if not lead:
        return '!no one-line opening (p.lead) after the lead photo'
    if len(' '.join(TAG.sub(' ', lead.group(1)).split())) > MAX_LEAD:
        return f'!opening paragraph above the table is over {MAX_LEAD} characters'
    return rest[lead.end():]  # data-through box + one key-fact line fit under this
# News answer blocks belong below the data.
NEWS_BLOCK = re.compile(r'class="[^"]*\bfcb-direct-answer\b')


def gap_between_byline_and_table(html: str, news: bool = False) -> str | None:
    """Return the markup between byline and table, or None if the page has no table marker."""
    mark = MARK.search(html)
    if not mark:
        return None
    rows = [m for m in BYLINE_ROW.finditer(html) if m.end() <= mark.start()]
    if not rows:
        return 'no byline row before the data table'
    between = html[rows[-1].end():mark.start()]
    if news:
        rest = strip_news_opening(between)
        if rest is not None:
            if rest.startswith('!'):
                return rest[1:]
            between = rest
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
            news = path.relative_to(ROOT).parts[0] == 'news' and str(path.relative_to(ROOT)) not in REQUIRED
            gap = gap_between_byline_and_table(html, news=news)
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

    def test_news_exception(self):
        photo = '<figure class="lead-photo"><img src="a.webp" width="1200" height="675"></figure>'
        ok = ('<div class="byline-row"></div><p class="top-link"><a>PBP</a></p>' + photo +
              '<p class="lead">Golden State leads 3-2.</p><h2>Data</h2><p>Data through G5. Methods.</p>'
              '<div class="table-wrap" data-fcb-data-table>')
        self.assertEqual(gap_between_byline_and_table(ok, news=True), '')
        self.assertTrue(gap_between_byline_and_table(ok, news=False))  # data pages stay strict
        two = ok.replace('<h2>', '<p>Second opening paragraph.</p><ul><li>x</li></ul><h2>')
        self.assertTrue(gap_between_byline_and_table(two, news=True))
        square = ok.replace('height="675"', 'height="1200"')
        self.assertIn('16:9', gap_between_byline_and_table(square, news=True))
        no_lead = ok.replace('<p class="lead">Golden State leads 3-2.</p>', '')
        self.assertTrue(gap_between_byline_and_table(no_lead, news=True))
        long = ok.replace('Golden State leads 3-2.', 'x ' * 300)
        self.assertTrue(gap_between_byline_and_table(long, news=True))


if __name__ == '__main__':
    unittest.main()
