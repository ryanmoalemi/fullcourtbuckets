"""Owner standing rule: every indexable FCB page ships full SEO meta, compact
visible breadcrumbs above the H1 with matching BreadcrumbList JSON-LD, one H1
and descriptive H2/H3 subheadings. Fails when any page (or a future builder)
misses one. Covers articles, player, team, play-by-play, data/tracker,
how-we-make, policy and hub pages."""
from __future__ import annotations

import collections
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import breadcrumbs  # noqa: E402
import social_meta  # noqa: E402

ROOT = breadcrumbs.ROOT
BASE = breadcrumbs.BASE
# Utility pages without editorial subheadings.
NO_H2_OK = {'/search/', '/contact/'}
META = {
    'title': r'<title>[^<]{10,}</title>',
    'meta description': r'<meta name="description" content="[^"]{50,}"',
    'canonical': r'<link rel="canonical" href="https://fullcourtbuckets\.com/',
    'og:title': r'property="og:title" content="[^"]+"',
    'og:description': r'property="og:description" content="[^"]+"',
    'og:url': r'property="og:url" content="https://',
    'og:image': r'property="og:image" content="https://',
    'twitter:card': r'name="twitter:card" content="summary',
    'twitter:title': r'name="twitter:title" content="[^"]+"',
}


def pages():
    for p, rel in breadcrumbs.iter_pages(ROOT):
        text = p.read_text(encoding='utf-8', errors='replace')
        if breadcrumbs.is_indexable(text):
            yield rel, text


def kind(rel: str) -> str:
    if rel.startswith('/news/') and rel != '/news/':
        return 'article'
    if re.fullmatch(r'/wnba/finals/\d+/game-\d+/play-by-play/', rel):
        return 'play-by-play'
    if rel.startswith('/wnba/teams/') and rel != '/wnba/teams/':
        return 'team'
    if re.fullmatch(r'/wnba/[a-z0-9-]+/', rel) and rel not in ('/wnba/teams/', '/wnba/viewership-attendance/', '/wnba/team-revenue/'):
        return 'player'
    return 'hub/data/static'


def check_breadcrumb_ld(trail, rel) -> list[str]:
    errs = []
    if not trail or len(trail) < 2:
        return ['BreadcrumbList needs at least 2 items']
    if trail[0][1] != BASE + '/':
        errs.append('first crumb must be Home')
    for name, item in trail:
        if not name.strip():
            errs.append('crumb with empty name')
        if not item.startswith(BASE + '/'):
            errs.append(f'crumb item not absolute FCB URL: {item!r}')
    if trail[-1][1] != BASE + rel:
        errs.append(f'last crumb {trail[-1][1]} is not this page')
    return errs


class SeoCompleteness(unittest.TestCase):
    maxDiff = None

    def test_every_page_has_meta_breadcrumbs_and_headings(self):
        problems = collections.defaultdict(list)
        seen = collections.Counter()
        for rel, text in pages():
            seen[kind(rel)] += 1
            head = text.split('</head>', 1)[0]
            for label, pat in META.items():
                if not re.search(pat, head):
                    problems[rel].append(f'missing {label}')
            blocks = breadcrumbs.jsonld_blocks(text)
            if any(b is None for b in blocks):
                problems[rel].append('invalid JSON-LD (does not parse)')
            if len(re.findall(r'<h1[\s>]', text, re.I)) != 1:
                problems[rel].append('needs exactly one <h1>')
            if rel not in NO_H2_OK and rel != '/' and not re.search(r'<h[23][\s>]', text, re.I):
                problems[rel].append('no H2/H3 subheadings')
            if rel == '/':
                continue
            ld = breadcrumbs.jsonld_trail(text)
            if ld is None:
                problems[rel].append('missing BreadcrumbList JSON-LD')
            else:
                problems[rel] += check_breadcrumb_ld(ld, rel)
            vis = breadcrumbs.VISIBLE_RE.search(text)
            h1 = re.search(r'<h1[\s>]', text, re.I)
            if not vis:
                problems[rel].append('missing visible breadcrumbs')
            elif h1 and vis.start() > h1.start():
                problems[rel].append('visible breadcrumbs must sit above the H1')
            elif h1 and re.search(r'<table\b', text[vis.end():h1.start()], re.I):
                problems[rel].append('data table between breadcrumbs and H1')
        self.assertTrue(seen['article'] and seen['player'] and seen['team'] and seen['play-by-play'], dict(seen))
        self.assertEqual({k: v for k, v in problems.items() if v}, {}, f'{len(problems)} pages fail the SEO rule')

    def test_titles_and_descriptions_are_unique(self):
        titles, descs = collections.defaultdict(list), collections.defaultdict(list)
        for rel, text in pages():
            t = re.search(r'<title>(.*?)</title>', text, re.S)
            d = re.search(r'<meta name="description" content="([^"]*)"', text)
            if t:
                titles[t.group(1).strip()].append(rel)
            if d:
                descs[d.group(1).strip()].append(rel)
        self.assertEqual({k: v for k, v in titles.items() if len(v) > 1}, {}, 'duplicate <title>')
        self.assertEqual({k: v for k, v in descs.items() if len(v) > 1}, {}, 'duplicate meta description')

    def test_pass_fixes_a_bare_future_page(self):
        """A new builder page with no crumbs/OG gets them from the shared passes."""
        page = ('<!doctype html><html><head><title>New data tool | Full Court Buckets</title>'
                '<meta name="description" content="x"><link rel="canonical" href="https://fullcourtbuckets.com/wnba/new-tool/">'
                '</head><body><main><h1>New data tool</h1><h2>Section</h2></main></body></html>')
        out = breadcrumbs.fix(page, '/wnba/new-tool/')
        out = social_meta.social_block(out, 'https://fullcourtbuckets.com/x.jpg', 'alt', 1200, 630)
        trail = breadcrumbs.jsonld_trail(out)
        self.assertEqual(trail[0], ('Home', BASE + '/'))
        self.assertEqual(trail[-1][1], BASE + '/wnba/new-tool/')
        self.assertLess(out.index('class="breadcrumbs"'), out.index('<h1>'))
        for tag in ('og:title', 'og:description', 'og:url', 'og:type', 'twitter:title'):
            self.assertIn(f'"{tag}"', out)

    def test_pbp_trail(self):
        trail = breadcrumbs.pbp_trail(2026, 5)
        self.assertEqual([n for n, _ in trail][:2], ['Home', 'WNBA'])
        self.assertTrue(trail[-1][1].endswith('/wnba/finals/2026/game-5/play-by-play/'))


if __name__ == '__main__':
    unittest.main()
