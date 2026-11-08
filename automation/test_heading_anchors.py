"""Built pages keep heading ids and never show a # permalink next to a heading."""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
ANCHOR_CLASSES = {'heading-anchor', 'fcb-anchor'}
HEADINGS = {'h2', 'h3'}


_BESIDE_HEADING = re.compile(
    r'<a\b[^>]*>\s*(?:<span\b[^>]*>\s*)?#\s*(?:</span>\s*)?</a>\s*<h[23]\b'
    r'|</h[23]>\s*<a\b[^>]*>\s*(?:<span\b[^>]*>\s*)?#\s*(?:</span>\s*)?</a>',
    re.I,
)


class _Scan(HTMLParser):
    """A heading permalink is a # link inside an h2/h3, or the heading-anchor / fcb-anchor class."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.offenders = []
        self.stack = []
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def _start(self, tag, attrs, empty):
        tag = tag.lower()
        classes = set((dict(attrs).get('class') or '').split())
        hit = classes & ANCHOR_CLASSES
        if hit:
            self.offenders.append('class ' + ' '.join(sorted(hit)))
        if tag == 'a':
            self._anchor = {'text': '', 'in_heading': any(item in HEADINGS for item in self.stack)}
        if not empty:
            self.stack.append(tag)

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor['text'] += data

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'a' and self._anchor is not None:
            text = re.sub(r'\s+', '', self._anchor['text'])
            if text == '#' and self._anchor['in_heading']:
                self.offenders.append('<a>#</a> inside a heading')
            self._anchor = None
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
            if self.stack:
                self.stack.pop()


def visible_heading_anchors(html: str) -> list[str]:
    scan = _Scan()
    try:
        scan.feed(html)
        scan.close()
    except Exception as exc:
        return [f'unparsed html ({exc})']
    if _BESIDE_HEADING.search(html):
        scan.offenders.append('<a>#</a> beside a heading')
    return scan.offenders


class HeadingAnchorTests(unittest.TestCase):
    def test_builders_keep_ids_and_omit_the_glyph(self):
        import citation
        html = citation.add_heading_anchors(
            '<article><h2>What each team could afford</h2>'
            '<h3 id="cba-rules"><a class="fcb-anchor" href="#cba-rules" aria-label="Link to this section">#</a>Rules</h3>'
            '</article><footer>',
        )
        self.assertIn('id="what-each-team-could-afford"', html)
        self.assertIn('<h3 id="cba-rules">Rules</h3>', html)
        self.assertNotIn('fcb-anchor', html)
        self.assertNotIn('>#<', html)
        self.assertEqual(visible_heading_anchors(html), [])

    def test_built_pages_have_no_visible_heading_anchors(self):
        pages = list(iter_html(ROOT))
        self.assertGreater(len(pages), 100)
        offenders = []
        for path in pages:
            found = visible_heading_anchors(path.read_text(encoding='utf-8'))
            if found:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f'{rel}: {found[0]}')
        self.assertEqual(offenders, [])
        js = (ROOT / 'assets' / 'site-nav.js').read_text(encoding='utf-8')
        css = (ROOT / 'assets' / 'site-nav.css').read_text(encoding='utf-8')
        citation = (ROOT / 'assets' / 'citation.css').read_text(encoding='utf-8')
        self.assertNotRegex(js, r"""className\s*=\s*['"]heading-anchor['"]""")
        self.assertNotRegex(js, r"""textContent\s*=\s*['"]#['"]""")
        self.assertNotIn('.heading-anchor', css)
        self.assertNotIn('.fcb-anchor', css)
        self.assertNotIn('.fcb-anchor', citation)

    def test_mitchell_section_ids_stay(self):
        page = (ROOT / 'news' / 'kelsey-mitchell-2027-free-agency-cap' / 'index.html').read_text(encoding='utf-8')
        for ident in ('cap-table', 'break-even-table', 'cba-rules', 'cap-comparison'):
            self.assertIn(f'id="{ident}"', page)
        self.assertEqual(visible_heading_anchors(page), [])


if __name__ == '__main__':
    unittest.main()
