"""The author byline sits directly under the H1 on every page that has one.

News, the ratings tracker, the viewership page, and the card collection all
follow it. The author profile puts the portrait directly under the name, then
the bio. Nightly runs keep the generators from putting a hero back on top.
"""
import re
import unittest
from pathlib import Path

import build_finals_ratings_tracker as tracker
import build_reese_cards as cards
import internal_links as links

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.git', '__pycache__', 'node_modules'}
BYLINE_NEXT = re.compile(
    r'</h1>\s*(?:<div class="byline-row[^"]*">\s*)?<a class="byline"',
    re.S,
)
AUTHOR_NEXT = re.compile(
    r'</h1>\s*(?:<picture\b[^>]*>\s*(?:<source\b[^>]*>\s*)*)?'
    r'<img\b[^>]*\bclass="[^"]*\bauthor-photo\b',
    re.S,
)
HERO_MARK = re.compile(
    r'<figure\b[^>]*\blead-photo\b|<img\b[^>]*\bclass="[^"]*\b(?:hero-photo|lead-photo)\b',
    re.S,
)


def _visible(html: str) -> str:
    html = re.sub(r'<style\b[^>]*>.*?</style>', '', html, flags=re.S | re.I)
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S | re.I)
    return html


def byline_problems(html: str, label: str) -> list[str]:
    """Return reasons the byline or author bio is not directly under the H1."""
    visible = _visible(html)
    issues = []
    if 'class="byline"' in visible:
        if not BYLINE_NEXT.search(visible):
            issues.append(f'{label}: byline is not directly under the H1')
        byline = visible.find('class="byline"')
        hero = HERO_MARK.search(visible)
        if hero and hero.start() < byline:
            issues.append(f'{label}: hero image precedes the byline')
    if 'class="author-photo"' in visible and 'class="bio"' in visible:
        if not AUTHOR_NEXT.search(visible):
            issues.append(f'{label}: author portrait is not directly under the H1')
        photo = visible.find('class="author-photo"')
        bio = visible.find('class="bio"')
        if bio < photo:
            issues.append(f'{label}: bio precedes the author portrait')
        hero = HERO_MARK.search(visible)
        if hero and hero.start() < bio:
            issues.append(f'{label}: hero image precedes the bio')
    return issues


def _pages():
    for path in ROOT.rglob('*.html'):
        if SKIP_DIRS.intersection(path.parts):
            continue
        yield path


class BylineOrderTests(unittest.TestCase):
    def test_every_published_page_puts_the_byline_under_the_h1(self):
        checked = 0
        problems = []
        for path in _pages():
            html = path.read_text(encoding='utf-8')
            visible = _visible(html)
            if 'class="byline"' not in visible and 'class="author-photo"' not in visible:
                continue
            checked += 1
            problems.extend(byline_problems(html, path.relative_to(ROOT).as_posix()))
        self.assertGreaterEqual(checked, 30)
        self.assertEqual(problems, [])

    def test_generators_emit_the_byline_under_the_h1(self):
        bare = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Future Recap</title></head>
<body><article class="article"><h1>Future Recap</h1>
<aside class="fcb-quick-cite"><p>Fast facts</p></aside>
<figure><img src="/images/articles/future.webp" alt="A player" width="1200" height="800"></figure>
<p class="lead">Later.</p></article></body></html>
'''
        ordered = links.order_news_lead(links.ensure_byline(bare))
        hub = tracker.article_html({})
        collection = cards.render_page(ROOT)
        author = links.render_author_page([])
        viewership = (ROOT / 'automation' / 'viewership_render.py').read_text(encoding='utf-8')
        h1 = viewership.find('<h1>{core.esc(core.PAGE_TITLE)}</h1>')
        byline = viewership.find('{byline}', h1)
        self.assertGreater(h1, 0)
        self.assertGreater(byline, h1)
        self.assertNotIn('hero-photo', viewership[h1:byline])
        self.assertNotIn('lead-photo', viewership[h1:byline])
        samples = {
            'order_news_lead': ordered,
            'ratings tracker template': hub,
            'card collection': collection,
            'author profile': author,
        }
        problems = []
        for label, html in samples.items():
            self.assertTrue(html, label)
            problems.extend(byline_problems(html, label))
        self.assertEqual(problems, [])
        visible_collection = _visible(collection)
        visible_ordered = _visible(ordered)
        self.assertLess(visible_collection.find('</h1>'), visible_collection.find('class="hero-photo"'))
        self.assertLess(visible_ordered.find('class="byline"'), visible_ordered.find('lead-photo'))
        self.assertNotIn('class="lead-photo"', hub)
        self.assertNotIn('hero-1200.webp', hub)
        self.assertIn('tracker-matchup', hub)
        h1 = hub.find('</h1>')
        byline = hub.find('class="byline"')
        summary = hub.find('class="lead"')
        photo = hub.find('tracker-matchup')
        table = hub.find('fcb-data-table')
        cite = hub.find('fcb-quick-cite')
        callout = hub.find('fcb-tracker-update')
        self.assertLess(h1, byline)
        self.assertLess(byline, summary)
        self.assertLess(summary, photo)
        self.assertLess(photo, table)
        self.assertLess(table, cite)
        self.assertLess(cite, callout)

    def test_nightly_lead_order_does_not_put_the_tracker_hero_back(self):
        html = tracker.article_html({})
        html = html.replace(
            '</h1>',
            '</h1><figure class="lead-photo"><img src="/images/articles/2026-wnba-finals-ratings-tracker/hero-1200.webp" alt="Viewer counts pending"></figure>',
            1,
        )
        fixed = links.order_news_lead(html, {'slug': '2026-wnba-finals-ratings-tracker'})
        self.assertNotIn('class="lead-photo"', fixed)
        self.assertNotIn('hero-1200.webp', fixed)
        self.assertLess(fixed.find('class="lead"'), fixed.find('tracker-matchup'))
        self.assertLess(fixed.find('tracker-matchup'), fixed.find('fcb-data-table'))
        self.assertLess(fixed.find('fcb-data-table'), fixed.find('fcb-quick-cite'))
        self.assertLess(fixed.find('fcb-quick-cite'), fixed.find('fcb-tracker-update'))

    def test_social_card_switches_to_the_latest_released_finals_game(self):
        self.assertEqual(tracker.tracker_social_headline({}), tracker.BASELINE_SOCIAL_STAT)
        self.assertEqual(tracker.tracker_social_headline({'games': []}), tracker.BASELINE_SOCIAL_STAT)
        payload = {'games': [
            {'game': 'Finals Game 1', 'date': '2026-10-17', 'viewers': 2100000},
            {'game': 'Finals Game 2', 'date': '2026-10-19', 'viewers': None},
        ]}
        self.assertEqual(tracker.tracker_social_headline(payload), 'Game 1 averaged 2.1 million viewers')
        payload['games'][1]['viewers'] = 1800000
        self.assertEqual(tracker.tracker_social_headline(payload), 'Game 2 averaged 1.8 million viewers')
        card = tracker.draw_social_card({})
        self.assertTrue(card.is_file())
        from PIL import Image
        with Image.open(card) as image:
            self.assertEqual(image.size, (tracker.SOCIAL_WIDTH, tracker.SOCIAL_HEIGHT))
