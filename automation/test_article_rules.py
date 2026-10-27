"""Standing article rules from docs/EDITORIAL_STYLE.md ("Standing article rules").

Mechanical checks on every published /news/ article:

- No "guaranteed" in the copy. A record or result is not guaranteed until it happens.
- "ever" / "all-time" record claims carry a scope ("since 2002", "in our
  2002-2026 database", "franchise", "regular season") or are attributed to a
  source ("per", "according to", "says", "calls", a quote).
- No request for credit, attribution, or a link back. Say the data is free to use.
- No google.com/search links (AI-tool drafts paste these in place of real links).
- SEO meta (title, meta description, canonical), a visible breadcrumb trail with
  BreadcrumbList JSON-LD, exactly one H1, and H2 subheads on longer stories.
"""
import json
import re
import unittest
from pathlib import Path

from test_editorial_style import _article_html, _articles, _visible

ROOT = Path(__file__).resolve().parents[1]

GUARANTEED_RE = re.compile(r'\bguaranteed\b', re.I)
CREDIT_RES = (
    re.compile(r'\bplease (?:credit|cite|attribute|link)\b', re.I),
    re.compile(r'\bwith (?:link )?attribution\b', re.I),
    re.compile(r'\battribution (?:is )?required\b', re.I),
    re.compile(r'\b(?:credit|cite) (?:us|Full Court Buckets|FCB)\b', re.I),
    re.compile(r'\blink back to (?:us|this page|Full Court Buckets)\b', re.I),
)
# FCB's own data, charts and embeds are CC0 (Ryan, Oct 27). Third-party photo
# credits keep their CC BY / CC BY-SA labels, so only FCB-license wording is flagged.
CC_BY_RES = (
    re.compile(r'\b(?:use|reuse|republish|cite|data|dataset|chart|embed|CSV|license|licensed)\b[^.<>]{0,60}?\bCC[ -]?BY\b(?!-SA)', re.I),
    re.compile(r'"license":\s*"https://creativecommons\.org/licenses/by/[0-9.]+/?",\s*"(?:isAccessibleForFree|creator)"'),
    # Embed snippets live HTML-escaped in a <textarea>; raw links are photo credits.
    re.compile(r'&lt;a href=&quot;https://creativecommons\.org/licenses/by/[0-9.]+/?&quot;&gt;CC BY'),
)
GOOGLE_SEARCH_RE = re.compile(r'href="[^"]*google\.[a-z.]+/search', re.I)
RECORD_RE = re.compile(r'\b(?:ever|all-time)\b', re.I)
SCOPE_RE = re.compile(
    r'since (?:19|20)\d\d|from (?:19|20)\d\d|(?:19|20)\d\d\s*[-–]\s*(?:19|20)?\d\d'
    r'|database|franchise|regular season|in (?:a|one|this|the) (?:season|postseason|series)'
    r'|\bper\b|according to|\bsays?\b|\bsaid\b|\bcalls?\b|\bcalled\b|\breports?\b'
    r'|["“”]|\b(?:her|his|their|its|the team\'s) (?:career|franchise)'
    r'|\b(?:have|has|had) ever\b|\bfirst-ever\b|\bscorer\b',
    re.I,
)


def _sentences(text):
    return re.split(r'(?<=[.!?])\s+', text)


def _page(slug):
    return (ROOT / 'news' / slug / 'index.html').read_text(encoding='utf-8')


def _published():
    out = []
    for article in _articles():
        slug = article.get('slug')
        if slug and (ROOT / 'news' / slug / 'index.html').is_file():
            out.append(slug)
    return out


def unscoped_record_claims(text):
    return [s for s in _sentences(text) if RECORD_RE.search(s) and not SCOPE_RE.search(s)]


def credit_requests(text):
    return [m.group(0) for r in CREDIT_RES for m in [r.search(text)] if m]


def cc_by_labels(page):
    """FCB data/chart/embed labels still using CC BY instead of CC0."""
    return [m.group(0)[:120] for r in CC_BY_RES for m in r.finditer(page)]


def seo_problems(page):
    problems = []
    if not re.search(r'<title>[^<]+</title>', page, re.I):
        problems.append('missing <title>')
    if not re.search(r'<meta\s+name="description"\s+content="[^"]+', page, re.I):
        problems.append('missing meta description')
    if not re.search(r'<link\s+rel="canonical"\s+href="[^"]+', page, re.I):
        problems.append('missing canonical')
    if not re.search(r'class="[^"]*breadcrumb', page, re.I):
        problems.append('missing visible breadcrumbs')
    has_list = False
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        if '"BreadcrumbList"' in block:
            json.loads(block)
            has_list = True
    if not has_list:
        problems.append('missing BreadcrumbList JSON-LD')
    h1s = len(re.findall(r'<h1\b', page, re.I))
    if h1s != 1:
        problems.append(f'{h1s} H1 tags (need exactly 1)')
    body = _visible(_article_html(page))
    if len(body) > 2500 and not re.search(r'<h2\b', page, re.I):
        problems.append('long story with no H2 subheads')
    return problems


class StandingArticleRules(unittest.TestCase):
    def test_rule_helpers(self):
        self.assertTrue(unscoped_record_claims('It was the lowest-scoring Finals game ever.'))
        self.assertFalse(unscoped_record_claims('It was the lowest-scoring Finals game since 2002.'))
        self.assertTrue(credit_requests('Please credit Full Court Buckets.'))
        self.assertTrue(credit_requests('Free to cite with link attribution.'))
        self.assertFalse(credit_requests('The data is free to use.'))
        self.assertTrue(cc_by_labels('Free to use and republish (CC BY 4.0).'))
        self.assertTrue(cc_by_labels('&lt;a href=&quot;https://creativecommons.org/licenses/by/4.0/&quot;&gt;CC BY 4.0&lt;/a&gt;'))
        self.assertFalse(cc_by_labels('by Prime Minister&#x27;s Office, <a href="https://creativecommons.org/licenses/by/4.0">CC BY 4.0</a>; cropped by FCB.'))
        self.assertFalse(cc_by_labels('Free to use and republish (CC0).'))
        self.assertFalse(cc_by_labels('Photo: Zafer, <a href="https://creativecommons.org/licenses/by/4.0/" rel="license">CC BY 4.0</a>, via Wikimedia Commons'))

    def test_published_articles(self):
        failures = []
        for slug in _published():
            page = _page(slug)
            text = _visible(_article_html(page))
            if GUARANTEED_RE.search(text):
                failures.append(f'{slug}: uses "guaranteed"')
            for s in unscoped_record_claims(text):
                failures.append(f'{slug}: unscoped ever/all-time claim: {s[:140]}')
            for hit in credit_requests(text):
                failures.append(f'{slug}: asks for credit: {hit}')
            for hit in cc_by_labels(page):
                failures.append(f'{slug}: FCB data labeled CC BY (use CC0): {hit}')
            if GOOGLE_SEARCH_RE.search(page):
                failures.append(f'{slug}: google.com/search link')
            for p in seo_problems(page):
                failures.append(f'{slug}: {p}')
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))


if __name__ == '__main__':
    unittest.main()
